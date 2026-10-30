"""검사 대상(고객) 저장소 받아오기.

백엔드가 직접 clone해서 폴더 경로만 넘겨도 되고, 이 함수를 써도 된다.
- 공개 저장소만 (로그인 정보를 쓰지 않음). 비공개면 바로 실패한다 (비밀번호를 묻느라 멈추지 않게).
- 최신 커밋 하나만 받는다 (--depth 1).
- 남의 코드를 받는 것이므로: https 주소만 허용, 심볼릭 링크는 일반 파일로 받음, LFS 파일은 받지 않음.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_ALLOWED_URL = re.compile(r"^https://[A-Za-z0-9.\-]+(:\d+)?/[\w.\-~/%]+?(\.git)?/?$")


class CloneError(RuntimeError):
    pass


def _git(args: list[str], cwd: str | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "GCM_INTERACTIVE": "never"})
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def clone_repo(url: str, dest: str | Path | None = None, ref: str | None = None,
               timeout: int = 180) -> tuple[Path, str]:
    """저장소를 받아 (폴더 경로, 커밋 SHA)를 돌려준다. dest가 없으면 임시 폴더를 만든다.

    다 쓴 임시 폴더는 호출한 쪽에서 shutil.rmtree로 지운다 (scan_repo는 알아서 지움).
    """
    if not shutil.which("git"):
        raise CloneError("git이 설치되어 있지 않습니다.")
    if not _ALLOWED_URL.match(url or ""):
        raise CloneError(f"https:// 로 시작하는 저장소 주소만 받을 수 있습니다: {url!r}")
    if ref is not None and (ref.startswith("-") or not re.match(r"^[\w.\-/]+$", ref)):
        raise CloneError(f"브랜치/태그 이름이 올바르지 않습니다: {ref!r}")

    dest = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="se-repo-")) / "repo"
    if dest.exists() and any(dest.iterdir()):
        raise CloneError(f"이미 내용이 있는 폴더입니다: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    args = ["-c", "core.symlinks=false", "-c", "protocol.file.allow=never",
            "clone", "--depth", "1", "--single-branch", "--no-tags"]
    if ref:
        args += ["--branch", ref]
    args += ["--", url, str(dest)]
    try:
        proc = _git(args, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CloneError(f"{timeout}초 안에 저장소를 받지 못했습니다.") from exc
    if proc.returncode != 0:
        msg = (proc.stderr or "").strip()[-400:]
        if "could not read Username" in msg or "Authentication failed" in msg or "not found" in msg.lower():
            msg += " (비공개 저장소이거나 주소가 틀렸을 수 있습니다)"
        raise CloneError(f"git clone 실패: {msg}")
    return dest, head_sha(dest) or ""


def head_sha(path: str | Path) -> str | None:
    """폴더가 git 저장소면 현재 커밋 SHA, 아니면 None."""
    if not shutil.which("git") or not (Path(path) / ".git").exists():
        return None
    try:
        # safe.directory: 폴더 소유자가 달라도(공유 폴더, 도커) git이 거부하지 않게
        proc = _git(["-c", "safe.directory=*", "-C", str(path), "rev-parse", "HEAD"], timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None
