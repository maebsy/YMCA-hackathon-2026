"""보안엔진 결과 → LLM 입력 꾸러미 (스캐너 설치 없이 돈다)."""
import json
from pathlib import Path

from conftest import fake_stripe_key
from test_parsers import OSV_OUTPUT

from security_engine import build_llm_input, render_llm_text
from security_engine.compare import compare
from security_engine.engine import _finalize
from security_engine.runners import gitleaks, osv


def make_result(tmp_path: Path) -> tuple[dict, str]:
    secret = fake_stripe_key()
    (tmp_path / "c.js").write_text(f'// a\nconst k = "{secret}";\n// b\n', encoding="utf-8")
    secret_findings, _ = gitleaks.parse(
        [{"RuleID": "stripe-access-token", "Description": "Stripe key", "File": "c.js",
          "StartLine": 2, "EndLine": 2, "Secret": secret, "Match": secret}], tmp_path)
    findings = osv.parse(OSV_OUTPUT, Path("/abs/site")) + secret_findings
    result = {
        "scan_id": "s1", "scanned_at": "2026-10-31T00:00:00Z", "status": "partial",
        "target": {"path": str(tmp_path), "repo_url": "https://github.com/x/x.github.io", "commit_sha": "abc"},
        "coverage": {
            "osv": {"status": "ok", "category": "dependency", "message": ""},
            "semgrep": {"status": "error", "category": "code", "message": "시간 초과"},
            "gitleaks": {"status": "ok", "category": "secret", "message": ""},
        },
        "suppressions": [], "findings": findings,
    }
    compare(result, None, tmp_path)
    return _finalize(result), secret


def test_llm_input_shape_and_safety(tmp_path):
    result, secret = make_result(tmp_path)
    payload = build_llm_input(result)
    dumped = json.dumps(payload, ensure_ascii=False)
    assert secret not in dumped                      # 비밀값 원문 없음
    assert payload["total_items"] == 3
    first = payload["items"][0]
    assert first["kind"] == "secret" and first["severity"] == "critical"   # 가장 위험한 것이 먼저
    assert ">   2 |" in first["code"]                # 문제 줄 표시
    assert any(f["flag"] == "rotate_secret" for f in first["flags"])
    # 검사 못 한 영역을 LLM에 알려준다 (안전하다고 말하지 않게)
    assert payload["not_checked"] == [{"tool": "semgrep", "category": "code", "reason": "시간 초과"}]
    dep = next(i for i in payload["items"] if i["kind"] == "dependency")
    assert dep["fix_hint"]["command"].startswith("npm install lodash@4.17.")
    assert payload["dependency_upgrades"][0]["target_version"] == "4.17.21"
    # 문제별 힌트와 패키지 묶음의 목표 버전이 같아야 헷갈리지 않는다 (NodeGoat 실검사에서 발견)
    assert all(i["fix_hint"]["target_version"] == "4.17.21" for i in payload["items"] if i["kind"] == "dependency")


def test_llm_text_and_truncation(tmp_path):
    result, secret = make_result(tmp_path)
    payload = build_llm_input(result, max_items=1)
    assert payload["truncated"] and len(payload["items"]) == 1
    text = render_llm_text(payload)
    assert "[검사 못 한 영역] semgrep" in text
    assert "lodash 4.17.15 → 4.17.21" in text
    assert secret not in text


def test_last_resort_redacts_openai_and_anthropic_keys():
    """PR #21 리뷰: sk-proj-… / sk-ant-… 키도 마지막 안전장치에서 가린다."""
    from security_engine.llm_input import _redact
    for key in ("sk-proj-" + "Ab3dEf6hIj9kLm2nOp5q", "sk-ant-api03-" + "Ab3dEf6hIj9kLm2nOp5q_x", "sk_live_" + "Ab3dEf6hIj9kLm2nOp"):
        out = _redact(f"key={key}")
        assert key not in out and "********" in out
