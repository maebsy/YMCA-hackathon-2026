"""의존성 취약점을 패키지 단위로 묶어 한 번만 설명하기 (#27)."""

import pytest

from app.llm.engine_adapter import from_engine_payload
from app.llm.pipeline import Explainer
from app.llm.prompts import render_finding
from tests.conftest import blue_draft

pytestmark = pytest.mark.anyio


def dep(fp: str, package: str, cve: str, severity: str, target: str | None, status: str = "code_issue") -> dict:
    hint = {
        "kind": "upgrade_dependency",
        "package": package,
        "ecosystem": "npm",
        "current_version": "4.17.15",
        "target_version": target,
        "lockfile": "package-lock.json",
        "command": f"npm install {package}@{target}" if target else None,
        "text": "버전을 올리세요",
    }
    return {
        "id": f"osv:{fp}",
        "kind": "dependency",
        "status": status,
        "change": "persisting",
        "severity": severity,
        "title": f"{package}: {cve}",
        "what": f"{cve} 설명",
        "where": "package-lock.json",
        "code": f"{package}@4.17.15",
        "rule_id": cve,
        "cwe": ["CWE-1321"],
        "fix_hint": hint,
        "flags": [],
        "references": [f"https://nvd.nist.gov/vuln/detail/{cve}"],
    }


@pytest.fixture
def payload() -> dict:
    return {
        "items": [
            dep("a1", "lodash", "CVE-2021-23337", "high", "4.17.21"),
            {
                "id": "semgrep:x1",
                "kind": "code",
                "status": "code_issue",
                "change": "new",
                "severity": "high",
                "title": "SQL 주입",
                "where": "api/a.js:3",
                "rule_id": "vibe/sql",
            },
            dep("a2", "lodash", "CVE-2020-8203", "critical", "4.17.19"),
            dep("a3", "lodash", "CVE-2019-10744", "medium", None),
            dep("a4", "lodash", "CVE-2018-3721", "low", "4.17.5", status="code_resolved"),
            dep("b1", "axios", "CVE-2023-45857", "medium", "1.6.0"),
        ],
        # 엔진은 상위 10개 패키지만 넣습니다. 여기엔 lodash 만 있다고 봅니다
        "dependency_upgrades": [
            {
                "ecosystem": "npm",
                "name": "lodash",
                "current_version": "4.17.15",
                "target_version": "4.17.21",
                "lockfile": "package-lock.json",
                "max_severity": "critical",
                "fix_count": 2,
                "unfixable_count": 1,
            }
        ],
    }


def test_same_package_is_explained_once(payload):
    findings = from_engine_payload(payload)

    fingerprints = [f.fingerprint for f in findings]
    # lodash 열린 3건 → 1건, 코드 1건, 해결된 lodash 1건(따로 건너뜀), axios 1건(혼자라 그대로)
    assert fingerprints == ["pkg:npm:lodash:package-lock.json", "semgrep:x1", "osv:a4", "osv:b1"]
    lodash = findings[0]
    assert lodash.covers == ["osv:a1", "osv:a2", "osv:a3"]
    assert lodash.severity == "critical"
    assert lodash.refs.cve == ["CVE-2019-10744", "CVE-2020-8203", "CVE-2021-23337"]


def test_package_uses_engine_target_and_command(payload):
    lodash = from_engine_payload(payload)[0]

    assert lodash.fixed_version == "4.17.21"
    assert lodash.fix_hint.command == "npm install lodash@4.17.21"
    assert "2건이 함께 해결" in lodash.fix_hint.text
    assert "고친 버전이 없는 1건" in lodash.fix_hint.text


def test_package_without_upgrade_entry_uses_member_versions(payload):
    payload["dependency_upgrades"] = []

    lodash = from_engine_payload(payload)[0]

    assert lodash.fixed_version == "4.17.21"  # 묶인 항목 중 첫 고친 버전 (엔진이 패키지 단위 목표로 넣어 줌)
    assert lodash.covers == ["osv:a1", "osv:a2", "osv:a3"]


