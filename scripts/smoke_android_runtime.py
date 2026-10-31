"""Run inside the build container to test the exact exported and pruned rootfs."""

import json
import lzma
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RUNTIME_SMOKE_CODE = """
import platform
import re
import ssl
from importlib import metadata

import cv2
import numpy
import onnxruntime
import rjieba
import yamlcore
import flask
import quickjs
from pyzbar.pyzbar import decode

opencv_names = {
    "opencv-python", "opencv-python-headless",
    "opencv-contrib-python", "opencv-contrib-python-headless",
}
installed = []
for distribution in metadata.distributions():
    name = re.sub(r"[-_.]+", "-", distribution.metadata.get("Name", "")).lower()
    if name in opencv_names:
        installed.append((name, distribution.version))
assert installed == [("opencv-python-headless", "4.11.0.86")], installed
assert cv2.__version__ == "4.11.0", cv2.__version__
assert platform.machine() == "aarch64", platform.machine()
gray = numpy.zeros((32, 32), dtype=numpy.uint8)
color = numpy.zeros((32, 32, 3), dtype=numpy.uint8)
cv2.blur(gray, (7, 7))
cv2.cvtColor(color, cv2.COLOR_RGB2GRAY)
cv2.matchTemplate(gray, gray[:8, :8], cv2.TM_CCOEFF_NORMED)
cv2.ORB_create().detectAndCompute(gray, None)
assert quickjs.Context().eval("1+1") == 2
print("ARM64 Python runtime imports and OpenCV checks passed")
"""


def smoke(archive_path: Path):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "rootfs"
        root.mkdir()
        with tempfile.TemporaryFile() as stored:
            with lzma.open(archive_path, "rb") as source:
                shutil.copyfileobj(source, stored)
            stored.seek(0)
            with zipfile.ZipFile(stored) as archive:
                archive.extractall(root)
                for info in archive.infolist():
                    mode = info.external_attr >> 16 & 0o777
                    if mode:
                        (root / info.filename).chmod(mode)
        # Only trusted build output is accepted by this build-time smoke checker.
        # Android's installer performs its own path and link validation.
        links = json.loads((root / ".symlinks.json").read_text())
        for name, target in links.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, path)
        # The Android host binds /dev into the runtime. Reproduce /dev/null
        # for ctypes.find_library subprocesses in this isolated chroot.
        os.mknod(root / "dev/null", stat.S_IFCHR | 0o666, os.makedev(1, 3))
        subprocess.run(
            [
                "chroot",
                str(root),
                "/usr/local/bin/python",
                "-c",
                RUNTIME_SMOKE_CODE,
            ],
            check=True,
        )


if __name__ == "__main__":
    smoke(Path(sys.argv[1]))
