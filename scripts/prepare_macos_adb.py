"""Stage the official macOS ADB binary and its notices for source use/packaging."""

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "36.0.0"
URL = f"https://dl.google.com/android/repository/platform-tools_r{VERSION}-darwin.zip"
SHA256 = "d3e9fa1df3345cf728586908426615a60863d2632f73f1ce14f0f1349ef000fd"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def verify_archive(archive):
    with Path(archive).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != SHA256:
        raise ValueError("macOS platform-tools SHA-256 mismatch")


def prepare_macos_adb(destination=None, archive=None):
    destination = Path(destination or PROJECT_ROOT / "platform-tools")
    if archive is None:
        cache = PROJECT_ROOT / ".cache/macos-adb"
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / f"platform-tools_r{VERSION}-darwin.zip"
        if not archive.exists():
            with tempfile.TemporaryDirectory(dir=cache) as temporary:
                download = Path(temporary) / "platform-tools.zip"
                with (
                    urllib.request.urlopen(URL, timeout=60) as response,
                    download.open("wb") as stream,
                ):
                    shutil.copyfileobj(response, stream)
                verify_archive(download)
                download.replace(archive)
    verify_archive(archive)
    with zipfile.ZipFile(archive) as package:
        files = {
            name: package.read(f"platform-tools/{name}")
            for name in ("adb", "NOTICE.txt", "source.properties")
        }
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = destination / name
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        target.chmod(0o755 if name == "adb" else 0o644)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="use an already downloaded ZIP")
    args = parser.parse_args()
    print(prepare_macos_adb(archive=args.archive))
