"""Build and export the Linux ARM64 Python environment used by Android hosts."""

import argparse
import json
import lzma
import posixpath
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pack_rootfs(source: Path, output: Path) -> None:
    links = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        stored = Path(temporary) / "runtime.zip"
        with tarfile.open(source) as archive, zipfile.ZipFile(stored, "w") as target:
            for member in archive:
                name = member.name.removeprefix("./")
                parts = Path(name).parts
                if not name or name in ("etc/hosts", "etc/resolv.conf"):
                    continue
                if name.startswith(
                    (
                        "dev/",
                        "proc/",
                        "sys/",
                        "tmp/",
                        "root/",
                        "mower/",
                        "mower-data/",
                        "usr/share/man/",
                        "usr/local/include/",
                    )
                ):
                    continue
                if any(
                    part in ("__pycache__", "tests", "test", ".pytest_cache")
                    for part in parts
                ) or name.endswith((".pyc", ".pyo", "/ddddocr/common.onnx")):
                    continue
                # Keep distribution copyrights and package licence metadata.
                if name.startswith("usr/share/doc/") and not name.endswith(
                    "/copyright"
                ):
                    continue
                if member.issym():
                    links[name] = member.linkname
                elif member.islnk():
                    links[name] = posixpath.relpath(
                        member.linkname, posixpath.dirname(name)
                    )
                elif member.isfile():
                    info = zipfile.ZipInfo(name)
                    info.external_attr = (member.mode | 0o100000) << 16
                    with (
                        archive.extractfile(member) as stream,
                        target.open(info, "w") as destination,
                    ):
                        shutil.copyfileobj(stream, destination)
            target.writestr(
                "etc/resolv.conf", "nameserver 223.5.5.5\nnameserver 1.1.1.1\n"
            )
            target.writestr("etc/hosts", "127.0.0.1 localhost\n::1 localhost\n")
            for name in (
                "mower/",
                "mower-data/",
                "dev/",
                "proc/",
                "sys/",
                "tmp/",
                "root/",
                "bridge/",
                "host-dev/",
                "host-proc/",
            ):
                target.writestr(name, "")
            target.writestr(".symlinks.json", json.dumps(links))
        pending = output.with_suffix(".tmp")
        try:
            if shutil.which("xz"):
                with pending.open("wb") as destination:
                    subprocess.run(
                        ["xz", "-T2", "-6", "--stdout", str(stored)],
                        stdout=destination,
                        check=True,
                    )
            else:
                with (
                    stored.open("rb") as source_stream,
                    lzma.open(pending, "wb", preset=6) as destination,
                ):
                    shutil.copyfileobj(source_stream, destination, 1024 * 1024)
            pending.replace(output)
        finally:
            pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/python-runtime.zip.xz"
    )
    args = parser.parse_args()
    image = "mower-android-update-runtime:build"
    subprocess.run(
        [
            "docker",
            "build",
            "--platform",
            "linux/arm64",
            "-f",
            "scripts/android-runtime.Dockerfile",
            "-t",
            image,
            ".",
        ],
        cwd=ROOT,
        check=True,
    )
    # Test the actual release image, including native dependencies, on ARM64.
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            image,
            "python",
            "-c",
            "import platform, ssl, cv2, numpy, onnxruntime, rjieba, yamlcore, flask; from pyzbar.pyzbar import decode; assert platform.machine() == 'aarch64'; assert cv2.__version__ == '4.9.0'; print(platform.python_version())",
        ],
        check=True,
    )
    container = subprocess.check_output(
        ["docker", "create", "--platform", "linux/arm64", image], text=True
    ).strip()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "rootfs.tar"
            subprocess.run(
                ["docker", "export", "-o", str(archive), container], check=True
            )
            pack_rootfs(archive, args.output)
    finally:
        subprocess.run(
            ["docker", "rm", container], check=True, stdout=subprocess.DEVNULL
        )

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            "-v",
            f"{args.output.resolve()}:/runtime.zip.xz:ro",
            "-v",
            f"{ROOT / 'scripts/smoke_android_runtime.py'}:/smoke.py:ro",
            image,
            "python",
            "/smoke.py",
            "/runtime.zip.xz",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
