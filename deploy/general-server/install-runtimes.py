"""Install pinned, checksum-verified Linux x86_64 tools in the current user's space."""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

CADDY_VERSION = "2.11.7"
NODE_VERSION = "24.19.0"


def download(url: str, target: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as stream:
        shutil.copyfileobj(response, stream)


def unpack_verified(base_url: str, archive: str, checksums: str, destination: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        download(f"{base_url}/{checksums}", work / checksums)
        entries = [line.split() for line in (work / checksums).read_text().splitlines() if line.strip()]
        hashes = [parts[0] for parts in entries if len(parts) == 2 and parts[1].lstrip("*") == archive]
        if len(hashes) != 1:
            raise RuntimeError("Release checksum entry is missing or ambiguous")
        expected = hashes[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}|[0-9a-f]{128}", expected):
            raise RuntimeError("Unsupported checksum format (expected SHA-256 or SHA-512)")
        algorithm = "sha256" if len(expected) == 64 else "sha512"
        download(f"{base_url}/{archive}", work / archive)
        with (work / archive).open("rb") as stream:
            actual = hashlib.file_digest(stream, algorithm).hexdigest()
        if actual != expected:
            raise RuntimeError("Release checksum mismatch; nothing installed")
        staging = work / "unpacked"
        staging.mkdir()
        with tarfile.open(work / archive) as bundle:
            bundle.extractall(staging, filter="data")
        if destination.exists():
            raise RuntimeError("Destination already exists; inspect it instead of overwriting")
        # npm/npx resolve their libraries relative to the symlink's real target.
        shutil.copytree(staging, destination, symlinks=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-node", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("This installer supports Linux x86_64 only")
    root = Path.home() / ".local/share/72hours"
    root.mkdir(parents=True, exist_ok=True)
    release = root / f"caddy-{CADDY_VERSION}"
    if not release.exists():
        unpack_verified(f"https://github.com/caddyserver/caddy/releases/download/v{CADDY_VERSION}",
                        f"caddy_{CADDY_VERSION}_linux_amd64.tar.gz", f"caddy_{CADDY_VERSION}_checksums.txt", release)
    (root / "bin").mkdir(exist_ok=True)
    caddy = release / "caddy"
    if not caddy.is_file():
        raise RuntimeError("Caddy binary missing; inspect existing installation")
    caddy.chmod(0o755)
    link = root / "bin/caddy"
    if link.exists() and not link.is_symlink():
        raise RuntimeError("Refusing to replace an unmanaged Caddy binary")
    temporary_link = link.with_name("caddy.new")
    if temporary_link.is_symlink():
        temporary_link.unlink()
    temporary_link.symlink_to(caddy)
    os.replace(temporary_link, link)
    if args.with_node:
        release = root / f"node-{NODE_VERSION}"
        if not release.exists():
            unpack_verified(f"https://nodejs.org/dist/v{NODE_VERSION}", f"node-v{NODE_VERSION}-linux-x64.tar.xz",
                            "SHASUMS256.txt", release)
        node = release / f"node-v{NODE_VERSION}-linux-x64"
        if not (node / "bin/node").is_file():
            raise RuntimeError("Node binary missing; inspect existing installation")
        environment = {**os.environ, "PATH": str(node / "bin") + os.pathsep + os.environ.get("PATH", "")}
        for command in ("node", "npm", "npx"):
            subprocess.run([str(node / "bin" / command), "--version"], check=True, env=environment)
        link = root / "node"
        if link.exists() and not link.is_symlink():
            raise RuntimeError("Refusing to replace an unmanaged Node directory")
        temporary_link = root / "node.new"
        if temporary_link.is_symlink():
            temporary_link.unlink()
        temporary_link.symlink_to(node, target_is_directory=True)
        os.replace(temporary_link, link)
    print("Runtime installation complete (user scope; official release checksums verified).")


if __name__ == "__main__":
    main()
