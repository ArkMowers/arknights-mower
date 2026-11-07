"""Windows desktop helpers leave when an owned controller terminates natively."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from arknights_mower.utils.instance_supervisor import (
    OwnedWindowsProcess,
    WindowsInstanceJob,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process ownership")
@pytest.mark.parametrize("role", ["splash", "tray", "window"])
def test_actual_desktop_launch_reaps_helper_after_native_parent_exit(tmp_path, role):
    marker = tmp_path / f"{role}.json"
    job = WindowsInstanceJob()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "arknights_mower.tests.desktop_parent_death_fixture",
            role,
            str(marker),
        ],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | 0x00000004,
    )
    parent = helper = None
    try:
        job.start(process)
        deadline = time.monotonic() + 12
        while not marker.exists():
            if time.monotonic() >= deadline:
                pytest.fail("temporary desktop helper did not become ready")
            time.sleep(0.01)
        values = json.loads(marker.read_text(encoding="utf-8"))
        parent = OwnedWindowsProcess(values["parent"], job)
        helper = OwnedWindowsProcess(values["helper"], job)
        assert parent.poll() is None
        assert helper.poll() is None
        parent.stop()
        deadline = time.monotonic() + 3
        while helper.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert helper.poll() == 0, "desktop helper survived its crashed controller"
    finally:
        for owned in (helper, parent):
            if owned is not None:
                if owned.poll() is None:
                    owned.stop()
                owned.close()
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=3)
        job.close()
