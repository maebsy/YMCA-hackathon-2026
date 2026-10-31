"""Scanner regression tests using file SQLite and a fresh, disposable local Postgres DB."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.explain_jobs.auth import SupabaseAuth
from app.explain_jobs.config import JobSettings
from app.explain_jobs.store import JobStore
from app.llm.engine_adapter import from_engine_payload
from app.llm.schemas import FindingInput
from app.scan_store import ScanStore, scan_job

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from security_engine import ScanOptions, build_llm_input, scan  # noqa: E402

URL = "https://github.com/example/demo"
OWNER, OTHER = uuid4(), uuid4()


def response_for(result):
    payload = build_llm_input(result, max_items=50)
    return {
        "scan_id": result["scan_id"],
        "result": result,
        "llm_input": payload,
        "findings": [item.model_dump(mode="json") for item in from_engine_payload(payload)],
    }


@pytest.fixture
def engine_response(tmp_path):
    """Run the real built-in scanner, without installing tools or reading real credentials."""
    counter = 0

    def make(db_files=0, env=True):
        nonlocal counter
        counter += 1
        site = tmp_path / f"site-{counter}"
        site.mkdir()
        if env:
            (site / ".env").write_text("SYNTHETIC_TEST_VALUE=placeholder\n", encoding="utf-8")
            (site / ".gitignore").write_text(".env*\n", encoding="utf-8")
        for index in range(db_files):
            (site / f"fixture-{index}.db").write_bytes(b"")
        result = scan(site, options=ScanOptions(tools=("config",)), repo_url=URL)
        return response_for(result)

    return make


def start(store, owner=None):
    job_id = uuid4().hex
    store.create(job_id, URL, owner)
    assert store.running(job_id)
    return job_id


def test_sqlite_response_survives_new_engine_and_store(tmp_path, engine_response):
    address = f"sqlite:///{tmp_path / 'scan.sqlite'}"
    engine = create_engine(address)
    store = ScanStore(engine)
    job_id = start(store)
    response = engine_response()
    store.complete(job_id, response)
    engine.dispose()

    reopened = create_engine(address)
    try:
        job = ScanStore(reopened).get(job_id)
        assert job["status"] == "done"
        assert job["result"] == response
        assert job["error"] is None
    finally:
        reopened.dispose()


def test_sqlite_owner_and_terminal_state_boundaries(tmp_path, engine_response):
    engine = create_engine(f"sqlite:///{tmp_path / 'owners.sqlite'}")
    try:
        store = ScanStore(engine)
        job_id = start(store, OWNER)
        assert store.get(job_id) is None
        assert store.get(job_id, OTHER) is None
        response = engine_response()
        store.complete(job_id, response)
        store.complete(job_id, {"result": {}})
        store.fail(job_id, {"code": "LATE_FAILURE"})
        assert not store.running(job_id)
        assert store.get(job_id, OWNER)["result"] == response
        assert store.get(job_id, OWNER)["status"] == "done"
    finally:
        engine.dispose()


def oversized_response(engine_response):
    response = engine_response()
    item = response["result"]["findings"][0]
    item["title"] = "Long engine finding " * 40
    item["location"]["file"] = "deep/" * 120 + "fixture.env"
    item["remediation"]["autofix"] = "safe_replacement()\n" * 150
    # The engine contract permits these values even though the LLM input is bounded.
    return response


def test_sqlite_preserves_valid_engine_values_beyond_llm_limits(tmp_path, engine_response):
    engine = create_engine(f"sqlite:///{tmp_path / 'large.sqlite'}")
    try:
        store = ScanStore(engine)
        job_id = start(store)
        response = oversized_response(engine_response)
        store.complete(job_id, response)
        assert store.get(job_id)["result"]["result"] == response["result"]
    finally:
        engine.dispose()


def test_restarted_sqlite_store_marks_expired_job_interrupted_and_preserves_other_worker(tmp_path, engine_response):
    address = f"sqlite:///{tmp_path / 'restart.sqlite'}"
    engine = create_engine(address)
    store = ScanStore(engine)
    expired, live = start(store), start(store)
    with engine.begin() as conn:
        conn.execute(update(scan_job).where(scan_job.c.id == expired).values(
            lease_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
    engine.dispose()
    reopened = create_engine(address)
    try:
        recovered = ScanStore(reopened)
        job = recovered.get(expired)
        assert job["status"] == "failed" and job["error"]["code"] == "SCAN_INTERRUPTED"
        assert recovered.get(live)["status"] == "running"
        recovered.complete(expired, engine_response())
        recovered.fail(expired, {"code": "LATE_FAILURE"})
        assert recovered.get(expired) == job
        assert not recovered.running(expired)
    finally:
        reopened.dispose()


@pytest.fixture(scope="module")
def pg_engine():
    address = os.environ.get("ASYNC_JOB_TEST_DATABASE_URL")
    if not address:
        pytest.skip("Set ASYNC_JOB_TEST_DATABASE_URL to disposable loopback Postgres")
    url = make_url(address)
    assert url.host in ("localhost", "127.0.0.1") and url.database == "postgres"
    assert url.drivername == "postgresql+psycopg"
    db_name = "ymca_scan_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
    engine = create_engine(url.set(database=db_name), connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE SCHEMA auth")
            conn.exec_driver_sql("CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb)")
        raw = engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute((ROOT / "docs/db-schema.sql").read_text(encoding="utf-8"))
                for name in ("026-async-llm.sql", "052-scan-persistence.sql"):
                    migration = (ROOT / "docs/migrations" / name).read_text(encoding="utf-8")
                    cursor.execute(migration)
                    cursor.execute(migration)
            raw.commit()
        finally:
            raw.close()
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{db_name}"')
        admin.dispose()


@pytest.fixture
def store(pg_engine):
    with pg_engine.begin() as conn:
        conn.exec_driver_sql("TRUNCATE auth.users, profile, project, scan, tool_run, finding, explanation, llm_job, scan_job RESTART IDENTITY CASCADE")
        for owner in (OWNER, OTHER):
            conn.execute(text("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES (:id,'test@example.invalid','{}')"), {"id": owner})
    return ScanStore(pg_engine)


def test_all_real_findings_are_persisted_beyond_preview_and_ready_for_worker(store, engine_response):
    response = engine_response(db_files=54)
    raw_findings = response["result"]["findings"]
    assert len(raw_findings) > 50
    assert len(response["findings"]) == 50
    assert all("raw" not in finding for finding in raw_findings)
    job_id = start(store, OWNER)
    store.complete(job_id, response)
    saved = store.get(job_id, OWNER)
    db_scan_id = saved["result"]["db_scan_id"]
    assert isinstance(db_scan_id, int)
    assert saved["result"]["scan_id"] == response["scan_id"]
    assert saved["result"]["result"]["scan_id"] == response["scan_id"]
    assert store.get(job_id, OTHER) is None
    assert store.get(job_id) is None
    project, scan_table, tool_run, finding = (store.tables[name] for name in ("project", "scan", "tool_run", "finding"))
    with store.engine.connect() as conn:
        project_row = conn.execute(select(project)).mappings().one()
        assert project_row["owner_id"] == OWNER
        assert project_row["claim_token_hash"] is None
        scan_row = conn.execute(select(scan_table)).mappings().one()
        assert scan_row["id"] == db_scan_id
        assert scan_row["status"] == "explaining"
        assert scan_row["finished_at"] is None
        assert scan_row["summary"] == response["result"]["summary"]
        assert conn.scalar(select(scan_job.c.scan_id)) == db_scan_id
        rows = conn.execute(select(finding)).mappings().all()
        assert len(rows) == len(raw_findings)
        assert {row["fingerprint"] for row in rows} == {item["fingerprint"] for item in raw_findings}
        env = next(row for row in rows if row["rule_id"] == "config/env-file-committed")
        assert env["file_path"] == ".env" and env["start_line"] is None
        assert env["refs"]["cwe"] == ["CWE-538"]
        assert env["llm_context"]["flags"][0]["flag"] == "rotate_secret"
        assert env["llm_context"]["status"] == "code_issue"
        assert env["llm_context"]["fix_hint"]["kind"] == "config_change"
        assert env["raw"] == next(item for item in raw_findings if item["fingerprint"] == env["fingerprint"])
        assert "placeholder" not in str(env["raw"])
        coverage = {row["tool"]: row for row in conn.execute(select(tool_run)).mappings()}
        assert set(coverage) == set(response["result"]["coverage"])
        assert coverage["config"]["status"] == "done"
        assert coverage["config"]["finding_count"] == len(raw_findings)
        assert coverage["config"]["coverage"] == response["result"]["coverage"]["config"]
        assert coverage["osv"]["status"] == "skipped"

    jobs = JobStore(store.engine)
    assert len(jobs.enqueue_ready()) == 50
    assert len(jobs.enqueue_ready()) == len(raw_findings) - 50
    claim = jobs.claim(180)
    assert claim is not None and not claim["invalid_context"]
    assert FindingInput.model_validate(claim["input"]).fingerprint in {item["fingerprint"] for item in raw_findings}


def test_dependency_rows_keep_individual_identity_and_flatten_package_fields(store, engine_response):
    response = engine_response()
    base = response["result"]["findings"][0]
    dependencies = []
    for index in (1, 2):
        item = deepcopy(base)
        item.update(fingerprint=f"osv:fixture-{index}", tool="osv", category="dependency", rule_id=f"CVE-2026-1000{index}",
                    title=f"Fixture dependency {index}", flags=[], location={"file": "package-lock.json", "start_line": None, "end_line": None},
                    package={"name": "example-package", "ecosystem": "npm", "version": "1.0.0"},
                    remediation={"kind": "upgrade_dependency", "target_version": "1.0.2"},
                    aliases=["CVE-2026-20001", "GHSA-fixture"],
                    references=[f"https://example.invalid/advisory/{number}" for number in range(6)])
        dependencies.append(item)
    response["result"]["findings"] = dependencies
    response = response_for(response["result"])
    assert len(response["findings"]) == 1  # The preview groups; storage must retain both engine identities.
    job_id = start(store, OWNER)
    store.complete(job_id, response)
    with store.engine.connect() as conn:
        rows = conn.execute(select(store.tables["finding"])).mappings().all()
    assert len(rows) == 2
    assert {row["fingerprint"] for row in rows} == {item["fingerprint"] for item in dependencies}
    for row in rows:
        assert row["package_name"] == "example-package"
        assert row["package_ecosystem"] == "npm"
        assert row["installed_version"] == "1.0.0" and row["fixed_version"] == "1.0.2"
        assert row["refs"]["cve"] == [row["rule_id"], "CVE-2026-20001"]
        assert len(row["refs"]["urls"]) == 6
        assert row["llm_context"]["fix_hint"]["command"] == "npm install example-package@1.0.2"


def test_postgres_preserves_valid_engine_values_beyond_llm_limits(store, engine_response):
    response = oversized_response(engine_response)
    job_id = start(store, OWNER)
    store.complete(job_id, response)
    assert store.get(job_id, OWNER)["result"]["result"] == response["result"]
    with store.engine.connect() as conn:
        row = conn.execute(select(store.tables["finding"])).mappings().one()
        assert row["raw"] == response["result"]["findings"][0]
        assert row["title"] == row["raw"]["title"]
        assert row["file_path"] == row["raw"]["location"]["file"]


@pytest.mark.parametrize("owned,empty,failed,expected", [
    (False, False, False, "done"),
    (True, True, False, "done"),
    (True, True, True, "failed"),
])
def test_final_scan_status_without_worker_work(store, engine_response, owned, empty, failed, expected):
    response = engine_response(env=not empty)
    if failed:
        response["result"]["status"] = "failed"
        response["result"]["coverage"]["config"]["status"] = "error"
    job_id = start(store, OWNER if owned else None)
    store.complete(job_id, response)
    saved = store.get(job_id, OWNER if owned else None)
    assert saved["status"] == expected
    with store.engine.connect() as conn:
        scan_row = conn.execute(select(store.tables["scan"])).mappings().one()
        assert scan_row["status"] == expected
        assert scan_row["finished_at"] is not None
        if not owned:
            assert conn.scalar(select(store.tables["project"].c.claim_token_hash)) == sha256(job_id.encode()).hexdigest()
    assert JobStore(store.engine).enqueue_ready() == []
    if failed:
        assert saved["error"]["code"] == "ENGINE_FAILED"


def test_duplicate_completion_does_not_duplicate_or_replace_results(store, engine_response):
    job_id = start(store, OWNER)
    response = engine_response()
    store.complete(job_id, response)
    original = store.get(job_id, OWNER)
    store.complete(job_id, engine_response(db_files=2))
    store.fail(job_id, {"code": "LATE_ERROR"})
    assert store.get(job_id, OWNER) == original
    with store.engine.connect() as conn:
        for name in ("project", "scan"):
            assert conn.scalar(select(func.count()).select_from(store.tables[name])) == 1
        assert conn.scalar(select(func.count()).select_from(store.tables["finding"])) == len(response["result"]["findings"])


@pytest.mark.parametrize("invalid", ["llm_input", "wrong_target", "duplicate"])
def test_invalid_engine_result_keeps_job_running_without_relational_writes(store, engine_response, invalid):
    response = engine_response()
    if invalid == "llm_input":
        response["result"] = response["llm_input"]
    elif invalid == "wrong_target":
        response["result"]["target"]["repo_url"] = "https://github.com/example/other"
    else:
        response["result"]["findings"].append(deepcopy(response["result"]["findings"][0]))
    job_id = start(store, OWNER)
    with pytest.raises(ValueError):
        store.complete(job_id, response)
    assert store.get(job_id, OWNER)["status"] == "running"
    assert store.get(job_id, OWNER)["result"] is None
    with store.engine.connect() as conn:
        for name in ("project", "scan", "tool_run", "finding"):
            assert conn.scalar(select(func.count()).select_from(store.tables[name])) == 0


def test_database_constraint_failure_rolls_back_relations_and_completion(store, engine_response):
    response = engine_response()
    response["result"]["coverage"]["unsupported"] = deepcopy(response["result"]["coverage"]["config"])
    job_id = start(store, OWNER)
    with pytest.raises(IntegrityError):
        store.complete(job_id, response)
    job = store.get(job_id, OWNER)
    assert job["status"] == "running" and job["result"] is None
    with store.engine.connect() as conn:
        for name in ("project", "scan", "tool_run", "finding"):
            assert conn.scalar(select(func.count()).select_from(store.tables[name])) == 0
        assert conn.scalar(select(scan_job.c.scan_id)) is None
    del response["result"]["coverage"]["unsupported"]
    store.complete(job_id, response)
    assert store.get(job_id, OWNER)["status"] == "done"


@pytest.mark.parametrize("running", [False, True])
def test_expired_postgres_job_cannot_complete_or_affect_live_worker(store, engine_response, running):
    expired = uuid4().hex
    store.create(expired, URL, OWNER)
    if running:
        assert store.running(expired)
    live = start(store, OTHER)
    with store.engine.begin() as conn:
        conn.execute(update(scan_job).where(scan_job.c.id == expired).values(
            lease_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
    # A delayed writer is fenced even before a client has polled the expired job.
    with pytest.raises(ValueError, match="lease expired"):
        store.complete(expired, engine_response())
    job = store.get(expired, OWNER)
    assert job["status"] == "failed" and job["error"]["code"] == "SCAN_INTERRUPTED"
    assert job["result"] is None
    assert store.get(live, OTHER)["status"] == "running"
    with store.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(store.tables["project"])) == 0
        assert conn.scalar(select(func.count()).select_from(store.tables["scan"])) == 0


def test_heartbeat_renews_only_live_job_and_does_not_revive_expired_job(store):
    live, expired = start(store, OWNER), start(store, OTHER)
    short_lease = datetime.now(timezone.utc) + timedelta(seconds=5)
    with store.engine.begin() as conn:
        conn.execute(update(scan_job).where(scan_job.c.id == live).values(lease_until=short_lease))
        conn.execute(update(scan_job).where(scan_job.c.id == expired).values(
            lease_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
    assert store.heartbeat(live)
    assert not store.heartbeat(expired)
    with store.engine.connect() as conn:
        assert conn.scalar(select(scan_job.c.lease_until).where(scan_job.c.id == live)) > short_lease
    assert store.get(live, OWNER)["status"] == "running"
    assert store.get(expired, OTHER)["error"]["code"] == "SCAN_INTERRUPTED"


@pytest.mark.parametrize("waiting_for_slot", [False, True])
def test_cancelled_worker_persists_interrupted_status(tmp_path, monkeypatch, waiting_for_slot):
    from app.routers import scans

    engine = create_engine(f"sqlite:///{tmp_path / 'cancelled.sqlite'}")
    store = ScanStore(engine)
    job_id = uuid4().hex
    store.create(job_id, URL)

    async def scenario():
        started = asyncio.Event()

        async def slow_scan(body):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(scans, "_slots", asyncio.Semaphore(0 if waiting_for_slot else 1))
        monkeypatch.setattr(scans, "_run_scan", slow_scan)
        worker = asyncio.create_task(scans._worker(job_id, scans.ScanRequest(repo_url=URL), store))
        if waiting_for_slot:
            await asyncio.sleep(0)
        else:
            await asyncio.wait_for(started.wait(), timeout=5)
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    try:
        asyncio.run(scenario())
        job = store.get(job_id)
        assert job["status"] == "failed"
        assert job["error"]["code"] == "SCAN_INTERRUPTED"
        assert job["result"] is None
    finally:
        engine.dispose()


def test_api_saves_oversized_valid_engine_json_and_reads_it_after_restart(tmp_path, engine_response, monkeypatch):
    import security_engine
    from app.routers import scans

    response = oversized_response(engine_response)
    monkeypatch.setattr(security_engine, "scan_repo", lambda *args, **kwargs: response["result"])
    monkeypatch.setattr(scans.job_settings, "llm_jobs_enabled", False)
    monkeypatch.setattr(scans, "_slots", asyncio.Semaphore(2))
    address = f"sqlite:///{tmp_path / 'api-restart.sqlite'}"
    engine = create_engine(address)
    app = FastAPI()
    app.state.scan_store = ScanStore(engine)
    app.include_router(scans.router, prefix="/api")
    with TestClient(app) as client:
        submitted = client.post("/api/scans", json={"repo_url": URL})
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]
        for _ in range(100):
            job = client.get(f"/api/scans/{job_id}").json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.02)
        assert job["status"] == "done", job
        assert job["result"]["result"] == response["result"]
        assert job["result"]["preview_errors"] == [{
            "fingerprint": response["result"]["findings"][0]["fingerprint"], "code": "LLM_INPUT_INVALID",
        }]
    engine.dispose()
    reopened = create_engine(address)
    try:
        restarted = FastAPI()
        restarted.state.scan_store = ScanStore(reopened)
        restarted.include_router(scans.router, prefix="/api")
        with TestClient(restarted) as client:
            assert client.get(f"/api/scans/{job_id}").json() == job
    finally:
        reopened.dispose()


def test_grouped_dependency_preview_overflow_preserves_individual_findings(tmp_path, engine_response, monkeypatch):
    import security_engine
    from app.routers import scans

    result = engine_response()["result"]
    base = result["findings"][0]
    dependencies = []
    for index in range(5):
        item = deepcopy(base)
        item.update(
            fingerprint=f"osv:long-title-{index}", tool="osv", category="dependency",
            rule_id=f"CVE-2026-3000{index}", title="x" * 480, flags=[],
            location={"file": "package-lock.json", "start_line": None, "end_line": None},
            package={"name": "example-package", "ecosystem": "npm", "version": "1.0.0"},
            remediation={"kind": "upgrade_dependency", "target_version": "1.0.2"},
        )
        dependencies.append(item)
    result["findings"] = dependencies
    payload = build_llm_input(result, max_items=50)
    assert len(from_engine_payload(payload, group_dependencies=False)) == 5
    with pytest.raises(ValidationError):
        from_engine_payload(payload)  # Individually valid titles overflow the group's what field.
    monkeypatch.setattr(security_engine, "scan_repo", lambda *args, **kwargs: result)
    response = asyncio.run(scans._run_scan(scans.ScanRequest(repo_url=URL)))
    assert response["preview_errors"] == []
    assert response["result"] == result
    assert {item["fingerprint"] for item in response["findings"]} == {item["fingerprint"] for item in dependencies}
    for item in response["findings"]:
        FindingInput.model_validate(item)
    engine = create_engine(f"sqlite:///{tmp_path / 'group-overflow.sqlite'}")
    try:
        store = ScanStore(engine)
        job_id = start(store)
        store.complete(job_id, response)
        assert store.get(job_id)["status"] == "done"
        assert store.get(job_id)["result"]["result"]["findings"] == dependencies
    finally:
        engine.dispose()


def test_scan_api_requires_verified_owner_for_persisted_response(tmp_path, engine_response, monkeypatch):
    from app.routers import scans

    engine = create_engine(f"sqlite:///{tmp_path / 'api.sqlite'}")
    store = ScanStore(engine)
    job_id = start(store, OWNER)
    store.complete(job_id, engine_response())
    app = FastAPI()
    app.state.scan_store = store
    config = JobSettings(_env_file=None, supabase_url="https://auth.example.invalid", supabase_publishable_key="test-public")

    def authenticate(request):
        users = {"Bearer owner": OWNER, "Bearer other": OTHER}
        owner = users.get(request.headers["Authorization"])
        return httpx.Response(200, json={"id": str(owner), "is_anonymous": False}) if owner else httpx.Response(401)

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(authenticate))
    app.state.job_auth = SupabaseAuth(config, auth_client)
    app.include_router(scans.router, prefix="/api")
    monkeypatch.setattr(scans.job_settings, "llm_jobs_enabled", True)
    try:
        with TestClient(app) as client:
            assert client.get(f"/api/scans/{job_id}").status_code == 401
            assert client.get(f"/api/scans/{job_id}", headers={"Authorization": "Bearer forged"}).status_code == 401
            assert client.get(f"/api/scans/{job_id}", headers={"Authorization": "Bearer other"}).status_code == 404
            response = client.get(f"/api/scans/{job_id}", headers={"Authorization": "Bearer owner"})
            assert response.status_code == 200 and response.json()["status"] == "done"
            assert response.headers["Cache-Control"] == "no-store"
            assert client.post("/api/scans", json={"repo_url": URL}).status_code == 401
        with engine.connect() as conn:
            assert conn.scalar(select(func.count()).select_from(scan_job)) == 1
    finally:
        asyncio.run(auth_client.aclose())
        engine.dispose()
