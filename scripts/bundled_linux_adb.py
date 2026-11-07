"""Collect the build runner's native ADB and make its bundled libraries relocatable."""

import shutil
import subprocess
from pathlib import Path


def linux_adb_assets():
    executable = shutil.which("adb")
    if not executable:
        raise FileNotFoundError("Install the adb package before building the Linux app")
    notices = (
        Path("/usr/share/doc/adb/copyright"),
        Path(executable).resolve().parent / "NOTICE.txt",
    )
    notice = next((path for path in notices if path.is_file()), None)
    if notice is None:
        raise FileNotFoundError("ADB license notice is missing")
    # Listing ADB as a binary lets PyInstaller collect its shared dependencies.
    return [(executable, "platform-tools")], [(str(notice), "platform-tools")]


def configure_linux_adb(bundle):
    executable = Path(bundle) / "_internal/platform-tools/adb"
    # RPATH also applies to ADB's indirect dependencies in _internal, so it can
    # run outside the parent Python process without relying on LD_LIBRARY_PATH.
    subprocess.run(
        ["patchelf", "--force-rpath", "--set-rpath", "$ORIGIN/..", str(executable)],
        check=True,
    )
