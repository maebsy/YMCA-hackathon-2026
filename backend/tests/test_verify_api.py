"""실검증 API (/api/verify): 접수 → 진행 조회 → 결과, 입력 제한, 대기열, 작업 소유자.

판정 로직은 test_verify.py가 맡고, 여기서는 verify()를 가짜로 바꿔 API 동작만 봅니다.
마지막 통합 테스트만 실제 데모 과녁을 API로 끝까지 실행합니다 (Node 22.5+ 필요).
"""
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import verify as R
from app.routers.scans import scan_user
from app.verify import jobs as J
from app.verify.jobs import VerifyJobs
from app.verify.schemas import AttackOutcome, VerifyResult


def _verified(*_a, **_k) -> VerifyResult:
    return VerifyResult(status="verified", message="ok", sandbox="local", attacks=[
        AttackOutcome(id="sqli-orders", before_succeeded=True, after_succeeded=False, verdict="verified"),
    ])


@pytest.fixture
def reuse_default(monkeypatch):
    monkeypatch.delenv("VERIFY_REUSE_SECONDS", raising=False)


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(R, "_runtime_ready", lambda: True)
    monkeypatch.setattr(R, "verify", _verified)


def _wait(client, job_id):
    for _ in range(200):
        job = client.get(f"/api/verify/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("실검증이 끝나지 않음")


def test_verify_job_returns_result_and_demo_inputs(ready):
    with TestClient(app) as client:
        r = client.post("/api/verify", json={"target": "demo"})
        assert r.status_code == 202 and r.json()["status"] == "queued"
        assert r.headers["cache-control"] == "no-store"
        job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["status"] == "verified"
    assert job["target"] == "demo"
    # 화면이 공격 요청과 '정적 탐지만' 항목을 보여 줄 수 있게 공격 정의 전체가 같이 옵니다
    ids = {a["id"]: a for a in job["attacks"]}
    assert ids["sqli-orders"]["request"]["path"] == "/api/orders"
    assert ids["jwt-hardcoded"]["runtime"] is False
    assert job["patched_files"] == ["server.js"]
    assert "WHERE id = ?" in job["patch_diff"] and job["patch_diff"].startswith("--- a/server.js")
    assert "owner" not in job and "finished" not in job
    assert job["reused"] is False
    assert datetime.fromisoformat(job["finished_at"]).tzinfo == timezone.utc


@pytest.mark.parametrize("status", ["verified", "fix_failed", "not_reproduced"])
def test_recent_result_is_reused_without_runtime_check(ready, reuse_default, monkeypatch, status):
    calls = []

    def work(*_a, **_k):
        calls.append(True)
        return _verified().model_copy(update={"status": status})

    def runtime_must_not_run():
        raise AssertionError("재사용할 때 실행 환경을 확인하면 안 됨")

    monkeypatch.setattr(R, "verify", work)
    with TestClient(app) as client:
        first = _wait(client, client.post("/api/verify").json()["job_id"])
        monkeypatch.setattr(R, "_runtime_ready", runtime_must_not_run)
        response = client.post("/api/verify", json={"target": "demo"})
        assert response.status_code == 202
        assert response.headers["cache-control"] == "no-store"
        start = response.json()
        assert start["status"] == "done" and start["reused"] is True
        assert start["job_id"] != first["job_id"]
        reused = client.get(f"/api/verify/{start['job_id']}").json()
    assert len(calls) == 1
    assert reused == {**first, "job_id": start["job_id"], "reused": True}


def test_reused_result_has_its_own_owner(ready, reuse_default):
    try:
        with TestClient(app) as client:
            app.dependency_overrides[scan_user] = lambda: "user-a"
            original = _wait(client, client.post("/api/verify").json()["job_id"])
            app.dependency_overrides[scan_user] = lambda: "user-b"
            response = client.post("/api/verify")
            assert response.status_code == 202 and response.json()["reused"] is True
            key = response.json()["job_id"]
            assert key != original["job_id"]
            assert client.get(f"/api/verify/{original['job_id']}").status_code == 404
            reused = client.get(f"/api/verify/{key}")
            assert reused.status_code == 200 and reused.json()["result"] == original["result"]
            assert "owner" not in reused.json() and "finished" not in reused.json()
            app.dependency_overrides[scan_user] = lambda: "user-a"
            assert client.get(f"/api/verify/{key}").status_code == 404
            assert client.get(f"/api/verify/{original['job_id']}").status_code == 200
    finally:
        app.dependency_overrides.pop(scan_user, None)


def test_zero_reuse_seconds_runs_every_time(ready, monkeypatch):
    monkeypatch.setenv("VERIFY_REUSE_SECONDS", "0")
    calls = []

    def work(*_a, **_k):
        calls.append(True)
        return _verified()

    monkeypatch.setattr(R, "verify", work)
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post("/api/verify")
            assert response.json()["status"] == "queued" and response.json()["reused"] is False
            assert _wait(client, response.json()["job_id"])["reused"] is False
    assert len(calls) == 2


@pytest.mark.parametrize("failure", ["error", "failed"])
def test_unsuccessful_execution_is_not_reused(ready, reuse_default, monkeypatch, failure):
    calls = []

    def work(*_a, **_k):
        calls.append(True)
        if failure == "failed":
            raise RuntimeError("실행 실패")
        return VerifyResult(status="error", message="실행 실패")

    monkeypatch.setattr(R, "verify", work)
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post("/api/verify")
            assert response.json()["status"] == "queued" and response.json()["reused"] is False
            job = _wait(client, response.json()["job_id"])
            assert job["status"] == ("done" if failure == "error" else "failed")
            assert datetime.fromisoformat(job["finished_at"]).tzinfo == timezone.utc
    assert len(calls) == 2


@pytest.mark.parametrize("value", ["", "invalid", "1.5", "-1"])
def test_invalid_reuse_seconds_uses_default(ready, monkeypatch, value):
    monkeypatch.setenv("VERIFY_REUSE_SECONDS", value)
    assert R._ReuseSettings().verify_reuse_seconds == 300
    with TestClient(app) as client:
        _wait(client, client.post("/api/verify").json()["job_id"])
        assert client.post("/api/verify").json()["reused"] is True


def test_reuse_expires_from_original_execution(ready, monkeypatch):
    monkeypatch.setenv("VERIFY_REUSE_SECONDS", "10")
    with TestClient(app) as client:
        original = _wait(client, client.post("/api/verify").json()["job_id"])
        finished = app.state.verify_jobs.jobs[original["job_id"]]["finished"]
        # asyncio도 같은 time 모듈을 쓰므로 단조 시계 전체를 바꾸지 않습니다.
        monkeypatch.setattr(J, "time", SimpleNamespace(monotonic=lambda: finished + 9))
        reused = client.post("/api/verify").json()
        assert reused["reused"] is True
        copy = client.get(f"/api/verify/{reused['job_id']}").json()
        assert copy["finished_at"] == original["finished_at"]
        monkeypatch.setattr(J, "time", SimpleNamespace(monotonic=lambda: finished + 10))
        fresh = client.post("/api/verify").json()
        assert fresh["status"] == "queued" and fresh["reused"] is False
        assert _wait(client, fresh["job_id"])["reused"] is False


def test_results_are_only_reused_for_the_same_target(ready, reuse_default):
    with TestClient(app) as client:
        original = _wait(client, client.post("/api/verify").json()["job_id"])
        app.state.verify_jobs.jobs[original["job_id"]]["target"] = "other"
        response = client.post("/api/verify").json()
        assert response["status"] == "queued" and response["reused"] is False
        _wait(client, response["job_id"])


def test_body_is_optional(ready):
    with TestClient(app) as client:
        r = client.post("/api/verify")
        assert r.status_code == 202
        _wait(client, r.json()["job_id"])


@pytest.mark.parametrize("body", [
    {"target": "user"},
    {"target": "demo", "repo_dir": "/etc"},
    {"target": "demo", "patch": {"files": {"server.js": "require('child_process').exec('id')"}}},
    {"target": "demo", "start_cmd": ["sh", "-c", "id"]},
])
def test_rejects_anything_but_the_demo_target(ready, body):
    """요청으로 경로·수정본·명령을 받으면 그 코드가 서버에서 격리 없이 돌 수 있어 422로 거절합니다."""
    with TestClient(app) as client:
        assert client.post("/api/verify", json=body).status_code == 422


def test_no_runtime_is_503(monkeypatch):
    monkeypatch.setattr(R, "_runtime_ready", lambda: False)
    with TestClient(app) as client:
        r = client.post("/api/verify")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "VERIFY_UNAVAILABLE"


def test_unknown_job_is_404(ready):
    with TestClient(app) as client:
        r = client.get("/api/verify/does-not-exist")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "VERIFY_JOB_NOT_FOUND"


def test_error_message_hides_server_details(monkeypatch):
    def boom(*_a, **_k):
        raise FileNotFoundError("C:/srv/72hours/private/backend.env")

    monkeypatch.setattr(R, "_runtime_ready", lambda: True)
    monkeypatch.setattr(R, "verify", boom)
    with TestClient(app) as client:
        job = _wait(client, client.post("/api/verify").json()["job_id"])
    assert job["status"] == "failed" and job["error"]["code"] == "VERIFY_ERROR"
    assert "backend.env" not in str(job)


def test_runs_one_at_a_time_and_caps_the_queue(monkeypatch):
    """LocalSandbox는 고정 포트를 써서 동시에 1건만 돌리고, 대기 포함 정원을 넘으면 429."""
    release, lock = threading.Event(), threading.Lock()
    live = {"now": 0, "max": 0}

    def slow(*_a, **_k):
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        release.wait(5)
        with lock:
            live["now"] -= 1
        return _verified()

    monkeypatch.setattr(R, "_runtime_ready", lambda: True)
    monkeypatch.setattr(R, "verify", slow)
    with TestClient(app) as client:
        app.state.verify_jobs = VerifyJobs(capacity=2)
        first = client.post("/api/verify").json()["job_id"]
        second = client.post("/api/verify").json()["job_id"]
        full = client.post("/api/verify")
        assert full.status_code == 429 and full.headers["retry-after"] == "60"
        assert full.json()["detail"]["code"] == "VERIFY_QUEUE_FULL"
        time.sleep(0.2)
        release.set()
        assert _wait(client, first)["status"] == "done"
        assert _wait(client, second)["status"] == "done"
    assert live["max"] == 1


def test_only_the_requester_can_read_the_job(ready):
    try:
        with TestClient(app) as client:
            app.dependency_overrides[scan_user] = lambda: "user-a"
            job_id = client.post("/api/verify").json()["job_id"]
            assert _wait(client, job_id)["status"] == "done"
            app.dependency_overrides[scan_user] = lambda: "user-b"
            assert client.get(f"/api/verify/{job_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(scan_user, None)


# ── 통합: API → 실제 데모 과녁 + 샌드박스 (Docker가 있으면 Docker, 없으면 LocalSandbox) ──
def _node_ok() -> bool:
    exe = shutil.which("node")
    if not exe or not shutil.which("npm"):
        return False
    try:
        return subprocess.run([exe, "-e", "require('node:sqlite')"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(not _node_ok(), reason="Node 22.5+(node:sqlite)·npm 필요")
def test_integration_demo_through_api():
    with TestClient(app) as client:
        r = client.post("/api/verify", json={"target": "demo"})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        for _ in range(600):
            job = client.get(f"/api/verify/{job_id}").json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.5)
    assert job["status"] == "done", job
    result = job["result"]
    assert result["status"] == "verified", result["message"]
    assert {a["id"]: a["verdict"] for a in result["attacks"]} == {"sqli-orders": "verified", "xss-search": "verified"}
    # 기능 테스트 건수까지 읽혀야 화면에 "3/3 통과"를 보여 줄 수 있습니다
    assert result["before_tests"]["passed"] == result["after_tests"]["passed"] == 3
    assert result["after_tests"]["failed"] == 0
