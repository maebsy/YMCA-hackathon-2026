"""실검증 API (/api/verify): 접수 → 진행 조회 → 결과, 입력 제한, 대기열, 작업 소유자.

판정 로직은 test_verify.py가 맡고, 여기서는 verify()를 가짜로 바꿔 API 동작만 봅니다.
마지막 통합 테스트만 실제 데모 과녁을 API로 끝까지 실행합니다 (Node 22.5+ 필요).
"""
import shutil
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import verify as R
from app.routers.scans import scan_user
from app.verify.jobs import VerifyJobs
from app.verify.schemas import AttackOutcome, VerifyResult


def _verified(*_a, **_k) -> VerifyResult:
    return VerifyResult(status="verified", message="ok", sandbox="local", attacks=[
        AttackOutcome(id="sqli-orders", before_succeeded=True, after_succeeded=False, verdict="verified"),
    ])


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
