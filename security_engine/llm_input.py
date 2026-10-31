"""보안엔진 결과 → LLM 입력으로 넘길 꾸러미 (보안엔진과 LLM 담당 사이의 약속).

LLM은 긴 원본 JSON을 다 읽을 필요가 없다. 여기서
  - 사용자가 지금 해야 할 일 순서로 정렬하고 (열린 문제 → 키 재발급 → 해결 확인)
  - 문제마다 '무엇 / 어디 / 문제 코드 / 고치는 힌트 / 주의 표시'만 남기고
  - 비밀값이 절대 섞이지 않게 한 번 더 확인한 뒤
넘겨준다.

    from security_engine import scan, build_llm_input, render_llm_text
    result = scan("C:/code/my-site")
    payload = build_llm_input(result)          # dict (구조화) → LLM에 JSON으로 넣거나
    text = render_llm_text(payload)            # str (사람이 읽는 형태) → 프롬프트에 바로 붙이기

CLI:  python -m security_engine llm-input result.json -o llm_input.json [--text]
"""
from __future__ import annotations

import re

from .models import (
    CODE_ISSUE,
    CODE_RESOLVED,
    FLAG_FILE_REMOVED,
    FLAG_IGNORED_BY_CONFIG,
    FLAG_LIKELY_PUBLIC_KEY,
    FLAG_LOCKFILE_REMOVED,
    FLAG_ROTATE_SECRET,
    FLAG_SUPPRESSED_COMMENT,
    FLAG_THIRD_PARTY,
    OUT_OF_SCOPE,
    RUNTIME_CHECK,
    SEVERITY_RANK,
    STATUS_LABEL_KO,
    TOOL_OK,
)
from .normalize import version_key

LLM_INPUT_VERSION = "1.0"

# LLM이 그대로 활용할 수 있는 주의 표시 설명
FLAG_NOTE_KO = {
    FLAG_SUPPRESSED_COMMENT: "숨김 주석(nosemgrep, gitleaks:allow)으로 경고만 가리려 했음. 주석을 지우고 실제로 고쳐야 함",
    FLAG_IGNORED_BY_CONFIG: "설정 파일(osv-scanner.toml)로 이 취약점을 무시하도록 해 둠. 무시가 아니라 업그레이드가 필요",
    FLAG_FILE_REMOVED: "파일 자체가 사라져서 해결로 보임. 기능을 지운 것인지, 다른 파일로 옮긴 것인지 확인 필요",
    FLAG_LOCKFILE_REMOVED: "lockfile이 사라져 외부 부품 검사를 못 함. lockfile을 다시 만들어 올려야 함",
    FLAG_ROTATE_SECRET: "코드에서 지우는 것만으로는 부족. 이미 노출된 키는 폐기하고 새로 발급해야 함",
    FLAG_LIKELY_PUBLIC_KEY: ("원래 공개용으로 만든 키로 보임(검색 전용 키, reCAPTCHA siteKey 등). 위험도 낮음. "
                             "같은 서비스의 비밀(관리자) 키가 아닌지만 확인"),
    FLAG_THIRD_PARTY: "외부 라이브러리 파일. 직접 고치기보다 라이브러리를 최신 버전으로 업데이트하거나 그대로 두어도 됨",
}

_UPGRADE_CMD = {
    "npm": "npm install {name}@{version}",
    "PyPI": 'pip install "{name}>={version}"',
    "RubyGems": "bundle update {name}",
    "Go": "go get {name}@v{version}",
    "crates.io": "cargo update -p {name} --precise {version}",
    "Packagist": "composer require {name}:^{version}",
    "Maven": "pom.xml/build.gradle에서 {name} 버전을 {version}으로 변경",
    "NuGet": "dotnet add package {name} --version {version}",
}

