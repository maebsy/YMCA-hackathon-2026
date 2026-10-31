"""보안엔진 본체.

    from security_engine import scan, scan_repo

    result = scan("C:/code/my-site")                       # 첫 검사
    result2 = scan("C:/code/my-site", previous=result)     # 재검사 (지난 결과와 비교)
    result3 = scan_repo("https://github.com/someone/someone.github.io")  # clone부터

결과는 JSON으로 바로 저장할 수 있는 dict다. 모양은 schema/scan_result.schema.json 참고.
"""
from __future__ import annotations

import copy
import re
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import fingerprint as fp
from . import osv_recheck, suppression
from .compare import compare
from .git import clone_repo, head_sha, remove_tree
from .models import (
    CATEGORY_BY_TOOL,
    CHANGES,
    CODE_ISSUE,
    ENGINE_NAME,
    ENGINE_VERSION,
    FLAG_IGNORED_BY_CONFIG,
    FLAG_THIRD_PARTY,
    OUT_OF_SCOPE,
    SCHEMA_VERSION,
    SEVERITIES,
    SEVERITY_RANK,
    STATUSES,
    THIRD_PARTY_HINT,
    TOOL_ERROR,
    TOOL_OK,
    TOOL_SKIPPED,
    TOOLS,
    ScanOptions,
)
from .normalize import scrub, version_key
from .runners import RUNNERS
from .runners.base import ToolRun, engine_name, find_binary, tool_version

_THIRD_PARTY = re.compile(THIRD_PARTY_HINT)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_tool(tool: str, target: Path, opts: ScanOptions) -> ToolRun:
    try:
        return RUNNERS[tool](target, opts)
    except Exception as exc:  # 도구 하나가 터져도 나머지 결과는 살린다
        return ToolRun(tool, TOOL_ERROR, f"엔진 내부 오류: {type(exc).__name__}: {exc}")


def _coverage(runs: dict[str, ToolRun]) -> dict:
    cov = {}
    for tool in TOOLS:
        r = runs[tool]
        cov[tool] = {
            "status": r.status,
            "state": "checked" if r.status == TOOL_OK else OUT_OF_SCOPE,
            "category": CATEGORY_BY_TOOL[tool],
            "message": r.message,
            "version": r.version,
            "engine": r.engine,
            "registry_used": r.registry_used,
            "count": len(r.findings),
            "duration_sec": r.duration_sec,
        }
    return cov


def _dependency_upgrades(findings: list[dict]) -> list[dict]:
    """패키지별로 '몇 버전으로 올리면 몇 개가 해결되는지' 묶음 (LLM 안내·화면용)."""
    plans: dict[tuple, dict] = {}
    for f in findings:
        if f["tool"] != "osv" or f["status"] != CODE_ISSUE or not f.get("package"):
            continue
        p = f["package"]
        key = (p["ecosystem"], p["name"], f["location"]["file"])
        plan = plans.setdefault(key, {
            "ecosystem": p["ecosystem"], "name": p["name"], "current_version": p["version"],
            "lockfile": f["location"]["file"], "target_version": None, "target_check": None,
            "fixes": [], "unfixable": [], "max_severity": "unknown",
        })
        tv = (f.get("remediation") or {}).get("target_version")
        # 같은 생태계 규칙으로 읽을 수 있는 목표만 비교한다. 읽을 수 없으면 추측해서 고르지 않는다 (#92)
        new_key = version_key(tv, p["ecosystem"]) if tv else None
        if new_key is not None:
            plan["fixes"].append(f["fingerprint"])
            old_key = version_key(plan["target_version"], p["ecosystem"]) if plan["target_version"] else None
            if old_key is None or new_key > old_key:
                plan["target_version"] = tv
                # 추천 버전을 OSV에 다시 조회한 결과 (#109). 묶음 목표 버전의 결과를 쓴다
                plan["target_check"] = (f.get("remediation") or {}).get("target_check")
        else:
            plan["unfixable"].append(f["fingerprint"])
        if SEVERITY_RANK[f["severity"]] < SEVERITY_RANK[plan["max_severity"]]:
            plan["max_severity"] = f["severity"]
    return sorted(plans.values(), key=lambda p: (SEVERITY_RANK[p["max_severity"]], p["name"]))


def _summary(findings: list[dict]) -> dict:
    open_ = [f for f in findings if f["status"] == CODE_ISSUE]
    return {
        "open": len(open_),
        "by_severity": {s: sum(1 for f in open_ if f["severity"] == s) for s in SEVERITIES},
        "by_category": {c: sum(1 for f in open_ if f["category"] == c) for c in CATEGORY_BY_TOOL.values()},
        "by_status": {s: sum(1 for f in findings if f["status"] == s) for s in STATUSES},
        "by_change": {c: sum(1 for f in findings if f.get("change") == c) for c in CHANGES},
        "flagged": sum(1 for f in findings if f.get("flags")),
    }


def _sort_key(f: dict):
    order = {CODE_ISSUE: 0}
    loc = f.get("location") or {}
    return (order.get(f["status"], 1), SEVERITY_RANK.get(f["severity"], 9), f["category"],
            loc.get("file") or "", loc.get("start_line") or 0)


