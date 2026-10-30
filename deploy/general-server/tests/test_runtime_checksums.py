import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("runtimes", Path(__file__).resolve().parents[1] / "install-runtimes.py")
runtimes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtimes)


class RuntimeIntegrityTests(unittest.TestCase):
    def archive(self, name="binary", content=b"verified test bytes"):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
        return buffer.getvalue()

    def install(self, archive, checksum, destination):
        def fake_download(url, target):
            target.write_bytes(archive if url.endswith("release.tar.gz") else checksum.encode())
        with patch.object(runtimes, "download", side_effect=fake_download):
            runtimes.unpack_verified("https://official.invalid", "release.tar.gz", "checksums.txt", destination)

    def test_sha256_and_sha512_official_formats(self):
        archive = self.archive()
        for algorithm in ("sha256", "sha512"):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "installed"
                digest = hashlib.new(algorithm, archive).hexdigest()
                self.install(archive, digest + "  release.tar.gz\n", destination)
                self.assertEqual((destination / "binary").read_bytes(), b"verified test bytes")

    def test_tampered_or_missing_checksum_never_installs(self):
        archive = self.archive()
        for checksum in ("0" * 64 + "  release.tar.gz", "0" * 128 + "  release.tar.gz",
                         "bad  release.tar.gz", "0" * 64 + "  other.tar.gz"):
            with self.subTest(checksum=checksum[:8]), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "installed"
                with self.assertRaises(RuntimeError):
                    self.install(archive, checksum, destination)
                self.assertFalse(destination.exists())

    def test_archive_cannot_escape_destination(self):
        archive = self.archive("../../outside")
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "installed"
            with self.assertRaises(tarfile.FilterError):
                self.install(archive, digest + "  release.tar.gz", destination)
            self.assertFalse(destination.exists())

    @unittest.skipIf(os.name == "nt", "Production Linux symlinks require Windows privileges")
    def test_relative_cli_symlink_survives_installation(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
            content = b"cli content"
            info = tarfile.TarInfo("lib/npm/bin/npm-cli.js")
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
            link = tarfile.TarInfo("bin/npm")
            link.type = tarfile.SYMTYPE
            link.linkname = "../lib/npm/bin/npm-cli.js"
            bundle.addfile(link)
        archive = buffer.getvalue()
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "installed"
            self.install(archive, digest + "  release.tar.gz", destination)
            self.assertTrue((destination / "bin/npm").is_symlink())
            self.assertEqual((destination / "bin/npm").resolve(), destination / "lib/npm/bin/npm-cli.js")
            self.assertEqual((destination / "bin/npm").read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
