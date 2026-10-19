"""Read actual Windows consoles; frozen selection is simulated in source Python."""

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console inheritance")
@pytest.mark.parametrize(
    "launch_mode, frozen",
    [("console", False), ("console", True), ("windowless", False), ("detached", False)],
    ids=["source", "frozen", "source-windowless", "source-detached"],
)
def test_supervised_console_output_and_window_visibility(
    tmp_path, monkeypatch, launch_mode, frozen
):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
    script = tmp_path / "console.py"
    script.write_text(
        dedent(
            """
            import ctypes
            from ctypes import wintypes
            import json
            from pathlib import Path
            import sys

            from arknights_mower.utils import instance_supervisor as supervisor
            from arknights_mower.utils import update_runtime as runtime

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetConsoleWindow.restype = wintypes.HWND
            kernel.GetConsoleProcessList.argtypes = [
                ctypes.POINTER(wintypes.DWORD), wintypes.DWORD
            ]
            if sys.argv[1] == "child":
                if sys.argv[3] == "console":
                    print("mower stdout", flush=True)
                    print("mower stderr", file=sys.stderr, flush=True)
                Path(sys.argv[2]).write_text(
                    json.dumps({"window": bool(kernel.GetConsoleWindow())}),
                    encoding="utf-8",
                )
                supervisor.child_exit("window")
            else:
                directory = Path(sys.argv[2])
                runtime.state_dir = lambda: directory / "updates"
                runtime.frozen = lambda: sys.argv[1] == "frozen"

                class Coord(ctypes.Structure):
                    _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT)]

                kernel.GetStdHandle.argtypes = [wintypes.DWORD]
                kernel.GetStdHandle.restype = wintypes.HANDLE
                kernel.GetConsoleMode.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
                ]
                kernel.ReadConsoleOutputCharacterW.argtypes = [
                    wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
                    Coord, ctypes.POINTER(wintypes.DWORD)
                ]
                console = kernel.GetStdHandle(-11)
                mode = wintypes.DWORD()
                attached = kernel.GetConsoleProcessList((wintypes.DWORD * 1)(), 1)
                if sys.argv[3] != "detached":
                    assert kernel.GetConsoleMode(console, ctypes.byref(mode))
                result = supervisor.supervise(
                    [sys.executable, __file__, "child", str(directory / "child.json"),
                     sys.argv[3]],
                    directory / "supervision",
                    startup_timeout=5,
                    poll_interval=0.01,
                    health_probe=lambda port, timeout: True,
                )
                buffer = ctypes.create_unicode_buffer(4096)
                count = wintypes.DWORD()
                if sys.argv[3] == "console":
                    assert kernel.ReadConsoleOutputCharacterW(
                        console, buffer, len(buffer) - 1,
                        Coord(0, 0), ctypes.byref(count)
                    )
                (directory / "console.json").write_text(
                    json.dumps({
                        "exit_code": result, "output": buffer.value,
                        "attached": bool(attached),
                        "window": bool(kernel.GetConsoleWindow()),
                    }),
                    encoding="utf-8",
                )
            """
        ),
        encoding="utf-8",
    )
    startup = None
    if launch_mode == "console":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    flags = {
        "console": subprocess.CREATE_NEW_CONSOLE,
        "windowless": subprocess.CREATE_NO_WINDOW,
        "detached": subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW,
    }[launch_mode]
    subprocess.run(
        [
            sys.executable,
            str(script),
            "frozen" if frozen else "source",
            str(tmp_path),
            launch_mode,
        ],
        check=True,
        timeout=20,
        creationflags=flags,
        startupinfo=startup,
    )
    report = json.loads((tmp_path / "console.json").read_text(encoding="utf-8"))
    child = json.loads((tmp_path / "child.json").read_text(encoding="utf-8"))
    assert report["exit_code"] == 0
    assert report["attached"] is (launch_mode != "detached")
    assert report["window"] is (launch_mode == "console")
    visible_output = launch_mode == "console" and not frozen
    assert child["window"] is visible_output
    if launch_mode == "console":
        for message in ("mower stdout", "mower stderr"):
            assert (message in report["output"]) is not frozen