def test_grouping_can_be_turned_off(payload):
    findings = from_engine_payload(payload, group_dependencies=False)

    assert len(findings) == len(payload["items"])
    assert all(not f.covers for f in findings)


def test_grouped_finding_lists_members_for_the_model(payload):
    rendered = render_finding(from_engine_payload(payload)[0])

    assert "같은 패키지의 취약점 3건" in rendered
    assert "CVE-2020-8203" in rendered
    assert "covers" not in rendered  # fingerprint 목록은 모델에 넘기지 않음


def test_many_members_are_summarized(payload):
    payload["items"] = [dep(f"m{i}", "lodash", f"CVE-2021-{1000 + i}", "low", "4.17.21") for i in range(20)]

    lodash = from_engine_payload(payload)[0]

    assert len(lodash.covers) == 20
    assert "외 5건" in lodash.what


async def test_one_llm_call_per_package(fake_vllm, payload):
    findings = from_engine_payload(payload)
    fake_vllm.queue("BlueDraft", blue_draft(), blue_draft(), blue_draft())

    results = await Explainer(fake_vllm.client()).explain_many(findings, "blue")

    # 그룹 안 했으면 5번(열린 lodash 3 + 코드 1 + axios 1) → 묶어서 3번
    assert len(fake_vllm.calls("BlueDraft")) == 3
    lodash = next(r for r in results if r.fingerprint.startswith("pkg:"))
    assert lodash.status == "done" and lodash.covers == ["osv:a1", "osv:a2", "osv:a3"]
    assert next(r for r in results if r.fingerprint == "osv:a4").status == "skipped"


# ── #83: 긴 설명이 몰린 패키지도 묶음이 깨지지 않아야 합니다 ──
def long_payload(count: int, title_len: int) -> dict:
    items = []
    for i in range(count):
        item = dep(f"l{i}", "big-lib", f"CVE-2026-{2000 + i}", "high", "9.9.9")
        item["title"] = (f"big-lib: CVE-2026-{2000 + i} " + "아주 긴 취약점 설명 " * 60)[:title_len]  # 개별 제목은 한도(500자) 안
        items.append(item)
    return {"items": items, "dependency_upgrades": []}


@pytest.mark.parametrize(("count", "title_len"), [(12, 400), (15, 490), (40, 490), (3, 490)])
def test_long_member_titles_keep_the_package_group(count, title_len):
    findings = from_engine_payload(long_payload(count, title_len))

    [group] = findings  # 실패하거나 개별 항목으로 풀리지 않고 한 묶음
    assert group.fingerprint.startswith("pkg:npm:big-lib:")
    assert len(group.what) <= 2000
    assert group.what.startswith(f"같은 패키지의 취약점 {count}건:")
    # 목록을 줄여도 원본 연결과 CVE는 모두 남습니다
    assert len(group.covers) == count
    assert len(group.refs.cve) == min(count, 30)
    listed = group.what.count("\n- CVE-")
    if listed < count:
        assert f"외 {count - listed}건" in group.what


def test_long_titles_say_why_members_were_left_out():
    group = from_engine_payload(long_payload(12, 400))[0]

    assert "설명이 길어 생략" in group.what
    assert "CVE-2026-2000" in group.what  # 앞 항목은 그대로 보입니다


def test_short_titles_are_listed_as_before(payload):
    # 기존 짧은 설명 묶음의 문장은 바뀌지 않습니다 (최대 15건 나열 + '외 N건')
    payload["items"] = [dep(f"m{i}", "lodash", f"CVE-2021-{1000 + i}", "low", "4.17.21") for i in range(20)]
    lodash = from_engine_payload(payload)[0]

    assert lodash.what.count("\n- CVE-") == 15
    assert lodash.what.endswith("\n- 외 5건")