# 혹시 남아 있을지 모르는 비밀값 모양 (마지막 안전장치)
_SECRET_LIKE = re.compile(
    r"(sk[-_](live|test)?_?[A-Za-z0-9]{16,}|sk-(proj|ant|svcacct|admin)-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{35}|gh[pousr]_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9_]{40,}|xox[baprs]-[A-Za-z0-9\-]{10,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def _redact(text: str) -> str:
    return _SECRET_LIKE.sub(lambda m: m.group(0)[:4] + "********", text or "")


def _where(f: dict) -> str:
    loc = f.get("location") or {}
    if loc.get("start_line"):
        if loc.get("end_line") and loc["end_line"] != loc["start_line"]:
            return f"{loc['file']}:{loc['start_line']}-{loc['end_line']}"
        return f"{loc['file']}:{loc['start_line']}"
    return loc.get("file") or ""


def _code_block(f: dict, max_lines: int) -> str:
    """앞뒤 줄을 포함한 코드에 줄 번호를 붙인다. 문제 줄은 '>'로 표시."""
    ev = f.get("evidence") or {}
    ctx = ev.get("context")
    if not ctx:
        return _redact(ev.get("snippet") or "")
    loc = f.get("location") or {}
    s, e = loc.get("start_line") or 0, loc.get("end_line") or loc.get("start_line") or 0
    out = []
    for i, line in enumerate(ctx["lines"][:max_lines]):
        n = ctx["start_line"] + i
        mark = ">" if s <= n <= e else " "
        out.append(f"{mark}{n:>4} | {line[:200]}")
    return _redact("\n".join(out))


def _fix_hint(f: dict, pkg_targets: dict | None = None) -> dict:
    rem = f.get("remediation") or {}
    kind = rem.get("kind")
    hint = {"kind": kind}
    if f["tool"] == "osv" and f.get("package"):
        p = f["package"]
        # 이 취약점 하나만 고치는 최소 버전이 아니라, 같은 패키지의 문제를 한 번에 다 고치는 버전을 안내
        key = (p["ecosystem"], p["name"], (f.get("location") or {}).get("file"))
        tv = (pkg_targets or {}).get(key) or rem.get("target_version")
        hint.update({
            "package": p["name"], "ecosystem": p["ecosystem"],
            "current_version": p["version"], "target_version": tv,
            "lockfile": (f.get("location") or {}).get("file"),
        })
        if tv:
            tmpl = _UPGRADE_CMD.get(p["ecosystem"])
            hint["command"] = tmpl.format(name=p["name"], version=tv) if tmpl else None
            hint["text"] = f"{p['name']}을(를) {p['version']} → {tv} 이상으로 올리고 lockfile도 함께 커밋"
        elif p.get("fixed_versions"):
            listed = ", ".join(p["fixed_versions"][:5])
            now = version_key(p["version"], p["ecosystem"])
            keys = [version_key(v, p["ecosystem"]) for v in p["fixed_versions"]]
            if now is not None and all(k is not None for k in keys):
                # 모두 비교했는데 현재보다 높은 수정 버전이 없음: 고쳐졌다가 현재 버전에서 다시 생긴 경우 (#92)
                hint["text"] = (f"알려진 고친 버전({listed})이 모두 현재 버전 {p['version']}보다 낮거나 같음. 현재 버전에서 다시 생긴 "
                                "취약점일 수 있어 낮은 버전으로 내리지 말고, 더 높은 수정 버전이 나왔는지 확인하거나 우회 필요")
            else:
                # 고친 버전 후보는 있지만 이 생태계 규칙으로 현재 버전과 비교하지 못해 목표를 정하지 않음 (#92)
                hint["text"] = (f"고친 버전 후보({listed})는 있지만 현재 버전 {p['version']}과 순서를 확실히 비교하지 못해 "
                                "업그레이드 목표를 정하지 않았음. 패키지 관리자의 버전 규칙으로 현재보다 높은 수정 버전인지 직접 확인 필요")
        else:
            hint["text"] = "아직 고친 버전이 없음. 다른 패키지로 바꾸거나, 취약한 기능을 쓰지 않도록 우회 필요"
    elif f["tool"] == "gitleaks":
        hint["text"] = ("① 해당 서비스에서 이 키를 즉시 폐기·재발급 ② 코드에서 지우고 환경 변수(.env, 배포 설정)로 옮김 "
                        "③ .env는 .gitignore에 추가 ④ 깃 기록에도 남아 있으므로 키 재발급이 핵심")
    else:
        hint["text"] = "규칙 설명(what)에 적힌 방법으로 코드를 수정"
        if rem.get("autofix"):
            hint["autofix"] = rem["autofix"]
    return hint


def _shorten(text: str, limit: int) -> str:
    """마크다운 제목·빈 줄을 정리하고 limit 글자로 자른다 (OSV 설명은 영어 원문이 매우 길다)."""
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _priority(f: dict) -> tuple:
    status_order = {CODE_ISSUE: 0, RUNTIME_CHECK: 1, OUT_OF_SCOPE: 2, CODE_RESOLVED: 3}
    return (status_order.get(f["status"], 9), SEVERITY_RANK.get(f["severity"], 9),
            0 if f.get("change") == "new" else 1, _where(f))


def _item(f: dict, max_code_lines: int, pkg_targets: dict | None = None, max_what: int = 400) -> dict:
    return {
        "id": f["fingerprint"],
        "kind": f["category"],                       # dependency | code | secret
        "status": f["status"],
        "status_label": STATUS_LABEL_KO[f["status"]],
        "change": f.get("change"),
        "severity": f["severity"],
        "title": _redact(f["title"]),
        "what": _redact(_shorten(f.get("message") or "", max_what)),
        "where": _where(f),
        "code": _code_block(f, max_code_lines),
        "rule_id": f["rule_id"],
        "cwe": f.get("cwe", []),
        "fix_hint": _fix_hint(f, pkg_targets),
        "flags": [{"flag": x, "note": FLAG_NOTE_KO.get(x, "")} for x in f.get("flags", [])],
        "references": f.get("references", [])[:3],
    }


def build_llm_input(result: dict, *, max_items: int = 30, include_resolved: bool = True,
                    max_code_lines: int = 12, max_upgrades: int = 10, max_what: int = 400) -> dict:
    """scan() 결과 → LLM 입력 꾸러미.

    max_items: LLM에 넣을 최대 문제 수 (토큰 절약). 우선순위가 높은 것부터 자른다.
    include_resolved: 해결된 문제도 넣을지 (재검사 리포트에서 '잘 고쳤어요'를 말해 주려면 True)
    """
    findings = [f for f in result.get("findings", [])
                if include_resolved or f["status"] != CODE_RESOLVED]
    findings.sort(key=_priority)
    upgrades = result.get("dependency_upgrades", [])
    pkg_targets = {(u["ecosystem"], u["name"], u["lockfile"]): u["target_version"]
                   for u in upgrades if u.get("target_version")}
    items = [_item(f, max_code_lines, pkg_targets, max_what) for f in findings[:max_items]]

    not_checked = []
    for tool, c in (result.get("coverage") or {}).items():
        if c.get("status") != TOOL_OK and c.get("status") != "skipped":
            not_checked.append({"tool": tool, "category": c.get("category"), "reason": c.get("message", "")})

    payload = {
        "llm_input_version": LLM_INPUT_VERSION,
        "scan_id": result.get("scan_id"),
        "scanned_at": result.get("scanned_at"),
        "site": {"repo_url": (result.get("target") or {}).get("repo_url"),
                 "commit_sha": (result.get("target") or {}).get("commit_sha")},
        "scan_status": result.get("status"),
        "is_rescan": result.get("comparison") is not None,
        "comparison": result.get("comparison"),
        "summary": result.get("summary"),
        "not_checked": not_checked,     # '검사하지 못한 영역' — LLM이 "안전합니다"라고 말하지 않도록
        "suppressions": result.get("suppressions", []),
        "dependency_upgrades": [
            {k: u[k] for k in ("ecosystem", "name", "current_version", "target_version", "lockfile", "max_severity")}
            | {"fix_count": len(u["fixes"]), "unfixable_count": len(u["unfixable"])}
            for u in upgrades[:max_upgrades]
        ],
        "dependency_upgrades_total": len(upgrades),   # 위 목록은 위험도 순 상위 max_upgrades개만
        "total_items": len(findings),
        "truncated": len(findings) > max_items,
        "items": items,
    }
    return payload


def render_llm_text(payload: dict) -> str:
    """LLM 프롬프트에 바로 붙일 수 있는 한국어 텍스트."""
    s = payload.get("summary") or {}
    lines = [
        f"[검사 결과] 상태={payload.get('scan_status')} / 열린 문제 {s.get('open', 0)}건"
        f" / 위험도 {s.get('by_severity', {})}",
    ]
    if payload.get("is_rescan"):
        c = payload["comparison"]
        lines.append(f"[지난 검사 대비] 새로 {c['new']} / 계속 {c['persisting']} / 해결 {c['resolved']}"
                     f" / 확인불가 {c['unverifiable']}")
    for nc in payload.get("not_checked", []):
        lines.append(f"[검사 못 한 영역] {nc['tool']}({nc['category']}): {nc['reason']}")
    for sp in payload.get("suppressions", []):
        lines.append(f"[검사 예외 설정 발견] {sp['file']} ({sp['tool']}, {sp['kind']}) {sp.get('detail') or ''}")
    for u in payload.get("dependency_upgrades", []):
        if u["target_version"]:
            lines.append(f"[업그레이드 묶음] {u['name']} {u['current_version']} → {u['target_version']}"
                         f" (문제 {u['fix_count']}건 해결)")
    if payload.get("dependency_upgrades_total", 0) > len(payload.get("dependency_upgrades", [])):
        lines.append(f"(업그레이드 묶음 전체 {payload['dependency_upgrades_total']}개 중 위험도 높은"
                     f" {len(payload['dependency_upgrades'])}개만 표시)")
    for i, it in enumerate(payload.get("items", []), 1):
        lines += [
            "",
            f"### {i}. [{it['status_label']}][{it['severity']}][{it['kind']}] {it['title']}",
            f"- 위치: {it['where']}",
            f"- 변화: {it['change']}",
            f"- 설명: {it['what']}",
        ]
        if it["code"]:
            lines += ["- 코드:", "```", it["code"], "```"]
        fh = it["fix_hint"]
        lines.append(f"- 고치는 힌트: {fh.get('text', '')}" + (f" (명령: {fh['command']})" if fh.get("command") else ""))
        for fl in it["flags"]:
            lines.append(f"- 주의: {fl['note']}")
    if payload.get("truncated"):
        lines.append(f"\n(전체 {payload['total_items']}건 중 우선순위 높은 {len(payload['items'])}건만 포함)")
    return "\n".join(lines)
