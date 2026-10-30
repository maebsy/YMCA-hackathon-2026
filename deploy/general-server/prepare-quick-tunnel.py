"""Explicit opt-in: prepare Cloudflare Quick Tunnel, without starting/publicizing it.

Run on the general server only after authorization to send demo traffic through Cloudflare.
Requires Python 3.12 and libc bcrypt support. No cloud account or vLLM credential is used.
"""

import crypt
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import tempfile
import urllib.request

VERSION = "2026.10.7"
# Official GitHub release asset digest, pinned with the binary version.
SHA256 = "1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872"


def write_private(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(text)
    path.chmod(0o600)


def main() -> None:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise SystemExit("Linux x86_64 only")
    if crypt.METHOD_BLOWFISH not in crypt.methods:
        raise SystemExit("bcrypt unavailable; do not publish without an authentication hash")
    home = Path.home()
    config = home / ".config/72hours"
    config.mkdir(parents=True, exist_ok=True, mode=0o700)
    config.chmod(0o700)
    root = home / ".local/share/72hours"
    root.mkdir(parents=True, exist_ok=True)
    binary = root / f"cloudflared-{VERSION}"
    if not binary.exists():
        with tempfile.TemporaryDirectory(dir=root) as directory:
            temporary = Path(directory) / "cloudflared"
            url = f"https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-linux-amd64"
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            with temporary.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != SHA256:
                    raise RuntimeError("cloudflared checksum mismatch; not installed")
            temporary.chmod(0o755)
            os.replace(temporary, binary)
    with binary.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != SHA256:
            raise RuntimeError("Existing cloudflared does not match pinned release")
    (root / "bin").mkdir(exist_ok=True)
    link = root / "bin/cloudflared"
    if link.exists() and not link.is_symlink():
        raise RuntimeError("Refusing to overwrite unmanaged binary")
    if link.is_symlink():
        link.unlink()
    link.symlink_to(binary)

    credentials = config / "demo-access.json"
    if credentials.exists():
        access = json.loads(credentials.read_text())
        credentials.chmod(0o600)
    else:
        access = {"username": "demo", "password": secrets.token_urlsafe(24)}
        write_private(credentials, json.dumps(access))
    if access.get("username") != "demo" or not isinstance(access.get("password"), str) or len(access["password"]) < 24:
        raise RuntimeError("Invalid existing demo credentials; inspect privately")
    password_hash = crypt.crypt(access["password"], crypt.mksalt(crypt.METHOD_BLOWFISH))
    if not password_hash or not password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        raise RuntimeError("Unable to create bcrypt hash")
    write_private(config / "quick-web.env", f"DEMO_USER=demo\nDEMO_PASSWORD_HASH={password_hash}\n")
    source = Path(__file__).resolve().parent
    runtime = home / "apps/72hours/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "Caddyfile.quick", runtime / "Caddyfile.quick")
    units = home / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    for name in ("72hours-quick-web.service", "72hours-quick-tunnel.service"):
        shutil.copyfile(source / "systemd" / name, units / name)
    subprocess.run([str(root / "bin/caddy"), "validate", "--config", str(runtime / "Caddyfile.quick"),
                    "--adapter", "caddyfile"], check=True,
                   env={**os.environ, "DEMO_USER": "demo", "DEMO_PASSWORD_HASH": password_hash})
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print("Prepared; not started. Demo credentials are in ~/.config/72hours/demo-access.json (600).")


if __name__ == "__main__":
    main()
