"""보안엔진(#15) LLM 입력 꾸러미의 항목(items[]) → FindingInput.

엔진 규격: security_engine/llm_input.py `_item()` (llm_input_version 1.0)
    {"id": "semgrep:...", "kind": "code", "status": "code_issue", "change": "new", "severity": "unknown",
     "title", "what", "where": "app/a.js:6-8", "code": "줄 번호가 붙은 코드", "rule_id", "cwe": [...],
     "fix_hint": {...}, "flags": [{"flag", "note"}], "references": [...]}

의존성 취약점은 같은 패키지(생태계, 이름, lockfile)끼리 묶어 한 번만 설명합니다(#27). 같은 패키지의 취약점은
대부분 업그레이드 한 번으로 함께 고쳐지고, 엔진도 패키지 단위로 목표 버전을 계산해 줍니다.
"""

import re

from app.llm.pipeline import skip_reason
from app.llm.schemas import FindingInput, FindingRefs, FixHint

_WHERE = re.compile(r"^(?P<file>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")
_CVE = re.compile(r"^CVE-\d{4}-\d+$", re.IGNORECASE)
# 엔진(security_engine/models.py SEVERITIES)과 같은 순서. 앞일수록 위험합니다
_SEVERITY_ORDER = ("critical", "high", "medium", "low", "info", "unknown")
_STATUS_ORDER = ("code_issue", "runtime_check_needed", "out_of_scope", "code_resolved")
_CHANGE_ORDER = ("new", "persisting", "unverifiable", "resolved")
# 묶음 설명(what)에 적을 취약점 수. 나머지는 개수만 적습니다
_MAX_LISTED = 15
# FindingInput.what 한도(2,000자). 넘으면 묶음 전체가 검증에 실패하므로 여기서 맞춥니다 (#83)
_WHAT_LIMIT = FindingInput.model_fields["what"].metadata[0].max_length
# 묶음 목록 한 줄에 쓰는 제목 길이. 긴 설명 하나가 다른 항목을 밀어내지 않게 합니다
_LISTED_TITLE = 160


def from_engine_item(item: dict) -> FindingInput:
    file_path, start, end = _parse_where(item.get("where") or "")
    hint = FixHint.model_validate(item["fix_hint"]) if item.get("fix_hint") else None
    rule_id = item["rule_id"]
    return FindingInput(
        fingerprint=item["id"],
        tool=item["id"].split(":", 1)[0] if ":" in item["id"] else "unknown",
        category=item["kind"],
        rule_id=rule_id,
        title=item["title"],
        severity=item["severity"],
        file_path=file_path,
        start_line=start,
        end_line=end,
        package_name=hint.package if hint else None,
        package_ecosystem=hint.ecosystem if hint else None,
        installed_version=hint.current_version if hint else None,
        fixed_version=hint.target_version if hint else None,
        refs=FindingRefs(
            cve=[rule_id] if _CVE.match(rule_id) else [],
            cwe=item.get("cwe") or [],
            urls=item.get("references") or [],
        ),
        snippet=item.get("code") or None,
        what=item.get("what") or None,
        flags=item.get("flags") or [],
        fix_hint=hint,
        status=item.get("status"),
        change=item.get("change"),
    )


def from_engine_payload(payload: dict, *, group_dependencies: bool = True) -> list[FindingInput]:
    """엔진 꾸러미 → FindingInput 목록. 의존성은 기본으로 패키지 단위로 묶습니다.

    건너뛸 항목(코드에서 해결됨 등)은 묶지 않고 그대로 둡니다. 결과에서 각자 skipped 로 나옵니다.
    """
    findings = [from_engine_item(item) for item in payload.get("items", [])]
    if not group_dependencies:
        return findings

    upgrades = {
        (u.get("ecosystem"), u.get("name"), u.get("lockfile")): u for u in payload.get("dependency_upgrades", [])
    }
    groups: dict[tuple, list[FindingInput]] = {}
    result: list[FindingInput] = []
    for finding in findings:
        if finding.category == "dependency" and finding.package_name and not skip_reason(finding):
            key = (finding.package_ecosystem, finding.package_name, finding.file_path)
            if key not in groups:
                groups[key] = []
                result.append(finding)  # 묶음이 들어갈 자리 (원래 순서 = 엔진의 우선순위 유지)
            groups[key].append(finding)
        else:
            result.append(finding)

    by_first = {members[0].fingerprint: members for members in groups.values()}
    return [
        _package_finding(by_first[f.fingerprint], upgrades.get(_key(f))) if f.fingerprint in by_first else f
        for f in result
    ]


