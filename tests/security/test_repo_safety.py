"""남의 저장소를 받아 검사할 때 우리 서버를 지키는지 (웹셸 방지).

공격자가 웹셸·설치 스크립트·서버 파일을 가리키는 링크를 넣은 저장소를 보내도
- 받은 코드는 실행되지 않고, 서버 파일 내용은 결과에 들어가지 않고, 임시 폴더는 지워진다.
- 이상한 주소는 git을 부르기 전에 거절하고, 너무 큰 저장소는 받자마자 지운다.
- 검사 도구와 git에는 서버 비밀값이 든 환경 변수를 넘기지 않는다.
스캐너가 없어도 돈다. 있으면 실제 검사까지 거친다.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from security_engine import engine, git
from security_engine.runners import base


def _git_cmd(args, cwd, **kw):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "commit.gpgsign=false", *args],
                          cwd=cwd, check=True, capture_output=True, text=True, **kw)


def _fake_clone(files: dict[str, int], returncode: int = 0):
    """git clone 대신 dest 폴더에 파일만 만든다 (이름: 크기)."""
    def fake_git(args, cwd=None, timeout=180):
        dest = Path(args[-1])
        dest.mkdir(parents=True, exist_ok=True)
        for name, size in files.items():
            (dest / name).write_bytes(b"x" * size)
        return subprocess.CompletedProcess(args, returncode, "", "fatal: early EOF" if returncode else "")
    return fake_git


def _record_mkdtemp(monkeypatch) -> list[str]:
    made = []
    real = git.tempfile.mkdtemp

    def mkdtemp(**kw):
        made.append(real(**kw))
        return made[-1]
    monkeypatch.setattr(git.tempfile, "mkdtemp", mkdtemp)
    return made


@pytest.mark.parametrize("url", [
    "https://github.com/o/r\n",
    "https://github.com/o/r --upload-pack=touch /tmp/pwned",
    "--upload-pack=touch /tmp/pwned",
    "ext::sh -c touch% /tmp/pwned",
    "file:///etc",
    "https://github.com/o/r.git?x=1",
    "https://github.com/o/r#x",
    "https://user:pw@github.com/o/r",
    "git@github.com:o/r.git",
])
def test_clone_rejects_command_like_urls_before_running_git(monkeypatch, url):
    called = []
    monkeypatch.setattr(git, "_git", lambda *a, **k: called.append(a))
    with pytest.raises(git.CloneError):
        git.clone_repo(url)
    assert not called


@pytest.mark.parametrize("env, files, message", [
    ({"SECURITY_ENGINE_MAX_REPO_FILES": "2"}, {"a": 1, "b": 1, "c": 1}, "2개"),
    ({"SECURITY_ENGINE_MAX_REPO_MB": "1"}, {"big.bin": 2 * 1024 * 1024}, "1MB"),
])
def test_too_large_repo_is_rejected_and_removed(monkeypatch, env, files, message):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(git, "_git", _fake_clone(files))
    made = _record_mkdtemp(monkeypatch)
    with pytest.raises(git.CloneError, match=f"너무 큽니다.*{message}"):
        git.clone_repo("https://github.com/o/r")
    assert made and not Path(made[0]).exists()


def test_failed_clone_leaves_no_temp_folder(monkeypatch):
    monkeypatch.setattr(git, "_git", _fake_clone({"half.txt": 10}, returncode=128))
    made = _record_mkdtemp(monkeypatch)
    with pytest.raises(git.CloneError, match="git clone 실패"):
        git.clone_repo("https://github.com/o/r")
    assert made and not Path(made[0]).exists()


def test_repo_within_limits_is_kept(monkeypatch):
    monkeypatch.setenv("SECURITY_ENGINE_MAX_REPO_FILES", "not-a-number")  # 잘못된 값이면 기본값
    monkeypatch.setattr(git, "_git", _fake_clone({"a.js": 10, "b.js": 10}))
    path, _ = git.clone_repo("https://github.com/o/r")
    try:
        assert (path / "a.js").exists()
    finally:
        git.remove_tree(path.parent)


def test_tools_and_git_do_not_get_server_secrets(monkeypatch):
    for name in ("DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SECURITY_ENGINE_FP_SALT", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "canary-" + name.lower())
    monkeypatch.setenv("https_proxy", "http://proxy.example:3128")
    seen = []

    def fake_run(cmd, **kw):
        seen.append({k.upper(): v for k, v in kw["env"].items()})
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake_run)

    base.run_cmd(["tool"], timeout=5, extra_env={"OSV_EXTRA": "1"})
    git._git(["--version"])

    tool_env, git_env = seen
    for env in seen:
        assert "canary-" not in json.dumps(env)
        assert env["HTTPS_PROXY"] == "http://proxy.example:3128"
        assert "PATH" in env
    assert tool_env["SEMGREP_SEND_METRICS"] == "off" and tool_env["OSV_EXTRA"] == "1"
    assert git_env["GIT_TERMINAL_PROMPT"] == "0"


@pytest.fixture
def attack_repo(tmp_path):
    """웹셸 대신 '실행되면 표시 파일을 만드는 코드'와 서버 비밀 파일을 가리키는 링크를 넣은 저장소."""
    canary = tmp_path / "pwned.txt"
    secret_value = "canary" + "-server-secret"
    secret = tmp_path / "server" / "backend.env"
    secret.parent.mkdir()
    secret.write_text(f"DB_PASSWORD={secret_value}\n", encoding="utf-8")

    src = tmp_path / "attack"
    (src / "public").mkdir(parents=True)
    (src / "api").mkdir()
    mark = canary.as_posix()
    (src / "public" / "shell.php").write_text(f"<?php file_put_contents('{mark}', 'php'); ?>\n", encoding="utf-8")
    (src / "api" / "cmd.js").write_text(f"require('fs').writeFileSync({mark!r}, 'node');\n", encoding="utf-8")
    (src / "package.json").write_text(json.dumps(
        {"name": "attack", "version": "1.0.0", "scripts": {"postinstall": "node api/cmd.js"}}), encoding="utf-8")
    _git_cmd(["init", "-q"], src)
    _git_cmd(["add", "."], src)
    # 심볼릭 링크는 OS 권한과 상관없이 git 색인에 직접 넣는다 (Windows에서도 같은 저장소가 만들어지게)
    blob = _git_cmd(["hash-object", "-w", "--stdin"], src, input=secret.as_posix()).stdout.strip()
    _git_cmd(["update-index", "--add", "--cacheinfo", f"120000,{blob},leak.env"], src)
    _git_cmd(["commit", "-q", "--no-verify", "-m", "attack"], src)
    return {"url": src.as_uri(), "canary": canary, "secret": secret, "secret_value": secret_value}


@pytest.fixture
def allow_local_clone(monkeypatch):
    """테스트에서만 github 주소 대신 로컬 저장소를 받게 한다. 나머지 clone 옵션은 실제 그대로 쓴다."""
    monkeypatch.setattr(git, "_ALLOWED_URL", re.compile(r"^file://"))
    real_git = git._git

    def local_git(args, cwd=None, timeout=180):
        args = ["protocol.file.allow=always" if a == "protocol.file.allow=never" else a for a in args]
        return real_git(args, cwd, timeout)
    monkeypatch.setattr(git, "_git", local_git)


def test_symlink_to_server_file_is_checked_out_as_plain_text(attack_repo, allow_local_clone):
    path, _ = git.clone_repo(attack_repo["url"])
    try:
        leak = path / "leak.env"
        assert not leak.is_symlink()
        assert leak.read_text(encoding="utf-8") == attack_repo["secret"].as_posix()  # 경로 글자만, 내용은 없음
    finally:
        git.remove_tree(path.parent)


def test_attack_repo_is_only_read_never_run(attack_repo, allow_local_clone, monkeypatch):
    cloned = []
    real_clone = engine.clone_repo

    def recording_clone(*a, **k):
        cloned.append(real_clone(*a, **k))
        return cloned[-1]
    monkeypatch.setattr(engine, "clone_repo", recording_clone)

    result = engine.scan_repo(attack_repo["url"])

    assert not attack_repo["canary"].exists()                                 # 웹셸·설치 스크립트가 돌지 않음
    assert attack_repo["secret_value"] not in json.dumps(result, ensure_ascii=False)  # 서버 파일을 읽지 않음
    assert not cloned[0][0].parent.exists()                                   # 검사 뒤 임시 폴더 삭제
