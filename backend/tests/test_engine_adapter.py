"""보안엔진(#15) LLM 입력 꾸러미와의 계약 테스트.

fixtures/engine_llm_input.json 은 PR #21 의 security_engine/schema/example_llm_input.json 사본입니다.
엔진 규격이 바뀌면 이 사본도 함께 바꾸고 테스트를 돌립니다.
"""

import json

import pytest

from app.llm.engine_adapter import from_engine_item, from_engine_payload
from app.llm.pipeline import Explainer, skip_reason
from tests.conftest import FIXTURES, blue_draft

pytestmark = pytest.mark.anyio


@pytest.fixture
def engine_payload() -> dict:
    return json.loads((FIXTURES / "engine_llm_input.json").read_text(encoding="utf-8"))


def test_every_engine_item_converts(engine_payload):
    findings = from_engine_payload(engine_payload)

    assert len(findings) == len(engine_payload["items"])
    by_tool = {f.tool: f for f in findings}
    assert set(by_tool) == {"semgrep", "gitleaks", "osv"}


def test_code_item_location_and_rule(engine_payload):
    finding = from_engine_item(engine_payload["items"][0])

    assert (finding.file_path, finding.start_line, finding.end_line) == ("api/app.py", 3, 3)
    assert finding.category == "code"
    assert finding.refs.cwe == ["CWE-89"]
    assert finding.snippet.startswith("    1 | import")
    assert finding.what.startswith("SQL 문을")
    assert finding.status == "code_issue" and finding.change == "persisting"


def test_dependency_item_carries_upgrade_hint(engine_payload):
    item = next(i for i in engine_payload["items"] if i["kind"] == "dependency")

    finding = from_engine_item(item)

    assert finding.file_path == "package-lock.json" and finding.start_line is None
    assert (finding.package_name, finding.installed_version, finding.fixed_version) == ("lodash", "4.17.15", "4.17.21")
    assert finding.fix_hint.command == "npm install lodash@4.17.21"
    assert finding.refs.cve == ["CVE-2021-23337"]


def test_flags_are_kept(engine_payload):
    item = next(i for i in engine_payload["items"] if i["kind"] == "secret")

    finding = from_engine_item(item)

    assert [f.flag for f in finding.flags] == ["rotate_secret", "file_removed"]
    assert "새로 발급" in finding.flags[0].note


def test_unknown_severity_and_line_range():
    item = {
        "id": "osv:abc",
        "kind": "code",
        "severity": "unknown",
        "title": "심각도 정보가 없는 결과",
        "where": "app/a.js:6-8",
        "rule_id": "vibe-coding/x",
    }

    finding = from_engine_item(item)

    assert finding.severity == "unknown"
    assert (finding.start_line, finding.end_line) == (6, 8)


def test_only_code_resolved_items_are_skipped(engine_payload):
    findings = {f.fingerprint: f for f in from_engine_payload(engine_payload)}
    reasons = {fp: skip_reason(f) for fp, f in findings.items()}

    skipped = {fp for fp, r in reasons.items() if r}
    assert skipped == {fp for fp, f in findings.items() if f.status == "code_resolved"}
    # 코드에서는 지웠지만 키 재발급이 남은 비밀값은 설명합니다
    secret = next(f for f in findings.values() if f.category == "secret")
    assert secret.change == "resolved" and skip_reason(secret) is None


async def test_engine_payload_end_to_end(fake_vllm, engine_payload):
    findings = from_engine_payload(engine_payload)
    to_explain = [f for f in findings if not skip_reason(f)]
    fake_vllm.queue("BlueDraft", *[blue_draft() for _ in to_explain])

    results = await Explainer(fake_vllm.client()).explain_many(findings, "blue")

    assert len(fake_vllm.calls("BlueDraft")) == len(to_explain) == 3
    assert [r.status for r in results].count("skipped") == 2
    assert all(r.reason for r in results if r.status == "skipped")
    assert all(r.status == "done" for r in results if r.status != "skipped")
