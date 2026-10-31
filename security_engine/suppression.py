"""'고친 척' 꼼수 찾기 — 저장소 단위.

엔진은 아래 설정을 전부 무시하고 검사하지만(숨김 = 해결 아님),
이런 파일이 있다는 사실 자체를 결과의 suppressions에 남겨 사용자·LLM이 알 수 있게 한다.

| 파일 | 도구 | 하는 일 |
|---|---|---|
| osv-scanner.toml 의 [[IgnoredVulns]] | osv | 특정 취약점을 무시 |
| .gitleaksignore | gitleaks | 특정 비밀값 발견을 무시 |
| .gitleaks.toml | gitleaks | 규칙·예외 목록을 바꿈 |
| .semgrepignore | semgrep | 특정 파일·폴더를 검사에서 뺌 |

줄 단위 주석(nosemgrep, gitleaks:allow)은 각 runner가 finding.flags에 표시한다.
"""
from __future__ import annotations

import os
from pathlib import Path

from .normalize import rel_path
from .runners.osv import ignored_ids

_SKIP_DIRS = {"node_modules", ".git", "vendor", ".venv", "venv", "dist", "build"}
_FILES = {
    ".gitleaksignore": ("gitleaks", "ignore_file"),
    ".gitleaks.toml": ("gitleaks", "custom_config"),
    ".semgrepignore": ("semgrep", "ignore_file"),
}


def detect(target: Path) -> list[dict]:
    found = []
    for file, ids in ignored_ids(target).items():
        for vid in ids:
            found.append({"tool": "osv", "file": file, "kind": "ignore_config", "detail": vid})
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name in _FILES:
                tool, kind = _FILES[name]
                found.append({"tool": tool, "file": rel_path(Path(dirpath) / name, target),
                              "kind": kind, "detail": None})
    return found


def osv_ignored_ids(suppressions: list[dict]) -> set[str]:
    return {s["detail"] for s in suppressions if s["tool"] == "osv" and s["detail"]}
