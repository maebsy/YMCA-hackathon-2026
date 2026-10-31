"""#109: 추천 업그레이드 버전을 OSV에 다시 조회해 남은 취약점을 확인한다. 네트워크는 쓰지 않는다(가짜 조회)."""
import io
import json

import pytest

from security_engine import osv_recheck
from security_engine.engine import _dependency_upgrades
from security_engine.llm_input import build_llm_input
from security_engine.models import ScanOptions


@pytest.fixture(autouse=True)
def _fresh_cache():
    osv_recheck.clear_cache()
    yield
    osv_recheck.clear_cache()


def dep(fp, target, name="lib", status="code_issue", eco="npm"):
    return {"tool": "osv", "status": status, "fingerprint": fp, "severity": "high", "category": "dependency",
            "rule_id": f"GHSA-{fp}", "title": f"{name} 1.0.0: 취약점", "message": "설명", "cwe": [], "flags": [],
            "references": [], "package": {"ecosystem": eco, "name": name, "version": "1.0.0", "fixed_versions": [target]},
            "location": {"file": "package-lock.json", "start_line": None, "end_line": None},
            "evidence": {"snippet": f"{name}@1.0.0", "context": None},
            "remediation": {"kind": "upgrade_dependency" if target else "no_fix_available",
                            "target_version": target, "autofix": None}}


class FakeOSV:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, keys):
        self.calls.append(list(keys))
        return [self.answers.get(k, []) for k in keys]


def test_recommended_version_with_remaining_vulns_is_vulnerable():
    """이슈 재현: 1.2.0을 추천했는데 1.2.0에도 다른 취약점이 있는 경우."""
    findings = [dep("a", "1.2.0"), dep("b", "1.1.0")]
    query = FakeOSV({("npm", "lib", "1.2.0"): ["GHSA-zzz", "CVE-2026-1"]})

    osv_recheck.recheck(findings, query=query)

    assert query.calls == [[("npm", "lib", "1.2.0"), ("npm", "lib", "1.1.0")]]  # 같은 (패키지, 버전)은 한 번만
    assert findings[0]["remediation"]["target_check"] == {
        "status": "vulnerable", "remaining": ["GHSA-zzz", "CVE-2026-1"], "remaining_count": 2, "reason": None}
    assert findings[1]["remediation"]["target_check"]["status"] == "clean"


def test_query_failure_is_unknown_not_clean():
    def broken(keys):
        raise OSError("network down")

    findings = [dep("a", "1.2.0")]
    osv_recheck.recheck(findings, query=broken)
    check = findings[0]["remediation"]["target_check"]
    assert check["status"] == "unknown" and check["remaining_count"] is None and check["reason"]


def test_wrong_answer_count_is_unknown():
    findings = [dep("a", "1.2.0"), dep("b", "2.0.0", name="other")]
    osv_recheck.recheck(findings, query=lambda keys: [[]])
    assert {f["remediation"]["target_check"]["status"] for f in findings} == {"unknown"}


def test_offline_or_disabled_never_queries():
    for opts in (ScanOptions(osv_offline=True), ScanOptions(osv_recheck=False)):
        findings = [dep("a", "1.2.0")]
        query = FakeOSV({})
        osv_recheck.recheck(findings, opts, query=query)
        assert query.calls == []
        assert findings[0]["remediation"]["target_check"]["status"] == "unknown"


def test_skips_resolved_and_unfixable_findings():
    findings = [dep("a", None), dep("b", "1.2.0", status="code_resolved")]
    query = FakeOSV({})
    osv_recheck.recheck(findings, query=query)
    assert query.calls == []
    assert all("target_check" not in f["remediation"] for f in findings)


def test_cache_reuses_until_ttl():
    clock = [1000.0]
    query = FakeOSV({("npm", "lib", "1.2.0"): ["GHSA-zzz"]})
    for _ in range(2):
        osv_recheck.recheck([dep("a", "1.2.0")], query=query, now=lambda: clock[0])
    assert len(query.calls) == 1
    clock[0] += osv_recheck.CACHE_TTL_SEC + 1
    findings = [dep("a", "1.2.0")]
    osv_recheck.recheck(findings, query=query, now=lambda: clock[0])
    assert len(query.calls) == 2 and findings[0]["remediation"]["target_check"]["status"] == "vulnerable"


def test_failures_are_not_cached():
    calls = []

    def flaky(keys):
        calls.append(keys)
        if len(calls) == 1:
            raise TimeoutError
        return [[] for _ in keys]

    for _ in range(2):
        findings = [dep("a", "1.2.0")]
        osv_recheck.recheck(findings, query=flaky)
    assert len(calls) == 2 and findings[0]["remediation"]["target_check"]["status"] == "clean"


def test_query_count_is_capped(monkeypatch):
    monkeypatch.setattr(osv_recheck, "MAX_QUERIES", 2)
    findings = [dep(str(i), f"1.{i}.0") for i in range(1, 4)]
    query = FakeOSV({})
    osv_recheck.recheck(findings, query=query)
    assert len(query.calls[0]) == 2
    assert [f["remediation"]["target_check"]["status"] for f in findings] == ["clean", "clean", "unknown"]


def test_remaining_list_is_capped_but_count_is_exact():
    ids = [f"GHSA-{i:04d}" for i in range(30)]
    findings = [dep("a", "1.2.0")]
    osv_recheck.recheck(findings, query=FakeOSV({("npm", "lib", "1.2.0"): ids}))
    check = findings[0]["remediation"]["target_check"]
    assert check["remaining_count"] == 30 and len(check["remaining"]) == osv_recheck.MAX_LISTED


