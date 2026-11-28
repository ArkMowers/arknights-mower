"""Offline child failures for the production JPEG transport."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

from arknights_mower.utils import jpeg_worker


def hang(mode):
    marker = os.environ.get("MOWER_JPEG_FIXTURE_MARKER")
    owned = {"pid": os.getpid()}
    if mode in ("native_hang", "startup_native_hang"):
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        owned["descendant_pid"] = descendant.pid
    if marker:
        Path(marker).write_text(json.dumps(owned), encoding="utf-8")
    if mode in ("native_hang", "startup_native_hang"):
        import ctypes

        # PyDLL deliberately retains the GIL, so the Python EOF watcher cannot run.
        sleep = ctypes.PyDLL("kernel32").Sleep
        sleep.argtypes = [ctypes.c_ulong]
        sleep.restype = None
        sleep(0xFFFFFFFF)
    Event().wait(10)
    raise TimeoutError("fixture hang returned")


def main(mode, mapping_path, port, token):
    if mode in ("parent", "parent_native", "parent_startup_native"):
        from threading import Thread

        import numpy as np

        from arknights_mower.utils.screenshot_encoding import ScreenshotEncoding

        child_mode = {
            "parent": "hang",
            "parent_native": "native_hang",
            "parent_startup_native": "startup_native_hang",
        }[mode]
        marker = str(Path(mapping_path).with_suffix(".worker.json"))
        os.environ["MOWER_JPEG_FIXTURE_MARKER"] = marker

        def command(path, address, secret):
            return [
                sys.executable,
                "-m",
                __spec__.name,
                child_mode,
                str(path),
                str(address),
                secret,
            ]

        bank = ScreenshotEncoding(command_factory=command)
        Thread(
            target=lambda: bank.encode(np.zeros((32, 48, 3), np.uint8)), daemon=True
        ).start()
        deadline = time.monotonic() + 5
        while not Path(marker).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        slot = bank._slots[0]
        owned = json.loads(Path(marker).read_text(encoding="utf-8"))
        Path(mapping_path).write_text(
            json.dumps(
                {
                    "pid": slot._process.pid,
                    "mapping": str(slot._mapping_path),
                    "child_pid": owned["pid"],
                    "descendant_pid": owned.get("descendant_pid"),
                }
            ),
            encoding="utf-8",
        )
        Event().wait(10)
        return
    if mode == "startup_exit":
        os._exit(23)
    if mode == "slow_start":
        time.sleep(5)
    if mode == "wrapper_exit":
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                __spec__.name,
                "startup_native_hang",
                mapping_path,
                port,
                token,
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        marker = Path(os.environ["MOWER_JPEG_FIXTURE_MARKER"])
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        os._exit(23)
    if mode == "startup_native_hang":
        hang(mode)
    if mode in ("partial", "dribble", "oversized", "bad_jpeg"):
        with socket.create_connection(("127.0.0.1", int(port))) as channel:
            channel.sendall(token.encode("ascii"))
            jpeg_worker.receive_exact(channel, jpeg_worker.REQUEST.size)
            if mode == "oversized":
                channel.sendall(
                    jpeg_worker.RESPONSE.pack(0, jpeg_worker.MAX_JPEG_BYTES + 1)
                )
            elif mode == "bad_jpeg":
                channel.sendall(jpeg_worker.RESPONSE.pack(0, 4))
            else:
                reply = jpeg_worker.RESPONSE.pack(0, 1)
                for byte in reply if mode == "dribble" else reply[:1]:
                    channel.sendall(bytes([byte]))
                    time.sleep(0.15)
            Event().wait(10)
        return
    if mode in ("exit", "hang", "error", "native_hang"):

        def fail(*args, **kwargs):
            if mode == "exit":
                os._exit(23)
            if mode == "error":
                raise MemoryError("offline allocation failure")
            hang(mode)

        jpeg_worker.encode_packed = fail
    if mode == "lean":
        unwanted = {"cv2", "numpy", "server", "arknights_mower.utils.config"}
        if unwanted.intersection(sys.modules):
            os._exit(24)
    jpeg_worker.worker_main(mapping_path, port, token)


if __name__ == "__main__":
    main(*sys.argv[1:])
