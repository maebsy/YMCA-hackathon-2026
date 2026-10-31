"""Pull reviewed main releases from GitHub; no inbound SSH or PC scheduler needed."""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

REPO = "maebsy/YMCA-hackathon-2026"
REPO_URL = f"https://github.com/{REPO}.git"
SHA = re.compile(r"[0-9a-f]{40}")


class Deferred(RuntimeError):
    pass


# 교체 대기 정책 (#151).
# 해석 작업은 백엔드 메모리에만 있어 재시작하면 끊깁니다. 그렇다고 교체를 위해 새 작업을 막으면(drain)
# 이용자가 계속 들어오는 동안 사이트가 막힙니다(운영에서 실제로 발생). 그래서 새 작업은 막지 않고,
# 진행 중 작업이 0이 되는 순간에만 아주 잠깐 막고 교체합니다. 계속 바쁘면 다음 타이머로 미룹니다.
DRAIN_POLL_SECONDS = 2
IDLE_WAIT_PER_RUN = 8 * 60  # 한 번 실행에서 빈 순간을 기다리는 시간 (서비스 TimeoutStartSec 25분 안)
DRAIN_CONFIRM_SECONDS = 20  # 막은 직후 막 들어온 요청이 끝나기를 기다리는 최대 시간. 넘으면 풀고 다시 기다림

# MCP(72hours-mcp: 검사별 연결 /mcp/h/* 와 서비스 MCP /mcp/service/rpc)도 같은 main 커밋으로 맞춥니다
MCP_SOURCE = "integrations/mcp-handoff"
MCP_LIVE_PORT = 8765
MCP_CANDIDATE_PORT = 18765
# 앱 교체가 성공하면 같은 커밋의 배포 스크립트로 자신을 갱신합니다 (예전에는 머지돼도 서버에 안 들어갔음)
RUNTIME_FILES = ("deploy.py", "deployment_entry.py", "snapshot.py")


def drain_record(path):
    """drain 파일의 시작 시각(epoch). 없거나 예전 형식(빈 파일)이면 None."""
    try:
        since = json.loads(path.read_text()).get("since")
        return float(since) if since else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def requirements(path):
    """의존성 목록만 비교합니다. 줄바꿈(CRLF)·주석·빈 줄 차이는 의존성 변경이 아닙니다."""
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return sorted(line for line in lines if line)


def atomic(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def get_json(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "72hours-main-deployer", **(headers or {})})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def ci_ready(runs, revision):
    latest = {}
    for run in runs:
        if run.get("head_sha") == revision and run.get("event") == "push" and run.get("head_branch") == "main":
            key = run["path"]
            if key not in latest or (run["id"], run.get("run_attempt", 1)) > (latest[key]["id"], latest[key].get("run_attempt", 1)):
                latest[key] = run
    return ".github/workflows/ci.yml" in latest and all(
        r.get("status") == "completed" and r.get("conclusion") == "success" for r in latest.values())


def safe_env():
    keys = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE",
            "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env["PATH"] = str(Path.home() / ".local/share/72hours/node/bin") + ":/usr/local/bin:/usr/bin:/bin"
    env.update(PYTHONDONTWRITEBYTECODE="1", NEXT_TELEMETRY_DISABLED="1", GIT_TERMINAL_PROMPT="0")
    return env


@contextmanager
def locks(paths):
    import fcntl
    with ExitStack() as stack:
        for path in paths:
            stream = stack.enter_context(path.open("a"))
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Deferred("another deployment is running") from None
        yield


