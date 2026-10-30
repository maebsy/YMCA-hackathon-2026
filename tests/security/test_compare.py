"""재검사 비교: 새로/계속/해결/확인불가 + 4가지 상태 (스캐너 설치 없이 돈다)."""
import copy

from security_engine.compare import compare
from security_engine.models import (
    CODE_ISSUE,
    CODE_RESOLVED,
    FLAG_FILE_REMOVED,
    OUT_OF_SCOPE,
    RUNTIME_CHECK,
)


def finding(fp, tool="semgrep", category="code", file="a.js", rule_id="vibe-coding/x"):
    return {"fingerprint": fp, "tool": tool, "category": category, "flags": [], "rule_id": rule_id,
            "location": {"file": file, "start_line": 1, "end_line": 1}}


def result(findings, cov=None, at="2026-11-01T00:00:00Z", registry_used=False):
    cov = cov or {"osv": "ok", "semgrep": "ok", "gitleaks": "ok"}
    coverage = {t: {"status": s} for t, s in cov.items()}
    coverage.setdefault("semgrep", {})["registry_used"] = registry_used
    return {"scan_id": at, "scanned_at": at, "target": {"commit_sha": None},
            "coverage": coverage,
            "findings": copy.deepcopy(findings)}


def by_fp(r):
    return {f["fingerprint"]: f for f in r["findings"]}


def test_first_scan_everything_new():
    r = compare(result([finding("s:1")]), None)
    f = by_fp(r)["s:1"]
    assert (f["change"], f["status"]) == ("new", CODE_ISSUE)
    assert r["comparison"] is None


def test_rescan_states(tmp_path):
    (tmp_path / "a.js").write_text("x", encoding="utf-8")
    prev = compare(result([finding("s:keep"), finding("s:fixed"), finding("g:key", "gitleaks", "secret"),
                           finding("s:gone", file="deleted.js")], at="t1"), None)
    cur = compare(result([finding("s:keep"), finding("s:brand-new")], at="t2"), prev, tmp_path)
    f = by_fp(cur)
    assert f["s:keep"]["change"] == "persisting" and f["s:keep"]["first_seen"] == "t1"
    assert f["s:brand-new"]["change"] == "new"
    assert (f["s:fixed"]["change"], f["s:fixed"]["status"]) == ("resolved", CODE_RESOLVED)
    # 비밀값은 코드에서 지워도 키 폐기가 필요 → 운영 환경 확인 필요
    assert f["g:key"]["status"] == RUNTIME_CHECK
    # 파일째 사라진 '해결'은 기능 삭제 의심 표시
    assert FLAG_FILE_REMOVED in f["s:gone"]["flags"]
    assert cur["comparison"]["resolved"] == 3


def test_tool_failure_is_not_resolution():
    prev = compare(result([finding("s:1")], at="t1"), None)
    cur = compare(result([], cov={"osv": "ok", "semgrep": "error", "gitleaks": "ok"}, at="t2"), prev)
    f = by_fp(cur)["s:1"]
    assert (f["change"], f["status"]) == ("unverifiable", OUT_OF_SCOPE)
    # 다음 검사에서 다시 확인되면 계속 있는 문제로 이어진다
    nxt = compare(result([finding("s:1")], at="t3"), cur)
    assert by_fp(nxt)["s:1"]["change"] == "persisting"
    assert by_fp(nxt)["s:1"]["first_seen"] == "t1"


def test_resolved_items_are_not_carried_forever():
    prev = compare(result([finding("s:1")], at="t1"), None)
    mid = compare(result([], at="t2"), prev)
    assert by_fp(mid)["s:1"]["change"] == "resolved"
    last = compare(result([], at="t3"), mid)
    assert last["findings"] == []


def test_registry_finding_not_resolved_when_registry_unused(tmp_path):
    """PR #21 리뷰: 재검사에서 레지스트리 접속이 막혀 우리 규칙만 돌았으면, 레지스트리 규칙 결과는 '해결'이 아니라 '확인 불가'."""
    (tmp_path / "a.js").write_text("x", encoding="utf-8")
    reg = finding("s:reg", rule_id="javascript.jwt.security.hardcoded-jwt-secret")
    ours = finding("s:ours")
    prev = compare(result([reg, ours], at="t1", registry_used=True), None)

    offline = by_fp(compare(result([], at="t2", registry_used=False), prev, tmp_path))
    assert (offline["s:reg"]["change"], offline["s:reg"]["status"]) == ("unverifiable", OUT_OF_SCOPE)
    assert (offline["s:ours"]["change"], offline["s:ours"]["status"]) == ("resolved", CODE_RESOLVED)

    online = by_fp(compare(result([], at="t2", registry_used=True), prev, tmp_path))
    assert online["s:reg"]["status"] == CODE_RESOLVED