def _fake_urlopen(payload):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        body = json.loads(request.data)
        assert request.full_url == osv_recheck.QUERYBATCH_URL and timeout == osv_recheck.TIMEOUT_SEC
        assert body["queries"][0] == {"package": {"ecosystem": "npm", "name": "lib"}, "version": "1.2.0"}
        return Response(json.dumps(payload).encode())
    return urlopen


def test_http_query_reads_querybatch(monkeypatch):
    monkeypatch.setattr(osv_recheck.urllib.request, "urlopen",
                        _fake_urlopen({"results": [{"vulns": [{"id": "B"}, {"id": "A"}, {"id": "A"}]}]}))
    assert osv_recheck._http_query([("npm", "lib", "1.2.0")]) == [["A", "B"]]


@pytest.mark.parametrize("payload", [{"results": [{"vulns": [{"id": "A"}], "next_page_token": "x"}]}, {"results": []}, {}])
def test_http_query_rejects_partial_answers(monkeypatch, payload):
    """잘린 결과·개수 불일치는 '안전'이 아니라 실패로 본다."""
    monkeypatch.setattr(osv_recheck.urllib.request, "urlopen", _fake_urlopen(payload))
    with pytest.raises(ValueError):
        osv_recheck._http_query([("npm", "lib", "1.2.0")])


def _scan_result(findings):
    return {"scan_id": "s", "scanned_at": "2026-11-01T00:00:00Z", "target": {}, "status": "complete",
            "comparison": None, "summary": {}, "coverage": {}, "suppressions": [],
            "dependency_upgrades": _dependency_upgrades(findings), "findings": findings}


def test_plan_uses_check_of_its_target_and_hint_warns():
    findings = [dep("a", "1.1.0"), dep("b", "1.2.0")]
    osv_recheck.recheck(findings, query=FakeOSV({("npm", "lib", "1.2.0"): ["GHSA-left"]}))
    result = _scan_result(findings)

    [plan] = result["dependency_upgrades"]
    assert plan["target_version"] == "1.2.0" and plan["target_check"]["remaining"] == ["GHSA-left"]

    payload = build_llm_input(result)
    assert payload["dependency_upgrades"][0]["target_check"]["status"] == "vulnerable"
    for item in payload["items"]:  # 묶음 목표(1.2.0) 기준으로, 1.1.0을 추천받은 항목에도 같은 경고
        hint = item["fix_hint"]
        assert hint["target_version"] == "1.2.0" and hint["target_check"] == "vulnerable"
        assert "1.2.0에도 알려진 취약점 1건(GHSA-left)" in hint["text"]


def test_hint_for_clean_and_unknown():
    clean = [dep("a", "1.2.0")]
    osv_recheck.recheck(clean, query=FakeOSV({}))
    [item] = build_llm_input(_scan_result(clean))["items"]
    assert item["fix_hint"]["target_check"] == "clean" and "남아" not in item["fix_hint"]["text"]

    offline = [dep("a", "1.2.0")]
    osv_recheck.recheck(offline, ScanOptions(osv_offline=True))
    [item] = build_llm_input(_scan_result(offline))["items"]
    assert item["fix_hint"]["target_check"] == "unknown" and "확인하지 못함" in item["fix_hint"]["text"]


def test_schema_accepts_target_check():
    jsonschema = pytest.importorskip("jsonschema")
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[2] / "security_engine/schema/scan_result.schema.json").read_text())
    findings = [dep("a", "1.2.0")]
    osv_recheck.recheck(findings, query=FakeOSV({("npm", "lib", "1.2.0"): ["X"]}))
    check = findings[0]["remediation"]["target_check"]
    only = {"$schema": schema.get("$schema"), "$defs": schema["$defs"], "$ref": "#/$defs/target_check"}
    jsonschema.validate(check, only)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**check, "status": "safe"}, only)


def test_real_scan_flow_fills_target_check(monkeypatch, tmp_path):
    """회귀: status 는 compare() 가 정하므로, 그 전에 재조회하면 모든 finding 이 건너뛰어져 target_check 가 비었습니다.
    엔진의 실제 scan() 흐름에서 finding 과 패키지 묶음 목표 모두 target_check 가 채워져야 합니다."""
    from security_engine import engine
    from security_engine.runners.base import ToolRun

    finding = {
        "fingerprint": "osv:lodash", "tool": "osv", "category": "dependency", "rule_id": "CVE-2019-10744",
        "title": "lodash", "severity": "critical", "location": {"file": "package-lock.json"},
        "package": {"ecosystem": "npm", "name": "lodash", "version": "4.17.11", "fixed_versions": ["4.17.12"]},
        "remediation": {"kind": "upgrade", "target_version": "4.17.12"}, "flags": [],
    }

    def fake_run(tool, root, opts):
        run = ToolRun(tool, engine.TOOL_OK if tool == "osv" else engine.TOOL_SKIPPED, "")
        if tool == "osv":
            run.findings = [dict(finding)]
        return run

    asked = []

    def fake_query(keys):
        asked.extend(keys)
        return [["GHSA-left-over-0001"] for _ in keys]

    monkeypatch.setattr(engine, "_run_tool", fake_run)
    monkeypatch.setattr(osv_recheck, "_http_query", fake_query)
    osv_recheck.clear_cache()

    result = engine.scan(tmp_path)

    assert asked == [("npm", "lodash", "4.17.12")]
    [f] = [f for f in result["findings"] if f["tool"] == "osv"]
    assert f["status"] == "code_issue"
    assert f["remediation"]["target_check"]["status"] == "vulnerable"
    [plan] = result["dependency_upgrades"]
    assert plan["target_check"]["status"] == "vulnerable"
