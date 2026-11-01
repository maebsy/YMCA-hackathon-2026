"""샌드박스: 대상 소스로 앱을 격리 실행하고 probe(공격 재생 + 테스트)를 돌립니다.

- DockerSandbox: 서버 운영용. `--network none` 컨테이너 안에서 probe를 실행합니다. 사용자 코드는 인터넷에
  닿지 못하고, 공격 요청도 컨테이너 안 127.0.0.1 로만 갑니다. 사용자 저장소 실검증은 반드시 이 경로를 씁니다.
- LocalSandbox: 개발·CI 및 우리 데모 과녁 전용. 서브프로세스로 실행하며 네트워크 격리가 없으므로
  **신뢰된 우리 소스(demo-vulnerable-site)에만** 씁니다. 사용자 저장소에는 쓰지 않습니다.

둘 다 run(workdir, cfg) -> probe JSON(dict) 을 돌려줍니다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

PROBE = Path(__file__).parent / "probe.mjs"
# probe는 UTF-8로 출력합니다. 지정하지 않으면 Windows는 cp949로 읽다가 한국어에서 깨집니다
_TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


class SandboxError(RuntimeError):
    pass


def docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "info"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


class LocalSandbox:
    """서브프로세스 실행. 격리 없음 → 신뢰된 우리 과녁 전용."""

    name = "local"

    def run(self, workdir: Path, cfg: dict, *, timeout: int = 150) -> dict:
        workdir = Path(workdir)
        if not (workdir / "node_modules").is_dir():
            # Windows의 npm은 npm.cmd라 이름만으로는 subprocess가 찾지 못합니다
            ci = subprocess.run([shutil.which("npm") or "npm", "ci", "--no-audit", "--no-fund"], cwd=workdir,
                                capture_output=True, **_TEXT, timeout=timeout)
            if ci.returncode != 0:
                raise SandboxError(f"npm ci 실패: {(ci.stderr or ci.stdout)[-300:]}")
        cfg = {**cfg, "cwd": str(workdir)}
        proc = subprocess.run(["node", str(PROBE)], input=json.dumps(cfg), cwd=str(workdir),
                              capture_output=True, **_TEXT, timeout=timeout)
        return _parse_probe(proc)


class DockerSandbox:
    """`--network none` 컨테이너 안에서 probe 실행. 사용자 저장소 실검증의 표준 경로."""

    name = "docker"
    BASE_IMAGE = "node:22-slim"

    def __init__(self, memory: str = "512m", cpus: str = "1", pids: int = 256):
        self.memory, self.cpus, self.pids = memory, cpus, pids
        self.docker = shutil.which("docker") or "docker"

    def run(self, workdir: Path, cfg: dict, *, timeout: int = 300) -> dict:
        workdir = Path(workdir)
        tag = f"verify-{uuid.uuid4().hex[:12]}"
        with tempfile.TemporaryDirectory() as ctx_s:
            ctx = Path(ctx_s)
            shutil.copytree(workdir, ctx / "repo", ignore=shutil.ignore_patterns("node_modules", ".git"),
                            symlinks=True)  # 링크를 따라가 서버 파일을 빌드 컨텍스트에 넣지 않음
            shutil.copy(PROBE, ctx / "probe.mjs")
            (ctx / "Dockerfile").write_text(_DOCKERFILE, encoding="utf-8")
            try:
                build = subprocess.run([self.docker, "build", "-t", tag, "."], cwd=str(ctx),
                                       capture_output=True, **_TEXT, timeout=timeout)
                if build.returncode != 0:
                    raise SandboxError(f"docker build 실패: {(build.stderr or build.stdout)[-400:]}")
                cfg = {**cfg, "cwd": "/app/repo"}
                # --network none: 컨테이너는 인터넷에 못 나감. probe는 컨테이너 안 127.0.0.1만 씁니다.
                run = subprocess.run(
                    [self.docker, "run", "--rm", "-i", "--network", "none",
                     "--memory", self.memory, "--cpus", self.cpus, "--pids-limit", str(self.pids),
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                     tag, "node", "/app/probe.mjs"],
                    input=json.dumps(cfg), capture_output=True, **_TEXT, timeout=timeout)
                return _parse_probe(run)
            finally:
                subprocess.run([self.docker, "rmi", "-f", tag], capture_output=True, timeout=60)


# 빌드(네트워크 O)에서 deps 설치, 실행(네트워크 X)에서 코드 구동.
# --ignore-scripts: 설치 스크립트(postinstall)로 빌드 때 임의 코드가 도는 것을 막습니다.
_DOCKERFILE = """FROM node:22-slim
WORKDIR /app/repo
COPY repo/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund || npm install --ignore-scripts --no-audit --no-fund
COPY repo/ ./
COPY probe.mjs /app/probe.mjs
RUN useradd -m runner && chown -R runner /app
USER runner
"""


def _parse_probe(proc: subprocess.CompletedProcess) -> dict:
    out = (proc.stdout or "").strip()
    if not out:
        raise SandboxError(f"probe 출력이 비었습니다 (종료 {proc.returncode}): {(proc.stderr or '')[-300:]}")
    try:
        return json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise SandboxError(f"probe 출력을 읽지 못했습니다: {out[:200]}") from exc


def pick_sandbox(trusted: bool):
    """사용자 저장소(trusted=False)는 Docker 필수. 우리 과녁(trusted=True)은 Docker 있으면 Docker, 없으면 Local."""
    if docker_available():
        return DockerSandbox()
    if trusted:
        return LocalSandbox()
    raise SandboxError("사용자 저장소 실제검증에는 Docker(격리)가 필요합니다. 서버에 Docker가 없습니다.")
