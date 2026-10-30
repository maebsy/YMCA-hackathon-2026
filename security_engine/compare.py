"""이전 검사 결과와 비교해서 change(새로/계속/해결/확인불가)와 status(4가지 상태)를 정한다.

판단 규칙
1. 이번 결과에 있음
   - 지난번 '열린 문제'에 같은 지문이 있음 → persisting, 아니면 new
   - status = code_issue
2. 지난번 '열린 문제'인데 이번 결과에 없음
   - 그 도구가 이번에 정상 실행됨(ok)  → resolved
       · 비밀값이면 status = runtime_check_needed (코드에서 지워도 키 폐기·재발급 필요)
       · 그 외는 status = code_resolved
       · 파일 자체가 없어졌으면 flags에 file_removed (기능을 지워서 '해결'한 것인지 확인 필요)
   - 그 도구가 이번에 못 돌았음(not_installed/no_target/error/skipped) → unverifiable, status = out_of_scope
       · OSV인데 lockfile이 사라졌으면 flags에 lockfile_removed
3. '열린 문제' = 지난 결과에서 status가 code_issue 이거나 change가 unverifiable 인 것
   (해결로 끝난 것은 다음 비교로 넘기지 않는다)
"""
from __future__ import annotations

import copy
from pathlib import Path

from .models import (
    CODE_ISSUE,
    CODE_RESOLVED,
    FLAG_FILE_REMOVED,
    FLAG_LOCKFILE_REMOVED,
    FLAG_ROTATE_SECRET,
    NEW,
    OUT_OF_SCOPE,
    PERSISTING,
    RESOLVED,
    RUNTIME_CHECK,
    STATUS_LABEL_KO,
    TOOL_OK,
    UNVERIFIABLE,
)
from .normalize import SourceReader


def open_findings(result: dict | None) -> dict[str, dict]:
    if not result:
        return {}
    return {
        f["fingerprint"]: f
        for f in result.get("findings", [])
        if f.get("status") == CODE_ISSUE or f.get("change") == UNVERIFIABLE
    }


def set_status(f: dict, status: str) -> None:
    f["status"] = status
    f["status_label"] = STATUS_LABEL_KO[status]


def compare(current: dict, previous: dict | None, target: Path | None = None) -> dict:
    """current를 고쳐서 돌려준다. previous가 없으면 전부 new (첫 검사)."""
    prev_open = open_findings(previous)
    now = current["scanned_at"]
    reader = SourceReader(target) if target else None

    # 이번에 나온 것 (이전 결과의 resolved/unverifiable 항목이 섞여 있으면 먼저 뺀다)
    fresh = [f for f in current.get("findings", []) if f.get("change") not in (RESOLVED, UNVERIFIABLE)]
    current_fps = set()
    for f in fresh:
        current_fps.add(f["fingerprint"])
        old = prev_open.get(f["fingerprint"])
        f["change"] = PERSISTING if old else NEW
        f["first_seen"] = (old or {}).get("first_seen") or now
        set_status(f, CODE_ISSUE)

    carried = []
    coverage = current.get("coverage", {})
    for fpr, old in prev_open.items():
        if fpr in current_fps:
            continue
        f = copy.deepcopy(old)
        f.pop("raw", None)
        f["flags"] = [x for x in f.get("flags", []) if x not in (FLAG_FILE_REMOVED, FLAG_LOCKFILE_REMOVED)]
        tool_ok = coverage.get(f["tool"], {}).get("status") == TOOL_OK
        if f["tool"] == "semgrep" and not str(f.get("rule_id", "")).startswith("vibe-coding/"):
            # 레지스트리 규칙으로 찾은 문제는 이번에 레지스트리 규칙을 실제로 돌렸을 때만 '해결'로 본다
            # (레지스트리 접속 실패로 우리 규칙만 돌았으면 → 확인 불가)
            tool_ok = tool_ok and bool(coverage.get("semgrep", {}).get("registry_used", False))
        file = (f.get("location") or {}).get("file")
        file_gone = bool(reader and file and not reader.exists(file))
        if tool_ok and not (f["tool"] == "osv" and file_gone):
            f["change"] = RESOLVED
            needs_rotation = f.get("category") == "secret" or FLAG_ROTATE_SECRET in f.get("flags", [])
            set_status(f, RUNTIME_CHECK if needs_rotation else CODE_RESOLVED)
            if file_gone:
                f["flags"].append(FLAG_FILE_REMOVED)
            f["resolved_at"] = now
        else:
            f["change"] = UNVERIFIABLE
            set_status(f, OUT_OF_SCOPE)
            if f["tool"] == "osv" and file_gone:
                f["flags"].append(FLAG_LOCKFILE_REMOVED)
        carried.append(f)

    current["findings"] = fresh + carried
    current["comparison"] = None if previous is None else {
        "base_scan_id": previous.get("scan_id"),
        "base_scanned_at": previous.get("scanned_at"),
        "base_commit_sha": (previous.get("target") or {}).get("commit_sha"),
        NEW: sum(1 for f in current["findings"] if f["change"] == NEW),
        PERSISTING: sum(1 for f in current["findings"] if f["change"] == PERSISTING),
        RESOLVED: sum(1 for f in current["findings"] if f["change"] == RESOLVED),
        UNVERIFIABLE: sum(1 for f in current["findings"] if f["change"] == UNVERIFIABLE),
    }
    return current
