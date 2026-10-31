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
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

REPO = "maebsy/YMCA-hackathon-2026"
REPO_URL = f"https://github.com/{REPO}.git"
SHA = re.compile(r"[0-9a-f]{40}")


class Deferred(RuntimeError):
    pass


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

    def drain(self, bootstrap=False):
        self.stage = "drain"
        headers = {"X-Deployment-Token": (self.control/"control-token").read_text().strip()}
        (self.control/"drain").touch()
        for _ in range(30):
            try:
                data = get_json("http://127.0.0.1:8000/api/_deployment/status", headers)
            except urllib.error.HTTPError as exc:
                legacy = not (self.target(self.root/"current")/"deployment.json").exists()
                if exc.code == 404 and bootstrap and legacy:
                    return  # Manual one-time migration from a pre-guard server; never enabled in timer.
                raise Deferred("Backend deployment guard unavailable") from None
            if data.get("draining") is True and data.get("busy") == 0:
                return
            time.sleep(2)
        raise Deferred("Active jobs: retry next timer without cancelling them")

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

    def execute(self, args):
        with locks([self.control/"deploy.lock", self.root/"frontend-deploy.lock"]):
            self.owns_lock = True
            if self.transaction.exists():
                self.stage = "recover_interrupted_switch"
                self.rollback()
            (self.control/"drain").unlink(missing_ok=True)
            self.revision = self.head()
            if self.state.exists():
                previous = json.loads(self.state.read_text())
                if previous.get("revision") == self.revision and previous["status"] == "failed" and not args.retry:
                    return
            applied = self.control/"applied.json"
            if applied.exists() and json.loads(applied.read_text()).get("revision") == self.revision and not args.retry:
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
                self.drain(args.bootstrap)
                self.activate(release, args.public_url)
            self.log = None
            self.record("deployed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home()/"apps/72hours")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--bootstrap", action="store_true", help="Operator-only first migration; inspect idle state first")
    parser.add_argument("--reviewed-schema-revision", help="Operator-reviewed exact SHA; never set in timer")
    parser.add_argument("--public-url", default=os.environ.get("DEPLOYMENT_PUBLIC_URL"))
    args = parser.parse_args()
    os.umask(0o077)
    deployer = Deployer(args.root)
    try:
        deployer.execute(args)
    except Exception as exc:
        if not deployer.owns_lock:
            print("Deployment lock busy; left the active deployment untouched.", flush=True)
            return 0
        if not deployer.transaction.exists():
            (deployer.control/"drain").unlink(missing_ok=True)
        status = "deferred" if isinstance(exc, Deferred) else "failed"
        # No raw command/env/exception text in the status document or journal.
        deployer.record(status, reason=str(exc) if isinstance(exc, Deferred) else type(exc).__name__)
        return 0 if status == "deferred" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