class Deployer:
    def __init__(self, root):
        self.root = root.resolve()
        self.control = self.root / "auto-deploy"
        self.runtime = Path(__file__).resolve().parent
        self.control.mkdir(parents=True, exist_ok=True)
        self.state = self.control / "status.json"
        self.transaction = self.control / "transaction.json"
        self.stage = "preflight"
        self.revision = None
        self.env = safe_env()
        self.log = None
        self.owns_lock = False
        self.retry = False

    def run(self, args, cwd=None, timeout=180):
        return subprocess.run(args, cwd=cwd, env=self.env, check=True, timeout=timeout,
                              stdout=self.log or subprocess.DEVNULL, stderr=subprocess.STDOUT)

    def capture(self, args):
        return subprocess.check_output(args, env=self.env, text=True, timeout=30,
                                       stderr=self.log or subprocess.DEVNULL).strip()

    def head(self):
        revision = self.capture(["git", "ls-remote", REPO_URL, "refs/heads/main"]).split()[0]
        if not SHA.fullmatch(revision):
            raise RuntimeError("Invalid main revision")
        return revision

    def ready(self, revision):
        try:
            data = get_json(f"https://api.github.com/repos/{REPO}/actions/runs?" +
                            urlencode({"head_sha": revision, "event": "push", "per_page": 100}))
        except (OSError, ValueError):
            raise Deferred("GitHub CI query unavailable; retry later") from None
        return data.get("total_count", 101) <= 100 and ci_ready(data.get("workflow_runs", []), revision)

    def record(self, status, **extra):
        value = {"status": status, "stage": self.stage, "revision": self.revision,
                 "at": datetime.now(timezone.utc).isoformat(), **extra}
        atomic(self.state, value)
        print(json.dumps(value), flush=True)

    def target(self, link):
        if not link.is_symlink():
            raise RuntimeError("Deployment requires managed symlinks")
        target = link.resolve(strict=True)
        if not target.is_relative_to(self.root) or target == self.root:
            raise RuntimeError("Release outside application root")
        return target

    def link(self, name, target):
        target = Path(target).resolve(strict=True)
        if not target.is_relative_to(self.root) or target == self.root:
            raise RuntimeError("Unsafe release path")
        tmp = self.root / (name + ".deploy-next")
        tmp.unlink(missing_ok=True)
        tmp.symlink_to(target, target_is_directory=True)
        os.replace(tmp, self.root / name)

    def restart(self):
        self.run(["systemctl", "--user", "restart", "72hours-backend", "72hours-frontend"], timeout=90)

    def health(self, backend=8000, frontend=3000, revision=None, public=None):
        base = public or f"http://127.0.0.1:{backend}"
        front = public or f"http://127.0.0.1:{frontend}"
        for _ in range(30):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=5) as response:
                    if json.load(response).get("status") != "ok":
                        raise ValueError("API health")
                    if revision and response.headers.get("x-72hours-release") != revision:
                        raise ValueError("Backend revision")
                if revision and get_json(front + "/deployment.json?v=" + revision).get("revision") != revision:
                    raise ValueError("Frontend revision")
                with urllib.request.urlopen(front + "/", timeout=5) as response:
                    if "72hours" not in response.read(2_000_000).decode("utf-8"):
                        raise ValueError("Frontend HTML")
                return
            except (OSError, ValueError):
                time.sleep(1)
        raise RuntimeError("Health or release verification failed")

    def prepare(self, revision):
        self.stage = "build"
        releases = self.root / "auto-releases"
        releases.mkdir(exist_ok=True)
        release = releases / revision
        if (release / ".ready").exists():
            return release
        if release.exists():
            raise RuntimeError("Incomplete release exists; preserve logs and use --retry")
        if shutil.disk_usage(self.root).free < 3 * 1024**3:
            raise Deferred("Less than 3 GiB disk free")
        self.run(["git", "clone", "--no-checkout", REPO_URL, str(release)])
        self.run(["git", "checkout", "--detach", revision], cwd=release)
        if self.capture(["git", "-C", str(release), "rev-parse", "HEAD"]) != revision:
            raise RuntimeError("Checkout mismatch")
        python = str(release / ".venv/bin/python")
        self.run([str(Path.home()/".local/bin/uv"), "venv", "--python", "/usr/bin/python3", str(release/".venv")])
        self.run([str(Path.home()/".local/bin/uv"), "pip", "install", "--python", python,
                  "-r", str(release/"backend/requirements.txt")], timeout=600)
        frontend = release / "frontend"
        self.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=frontend, timeout=600)
        marker = {"revision": revision, "repository": REPO, "built_at": datetime.now(timezone.utc).isoformat()}
        atomic(release / "deployment.json", marker)
        atomic(frontend / "public/deployment.json", marker)
        self.run(["npm", "run", "build"], cwd=frontend, timeout=600)
        self.stage = "candidate_health"
        env = {**self.env, "DATABASE_URL": f"sqlite:///{release}/candidate.sqlite", "LLM_JOBS_ENABLED": "false",
               "SCAN_REQUIRE_AUTH": "false", "LLM_BASE_URL": "http://127.0.0.1:9/v1", "LLM_API_KEY": "unused",
               "DEPLOYMENT_CONTROL_DIR": str(self.control), "NODE_ENV": "production"}
        with ExitStack() as stack:
            processes = []
            for args, cwd in (
                ([python, "-m", "uvicorn", "deployment_entry:create_app", "--factory", "--app-dir", str(self.runtime),
                  "--host", "127.0.0.1", "--port", "18080", "--no-access-log"], release/"backend"),
                (["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "13000"], frontend),
            ):
                process = subprocess.Popen(args, cwd=cwd, env=env, stdout=self.log, stderr=subprocess.STDOUT)
                processes.append(process)
                stack.callback(self.stop_candidate, process)
            self.health(18080, 13000, revision)
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("Candidate process exited; possible port conflict")
        (release / ".ready").touch()
        return release

    def check_schema(self, release, reviewed_revision=None):
        self.stage = "schema_review"
        old = self.target(self.root / "current")
        old_sha = self.capture(["git", "-C", str(old), "rev-parse", "HEAD"])
        # Earlier manual releases may be squashed commits absent from a fresh clone.
        self.run(["git", "-C", str(release), "fetch", "--no-tags", "--no-write-fetch-head", str(old), old_sha])
        changed = self.capture(["git", "-C", str(release), "diff", "--name-only", old_sha, self.revision]).splitlines()
        schema = ("docs/migrations/", "docs/db-schema.sql", "backend/migrations/",
                  "backend/app/models.py", "backend/app/db.py", "backend/app/scan_store.py",
                  "backend/app/explain_jobs/store.py")
        if any(path.startswith(schema) for path in changed) and reviewed_revision != self.revision:
            raise Deferred("Database storage/schema changes require review for this exact revision")

    @staticmethod
    def stop_candidate(process):
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def paused(self):
        """운영자가 --pause 로 멈췄으면 그 기록(dict), 아니면 None."""
        try:
            return json.loads((self.control/"paused.json").read_text())
        except (OSError, ValueError):
            return None

    def guard_status(self, headers, bootstrap=False):
        """백엔드의 진행 중 작업 수. 가드가 없는 예전 서버의 첫 이전(--bootstrap)만 None."""
        try:
            return get_json("http://127.0.0.1:8000/api/_deployment/status", headers)
        except urllib.error.HTTPError as exc:
            legacy = not (self.target(self.root/"current")/"deployment.json").exists()
            if exc.code == 404 and bootstrap and legacy:
                return None  # Manual one-time migration from a pre-guard server; never enabled in timer.
            raise Deferred("Backend deployment guard unavailable") from None

    def drain(self, bootstrap=False, now=False):
        """새 작업을 막지 않고 진행 중 작업이 0이 되는 순간을 기다렸다가, 그때만 잠깐 막고 교체 단계로 넘깁니다."""
        self.stage = "drain"
        headers = {"X-Deployment-Token": (self.control/"control-token").read_text().strip()}
        marker = self.control/"drain"
        if now:
            # 운영자 지시(--now): 기다리지 않고 바로 교체합니다. 진행 중 해석은 끊깁니다
            atomic(marker, {"revision": self.revision, "since": time.time()})
            return
        for _ in range(int(IDLE_WAIT_PER_RUN / DRAIN_POLL_SECONDS)):
            if self.paused():
                raise Deferred("Paused by operator while waiting; nothing changed")
            data = self.guard_status(headers, bootstrap)
            if data is None:
                return
            if data.get("busy") == 0:
                atomic(marker, {"revision": self.revision, "since": time.time()})
                # 확인과 차단 사이에 막 들어온 요청이 있을 수 있어, 막은 뒤 한 번 더 0인지 봅니다 (최대 20초만 막음)
                for _ in range(int(DRAIN_CONFIRM_SECONDS / DRAIN_POLL_SECONDS)):
                    data = self.guard_status(headers)
                    if data.get("draining") is True and data.get("busy") == 0:
                        return
                    time.sleep(DRAIN_POLL_SECONDS)
                marker.unlink(missing_ok=True)
            time.sleep(DRAIN_POLL_SECONDS)
        raise Deferred("Active jobs: waiting for an idle moment without pausing new jobs")

    def rollback(self):
        old = json.loads(self.transaction.read_text())
        self.link("current", old["backend"])
        self.link("frontend", old["frontend"])
        self.restart()
        self.health()
        self.transaction.unlink()
        (self.control/"drain").unlink(missing_ok=True)

    def activate(self, release, public=None):
        self.stage = "activate"
        backup = self.control / "backups" / f"{self.revision}-{time.time_ns()}"
        backup.mkdir(parents=True)
        old_backend = self.target(self.root/"current")
        self.run([str(old_backend/".venv/bin/python"), str(self.runtime/"snapshot.py"), str(backup)],
                 cwd=old_backend/"backend", timeout=60)
        atomic(self.transaction, {"backend": str(self.target(self.root/"current")),
                                  "frontend": str(self.target(self.root/"frontend"))})
        try:
            self.link("current", release)
            self.link("frontend", release / "frontend")
            self.restart()
            self.health(revision=self.revision)
            if public:
                self.health(revision=self.revision, public=public)
        except BaseException:
            self.stage = "rollback"
            self.rollback()
            raise
        self.transaction.unlink()
        (self.control/"drain").unlink(missing_ok=True)
        atomic(self.control/"applied.json", {"revision": self.revision})

    def read_control(self, name):
        try:
            return json.loads((self.control/name).read_text())
        except (OSError, ValueError):
            return None

    def mcp_pending(self, release):
        """이 커밋의 MCP를 올려야 하는지. 같은 커밋에서 실패했으면 --retry 전까지 다시 시도하지 않습니다."""
        if not (self.root/"mcp/live-current").is_symlink():
            return False  # MCP를 이 방식으로 관리하지 않는 서버
        applied = (self.read_control("mcp-applied.json") or {}).get("revision")
        if applied == self.revision:
            return False
        if not self.retry and (self.read_control("mcp-failed.json") or {}).get("revision") == self.revision:
            return False
        if applied:
            try:
                changed = self.capture(["git", "-C", str(release), "diff", "--name-only", applied, self.revision,
                                        "--", MCP_SOURCE])
            except subprocess.SubprocessError:
                changed = "unknown"  # 비교할 수 없으면 올려서 맞춥니다
            if not changed:
                atomic(self.control/"mcp-applied.json", {"revision": self.revision})
                return False
        return True

    def mcp_env(self):
        """72hours-mcp 서비스와 같은 설정(MCP_PUBLIC_ORIGIN 등). 값은 기록하지 않습니다."""
        values = {}
        path = Path.home()/".config/72hours/mcp.env"
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        if not values.get("MCP_PUBLIC_ORIGIN"):
            raise Deferred("MCP_PUBLIC_ORIGIN is not configured")
        return values

    def mcp_check(self, port, host):
        """MCP 상태와 서비스 MCP 도구 목록을 실제 공개 주소의 Host로 확인합니다."""
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
        headers = {"Host": host, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        for _ in range(30):
            try:
                if get_json(f"http://127.0.0.1:{port}/mcp/health", {"Host": host}).get("status") != "ok":
                    raise ValueError("MCP health")
                request = urllib.request.Request(f"http://127.0.0.1:{port}/mcp/service/rpc", data=body, headers=headers)
                with urllib.request.urlopen(request, timeout=10) as response:
                    names = {tool["name"] for tool in json.load(response)["result"]["tools"]}
                if {"service_info", "start_scan"} <= names:
                    return names
                raise ValueError("MCP tools missing")
            except (OSError, ValueError, KeyError, TypeError):
                time.sleep(1)
        raise RuntimeError("MCP health or tool list failed")

    def deploy_mcp(self, release):
        """MCP를 후보 포트에서 확인한 뒤 교체하고, 실패하면 이전 버전으로 되돌립니다. 작업 공간·연결 DB는 그대로 둡니다."""
        self.stage = "mcp"
        base = self.root/"mcp"
        source = release/MCP_SOURCE
        previous = (base/"live-current").resolve(strict=True)
        if requirements(previous/"requirements.txt") != requirements(source/"requirements.txt"):
            # 공용 가상환경을 바꾸면 지금 도는 MCP에도 영향이 가므로 운영자가 직접 갱신합니다
            raise Deferred("MCP dependencies changed; update the MCP venv first")
        settings = self.mcp_env()
        origins = settings["MCP_PUBLIC_ORIGIN"]
        host = origins.split(",")[0].strip().split("://", 1)[-1].split("/", 1)[0]
        target = base/"releases"/self.revision
        python = str(base/".venv/bin/python")
        if not (target/".ready").exists():
            shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("tests", "__pycache__"))
            candidate = Path(tempfile.mkdtemp(prefix="mcp-candidate-", dir=base))
            try:
                process = subprocess.Popen(
                    [python, str(target/"live_server.py"), "--database", str(candidate/"links.sqlite3"),
                     "--public-origin", origins, "--port", str(MCP_CANDIDATE_PORT)],
                    cwd=target, env={**self.env, **settings}, stdout=self.log, stderr=subprocess.STDOUT)
                try:
                    self.mcp_check(MCP_CANDIDATE_PORT, host)
                    if process.poll() is not None:
                        raise RuntimeError("MCP candidate exited; possible port conflict")
                finally:
                    self.stop_candidate(process)
            finally:
                shutil.rmtree(candidate, ignore_errors=True)
            (target/".ready").touch()
        try:
            self.link("mcp/live-current", target)
            self.run(["systemctl", "--user", "restart", "72hours-mcp"], timeout=60)
            self.mcp_check(MCP_LIVE_PORT, host)
        except BaseException:
            self.stage = "mcp_rollback"
            self.link("mcp/live-current", previous)
            self.run(["systemctl", "--user", "restart", "72hours-mcp"], timeout=60)
            raise
        atomic(self.control/"mcp-applied.json", {"revision": self.revision})

    def update_mcp(self, release):
        """MCP 교체 결과("deployed"/"failed"/None). MCP 실패는 이미 끝난 앱 교체를 되돌리지 않습니다."""
        if not self.mcp_pending(release):
            return None
        try:
            self.deploy_mcp(release)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, Deferred) else type(exc).__name__
            atomic(self.control/"mcp-failed.json", {"revision": self.revision, "reason": reason})
            return "failed"
        (self.control/"mcp-failed.json").unlink(missing_ok=True)
        return "deployed"

    def update_runtime(self, release):
        """같은 커밋의 배포 스크립트로 자신을 갱신합니다. 문법이 틀린 파일이 하나라도 있으면 아무것도 바꾸지 않습니다."""
        if self.runtime != (self.control/"runtime").resolve():
            return []  # 저장소에서 직접 실행(테스트·수동)할 때는 건드리지 않음
        source = release/"deploy/general-server/auto-deploy"
        changed = [name for name in RUNTIME_FILES if (source/name).read_bytes() != (self.runtime/name).read_bytes()]
        pinned = self.control/"runtime-pinned"
        if pinned.exists():
            # 운영자가 install.sh로 직접 설치한 사본은 main이 같은 내용을 가질 때까지 되돌리지 않습니다
            if not changed:
                pinned.unlink()
            return []
        try:
            for name in changed:
                compile((source/name).read_text(encoding="utf-8"), name, "exec")
        except SyntaxError:
            return ["invalid"]
        for name in changed:
            temporary = self.runtime/(name + ".next")
            shutil.copyfile(source/name, temporary)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.runtime/name)
        return changed

    def follow_up(self, release):
        """앱과 같은 커밋으로 MCP·배포 스크립트를 맞춥니다. 앱이 이미 최신이어도 남은 것만 이어서 합니다."""
        mcp = self.update_mcp(release)
        runtime = self.update_runtime(release)
        return {key: value for key, value in (("mcp", mcp), ("runtime", runtime)) if value}

    def execute(self, args):
        with locks([self.control/"deploy.lock", self.root/"frontend-deploy.lock"]):
            self.owns_lock = True
            if self.transaction.exists():
                self.stage = "recover_interrupted_switch"
                self.rollback()
            marker = self.control/"drain"
            if self.paused():
                # 운영자가 멈춤: 새 작업을 막고 있던 대기도 바로 풀어 이용자를 막지 않습니다
                marker.unlink(missing_ok=True)
                self.stage = "paused"
                self.record("paused", reason=self.paused().get("reason", ""))
                return
            marker.unlink(missing_ok=True)  # 실행 사이에 이용자를 막아 두는 일은 없습니다 (#151)
            self.retry = args.retry
            self.revision = self.head()
            if self.state.exists():
                previous = json.loads(self.state.read_text())
                if previous.get("revision") == self.revision and previous["status"] == "failed" and not args.retry:
                    return
            applied = self.control/"applied.json"
            if applied.exists() and json.loads(applied.read_text()).get("revision") == self.revision and not args.retry:
                release = self.root/"auto-releases"/self.revision
                if (release/".ready").exists():
                    (self.control/"logs").mkdir(exist_ok=True)
                    with (self.control/"logs"/(self.revision + ".log")).open("a") as self.log:
                        done = self.follow_up(release)
                    self.log = None
                    if done:
                        self.stage = "follow_up"
                        self.record("deployed", **done)
                return
            self.stage = "ci"
            if not self.ready(self.revision):
                raise Deferred("main push CI incomplete or not successful")
            if args.check:
                self.record("eligible")
                return
            if args.retry:
                release = self.root/"auto-releases"/self.revision
                if release.exists() and not (release/".ready").exists():
                    release.rename(release.with_name(release.name + f"-failed-{time.time_ns()}"))
            logs = self.control/"logs"
            logs.mkdir(exist_ok=True)
            with (logs/(self.revision + ".log")).open("a") as self.log:
                previous = (self.target(self.root/"current"), self.target(self.root/"frontend"))
                release = self.prepare(self.revision)
                if args.prepare_only:
                    self.record("prepared")
                    return
                if self.head() != self.revision or not self.ready(self.revision):
                    raise Deferred("main or CI changed while building")
                if previous != (self.target(self.root/"current"), self.target(self.root/"frontend")):
                    raise Deferred("Another operator changed the active release while building")
                self.check_schema(release, args.reviewed_schema_revision)
                self.drain(args.bootstrap, getattr(args, "now", False))
                self.activate(release, args.public_url)
                done = self.follow_up(release)
            self.log = None
            self.record("deployed", **done)


