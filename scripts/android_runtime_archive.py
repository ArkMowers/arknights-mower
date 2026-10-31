"""Inspect the Python rootfs shared by the Android builder and release validator."""

import hashlib
import json
import lzma
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

RUNTIME_FILE = "python-runtime.zip.xz"


def runtime_metadata(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("missing Python runtime archive")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with tempfile.TemporaryFile() as expanded:
        with lzma.open(path, "rb") as stream:
            shutil.copyfileobj(stream, expanded, 1024 * 1024)
        expanded.seek(0)
        with zipfile.ZipFile(expanded) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.testzip() is not None:
                raise ValueError("invalid Python runtime ZIP")
            for name in names:
                parts = PurePosixPath(name)
                if parts.is_absolute() or ".." in parts.parts or "\\" in name:
                    raise ValueError("unsafe Python runtime path")
                if (
                    name.startswith(("mower/", "mower-data/"))
                    and not name.endswith("/")
                ) or "mower_android" in parts.parts:
                    raise ValueError("runtime contains application or user data")
            binaries = [
                name
                for name in names
                if re.fullmatch(r"usr/local/bin/python3\.\d+", name)
            ]
            if len(binaries) != 1:
                raise ValueError("missing or ambiguous Python interpreter")
            binary = archive.read(binaries[0])
            if (
                len(binary) < 20
                or binary[:6] != b"\x7fELF\x02\x01"
                or int.from_bytes(binary[18:20], "little") != 183
            ):
                raise ValueError("Python interpreter must be Linux ARM64 ELF")
            python = binaries[0].removeprefix("usr/local/bin/python")
            for required in (
                "usr/lib/os-release",
                "etc/ssl/certs/ca-certificates.crt",
                ".symlinks.json",
            ):
                if not archive.read(required).strip():
                    raise ValueError(f"empty Python runtime file: {required}")
            links = json.loads(archive.read(".symlinks.json"))
            if not isinstance(links, dict):
                raise ValueError("invalid runtime symlink map")
            for name, target in links.items():
                parts = PurePosixPath(name)
                if (
                    not isinstance(target, str)
                    or parts.is_absolute()
                    or ".." in parts.parts
                    or "\\" in name
                    or name in names
                ):
                    raise ValueError("invalid runtime symlink entry")
            unpacked = sum(info.file_size for info in archive.infolist())
    return {
        "python": python,
        "runtime": {"file": RUNTIME_FILE, "sha256": digest, "unpacked_size": unpacked},
    }
