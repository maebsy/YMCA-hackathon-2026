"""스캐너 실행 공통 부분: 실행 파일 찾기, 명령 실행, 결과 담는 그릇."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from ..models import TOOL_ERROR

# 실행 파일 이름. Windows에서 릴리스 파일 이름을 그대로 둔 경우도 찾아준다.
BINARY_NAMES = {
    "osv": ["osv-scanner", "osv-scanner_windows_amd64", "osv-scanner_windows_arm64"],
    "semgrep": ["semgrep"],
    "gitleaks": ["gitleaks"],
}


@dataclass
class ToolRun:
    tool: str
    status: str
    message: str = ""
    version: str | None = None
    findings: list[dict] = field(default_factory=list)
    duration_sec: float = 0.0
    # 엔진 내부용: 다른 도구 결과에서 가려야 할 비밀값. 결과 JSON에는 절대 넣지 않는다.
    secrets: list[str] = field(default_factory=list, repr=False)


def find_binary(tool: str) -> str | None:
    """환경 변수(SECURITY_ENGINE_OSV_BIN 등) → PATH 순서로 실행 파일을 찾는다."""
    override = os.environ.get(f"SECURITY_ENGINE_{tool.upper()}_BIN")
    if override:
        return override if (os.path.isfile(override) or shutil.which(override)) else None
    for name in BINARY_NAMES[tool]:
        found = shutil.which(name)
        if found:
            return found
    return None


def run_cmd(cmd: list[str], timeout: int, cwd: str | None = None,
            extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",        # Windows에서 Semgrep이 한글 경로·출력 때문에 죽지 않게
        "NO_COLOR": "1",
        "SEMGREP_SEND_METRICS": "off",
        "SEMGREP_ENABLE_VERSION_CHECK": "0",  # 버전 확인 접속 때문에 오프라인에서 1분 넘게 멈추는 것 방지
    })
    if extra_env:
        env.update(extra_env)
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout,
        encoding="utf-8", errors="replace", **kwargs,
    )


def tool_version(binary: str, args: list[str]) -> str | None:
    try:
        out = run_cmd([binary, *args], timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\d+\.\d+\.\d+", (out.stdout or "") + (out.stderr or ""))
    return m.group(0) if m else None


def tail(text: str | None, n: int = 400) -> str:
    text = (text or "").strip()
    return text[-n:]


def error_run(tool: str, message: str, version: str | None = None) -> ToolRun:
    return ToolRun(tool=tool, status=TOOL_ERROR, message=message, version=version)
