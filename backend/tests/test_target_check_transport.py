"""#129: summary truncation must not erase target-version warnings before reports/LLM."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.llm.engine_adapter import from_engine_payload
from app.llm.prompts import render_finding
from app.reports.plain import build_plain_report
from app.reports.schemas import PlainReportRequest


@pytest.mark.parametrize("limit", [0, 10])
@pytest.mark.parametrize("status", ["vulnerable", "unknown", "clean"])
def test_omitted_upgrade_keeps_check_through_report_and_prompt(monkeypatch, limit, status):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from security_engine import osv_recheck
    from security_engine.engine import _dependency_upgrades
    from security_engine.llm_input import build_llm_input

    findings = []
    for package in range(11):
        for index in range(2):
            findings.append({
                "tool":"osv", "status":"code_issue", "fingerprint":f"osv:{package}-{index}",
                "category":"dependency", "severity":"high", "rule_id":f"GHSA-example-{index}",
                "title":"dependency issue", "message":"upgrade needed", "cwe":[], "flags":[],
                "references":[], "location":{"file":"package-lock.json"}, "evidence":{},
                "package":{"ecosystem":"npm", "name":f"lib-{package:02}", "version":"1.0.0", "fixed_versions":["1.2.0"]},
                "remediation":{"kind":"upgrade_dependency", "target_version":"1.2.0"},
            })

    def query(keys):
        if status == "unknown":
            raise OSError("test network failure")
        return [["GHSA-still-vulnerable"] if status == "vulnerable" else [] for _ in keys]

    osv_recheck.clear_cache()
    try:
        osv_recheck.recheck(findings, query=query)
    finally:
        osv_recheck.clear_cache()
    payload = build_llm_input({"findings":findings, "dependency_upgrades":_dependency_upgrades(findings)},
                              max_upgrades=limit)
    assert len(payload["items"]) == 22
    assert len(payload["dependency_upgrades"]) == limit
    group = next(f for f in from_engine_payload(payload) if f.package_name == "lib-10")
    assert group.fix_hint.target_check == status
    assert group.fix_hint.target_version == "1.2.0"
    assert group.fix_hint.command == "npm install lib-10@1.2.0"
    prompt = render_finding(group)
    assert f'"target_check": "{status}"' in prompt
    if status != "clean":
        expected = "GHSA-still-vulnerable" if status == "vulnerable" else "확인하지 못함"
        assert expected in group.fix_hint.text
        assert expected in prompt
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        request = PlainReportRequest(scan={"site_name":"test", "scanned_at":now}, findings=[group])
        report = build_plain_report(request, now)
        assert expected in report.model_dump_json()


@pytest.mark.parametrize("second_target,second_status,expected", [
    ("4.17.21", "vulnerable", "vulnerable"),
    ("4.17.21", "unknown", "unknown"),
    ("4.17.19", "vulnerable", "clean"),
])
def test_fallback_uses_conservative_status_for_the_selected_version(second_target, second_status, expected):
    from tests.test_dependency_grouping import dep

    first = dep("a", "lib", "CVE-2026-1001", "high", "4.17.21")
    second = dep("b", "lib", "CVE-2026-1002", "high", second_target)
    first["fix_hint"]["target_check"] = "clean"
    second["fix_hint"].update(target_check=second_status, text=None)
    [group] = from_engine_payload({"items":[first, second]})
    assert group.fix_hint.target_version == "4.17.21"
    assert group.fix_hint.target_check == expected
    if expected != "clean":
        assert "취약점" in group.fix_hint.text  # Missing note still gets an explicit warning.
