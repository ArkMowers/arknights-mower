"""Synthetic command retains inherited output until the test releases it."""

import json
import os
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def wait_for(path, timeout=15, *, cancel=None):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if cancel is not None and cancel.exists():
            return False
        if time.monotonic() >= deadline:
            raise TimeoutError(str(path))
        time.sleep(0.01)
    return True


def main():
    mode, folder, outcome = sys.argv[1:4]
    folder = Path(folder)
    if mode in {"descendant", "writer"}:
        (folder / "descendant.ready").touch()
        try:
            if mode == "writer":
                for channel, descriptor in (("stdout", 1), ("stderr", 2)):
                    if not wait_for(
                        folder / f"write.{channel}", cancel=folder / "release"
                    ):
                        return
                    os.write(descriptor, f"descendant {channel}\n".encode())
                    (folder / f"wrote.{channel}").touch()
            wait_for(folder / "release")
        finally:
            (folder / "descendant.stopped").touch()
        return
    if mode in {"command", "writer_command"}:
        subprocess.Popen(
            [
                sys.executable,
                "-B",
                __file__,
                "writer" if mode == "writer_command" else "descendant",
                str(folder),
                outcome,
            ],
            stdin=subprocess.DEVNULL,
            stdout=sys.stdout,
            stderr=sys.stderr,
            close_fds=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        wait_for(folder / "descendant.ready")
        os.write(1, b"command stdout\n")
        os.write(2, b"command stderr\n")
        if outcome == "timeout":
            time.sleep(15)
        elif outcome == "failure":
            sys.exit(7)
        return

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from arknights_mower.utils.config.device_profile import DeviceProfile
    from arknights_mower.utils.device import manager_io, preflight_io
    from arknights_mower.utils.device.adb_client import server, shared
    from arknights_mower.utils.device.mumu12ipc import input as mumu_input

    adapter = sys.argv[4]
    argv = [sys.executable, "-B", __file__, "command", str(folder), outcome]
    processes, streams = [], []
    original = subprocess.Popen

    def spawn(command, **kwargs):
        if command[0] in {"synthetic-adb", "synthetic-manager"}:
            command = argv
        streams.extend(
            stream
            for stream in (kwargs.get("stdout"), kwargs.get("stderr"))
            if hasattr(stream, "fileno")
        )
        process = original(command, **kwargs)
        processes.append(process)
        return process

    manager_io.subprocess.Popen = spawn
    # The synthetic command needs about 0.4 s to start and hand over its
    # inherited handles, so the deadline keeps a margin above that while still
    # staying far below the descendant's fifteen-second hold.
    preflight_io.COMMAND_TIMEOUT = 1.0
    if adapter == "adb":
        server.probe_adb_server = lambda *args, **kwargs: None
        operation = partial(preflight_io.ProductionPreflightIO()._run_adb, argv)
    elif adapter == "guard_version":
        operation = partial(server.adb_client_version, "synthetic-adb", timeout=1.0)
    elif adapter == "shared_start":
        coordinator = shared.SharedADBRecovery(probe=lambda timeout: None)

        def operation():
            return coordinator._start("synthetic-adb", 41, time.monotonic() + 1.0, None)
    elif adapter == "mumu_input":
        mumu_input.resolve_mumu_paths = lambda *args: (
            "synthetic-root",
            "synthetic-manager",
        )
        mumu_input.io_timeout = lambda maximum: min(1.0, maximum)
        mumu_input.multiprocessing.get_context = Mock()
        device = SimpleNamespace(profile=DeviceProfile(instance_id="1"))
        operation = partial(mumu_input.MuMuInputSession, device)
    else:
        operation = partial(preflight_io.ProductionPreflightIO()._run, argv)
    (folder / "probe.ready").touch()
    wait_for(folder / "go")
    started = time.monotonic()
    try:
        output = operation()
        result = {"stdout": output.decode(), "error": None}
    except Exception as exc:
        result = {"error": type(exc).__name__}
    result["elapsed"] = time.monotonic() - started
    result["reaped"] = all(process.poll() is not None for process in processes)
    result["streams_closed"] = bool(streams) and all(
        stream.closed for stream in streams
    )
    if adapter == "mumu_input":
        result["worker_started"] = mumu_input.multiprocessing.get_context.called
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
