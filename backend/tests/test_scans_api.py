"""검사 API (/api/scans): 접수 → 진행 조회 → 결과, 재검사 비교, 주소 제한. 실제 스캐너 없이 엔진의 scan_repo만 바꿔 끼웁니다."""
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app  # app.routers.scans 가 저장소 루트(security_engine)를 import 경로에 넣습니다

import security_engine  # noqa: E402
from security_engine import scan  # noqa: E402
from security_engine.models import ScanOptions  # noqa: E402


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


# ── 검사 대상 제한: 허용한 소유자만, 관리자는 예외 (#67) ──
from uuid import UUID  # noqa: E402

from app.explain_jobs.config import job_settings  # noqa: E402
from app.routers import scans  # noqa: E402

ADMIN = UUID(int=7)


@pytest.mark.parametrize(
    ("url", "user", "allowed"),
    [
        ("https://github.com/OWASP/NodeGoat", None, True),
        ("https://github.com/owasp/juice-shop.git", None, True),  # 대소문자 무시
        ("https://github.com/someone-else/shop", None, False),
        ("https://github.com/OWASPx/NodeGoat", None, False),  # 접두어만 같은 소유자
        ("https://github.com/someone-else/shop", UUID(int=8), False),  # 관리자가 아닌 로그인 사용자
        ("https://github.com/someone-else/shop", ADMIN, True),  # 관리자는 예외
    ],
)
def test_target_owner_allowlist(monkeypatch, url, user, allowed):
    monkeypatch.setattr(job_settings, "scan_allowed_owners", "OWASP, maebsy")
    monkeypatch.setattr(job_settings, "scan_admin_user_ids", str(ADMIN).upper())
    assert scans._target_allowed(url, user) is allowed


def test_empty_allowlist_means_no_restriction(monkeypatch):
    monkeypatch.setattr(job_settings, "scan_allowed_owners", "")
    assert scans._target_allowed("https://github.com/anyone/repo", None)


def test_disallowed_owner_is_rejected_before_queueing(monkeypatch, fake_scan_repo):
    monkeypatch.setattr(job_settings, "scan_allowed_owners", "OWASP")
    with TestClient(app) as client:
        r = client.post("/api/scans", json={"repo_url": "https://github.com/demo/site"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "SCAN_TARGET_NOT_ALLOWED"
        ok = client.post("/api/scans", json={"repo_url": "https://github.com/OWASP/site"})
        assert ok.status_code == 202
        assert _wait(client, ok.json()["job_id"])["status"] == "done"


# ── 검사 API 보호: 대기열 상한·엔진 미설치·오류 원문·인증 설정 조합 (#53) ──
from fastapi import HTTPException  # noqa: E402

URL = "https://github.com/demo/site"


def test_queue_full_returns_429(monkeypatch, fake_scan_repo):
    monkeypatch.setattr(scans, "MAX_ACTIVE", 0)  # 이미 꽉 찬 상태
    with TestClient(app) as client:
        r = client.post("/api/scans", json={"repo_url": URL})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "SCAN_QUEUE_FULL"
    assert r.headers["retry-after"] == "60"


def test_queue_has_room_again_after_jobs_finish(fake_scan_repo):
    with TestClient(app) as client:
        for _ in range(scans.MAX_ACTIVE + 2):  # 하나씩 끝나면 참조가 빠져 상한에 걸리지 않습니다
            job_id = client.post("/api/scans", json={"repo_url": URL}).json()["job_id"]
            assert _wait(client, job_id)["status"] == "done"
    assert not scans._tasks


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


@pytest.mark.parametrize(("llm_jobs_enabled", "scan_require_auth"), [(True, False), (False, True), (True, True)])
def test_auth_settings_either_flag_requires_login(monkeypatch, fake_scan_repo, llm_jobs_enabled, scan_require_auth):
    """두 설정 중 하나라도 켜면 로그인이 필요하고, 남의 검사는 404입니다."""
    with TestClient(app) as client:
        monkeypatch.setattr(job_settings, "llm_jobs_enabled", llm_jobs_enabled)
        monkeypatch.setattr(job_settings, "scan_require_auth", scan_require_auth)
        monkeypatch.setattr(app.state, "job_auth", FakeAuth(), raising=False)
        a, b = {"Authorization": "Bearer token-a"}, {"Authorization": "Bearer token-b"}

        assert client.post("/api/scans", json={"repo_url": URL}).status_code == 401
        assert client.post("/api/scans", json={"repo_url": URL}, headers={"Authorization": "Bearer nope"}).status_code == 401
        r = client.post("/api/scans", json={"repo_url": URL}, headers=a)
        assert r.status_code == 202
        job_id = r.json()["job_id"]

        assert client.get(f"/api/scans/{job_id}").status_code == 401
        assert client.get(f"/api/scans/{job_id}", headers=b).status_code == 404
        for _ in range(100):
            job = client.get(f"/api/scans/{job_id}", headers=a).json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.05)
        assert job["status"] == "done"
        # 재검사도 내 저장본만 이어 받습니다: 남이 내 scan_id를 previous로 쓰면 404
        prev = {"scan_id": job["result"]["scan_id"]}
        assert client.post("/api/scans", json={"repo_url": URL, "previous": prev}, headers=b).status_code == 404
        assert client.post("/api/scans", json={"repo_url": URL, "previous": prev}, headers=a).status_code == 202


def test_auth_off_by_default(fake_scan_repo):
    assert not job_settings.llm_jobs_enabled and not job_settings.scan_require_auth
    with TestClient(app) as client:
        assert client.post("/api/scans", json={"repo_url": URL}).status_code == 202
