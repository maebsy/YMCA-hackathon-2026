"""검사 API (/api/scans): 접수 → 진행 조회 → 결과, 재검사 비교, 주소 제한. 실제 스캐너 없이 엔진의 scan_repo만 바꿔 끼웁니다."""
import sys
import time
from collections import OrderedDict
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app  # app.routers.scans 가 저장소 루트(security_engine)를 import 경로에 넣습니다

import security_engine  # noqa: E402
from security_engine import scan  # noqa: E402
from security_engine.models import ScanOptions  # noqa: E402

from app.explain_jobs.config import job_settings  # noqa: E402
from app.routers import scans  # noqa: E402


@pytest.fixture
def site(tmp_path):
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")  # 설정 검사기가 잡는 문제 1건
    return tmp_path


@pytest.fixture
def fake_scan_repo(monkeypatch, site):
    def fake(repo_url, previous=None, **kw):
        return scan(site, previous, options=ScanOptions(tools=("config",)), repo_url=repo_url)

    monkeypatch.setattr(security_engine, "scan_repo", fake)


def _wait(client, job_id):
    for _ in range(100):
        job = client.get(f"/api/scans/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("검사가 끝나지 않음")


def test_scan_job_then_rescan(fake_scan_repo, site):
    url = "https://github.com/demo/site"
    with TestClient(app) as client:
        r = client.post("/api/scans", json={"repo_url": url})
        assert r.status_code == 202
        job = _wait(client, r.json()["job_id"])
        assert job["status"] == "done", job
        first = job["result"]
        assert first["coverage"]["config"]["status"] == "ok"
        assert first["findings"] and first["report_scan"]["repo"] == url
        assert first["report_scan"]["resolved_at"] is None

        (site / ".env").unlink()  # 고친 뒤 재검사
        r = client.post("/api/scans", json={"repo_url": url, "previous": first["result"]})
        second = _wait(client, r.json()["job_id"])["result"]
        assert second["comparison"]["resolved"] >= 1
        assert second["report_scan"]["resolved_at"]  # 열린 문제 0건 → 완료 리포트

        report = client.post("/api/reports/plain", json={
            "scan": second["report_scan"], "findings": second["findings"], "explain_results": []})
        assert report.status_code == 200


def test_rejects_non_github_url():
    with TestClient(app) as client:
        r = client.post("/api/scans", json={"repo_url": "https://169.254.169.254/latest"})
        assert r.status_code == 400
        assert client.get("/api/scans/nope").status_code == 404


# ── 검사 API 보호 (#53) ──
URL = "https://github.com/demo/site"


@pytest.fixture(autouse=True)
def fresh_jobs(monkeypatch):
    monkeypatch.setattr(scans, "_jobs", OrderedDict())


def _fake_job(status):
    return {"job_id": status, "status": status, "repo_url": URL, "result": None, "error": None, "owner": None}


def test_queue_full_returns_429(fake_scan_repo):
    for i in range(scans.MAX_ACTIVE):
        scans._jobs[f"q{i}"] = _fake_job("queued")
    with TestClient(app) as client:
        r = client.post("/api/scans", json={"repo_url": URL})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "SCAN_QUEUE_FULL"
    assert r.headers["retry-after"] == "60"


def test_eviction_keeps_unfinished_jobs():
    scans._jobs["running"] = _fake_job("running")
    for i in range(scans.MAX_KEPT + 10):
        scans._jobs[f"d{i}"] = _fake_job("done")

    scans._evict_finished()

    assert "running" in scans._jobs  # 가장 오래됐어도 진행 중이면 남김
    assert len(scans._jobs) == scans.MAX_KEPT
    assert "d0" not in scans._jobs and f"d{scans.MAX_KEPT + 9}" in scans._jobs


def test_task_reference_is_kept_until_done(fake_scan_repo):
    with TestClient(app) as client:
        job_id = client.post("/api/scans", json={"repo_url": URL}).json()["job_id"]
        assert _wait(client, job_id)["status"] == "done"
    assert not scans._tasks  # 끝나면 참조도 정리


def test_missing_engine_returns_503(monkeypatch):
    monkeypatch.setitem(sys.modules, "security_engine.git", None)  # import 하면 ImportError
    with TestClient(app) as client:
        r = client.post("/api/scans", json={"repo_url": URL})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "ENGINE_UNAVAILABLE"


def test_scan_error_hides_internal_message(monkeypatch):
    def boom(repo_url, previous=None, **kw):
        raise RuntimeError("/srv/72hours/private/path exploded")

    monkeypatch.setattr(security_engine, "scan_repo", boom)
    with TestClient(app) as client:
        job = _wait(client, client.post("/api/scans", json={"repo_url": URL}).json()["job_id"])
    assert job["status"] == "failed" and job["error"]["code"] == "SCAN_ERROR"
    assert "/srv" not in job["error"]["message"] and "RuntimeError" not in job["error"]["message"]


class FakeAuth:
    USERS = {"token-a": UUID(int=1), "token-b": UUID(int=2)}

    async def verify(self, token):
        if token not in self.USERS:
            raise HTTPException(401, "INVALID_ACCESS_TOKEN")
        return self.USERS[token]


def test_auth_required_and_jobs_are_owner_only(monkeypatch, fake_scan_repo):
    with TestClient(app) as client:
        monkeypatch.setattr(job_settings, "scan_require_auth", True)
        monkeypatch.setattr(app.state, "job_auth", FakeAuth(), raising=False)
        a = {"Authorization": "Bearer token-a"}

        assert client.post("/api/scans", json={"repo_url": URL}).status_code == 401
        assert client.post("/api/scans", json={"repo_url": URL}, headers={"Authorization": "Bearer nope"}).status_code == 401
        r = client.post("/api/scans", json={"repo_url": URL}, headers=a)
        assert r.status_code == 202
        job_id = r.json()["job_id"]

        assert client.get(f"/api/scans/{job_id}", headers={"Authorization": "Bearer token-b"}).status_code == 404
        assert client.get(f"/api/scans/{job_id}").status_code == 401
        mine = client.get(f"/api/scans/{job_id}", headers=a)
        assert mine.status_code == 200 and "owner" not in mine.json()
