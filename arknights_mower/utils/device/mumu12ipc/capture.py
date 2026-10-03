"""A persistent owned process bounds native MuMu screenshot calls."""

import ctypes

import numpy as np

from arknights_mower.utils.device.mumu12ipc.core import (
    MuMu12IPC,
    MuMuIpcError,
    bind_display,
    capture_native_frame,
)
from arknights_mower.utils.device.mumu12ipc.paths import resolve_mumu_paths
from arknights_mower.utils.device.native_capture import NativeCaptureSession


def _capture_worker(root, instance, package, frame_buffer, channel):
    """Keep all potentially blocking vendor calls in one owned process."""
    ipc = object.__new__(MuMu12IPC)
    ipc._conn = 0
    ipc._dll = None
    try:
        ipc._emu_root = root
        ipc._load_renderer()
        connection = ipc._dll.nemu_connect(root, int(instance))
        if connection <= 0:
            raise MuMuIpcError(
                f"MuMu IPC 连接失败：原生返回码 {connection}",
                return_code=connection,
            )
        ipc._conn = connection
        display = bind_display(ipc._dll, connection, package)
        buffer = (ctypes.c_ubyte * (1920 * 1080 * 4))()
        output = np.frombuffer(frame_buffer, np.uint8).reshape(1080, 1920, 3)
        while channel.recv() == "capture":
            frame = capture_native_frame(ipc._dll, connection, display, buffer)
            np.copyto(output, frame)
            channel.send(("ok", "", None, None))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            channel.send(
                (
                    "error",
                    str(exc).encode("utf-8")[:1024].decode("utf-8", "ignore"),
                    getattr(exc, "return_code", None),
                    getattr(exc, "actual_size", None),
                )
            )
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        try:
            if ipc._conn > 0:
                ipc._dll.nemu_disconnect(ipc._conn)
        finally:
            channel.close()


class MuMuCaptureSession(NativeCaptureSession):
    """Keep MuMu's vendor contract in the shared owned-process lifecycle."""

    def __init__(self, profile):
        root, _ = resolve_mumu_paths(profile.installation_path, profile.manager_path)
        super().__init__(
            _capture_worker,
            (root, profile.instance_id, profile.game_package),
            label="MuMu IPC",
            error_type=MuMuIpcError,
        )
