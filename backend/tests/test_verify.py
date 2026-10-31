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
    src = (DEMO / "server.js").read_text()
    fixed = src.replace(
        'const rows = db.query("SELECT * FROM orders WHERE id = " + orderId);',
        'const rows = db.query("SELECT * FROM orders WHERE id = ?", orderId);',
    ).replace(
        'const q = req.query.q || "";',
        'const q = String(req.query.q || "").replace(/[&<>"\\\']/g, c => '
        '({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\\\'":"&#39;"}[c]));',
    )
    assert "WHERE id = ?" in fixed
    r = verify(VerifyRequest(repo_dir=str(DEMO), attacks=attacks, patch=Patch(files={"server.js": fixed})),
               trusted=True)
    assert r.status == "verified", r.message
    assert {o.id: o.verdict for o in r.attacks} == {"sqli-orders": "verified", "xss-search": "verified"}
    assert r.after_tests.ok is True
