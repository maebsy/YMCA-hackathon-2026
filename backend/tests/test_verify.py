"""Red–Blue 실검증 테스트.

- 판정 로직(verified/fix_failed/not_reproduced/error)은 샌드박스 출력을 가짜로 주입해 node 없이 빠르게 검증.
- 통합 테스트는 실제 데모 과녁 + LocalSandbox 로 '수정 전 공격 성공 → 수정 후 차단'을 끝까지 확인(node 필요).
"""
import json
import shutil
from pathlib import Path

import pytest

from app.verify import Patch, VerifyRequest, verify
from app.verify import verifier as V
from app.verify.schemas import AttackSpec

DEMO = Path(__file__).resolve().parents[2] / "demo-vulnerable-site"

SQLI = AttackSpec(id="sqli", runtime=True, success_when="json_array_len_gte:2",
                  request={"method": "GET", "path": "/api/orders", "query": {"orderId": "0 OR 1=1"}})


def _req(**kw):
    return VerifyRequest(repo_dir=str(DEMO), attacks=[SQLI], patch=Patch(files={}), **kw)


class _FakeSandbox:
    name = "local"

    def __init__(self, before, after):
        self._runs = [before, after]

    def run(self, workdir, cfg, **kw):
        return self._runs.pop(0)


def _probe(attack_ok, tests_ok=True):
    return {"reachable": True, "attacks": [{"id": "sqli", "succeeded": attack_ok, "status": 200, "evidence": "x"}],
            "tests": {"ok": tests_ok, "passed": 3, "failed": 0 if tests_ok else 1}}


def test_verified(monkeypatch):
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(_probe(True), _probe(False)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "verified"
    assert r.attacks[0].verdict == "verified"


def test_fix_failed_attack_still_works(monkeypatch):
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(_probe(True), _probe(True)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "fix_failed"
    assert r.attacks[0].verdict == "fix_failed"


def test_fix_failed_tests_broken(monkeypatch):
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(_probe(True), _probe(False, tests_ok=False)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "fix_failed"  # 공격은 막혔어도 기능이 깨지면 실패


def test_not_reproduced(monkeypatch):
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(_probe(False), _probe(False)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "not_reproduced"


def test_error_app_not_up(monkeypatch):
    dead = {"reachable": False, "appError": "boom", "attacks": [], "tests": {}}
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(dead, dead))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "error"


def test_user_repo_requires_docker(monkeypatch):
    """사용자 저장소(trusted=False)는 Docker 없으면 실검증을 거부해야 한다."""
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: (_ for _ in ()).throw(
        __import__("app.verify.sandbox", fromlist=["SandboxError"]).SandboxError("Docker 필요")))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=False)
    assert r.status == "error" and "Docker" in r.message


def test_after_app_not_up_is_fix_failed(monkeypatch):
    """리뷰 재현(#86): 수정 전 공격 성공 / 수정 후 앱이 안 뜸(공격 결과 없음) / 테스트 통과 → verified가 아니라 fix_failed."""
    dead_after = {"reachable": False, "appError": "listen 실패", "attacks": [],
                  "tests": {"ok": True, "passed": 3, "failed": 0}}
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(_probe(True), dead_after))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "fix_failed"
    assert "수정 후 앱이 뜨지 않았습니다" in r.message
    assert not r.attacks  # '차단됨'으로 센 공격이 없어야 함


def test_missing_attack_result_is_error(monkeypatch):
    """수정 후 결과에 해당 공격이 빠져 있으면 '차단'으로 세지 않고 error."""
    after = {"reachable": True, "attacks": [], "tests": {"ok": True, "passed": 3, "failed": 0}}
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _FakeSandbox(_probe(True), after))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "error" and "sqli" in r.message


