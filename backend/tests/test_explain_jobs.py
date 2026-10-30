"""PostgreSQL integration tests: only a fresh random DB on explicitly supplied loopback Postgres."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url

from app.explain_jobs.api import router
from app.explain_jobs.auth import SupabaseAuth
from app.explain_jobs.config import JobSettings
from app.explain_jobs.store import JobStore, NotFound
from app.explain_jobs.worker import run_once
from app.llm.schemas import ExplainResult, Explanation
from tests.conftest import blue_draft
from tests.test_job_auth import OWNER

OTHER = uuid4()
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pg_engine():
    address = os.environ.get("ASYNC_JOB_TEST_DATABASE_URL")
    if not address:
        pytest.skip("Set ASYNC_JOB_TEST_DATABASE_URL to disposable loopback Postgres")
    url = make_url(address)
    assert url.host in ("localhost", "127.0.0.1") and url.database == "postgres"
    assert url.drivername == "postgresql+psycopg"
    db_name = "ymca_jobs_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
    engine = create_engine(url.set(database=db_name), pool_size=6, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE SCHEMA auth")
            conn.exec_driver_sql("CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb)")
        # Exact #7 fixture, then #26 twice to verify re-application.
        raw = engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute((ROOT / "backend/tests/fixtures/db_schema_7.sql").read_text(encoding="utf-8"))
                migration = (ROOT / "docs/migrations/026-async-llm.sql").read_text(encoding="utf-8")
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
        conn.exec_driver_sql("TRUNCATE auth.users, profile, project, scan, tool_run, finding, explanation, llm_job RESTART IDENTITY CASCADE")
        conn.execute(text("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES (:id,'demo@example.invalid','{}')"), {"id": OWNER})
        conn.execute(text("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES (:id,'other@example.invalid','{}')"), {"id": OTHER})
        conn.execute(text("INSERT INTO project(owner_id,name,repo_url) VALUES (:id,'demo','https://github.com/example/demo')"), {"id": OWNER})
        conn.execute(text("INSERT INTO project(owner_id,name,repo_url) VALUES (:id,'other','https://github.com/example/other')"), {"id": OTHER})
        conn.exec_driver_sql("INSERT INTO scan(project_id,status) VALUES (1,'explaining'),(2,'explaining')")
        for scan_id in (1, 2):
            conn.execute(text("""INSERT INTO finding(scan_id,fingerprint,tool,category,rule_id,title,severity,raw)
                VALUES (:scan_id,'finding-1','semgrep','code','rule','Example finding','high','{}')"""), {"scan_id": scan_id})
    return JobStore(pg_engine)


@pytest.fixture
def api(store):
    app = FastAPI()
    config = JobSettings(_env_file=None, supabase_url="https://auth.example.invalid", supabase_publishable_key="test-public")
    def handler(request):
        token = request.headers["Authorization"]
        users = {"Bearer owner-token": OWNER, "Bearer other-token": OTHER}
        if token not in users:
            return httpx.Response(401)
        return httpx.Response(200, json={"id": str(users[token]), "is_anonymous": False})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.state.job_auth = SupabaseAuth(config, client)
    app.state.job_store = store
    app.include_router(router, prefix="/api")
    with TestClient(app) as browser:
        yield browser
    asyncio.run(client.aclose())


def headers(owner=True):
    return {"Authorization": "Bearer owner-token" if owner else "Bearer other-token"}


def result(fingerprint="finding-1", status="done"):
    if status != "done":
        return ExplainResult(fingerprint=fingerprint, status=status, reason="Already resolved" if status == "skipped" else None,
                             error_code="LLM_UNAVAILABLE" if status == "failed" else None,
                             error="private failure detail" if status == "failed" else None)
    explanation = Explanation(**blue_draft(), fingerprint=fingerprint, variant="D", model="fake",
                              prompt_version="test", latency_ms=1, completion_tokens=1,
                              red_verdict="pass", red_rounds=[{"round": 1, "verdict": "pass", "issues": [], "latency_ms": 1}])
    return ExplainResult(fingerprint=fingerprint, status="done", explanation=explanation)


def test_unauthenticated_forged_and_cross_tenant_requests(api, store):
    for method in ("get", "post"):
        kwargs = {"json": {}} if method == "post" else {}
        call = getattr(api, method)
        assert call("/api/scans/1/explanations", **kwargs).status_code == 401
        assert call("/api/scans/1/explanations", headers={"Authorization": "Bearer forged"}, **kwargs).status_code == 401
        assert call("/api/scans/2/explanations", headers=headers(), **kwargs).status_code == 404
        assert call("/api/scans/999/explanations", headers=headers(), **kwargs).status_code == 404
    with store.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(store.job)) == 0


def test_enqueue_returns_202_without_llm_and_is_idempotent(api, store):
    response = api.post("/api/scans/1/explanations", headers=headers(), json={})
    assert response.status_code == 202
    assert len(response.json()["queued_job_ids"]) == 1
    assert response.headers["Location"] == "/api/scans/1/explanations"
    assert api.post("/api/scans/1/explanations", headers=headers(), json={}).json()["queued_job_ids"] == []
    assert api.post("/api/scans/1/explanations", headers=headers(), json={"findings": []}).status_code == 422
    assert api.get("/api/scans/1/explanations", headers=headers()).json()["items"][0]["explain_status"] == "pending"


def test_worker_persists_result_and_polling_sees_it(api, store):
    class Explainer:
        async def explain_many(self, findings, mode):
            assert mode == "red_blue"
            assert len(findings) == 1 and findings[0].fingerprint == "finding-1"
            return [result()]
    assert asyncio.run(run_once(store, Explainer()))  # automatic enqueue after committed scanner status
    response = api.get("/api/scans/1/explanations", headers=headers())
    item = response.json()["items"][0]
    assert item["explain_status"] == "done" and item["result"]["explanation"]["red_verdict"] == "pass"
    assert response.headers["Cache-Control"] == "no-store"
    with store.engine.connect() as conn:
        assert conn.scalar(select(store.explanation.c.variant)) == "D"
        assert conn.scalar(select(store.scan.c.status).where(store.scan.c.id == 1)) == "done"


@pytest.mark.parametrize("status", ["failed", "skipped"])
def test_partial_outcomes_are_persisted_without_provider_error(store, status):
    store.enqueue(1, OWNER)
    claim = store.claim(180)
    assert store.complete(claim, result(status=status))
    item = store.list_results(1, OWNER, 0, 50)["items"][0]
    assert item["explain_status"] == status
    assert "private failure" not in str(item)
    with store.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(store.explanation)) == 0


def test_two_workers_cannot_claim_the_same_live_job(store):
    store.enqueue(1, OWNER)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.claim(180), range(2)))
    assert sum(claim is not None for claim in claims) == 1


def test_duplicate_submissions_are_atomic(store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.enqueue(1, OWNER), range(2)))
    assert sum(map(len, results)) == 1


def expire(store, claim):
    with store.engine.begin() as conn:
        conn.execute(update(store.job).where(store.job.c.id == claim["id"]).values(
            lease_until=func.now() - timedelta(seconds=1),
        ))


def test_restart_recovers_lease_and_rejects_stale_writer(store):
    store.enqueue(1, OWNER)
    old = store.claim(180)
    expire(store, old)
    new_store = JobStore(store.engine)  # no in-process queue state required
    new = new_store.claim(180)
    assert old["id"] == new["id"] and old["token"] != new["token"]
    assert not store.complete(old, result())
    assert not store.heartbeat(old["id"], old["token"], 180)
    assert new_store.complete(new, result())
    assert not store.complete(old, result(status="failed"))


def test_crash_retry_limit_is_terminal(store):
    store.enqueue(1, OWNER)
    for _ in range(3):
        claim = store.claim(180)
        assert claim
        expire(store, claim)
    assert store.claim(180) is None
    item = store.list_results(1, OWNER, 0, 50)["items"][0]
    assert item["explain_status"] == "failed" and item["error_code"] == "WORKER_LOST"


def test_heartbeat_extends_lease(store):
    store.enqueue(1, OWNER)
    claim = store.claim(30)
    assert store.heartbeat(claim["id"], claim["token"], 180)
    with store.engine.connect() as conn:
        until = conn.scalar(select(store.job.c.lease_until))
        now = conn.scalar(select(func.now()))
    assert (until - now).total_seconds() > 150


def test_wrong_result_identity_never_writes(store):
    store.enqueue(1, OWNER)
    claim = store.claim(180)
    with pytest.raises(ValueError):
        store.complete(claim, result(fingerprint="different"))
    assert store.list_results(1, OWNER, 0, 50)["items"][0]["explain_status"] == "pending"


def test_atomic_completion_rolls_back_on_explanation_failure(store):
    store.enqueue(1, OWNER)
    claim = store.claim(180)
    broken = result()
    broken.explanation.priority = "invalid-db-priority"
    with pytest.raises(Exception):
        store.complete(claim, broken)
    assert store.list_results(1, OWNER, 0, 50)["items"][0]["job_status"] == "running"
    assert store.complete(claim, result())


def test_worker_timeout_and_exception_are_terminal(store):
    class Slow:
        async def explain_many(self, findings, mode):
            await asyncio.sleep(10)
    config = SimpleNamespace(llm_job_timeout_s=0.01, llm_job_lease_s=30)
    asyncio.run(run_once(store, Slow(), config))
    assert store.list_results(1, OWNER, 0, 50)["items"][0]["error_code"] == "LLM_JOB_TIMEOUT"


def test_worker_cancellation_leaves_durable_recoverable_job(store):
    async def scenario():
        started = asyncio.Event()
        class Slow:
            async def explain_many(self, findings, mode):
                started.set()
                await asyncio.sleep(10)
        task = asyncio.create_task(run_once(store, Slow()))
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    item = store.list_results(1, OWNER, 0, 50)["items"][0]
    assert item["job_status"] == "running" and item["explain_status"] == "pending"


def test_unowned_scans_are_not_automatically_enqueued(store):
    with store.engine.begin() as conn:
        conn.execute(update(store.project).where(store.project.c.id == 1).values(owner_id=None, claim_token_hash="test-claim-hash"))
    with pytest.raises(NotFound):
        store.enqueue(1, OWNER)
    store.enqueue_ready()
    with store.engine.connect() as conn:
        assert conn.scalar(select(store.job.c.finding_id)) == 2


def test_incomplete_scan_is_rejected_and_results_are_paginated(api, store):
    with store.engine.begin() as conn:
        conn.execute(update(store.scan).where(store.scan.c.id == 1).values(status="scanning"))
    assert api.post("/api/scans/1/explanations", headers=headers(), json={}).status_code == 409
    assert api.get("/api/scans/1/explanations?limit=51", headers=headers()).status_code == 422


def test_startup_refuses_sqlite_in_jobs_mode():
    with pytest.raises(RuntimeError):
        JobStore(create_engine("sqlite://"))


def test_bad_scanner_context_fails_without_poisoning_queue(store):
    with store.engine.begin() as conn:
        conn.execute(update(store.finding).where(store.finding.c.id == 1).values(llm_context=[]))
    class NeverCalled:
        async def explain_many(self, *args):
            pytest.fail("Malformed DB input must not reach the GPU")
    asyncio.run(run_once(store, NeverCalled()))
    assert store.list_results(1, OWNER, 0, 50)["items"][0]["error_code"] == "LLM_JOB_FAILED"


def test_scanner_skip_context_is_preserved_without_overwriting_identity(store):
    with store.engine.begin() as conn:
        conn.execute(update(store.finding).where(store.finding.c.id == 1).values(llm_context={
            "status": "out_of_scope", "change": "unverifiable", "fingerprint": "must-not-overwrite",
        }))
    class Skip:
        async def explain_many(self, findings, mode):
            assert findings[0].status == "out_of_scope"
            assert findings[0].fingerprint == "finding-1"
            return [result(status="skipped")]
    asyncio.run(run_once(store, Skip()))
    assert store.list_results(1, OWNER, 0, 50)["items"][0]["explain_status"] == "skipped"


def test_polling_pagination_preserves_cursor_and_tenant_boundary(api, store):
    with store.engine.begin() as conn:
        conn.execute(text("""INSERT INTO finding(scan_id,fingerprint,tool,category,rule_id,title,severity,raw)
            VALUES (1,'finding-3','semgrep','code','rule','Another finding','high','{}')"""))
    first = api.get("/api/scans/1/explanations?limit=1", headers=headers()).json()
    assert first["next_after_id"] == 1
    second = api.get(f"/api/scans/1/explanations?limit=1&after_id={first['next_after_id']}", headers=headers()).json()
    assert second["next_after_id"] is None
    assert [item["finding_id"] for item in second["items"]] == [3]


def test_new_queue_has_rls_without_public_policies(store):
    with store.engine.connect() as conn:
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.llm_job'::regclass"))
        assert conn.scalar(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='llm_job'")) == 0
