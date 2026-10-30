"""보안엔진(#15) LLM 입력 꾸러미의 항목(items[]) → FindingInput.

엔진 규격: security_engine/llm_input.py `_item()` (llm_input_version 1.0)
    {"id": "semgrep:...", "kind": "code", "status": "code_issue", "change": "new", "severity": "unknown",
     "title", "what", "where": "app/a.js:6-8", "code": "줄 번호가 붙은 코드", "rule_id", "cwe": [...],
     "fix_hint": {...}, "flags": [{"flag", "note"}], "references": [...]}
"""

import re

from app.llm.schemas import FindingInput, FindingRefs, FixHint

_WHERE = re.compile(r"^(?P<file>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")
_CVE = re.compile(r"^CVE-\d{4}-\d+$", re.IGNORECASE)


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


def from_engine_payload(payload: dict) -> list[FindingInput]:
    return [from_engine_item(item) for item in payload.get("items", [])]


def _parse_where(where: str) -> tuple[str | None, int | None, int | None]:
    if not where:
        return None, None, None
    m = _WHERE.match(where)
    if not m:
        return where, None, None  # 의존성 항목은 "package-lock.json" 처럼 파일만 옵니다
    start = int(m["start"])
    end = int(m["end"]) if m["end"] else start
    return m["file"], start, end
