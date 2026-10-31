"""Explicitly open the existing demo to anonymous visitors, without restarting its tunnel.

Run only after the operator has approved public, account-free web/API use.
Requires the managed Caddy 2.11+ service. Does not change backend/GPU settings.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request


AUTH_BLOCK = "\tbasic_auth {\n\t\t{$DEMO_USER} {$DEMO_PASSWORD_HASH}\n\t}\n"


def without_login(config):
    if config.count(AUTH_BLOCK) != 1:
        raise ValueError("Expected exactly the managed demo basic_auth block; inspect configuration")
    return config.replace(AUTH_BLOCK, "", 1)


def main():
    root = Path.home() / "apps/72hours/runtime"
    config = root / "Caddyfile.quick"
    binary = Path.home() / ".local/share/72hours/bin/caddy"
    lock = (root / "quick-web-access.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    version = subprocess.check_output([str(binary), "version"], text=True)
    match = re.match(r"v(\d+)\.(\d+)\.", version)
    if not match or tuple(map(int, match.groups())) < (2, 11):
        raise RuntimeError("Caddy 2.11+ is required for a signal-based reload")

    def pid(service):
        value = int(subprocess.check_output(
            ["systemctl", "--user", "show", service, "--property=MainPID", "--value"], text=True))
        if value <= 0:
            raise RuntimeError(f"Service is not running: {service}")
        return value

    web_pid, tunnel_pid = pid("72hours-quick-web"), pid("72hours-quick-tunnel")
    argv = Path(f"/proc/{web_pid}/cmdline").read_bytes().decode().split("\0")
    if "--resume" in argv or "--config" not in argv or argv[argv.index("--config") + 1] != str(config):
        raise RuntimeError("Unexpected Caddy startup configuration; no changes applied")
    original = config.read_text()
    if "admin off" not in original:
        raise RuntimeError("Expected managed admin-off config; inspect before signal reload")
    candidate = without_login(original)
    temporary = config.with_name("Caddyfile.quick.public-candidate")
    backup = config.with_name(f"Caddyfile.quick.before-public-{time.time_ns()}")

    def write_private(path, content):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content)

    def reload_config():
        subprocess.run(["systemctl", "--user", "kill", "--kill-whom=main", "--signal=USR1",
                        "72hours-quick-web"], check=True)

    def check_public():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for route in ("/", "/api/health", "/healthz"):
            with opener.open("http://127.0.0.1:8088" + route, timeout=10) as response:
                if response.status != 200 or response.headers.get("WWW-Authenticate"):
                    raise RuntimeError("Anonymous access not ready")

    write_private(temporary, candidate)
    try:
        subprocess.run([str(binary), "validate", "--config", str(temporary), "--adapter", "caddyfile"], check=True)
        write_private(backup, original)
        temporary.replace(config)
        try:
            reload_config()
            for attempt in range(10):
                try:
                    check_public()
                    break
                except Exception:
                    if attempt == 9:
                        raise
                    time.sleep(1)
            if pid("72hours-quick-web") != web_pid or pid("72hours-quick-tunnel") != tunnel_pid:
                raise RuntimeError("A service restarted unexpectedly")
        except Exception:
            write_private(temporary, original)
            temporary.replace(config)
            reload_config()
            raise
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({"anonymous_access": True, "web_pid": web_pid, "tunnel_pid": tunnel_pid,
                      "backup": str(backup)}))


if __name__ == "__main__":
    main()
