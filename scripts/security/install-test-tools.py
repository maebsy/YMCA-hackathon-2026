"""Install checksum-pinned Windows scanners in a dedicated test directory, never global PATH."""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import urllib.request
import zipfile

ASSETS = (
    ("https://github.com/opengrep/opengrep/releases/download/v1.33.1/opengrep_windows_x86.exe",
     "132e606e071bdd3928286fddc893198a6106a90820d46e21197e0ace1a23e0c1"),
    ("https://github.com/google/osv-scanner/releases/download/v2.7.0/osv-scanner_windows_amd64.exe",
     "9964ed64ec9a387391eb4cc006ad5c531154821aef29b793e02c448de4686438"),
    ("https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_windows_x64.zip",
     "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Windows x64 test runtime only")
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for url, expected in ASSETS:
        archive = root / url.rsplit("/", 1)[1]
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as stream:
                shutil.copyfileobj(response, stream)
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise RuntimeError("Official release digest mismatch; refusing to execute")
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as bundle:
                binary = bundle.read("gitleaks.exe")
            destination = root / "gitleaks.exe"
            if destination.exists() and destination.read_bytes() != binary:
                raise RuntimeError("Refusing to overwrite another Gitleaks binary")
            destination.write_bytes(binary)
        print("Verified", archive.name)


if __name__ == "__main__":
    main()