def test_pre_broken_tests_not_blamed_on_fix(monkeypatch):
    """수정 전부터 실패하던 테스트는 수정본 탓이 아님 → 공격이 막혔으면 verified, 단 기능 보존 미확인을 알림."""
    monkeypatch.setattr(V, "pick_sandbox",
                        lambda trusted: _FakeSandbox(_probe(True, tests_ok=False), _probe(False, tests_ok=False)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=True)
    assert r.status == "verified"
    assert "수정 전부터 실패" in r.message


def test_symlink_copied_as_link_not_content(monkeypatch, tmp_path):
    """저장소 안 심볼릭 링크가 가리키는 바깥 파일 내용이 사본으로 들어가지 않아야 함."""
    secret = tmp_path / "server-secret.txt"
    secret.write_text("SERVER-ONLY", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "leak").symlink_to(secret)
    seen = {}

    class _Spy(_FakeSandbox):
        def run(self, workdir, cfg, **kw):
            seen.setdefault("dirs", []).append(workdir)
            seen["is_link"] = (Path(workdir) / "leak").is_symlink()
            return super().run(workdir, cfg, **kw)

    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: _Spy(_probe(True), _probe(False)))
    r = verify(VerifyRequest(repo_dir=str(repo), attacks=[SQLI], patch=Patch(files={})), trusted=True)
    assert r.status == "verified"
    assert seen["is_link"] is True  # 내용이 복사된 일반 파일이 아니라 링크 그대로


ISO_OK = {"network_isolated": True, "non_root": True, "caps_dropped": True, "no_new_privs": True}


def _iso(probe, iso):
    return {**probe, "isolation": iso}


def test_user_repo_without_confirmed_isolation_is_error(monkeypatch):
    """사용자 저장소는 격리가 실행 결과로 확인되지 않으면(예: 네트워크가 열려 있음) 판정을 내지 않는다."""
    leaky = {**ISO_OK, "network_isolated": False}
    monkeypatch.setattr(V, "pick_sandbox",
                        lambda trusted: _FakeSandbox(_iso(_probe(True), leaky), _iso(_probe(False), leaky)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=False)
    assert r.status == "error" and "network_isolated" in r.message
    assert r.isolation_confirmed is False


def test_user_repo_with_confirmed_isolation_is_judged(monkeypatch):
    monkeypatch.setattr(V, "pick_sandbox",
                        lambda trusted: _FakeSandbox(_iso(_probe(True), ISO_OK), _iso(_probe(False), ISO_OK)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=False)
    assert r.status == "verified" and r.isolation_confirmed is True


def test_isolation_must_hold_in_both_runs(monkeypatch):
    """수정 후 실행에서 한 항목이라도 깨지면 격리 확인 실패."""
    broken = {**ISO_OK, "caps_dropped": False}
    monkeypatch.setattr(V, "pick_sandbox",
                        lambda trusted: _FakeSandbox(_iso(_probe(True), ISO_OK), _iso(_probe(False), broken)))
    monkeypatch.setattr(shutil, "copytree", lambda *a, **k: None)
    r = verify(_req(), trusted=False)
    assert r.status == "error" and r.isolation.caps_dropped is False


# ── 통합: 실제 데모 과녁 + LocalSandbox (Node 22.5+ 필요: 데모가 내장 node:sqlite 사용) ──
def _node_ok() -> bool:
    import subprocess
    exe = shutil.which("node")
    if not exe or not shutil.which("npm"):
        return False
    try:
        out = subprocess.run([exe, "-e", "require('node:sqlite')"], capture_output=True, timeout=20)
        return out.returncode == 0
    except Exception:
        return False


needs_node = pytest.mark.skipif(not _node_ok(), reason="Node 22.5+(node:sqlite)·npm 필요")


@needs_node
def test_integration_demo_before_after():
    attacks = [AttackSpec(**a) for a in json.loads((DEMO / "verify" / "attacks.json").read_text())["attacks"]]
    # 기준 수정본(Blue가 내야 할 수정의 예시): 파라미터 바인딩 + 출력 이스케이프 + 서명 키 환경변수화
    fixed = (DEMO / "verify" / "fix" / "server.js").read_text()
    assert "WHERE id = ?" in fixed and "demo-insecure-key" not in fixed
    r = verify(VerifyRequest(repo_dir=str(DEMO), attacks=attacks, patch=Patch(files={"server.js": fixed})),
               trusted=True)
    assert r.status == "verified", r.message
    assert {o.id: o.verdict for o in r.attacks} == {"sqli-orders": "verified", "xss-search": "verified"}
    assert r.after_tests.ok is True