def _key(f: FindingInput) -> tuple:
    return (f.package_ecosystem, f.package_name, f.file_path)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _group_what(members: list[FindingInput]) -> str:
    """같은 패키지 취약점 목록을 what 한도 안에 씁니다 (#83).

    설명이 길어 다 못 쓰면 앞에서부터 들어가는 만큼만 적고 남은 개수를 밝힙니다.
    CVE·원본 항목 연결은 refs.cve와 covers에 그대로 남아 있으므로 목록을 줄여도 잃지 않습니다.
    """
    head = f"같은 패키지의 취약점 {len(members)}건:"
    lines: list[str] = []
    used = len(head)
    for m in members[:_MAX_LISTED]:
        line = f"- {m.rule_id} ({m.severity}): {_clip(m.title, _LISTED_TITLE)}"
        rest = len(members) - len(lines) - 1
        # 이 줄을 넣고도 '외 N건' 줄이 들어갈 자리가 남아야 넣습니다
        tail = len(f"\n- 외 {rest}건 (설명이 길어 생략, 전체는 CVE·원본 항목 참고)") if rest else 0
        if used + 1 + len(line) + tail > _WHAT_LIMIT:
            break
        lines.append(line)
        used += 1 + len(line)
    rest = len(members) - len(lines)
    if rest:
        reason = " (설명이 길어 생략, 전체는 CVE·원본 항목 참고)" if len(lines) < min(len(members), _MAX_LISTED) else ""
        lines.append(f"- 외 {rest}건{reason}")
    return _clip("\n".join([head, *lines]), _WHAT_LIMIT)


def _package_finding(members: list[FindingInput], upgrade: dict | None) -> FindingInput:
    first = members[0]
    if len(members) == 1:
        return first

    target = (upgrade or {}).get("target_version") or next((m.fixed_version for m in members if m.fixed_version), None)
    unfixable = [m for m in members if not m.fixed_version]
    hint = first.fix_hint or FixHint()
    fixed_count = (upgrade or {}).get("fix_count", len(members) - len(unfixable))
    note = f"{first.package_name}을(를) {first.installed_version} → {target} 이상으로 올리면 {fixed_count}건이 함께 해결됩니다"
    if unfixable:
        note += f". 고친 버전이 없는 {len(unfixable)}건은 다른 패키지로 바꾸거나 취약한 기능을 쓰지 않도록 따로 대처해야 합니다"

    return FindingInput(
        fingerprint=f"pkg:{first.package_ecosystem}:{first.package_name}:{first.file_path}"[:200],
        tool=first.tool,
        category="dependency",
        rule_id=f"upgrade:{first.package_name}"[:200],
        title=f"{first.package_name} {first.installed_version}: 취약점 {len(members)}건"[:500],
        severity=min((m.severity for m in members), key=_SEVERITY_ORDER.index),
        file_path=first.file_path,
        package_name=first.package_name,
        package_ecosystem=first.package_ecosystem,
        installed_version=first.installed_version,
        fixed_version=target,
        refs=FindingRefs(
            cve=sorted({c for m in members for c in m.refs.cve})[:30],
            cwe=sorted({c for m in members for c in m.refs.cwe})[:20],
            urls=[u for m in members for u in m.refs.urls][:3],
        ),
        snippet=first.snippet,
        what=_group_what(members),
        flags=list({f.flag: f for m in members for f in m.flags}.values())[:10],
        fix_hint=hint.model_copy(update={"target_version": target, "text": note, "command": _command(hint, target)}),
        status=min((m.status for m in members if m.status), key=_STATUS_ORDER.index, default=None),
        change=min((m.change for m in members if m.change), key=_CHANGE_ORDER.index, default=None),
        covers=[m.fingerprint for m in members],
    )


def _command(hint: FixHint, target: str | None) -> str | None:
    # 엔진은 패키지 단위 목표 버전으로 명령을 만들어 줍니다. 버전이 다르면 명령 속 버전만 바꿉니다
    if not hint.command or not target or not hint.target_version or hint.target_version == target:
        return hint.command
    return hint.command.replace(hint.target_version, target)


def _parse_where(where: str) -> tuple[str | None, int | None, int | None]:
    if not where:
        return None, None, None
    m = _WHERE.match(where)
    if not m:
        return where, None, None  # 의존성 항목은 "package-lock.json" 처럼 파일만 옵니다
    start = int(m["start"])
    end = int(m["end"]) if m["end"] else start
    return m["file"], start, end
