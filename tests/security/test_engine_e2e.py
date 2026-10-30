"""실제 스캐너로 끝까지 돌려보는 테스트. 설치 안 된 도구는 건너뛴다.

OSV는 인터넷(api.osv.dev)이 필요해서 여기서는 끈다.
"""
import json
from pathlib import Path

import pytest
from conftest import fake_stripe_key

from security_engine import ScanOptions, scan
from security_engine.cli import main
from security_engine.runners.base import find_binary

needs_semgrep = pytest.mark.skipif(not find_binary("semgrep"), reason="semgrep 미설치")
needs_gitleaks = pytest.mark.skipif(not find_binary("gitleaks"), reason="gitleaks 미설치")
OPTS = ScanOptions(tools=("semgrep", "gitleaks"), semgrep_registry=(), timeout_sec=300)


@needs_semgrep
@needs_gitleaks
def test_scan_then_rescan(vibe_site: Path):
    first = scan(vibe_site, options=OPTS)
    assert first["status"] == "complete"
    rules = {f["rule_id"] for f in first["findings"]}
    assert {"vibe-coding/public-env-exposes-secret", "vibe-coding/supabase-service-role-in-client",
            "vibe-coding/sql-string-concat", "vibe-coding/js-eval-dynamic",
            "vibe-coding/react-dangerously-set-inner-html"} <= rules
    assert any(f["category"] == "secret" for f in first["findings"])
    assert fake_stripe_key() not in json.dumps(first, ensure_ascii=False)  # 비밀값 원문이 없어야 함
    eval_f = next(f for f in first["findings"] if f["rule_id"].endswith("js-eval-dynamic"))
    assert "suppressed_by_comment" in eval_f["flags"]

    # 사용자가 SQL을 고치고, 키를 지우고, 맨 위에 줄을 하나 추가
    server = vibe_site / "api" / "server.js"
    code = server.read_text(encoding="utf-8").replace(
        '"SELECT * FROM users WHERE id = " + req.query.id', '"SELECT * FROM users WHERE id = ?", [req.query.id]')
    server.write_text("// fixed\n" + code, encoding="utf-8")
    (vibe_site / "api" / "config.js").write_text("module.exports = { stripeKey: process.env.STRIPE_KEY };\n",
                                                 encoding="utf-8")

    second = scan(vibe_site, previous=first, options=OPTS)
    states = {f["rule_id"]: (f["change"], f["status"]) for f in second["findings"]}
    assert states["vibe-coding/sql-string-concat"] == ("resolved", "code_resolved")
    assert states["vibe-coding/js-eval-dynamic"] == ("persisting", "code_issue")  # 줄이 밀려도 같은 문제
    secret = [f for f in second["findings"] if f["category"] == "secret"]
    assert secret and all(f["status"] == "runtime_check_needed" for f in secret)
    assert second["comparison"]["new"] == 0


@needs_semgrep
def test_cli_writes_valid_json(vibe_site: Path, tmp_path: Path):
    out = tmp_path / "r.json"
    code = main(["scan", str(vibe_site), "--tools", "semgrep", "--no-registry", "-o", str(out), "--quiet"])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["coverage"]["osv"]["status"] == "skipped"
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).resolve().parents[2] / "security_engine" / "schema" / "scan_result.schema.json"
    jsonschema.validate(data, json.loads(schema_path.read_text(encoding="utf-8")))


def test_missing_tool_is_out_of_scope(vibe_site: Path, monkeypatch):
    monkeypatch.setenv("SECURITY_ENGINE_OSV_BIN", str(vibe_site / "nope"))
    r = scan(vibe_site, options=ScanOptions(tools=("osv",)))
    assert r["coverage"]["osv"]["status"] == "not_installed"
    assert r["coverage"]["osv"]["state"] == "out_of_scope"
    assert r["status"] == "failed"


@needs_semgrep
def test_builtin_rules_pass_semgrep_test():
    """rules/의 각 규칙이 테스트 파일의 'ruleid' 줄은 잡고 'ok' 줄은 안 잡는지 (semgrep --test)."""
    import subprocess

    from security_engine.models import BUILTIN_RULES_DIR
    from security_engine.runners.base import run_cmd

    proc = run_cmd([find_binary("semgrep"), "--test", "--metrics=off", str(BUILTIN_RULES_DIR)], timeout=300)
    assert proc.returncode == 0, (proc.stdout or "")[-2000:]
    assert isinstance(proc, subprocess.CompletedProcess)


@needs_semgrep
def test_no_registry_uses_only_our_rules(vibe_site: Path):
    """--no-registry(semgrep_registry=())면 우리 규칙만 → 모든 rule_id가 vibe-coding/로 시작."""
    r = scan(vibe_site, options=ScanOptions(tools=("semgrep",), semgrep_registry=()))
    assert r["coverage"]["semgrep"]["message"] == ""
    assert r["findings"] and all(f["rule_id"].startswith("vibe-coding/") for f in r["findings"])


@needs_semgrep
def test_third_party_library_is_downgraded(tmp_path: Path):
    """외부 라이브러리(assets/js/plugins/…) 안의 위험 패턴은 숨기지 않고 low + third_party_code (블로그 실검사에서 발견)."""
    site = tmp_path / "blog"
    (site / "assets" / "js" / "plugins").mkdir(parents=True)
    code = "function f(html){ var el = document.createElement('div'); el.innerHTML = html; }\n"
    (site / "assets" / "js" / "plugins" / "jquery.popup.js").write_text(code, encoding="utf-8")
    (site / "app.js").write_text(code, encoding="utf-8")
    r = scan(site, options=ScanOptions(tools=("semgrep",), semgrep_registry=()))
    by_file = {f["location"]["file"]: f for f in r["findings"]}
    lib = by_file["assets/js/plugins/jquery.popup.js"]
    assert lib["severity"] == "low" and "third_party_code" in lib["flags"]
    assert by_file["app.js"]["severity"] == "medium" and not by_file["app.js"]["flags"]   # 내 코드는 그대로


def test_registry_on_by_default():
    """기본값은 우리 규칙 + Semgrep 레지스트리(p/default). CLI --no-registry로 끌 수 있다."""
    from security_engine.cli import _options
    import argparse
    assert ScanOptions().semgrep_registry == ("p/default",)
    ns = argparse.Namespace(tools=None, no_registry=True, with_registry=None, semgrep_config=None,
                            osv_offline=False, timeout=600, include_raw=False)
    assert _options(ns).semgrep_registry == ()
    ns.no_registry = False
    assert _options(ns).semgrep_registry == ("p/default",)
