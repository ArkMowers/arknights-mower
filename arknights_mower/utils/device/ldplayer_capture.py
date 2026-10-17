"""LD screenshot enhancement binds its vendor object to one verified instance."""

import ctypes
import os
import platform
import subprocess
import time
from threading import Event, Lock, RLock

import numpy as np

from arknights_mower.utils.config.device_profile import capture_compatibility_error
from arknights_mower.utils.device.io_budget import device_io_budget, io_timeout
from arknights_mower.utils.device.ldplayer_discovery import (
    locate_ldplayer_manager,
    parse_ldplayer_instances,
)
from arknights_mower.utils.device.ldplayer_endpoint import LDPlayerEndpointResolver
from arknights_mower.utils.device.manager_io import run_manager_command
from arknights_mower.utils.device.native_capture import NativeCaptureSession
from arknights_mower.utils.device.screenshot_backend import FrameSizeMismatch


class LDCaptureError(RuntimeError):
    pass


class _LDRenderer:
    """Windows x64 ABI: deleting destructor, cap and release occupy slots 0–2."""

    def __init__(self, library, index, pid):
        self._dll = ctypes.CDLL(library)
        create = self._dll.CreateScreenShotInstance
        create.argtypes = [ctypes.c_uint, ctypes.c_uint]
        create.restype = ctypes.c_void_p
        self._instance = create(index, pid)
        if not self._instance:
            raise LDCaptureError(
                "LD 截图增强无法连接所选实例，请检查模拟器版本和运行状态。"
            )
        self._release = None
        table = ctypes.cast(
            self._instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        # x64 uses the unified Windows calling convention, including `this`.
        self._release = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(table[2])
        self._cap = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(table[1])

    def capture_frame(self):
        pixels = self._cap(self._instance)
        if not pixels:
            raise LDCaptureError("LD 截图增强未返回画面，请检查所选实例。")
        raw = np.ctypeslib.as_array(
            ctypes.cast(pixels, ctypes.POINTER(ctypes.c_ubyte)),
            shape=(1080 * 1920 * 3,),
        ).reshape(1080, 1920, 3)
        return raw[::-1, :, ::-1].copy()

    def close(self):
        instance, self._instance = self._instance, None
        if instance and self._release:
            self._release(instance)


def _capture_worker(library, index, pid, frame_buffer, channel):
    renderer = None
    try:
        renderer = _LDRenderer(library, index, pid)
        output = np.frombuffer(frame_buffer, np.uint8).reshape(1080, 1920, 3)
        while channel.recv() == "capture":
            np.copyto(output, renderer.capture_frame())
            channel.send(("ok", "", None, None))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            message = str(exc).encode("utf-8")[:1024].decode("utf-8", "ignore")
            channel.send(("error", message, None, None))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        try:
            if renderer is not None:
                renderer.close()
        finally:
            channel.close()


class LDCaptureSession:
    """Verify identity and dimensions around every bounded native frame."""

    def __init__(self, profile, adb_path, serial):
        self._profile = profile.model_copy(
            update={"adb_path": adb_path, "last_serial": serial}, deep=True
        )
        self._native = None
        self._identity = None
        self._manager = None
        self._library = None
        self._failure = None
        self._interrupted = Event()
        self._lock = Lock()
        self._state_lock = RLock()
        self.owner_pid = os.getpid()

    def _remaining(self, deadline):
        if self.owner_pid != os.getpid() or self._interrupted.is_set():
            raise LDCaptureError("LD 截图增强会话已关闭或所有权不匹配。")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("LD 截图增强未在限定时间返回画面。")
        return remaining

    def _observe(self):
        result = run_manager_command(
            [str(self._manager), "list2"],
            timeout=io_timeout(3),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        rows, _ = parse_ldplayer_instances(
            result.stdout, self._profile.instance_id, self._profile.instance_name
        )
        row = rows[0]
        if row["state"] != "running":
            raise LDCaptureError("LD 截图增强所绑定的实例未运行，请重新连接。")
        size = row.get("display_size")
        if size is None:
            raise LDCaptureError(
                "雷电管理器未报告画面尺寸，请升级雷电模拟器或选择其他截图方式。"
            )
        if size != [1920, 1080]:
            raise FrameSizeMismatch(f"LD 截图增强实际画面尺寸为 {size[0]}×{size[1]}")
        identity = (row["pid"], row["vbox_pid"])
        if self._identity is not None and identity != self._identity:
            raise LDCaptureError("LD 截图增强所绑定的实例进程已变化，请重新连接。")
        return identity

    def _bind(self):
        reason = capture_compatibility_error(
            self._profile.preset_id, "ld_native", platform.system().lower()
        )
        if reason:
            raise LDCaptureError(reason)
        if ctypes.sizeof(ctypes.c_void_p) != 8 or platform.machine().lower() not in {
            "amd64",
            "x86_64",
        }:
            raise LDCaptureError("LD 截图增强需要 Windows x64 运行环境。")
        self._manager, root = locate_ldplayer_manager(
            self._profile.manager_path or self._profile.installation_path
        )
        if self._manager is None:
            raise LDCaptureError("未找到雷电管理器，请检查模拟器路径。")
        self._library = root / "ldopengl64.dll"
        if not self._library.is_file():
            raise LDCaptureError(
                "雷电目录缺少 ldopengl64.dll，请升级雷电模拟器或选择其他截图方式。"
            )
        if not self._profile.last_serial or not self._profile.adb_path:
            raise LDCaptureError("LD 截图增强需要已验证的 ADB 地址和程序。")
        self._identity = self._observe()
        if any(
            value > 0xFFFFFFFF
            for value in (int(self._profile.instance_id), *self._identity)
        ):
            raise LDCaptureError("雷电实例编号或进程编号超出截图接口范围，请重新检测。")
        observation = LDPlayerEndpointResolver().inspect(
            self._profile, self._manager, io_timeout(10)
        )
        if (
            observation.state != "running"
            or observation.serial != self._profile.last_serial
        ):
            raise LDCaptureError("LD 截图增强实例与所选 ADB 地址不一致，请重新绑定。")
        self._observe()
        with self._state_lock:
            if self._interrupted.is_set():
                raise LDCaptureError("LD 截图增强会话已中断。")
            self._native = NativeCaptureSession(
                _capture_worker,
                (str(self._library), int(self._profile.instance_id), self._identity[0]),
                label="LD 截图增强",
                error_type=LDCaptureError,
            )

    def capture_frame(self):
        deadline = time.monotonic() + io_timeout(10)
        if not self._lock.acquire(timeout=self._remaining(deadline)):
            raise TimeoutError("LD 截图增强等待前一张画面超时。")
        try:
            if self._failure is not None:
                raise self._failure
            with device_io_budget(lambda: self._remaining(deadline)):
                if self._native is None:
                    self._bind()
                else:
                    self._observe()
                frame = self._native.capture_frame()
                self._observe()
                return frame
        except Exception as exc:
            self._failure = exc
            raise
        finally:
            self._lock.release()

    def interrupt(self):
        if self.owner_pid == os.getpid():
            self._interrupted.set()
            with self._state_lock:
                if self._native is not None:
                    self._native.interrupt()

    def close(self):
        if self.owner_pid != os.getpid():
            return
        self.interrupt()
        with self._state_lock:
            native, self._native = self._native, None
        if native is not None:
            native.close()
