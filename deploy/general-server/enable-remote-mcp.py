"""Add the separately deployed MCP to the managed origin without restarting its tunnel."""
import fcntl
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

BLOCK = """\t# 72hours independent remote MCP
\t@mcp path /mcp /mcp/*
\thandle @mcp {
\t\theader Cache-Control \"no-store\"
\t\treverse_proxy 127.0.0.1:8765
\t}
"""


def with_mcp(original):
    if BLOCK in original:
        return original
    marker = "\t@api path /api /api/*\n"
    if original.count(marker) != 1 or "/mcp" in original:
        raise ValueError("Unexpected or existing MCP configuration; inspect before applying")
    return original.replace(marker, BLOCK + marker, 1)


def main():
    runtime = Path.home() / "apps/72hours/runtime"
    config = runtime / "Caddyfile.quick"
    binary = Path.home() / ".local/share/72hours/bin/caddy"
    version = subprocess.check_output([str(binary), "version"], text=True)
    match = re.match(r"v(\d+)\.(\d+)\.", version)
    if not match or tuple(map(int, match.groups())) < (2, 11):
        raise RuntimeError("Caddy 2.11+ is required for signal-based reload")
    with (runtime / "quick-web-access.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        def pid(service):
            value = int(subprocess.check_output(["systemctl", "--user", "show", service,
                        "--property=MainPID", "--value"], text=True))
            if not value:
                raise RuntimeError(f"{service} is not running")
            return value

        services = ["72hours-quick-web", "72hours-quick-tunnel", "72hours-backend", "72hours-frontend"]
        before = {service: pid(service) for service in services}
        argv = Path(f"/proc/{before['72hours-quick-web']}/cmdline").read_bytes().decode().split("\0")
        if "--config" not in argv or argv[argv.index("--config") + 1] != str(config) or "--resume" in argv:
            raise RuntimeError("Unexpected Caddy startup configuration")
        original = config.read_text()
        if "admin off" not in original:
            raise RuntimeError("Expected managed admin-off configuration")
        candidate = with_mcp(original)
        temporary = config.with_name("Caddyfile.quick.mcp-candidate")
        temporary.write_text(candidate)
        temporary.chmod(0o600)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def check(port, route):
            with opener.open(f"http://127.0.0.1:{port}{route}", timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError(f"Health check failed: {route}")

        def reload():
            subprocess.run(["systemctl", "--user", "kill", "--kill-whom=main", "--signal=USR1",
                            "72hours-quick-web"], check=True)
            time.sleep(1)

        try:
            check(8765, "/mcp/health")
            subprocess.run([str(binary), "validate", "--config", str(temporary), "--adapter", "caddyfile"], check=True)
            backup = config.with_name(f"Caddyfile.quick.before-mcp-{time.time_ns()}")
            backup.write_text(original)
            backup.chmod(0o600)
            temporary.replace(config)
            try:
                reload()
                for route in ("/", "/api/health", "/healthz", "/mcp/health", "/mcp/connect"):
                    check(8088, route)
                if before != {service: pid(service) for service in services}:
                    raise RuntimeError("Existing service PID changed")
            except Exception:
                config.write_text(original)
                reload()
                raise
            print(json.dumps({"enabled": True, "existing_pids": before, "backup": str(backup)}))
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