def pause(root, reason=""):
    """자동 배포를 멈춥니다. 잠금 없이 바로 기록하므로 배포가 기다리는 중이어도 다음 확인(5초 안)에 멈춥니다."""
    control = root / "auto-deploy"
    control.mkdir(parents=True, exist_ok=True)
    atomic(control/"paused.json", {"at": datetime.now(timezone.utc).isoformat(), "reason": reason[:200]})
    # 교체 중(transaction)이 아니면 새 작업 차단을 바로 풀어 이용자를 막지 않습니다. 교체 중이면 교체가 끝나며 풀립니다
    if not (control/"transaction.json").exists():
        (control/"drain").unlink(missing_ok=True)


def resume(root):
    (root / "auto-deploy" / "paused.json").unlink(missing_ok=True)


def show_status(root):
    """멈춤·대기·진행 중 작업·적용 버전을 한 번에 보여 줍니다 (읽기만 함)."""
    control = root / "auto-deploy"

    def read(name):
        try:
            return json.loads((control/name).read_text())
        except (OSError, ValueError):
            return None
    since = drain_record(control/"drain")
    out = {
        "paused": read("paused.json"),
        "applied": (read("applied.json") or {}).get("revision"),
        "last_run": read("status.json"),
        "draining_since_seconds": round(time.time() - since) if since else ((control/"drain").exists() or None),
        "mcp_applied": (read("mcp-applied.json") or {}).get("revision"),
        "mcp_failed": read("mcp-failed.json"),
    }
    try:
        token = (control/"control-token").read_text().strip()
        out["backend"] = get_json("http://127.0.0.1:8000/api/_deployment/status", {"X-Deployment-Token": token})
    except (OSError, ValueError, urllib.error.URLError):
        out["backend"] = "unavailable"
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home()/"apps/72hours")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--bootstrap", action="store_true", help="Operator-only first migration; inspect idle state first")
    parser.add_argument("--reviewed-schema-revision", help="Operator-reviewed exact SHA; never set in timer")
    parser.add_argument("--public-url", default=os.environ.get("DEPLOYMENT_PUBLIC_URL"))
    control = parser.add_mutually_exclusive_group()
    control.add_argument("--pause", metavar="REASON", nargs="?", const="",
                         help="자동 배포 멈춤 (예: 시연·테스트 중). 기다리던 새 작업 차단도 바로 풂")
    control.add_argument("--resume", action="store_true", help="자동 배포 다시 켜기 (다음 타이머에 이어서 진행)")
    control.add_argument("--status", action="store_true", help="멈춤·대기·진행 중 작업·적용 버전 보기")
    parser.add_argument("--now", action="store_true",
                        help="운영자 전용: 진행 중 작업이 빌 때까지 기다리지 않고 바로 교체 (진행 중 해석은 끊김). 타이머에는 쓰지 않음")
    args = parser.parse_args()
    os.umask(0o077)
    if args.pause is not None:
        pause(args.root, args.pause)
        print("자동 배포를 멈췄습니다. 다시 켜려면 --resume", flush=True)
        return 0
    if args.resume:
        resume(args.root)
        print("자동 배포를 다시 켰습니다. 다음 타이머(최대 2분)에 이어서 진행합니다.", flush=True)
        return 0
    if args.status:
        show_status(args.root)
        return 0
    deployer = Deployer(args.root)
    try:
        deployer.execute(args)
    except Exception as exc:
        if not deployer.owns_lock:
            print("Deployment lock busy; left the active deployment untouched.", flush=True)
            return 0
        # 교체 중이 아니면 새 작업 차단을 남기지 않습니다 (#151)
        if not deployer.transaction.exists():
            (deployer.control/"drain").unlink(missing_ok=True)
        status = "deferred" if isinstance(exc, Deferred) else "failed"
        # No raw command/env/exception text in the status document or journal.
        deployer.record(status, reason=str(exc) if isinstance(exc, Deferred) else type(exc).__name__)
        return 0 if status == "deferred" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
