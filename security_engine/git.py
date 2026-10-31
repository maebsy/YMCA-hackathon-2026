"""검사 대상(고객) 저장소 받아오기.

백엔드가 직접 clone해서 폴더 경로만 넘겨도 되고, 이 함수를 써도 된다.
- 공개 저장소만 (로그인 정보를 쓰지 않음). 비공개면 바로 실패한다 (비밀번호를 묻느라 멈추지 않게).
- 최신 커밋 하나만 받는다 (--depth 1).
- 남의 코드를 받는 것이므로: https://github.com 주소만 허용, 심볼릭 링크는 일반 파일로 받음, LFS 파일은 받지 않음.
- 받은 코드는 실행·설치·빌드하지 않는다. 받은 직후 크기를 재서 너무 크면 지우고 멈춘다.
- git에는 서버 비밀값이 든 환경 변수를 넘기지 않는다 (runners.base.safe_env).
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from .runners.base import safe_env

# 공개 GitHub 저장소만 (내부 주소·다른 호스트로 요청이 나가는 SSRF 통로를 막는다).
# 끝은 \Z로 맞춘다: $는 맨 끝 줄바꿈 하나를 그냥 통과시킨다.
_ALLOWED_URL = re.compile(r"^https://github\.com/[\w.\-]+/[\w.\-]+?(\.git)?/?\Z")

# 받은 저장소 크기 한도 (.git 폴더 제외). 아주 큰 저장소로 서버 디스크와 검사 시간을 다 쓰지 못하게 한다.
# 바이브코딩 사이트 저장소보다 넉넉하게 잡은 기본값이고, 환경 변수로 바꿀 수 있다.
DEFAULT_MAX_REPO_MB = 200
DEFAULT_MAX_REPO_FILES = 20_000


class CloneError(RuntimeError):
    pass


def _git(args: list[str], cwd: str | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    env = safe_env({"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "GCM_INTERACTIVE": "never"})
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def remove_tree(path: str | Path) -> None:
    """받은 저장소 폴더를 지운다. 없으면 그냥 넘어간다.

    Windows에서는 git이 .git/objects 파일을 읽기 전용으로 만들어 shutil.rmtree(ignore_errors=True)가
    조용히 실패하고 폴더가 남는다 → 쓰기 권한을 주고 다시 지운다.
    """
    def retry(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onexc=retry)


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _check_size(path: Path) -> None:
    """받은 폴더가 SECURITY_ENGINE_MAX_REPO_MB / SECURITY_ENGINE_MAX_REPO_FILES를 넘으면 CloneError."""
    max_mb = _env_int("SECURITY_ENGINE_MAX_REPO_MB", DEFAULT_MAX_REPO_MB)
    max_files = _env_int("SECURITY_ENGINE_MAX_REPO_FILES", DEFAULT_MAX_REPO_FILES)
    hint = "검사할 사이트 코드만 담긴 저장소로 다시 시도하세요."
    total = files = 0
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            files += 1
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
        if files > max_files:
            raise CloneError(f"저장소가 너무 큽니다: 파일이 {max_files:,}개를 넘습니다. {hint}")
        if total > max_mb * 1024 * 1024:
            raise CloneError(f"저장소가 너무 큽니다: {max_mb:,}MB를 넘습니다. {hint}")


def clone_repo(url: str, dest: str | Path | None = None, ref: str | None = None,
               timeout: int = 180) -> tuple[Path, str]:
    """저장소를 받아 (폴더 경로, 커밋 SHA)를 돌려준다. dest가 없으면 임시 폴더를 만든다.

    다 쓴 임시 폴더는 호출한 쪽에서 remove_tree로 지운다 (scan_repo는 알아서 지움).
    실패하면(받기 실패, 시간 초과, 크기 초과) 여기서 만든 임시 폴더는 바로 지우고 CloneError를 낸다.
    """
    if not shutil.which("git"):
        raise CloneError("git이 설치되어 있지 않습니다.")
    if not _ALLOWED_URL.match(url or ""):
        raise CloneError(f"https://github.com/<owner>/<repo> 형식의 공개 저장소 주소만 받을 수 있습니다: {url!r}")
    if ref is not None and (ref.startswith("-") or not re.match(r"^[\w.\-/]+$", ref)):
        raise CloneError(f"브랜치/태그 이름이 올바르지 않습니다: {ref!r}")

    own_tmp = dest is None
    dest = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="se-repo-")) / "repo"
    if dest.exists() and any(dest.iterdir()):
        raise CloneError(f"이미 내용이 있는 폴더입니다: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    # core.autocrlf=false: 검사 서버 OS 설정에 따라 줄바꿈이 바뀌지 않게, 저장소에 들어 있는 그대로 받는다 (#58)
    args = ["-c", "core.symlinks=false", "-c", "protocol.file.allow=never", "-c", "core.autocrlf=false",
            "clone", "--depth", "1", "--single-branch", "--no-tags"]
    if ref:
        args += ["--branch", ref]
    args += ["--", url, str(dest)]
    try:
        try:
            proc = _git(args, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise CloneError(f"{timeout}초 안에 저장소를 받지 못했습니다.") from exc
        if proc.returncode != 0:
            msg = (proc.stderr or "").strip()[-400:]
            if "could not read Username" in msg or "Authentication failed" in msg or "not found" in msg.lower():
                msg += " (비공개 저장소이거나 주소가 틀렸을 수 있습니다)"
            raise CloneError(f"git clone 실패: {msg}")
        _check_size(dest)
    except CloneError:
        # 받다 만 파일이나 너무 큰 저장소를 서버에 남기지 않는다 (호출한 쪽이 준 dest는 그쪽 몫)
        if own_tmp:
            remove_tree(dest.parent)
        raise
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