def scan(target: str | Path, previous: dict | None = None, *, options: ScanOptions | None = None,
         repo_url: str | None = None, commit_sha: str | None = None) -> dict:
    """폴더 하나를 검사한다.

    target: 검사할 코드 폴더
    previous: 같은 사이트의 직전 검사 결과(dict). 주면 재검사로 보고 비교한다.
    options: ScanOptions (생략하면 기본값)
    repo_url, commit_sha: 결과에 기록만 한다 (commit_sha는 생략하면 폴더에서 읽음)
    """
    opts = options or ScanOptions()
    root = Path(target).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"검사할 폴더가 없습니다: {root}")
    started = time.monotonic()
    scanned_at = _now()

    tools = [t for t in TOOLS if t in opts.tools]
    with ThreadPoolExecutor(max_workers=len(tools) or 1) as pool:
        futures = {t: pool.submit(_run_tool, t, root, opts) for t in tools}
        runs = {t: fut.result() for t, fut in futures.items()}
    for t in TOOLS:
        runs.setdefault(t, ToolRun(t, TOOL_SKIPPED, "옵션으로 이번 검사에서 뺐습니다."))

    # 가릴 비밀값: Gitleaks가 찾은 값 + 코드 검사기의 비밀값 규칙(CWE-798 등)이 잡은 문자열
    secrets = [s for t in TOOLS for s in runs[t].secrets]
    findings: list[dict] = []
    for t in TOOLS:
        for f in runs[t].findings:
            # 비밀값이 다른 도구의 증거 코드·메시지에 섞여 나오는 경우까지 가린다
            for key in ("evidence", "raw", "title", "message"):
                if key in f:
                    f[key] = scrub(f[key], secrets)
            findings.append(f)
        runs[t].secrets = []
    secrets = []

    fp.make_unique(findings)
    for f in findings:
        # 외부 라이브러리 파일의 코드 문제: 숨기지 않고 위험도를 낮추고 '업데이트' 안내로 바꾼다
        if f["tool"] == "semgrep" and _THIRD_PARTY.search((f.get("location") or {}).get("file") or ""):
            f["flags"].append(FLAG_THIRD_PARTY)
            f["severity"] = "low"
    sups = suppression.detect(root)
    ignored = suppression.osv_ignored_ids(sups)
    for f in findings:
        if f["tool"] == "osv" and ignored & set([f["rule_id"], *f.get("aliases", [])]):
            f["flags"].append(FLAG_IGNORED_BY_CONFIG)

    statuses = [r.status for r in runs.values()]
    status = "complete" if all(s in (TOOL_OK, TOOL_SKIPPED, "no_target") for s in statuses) else "partial"
    if not any(s == TOOL_OK for s in statuses):
        status = "failed"

    result = {
        "schema_version": SCHEMA_VERSION,
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION},
        "scan_id": uuid.uuid4().hex,
        "scanned_at": scanned_at,
        "duration_sec": 0.0,
        "target": {
            "path": str(root),
            "repo_url": repo_url,
            "commit_sha": commit_sha or head_sha(root),
        },
        "status": status,
        "coverage": _coverage(runs),
        "suppressions": sups,
        "summary": {},
        "comparison": None,
        "dependency_upgrades": [],
        "findings": findings,
    }
    compare(result, previous, root)
    # 추천 버전에 다른 취약점이 남았는지 (#109). status(code_issue)는 compare()가 정하므로 그 뒤에 조회합니다
    if runs["osv"].status == TOOL_OK:
        osv_recheck.recheck(result["findings"], opts)
    _finalize(result)
    result["duration_sec"] = round(time.monotonic() - started, 2)
    return result


def _finalize(result: dict) -> dict:
    result["findings"].sort(key=_sort_key)
    result["summary"] = _summary(result["findings"])
    result["dependency_upgrades"] = _dependency_upgrades(result["findings"])
    return result


def compare_results(current: dict, previous: dict | None) -> dict:
    """이미 저장된 두 결과를 다시 비교한다 (current는 바꾸지 않고 새 dict를 돌려줌).

    검사 폴더가 아직 있으면 '파일이 사라졌는지'까지 확인한다.
    """
    result = copy.deepcopy(current)
    path = Path((result.get("target") or {}).get("path") or "")
    compare(result, previous, path if path.is_dir() else None)
    return _finalize(result)


def scan_repo(repo_url: str, previous: dict | None = None, *, options: ScanOptions | None = None,
              ref: str | None = None, keep_dir: str | Path | None = None) -> dict:
    """저장소 주소를 받아 clone → 검사 → (임시 폴더 삭제)까지 한 번에.

    keep_dir를 주면 그 폴더에 받고 지우지 않는다 (디버깅용).
    """
    path, sha = clone_repo(repo_url, dest=keep_dir, ref=ref)
    try:
        return scan(path, previous, options=options, repo_url=repo_url, commit_sha=sha)
    finally:
        if keep_dir is None:
            remove_tree(path.parent)


def doctor() -> dict:
    """스캐너 설치 상태 점검: {도구: {"path": ..., "version": ...}}"""
    args = {"osv": ["--version"], "semgrep": ["--version"], "gitleaks": ["version"]}
    out = {}
    for t in TOOLS:
        if t not in args:  # 엔진 안에 들어 있는 검사기(설정 검사기)는 설치가 필요 없다
            out[t] = {"path": "(내장)", "version": ENGINE_VERSION, "engine": "builtin"}
            continue
        b = find_binary(t)
        out[t] = {"path": b, "version": tool_version(b, args[t]) if b else None, "engine": engine_name(b)}
    out["git"] = {"path": shutil.which("git"), "version": None}
    return out
