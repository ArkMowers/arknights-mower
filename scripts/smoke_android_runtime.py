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
                'import ssl, cv2, numpy, onnxruntime, rjieba, yamlcore, flask; from pyzbar.pyzbar import decode; print("Exported ARM64 Python runtime imports passed")',
            ],
            check=True,
        )


if __name__ == "__main__":
    smoke(Path(sys.argv[1]))
