# MIT-licensed clean-room reimplementation for MuMu12 IPC bindings.
# This file intentionally avoids copying any GPL-licensed implementation details.
# It only binds to the public C API exposed by external_renderer_ipc.dll.

import ctypes
import functools
import json
import os
import subprocess
import time
from typing import Any, Callable, Optional

import numpy as np

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger
from arknights_mower.utils.simulator import restart_simulator


def retry_wrapper(max_retries: int = 3, delay: float = 0.5):
    """
    通用重试装饰器（适配 @retry_wrapper(3) 用法）
    - 捕获异常 -> 重置连接状态 -> 尝试重启模拟器 -> 睡眠 -> 重试
    - 命中 MowerExit 直接向上抛出，避免吞掉退出信号
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(self, *args, **kwargs)
                except MowerExit:
                    raise
                except RuntimeError as e:
                    last_exc = e
                    logger.info(
                        f"{func.__name__} runtime error (attempt {attempt}/{max_retries}): {e}"
                    )
                    try:
                        # 若有该方法则调用
                        if hasattr(self, "device") and hasattr(
                            self.device, "check_current_focus"
                        ):
                            self.device.check_current_focus()
                    except Exception as inner:
                        logger.info(f"check_current_focus failed: {inner}")
                except Exception as e:
                    last_exc = e
                    logger.info(
                        f"{func.__name__} failed (attempt {attempt}/{max_retries}): {e}"
                    )

                    try:
                        if hasattr(self, "_conn"):
                            self._conn = 0
                        if hasattr(self, "_display_id"):
                            self._display_id = -1
                        restart_simulator()
                    except Exception as inner:
                        logger.error(f"restart_simulator failed: {inner}")
                time.sleep(delay)
            if last_exc is not None:
                raise last_exc
            raise RuntimeError(f"{func.__name__} failed after {max_retries} retries")

        return wrapper

    return decorator


class MuMuIpcError(RuntimeError):
    pass


class MuMu12IPC:
    """
    Drop-in replacement implementing display capture and input injection via MuMu 12
    external_renderer_ipc.dll.

    Public methods preserved for compatibility:
      - connect(), get_display_id(), capture_display()
      - key_down(), key_up(), touch_down(), touch_up()
      - finger_touch_down(), finger_touch_up()
      - tap(), send_keyevent(), back()
      - swipe(), swipe_ext(), kill_server(), reset_when_exit()
    """

    _W = 1920
    _H = 1080
    _BYTES = _W * _H * 4

    def __init__(self, device):
        self.device = device
        # Normalize emulator folder from config (compatible with your project layout)
        norm = os.path.normpath(config.conf.simulator.simulator_folder)
        self._emu_root = (
            os.path.dirname(norm) if os.path.basename(norm).lower() == "shell" else norm
        )

        self._index: int = int(config.conf.simulator.index)
        self._conn: int = 0
        self._display_id: int = -1
        self._app_index: int = (
            0  # 0 works for single-game bind; adjust if multi instance mapping needed
        )

        # Manager path (CLI JSON for version/status)
        self._manager = os.path.join(
            config.conf.simulator.simulator_folder, "MuMuManager.exe"
        )

        # Lazy-initialized members
        self._dll = None
        self._buffer = None  # single reusable framebuffer
        self._is_new_coord: Optional[bool] = None  # coord system flag (>= 4.1.21)

        # Preload to fail-fast with clear diagnostics
        self._load_renderer()

    # -----------------------
    # Loading / version logic
    # -----------------------
    def _load_renderer(self):
        """
        Load external_renderer_ipc.dll from typical MuMu 12 locations.
        """
        candidates = [
            os.path.join(self._emu_root, "shell", "sdk", "external_renderer_ipc.dll"),
            os.path.join(self._emu_root, "sdk", "external_renderer_ipc.dll"),
        ]
        last_err = None
        for path in candidates:
            try:
                self._dll = ctypes.CDLL(path)
                logger.debug(f"Loaded MuMu renderer DLL: {path}")
                break
            except OSError as e:
                last_err = e
                logger.debug(f"Failed to load renderer from {path}: {e}")
        if self._dll is None:
            msg = f"Cannot load external_renderer_ipc.dll. Checked: {candidates}. Last error: {last_err}"
            logger.error(msg)
            raise MuMuIpcError(msg)

        # Bind types only after successful load
        self._dll.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        self._dll.nemu_connect.restype = ctypes.c_int

        self._dll.nemu_disconnect.argtypes = [ctypes.c_int]
        self._dll.nemu_disconnect.restype = None

        self._dll.nemu_get_display_id.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._dll.nemu_get_display_id.restype = ctypes.c_int

        self._dll.nemu_capture_display.argtypes = [
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self._dll.nemu_capture_display.restype = ctypes.c_int

        self._dll.nemu_input_event_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_touch_down.restype = ctypes.c_int

        self._dll.nemu_input_event_touch_up.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dll.nemu_input_event_touch_up.restype = ctypes.c_int

        self._dll.nemu_input_event_finger_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_finger_touch_down.restype = ctypes.c_int

        self._dll.nemu_input_event_finger_touch_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_finger_touch_up.restype = ctypes.c_int

        self._dll.nemu_input_event_key_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_key_down.restype = ctypes.c_int

        self._dll.nemu_input_event_key_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._dll.nemu_input_event_key_up.restype = ctypes.c_int

    def _manager_json(self, subcmd: str) -> dict:
        """
        Call MuMuManager.exe to get JSON for 'setting' or 'info' and decode.
        """
        cmd = [self._manager, subcmd, "-v", str(self._index), "-a"]
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            ).stdout.strip()
            return json.loads(out)
        except Exception as e:
            raise Exception(f"MuMuManager `{subcmd}` failed: {e}")

    def _emu_version(self) -> tuple:
        """
        Returns (major, minor, patch) for decision-making. Caches coord mapping rule.
        """
        data = self._manager_json("setting")
        version = str(data.get("core_version", "0.0.0"))
        parts = tuple(int(x) for x in version.split(".")[:3])
        if self._is_new_coord is None:
            # MuMu 12 changed coordinate arguments since 4.1.21
            self._is_new_coord = parts >= (4, 1, 21)
        return parts

    def _emu_state(self) -> str:
        """
        'running' | 'launching' | 'stopped'
        """
        info = self._manager_json("info")
        if (
            info.get("is_android_started")
            or info.get("player_state") == "start_finished"
        ):
            return "running"
        if info.get("is_process_started"):
            return "launching"
        return "stopped"

    # -----------------------
    # Connection & display
    # -----------------------
    def connect(self):
        """
        Establish IPC connection to emulator if running.
        """
        if self._emu_state() != "running":
            raise Exception("模拟器未启动，请启动模拟器")
        path = ctypes.c_wchar_p(self._emu_root)
        self._conn = self._dll.nemu_connect(path, self._index)
        if self._conn == 0:
            raise Exception("连接模拟器失败，请启动模拟器")
        logger.info("MuMu IPC connected.")

    def get_display_id(self):
        """
        Bind to target app display using package name from config.
        """
        pkg = config.conf.APPNAME.encode("utf-8")
        self._display_id = self._dll.nemu_get_display_id(
            self._conn, pkg, self._app_index
        )
        if self._display_id < 0:
            raise RuntimeError("获取Display ID失败")
        logger.debug(f"Display bound: id={self._display_id}")

    @retry_wrapper(3)  # type: ignore
    def _ensure_ready(self):
        """
        Ensure connection and display id are valid; auto-recover if needed.
        """
        if self._conn == 0:
            self.connect()
        if self._display_id < 0:
            self.get_display_id()

    def _ensure_buffer(self):
        if self._buffer is None:
            self._buffer = (ctypes.c_ubyte * self._BYTES)()

    def capture_display(self) -> np.ndarray:
        """
        Capture RGBA frame into reusable buffer, return HxWx3 (RGB) numpy array flipped to upright.
        """
        try:
            self._ensure_ready()
            self._ensure_buffer()

            w = ctypes.c_int(self._W)
            h = ctypes.c_int(self._H)
            ret = self._dll.nemu_capture_display(
                self._conn,
                self._display_id,
                self._BYTES,
                ctypes.byref(w),
                ctypes.byref(h),
                self._buffer,
            )
            if ret != 0:
                raise MuMuIpcError(f"capture failed: {ret}")

            # Interpret buffer: RGBA -> RGB, flip vertically
            frame = np.frombuffer(self._buffer, dtype=np.uint8).reshape(
                (self._H, self._W, 4)
            )[:, :, :3]
            return np.flipud(frame)
        except Exception as e:
            logger.error(f"capture_display error: {e}")
            # Attempt soft recovery for next call
            self._conn = 0
            self._display_id = -1
            self.device.exit()
            return np.zeros((self._H, self._W, 3), dtype=np.uint8)

    def _map_xy(self, x: int, y: int) -> tuple[int, int]:
        """
        Map logical coordinates to MuMu IPC expected arguments depending on version.
        """
        if self._is_new_coord is None:
            self._emu_version()
        if self._is_new_coord:
            return int(x), int(y)
        return int(self._H - y), int(x)

    def key_down(self, key_code: int):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_key_down(
                self._conn, self._display_id, int(key_code)
            )
            if rc != 0:
                raise MuMuIpcError(f"key_down failed: {rc}")
        except Exception as e:
            logger.error(f"key_down error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def key_up(self, key_code: int):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_key_up(
                self._conn, self._display_id, int(key_code)
            )
            if rc != 0:
                raise MuMuIpcError(f"key_up failed: {rc}")
        except Exception as e:
            logger.error(f"key_up error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def touch_down(self, x: int, y: int):
        try:
            self._ensure_ready()
            tx, ty = self._map_xy(x, y)
            rc = self._dll.nemu_input_event_touch_down(
                self._conn, self._display_id, tx, ty
            )
            if rc != 0:
                raise MuMuIpcError(f"touch_down failed: {rc}")
        except Exception as e:
            logger.error(f"touch_down error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def touch_up(self):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_touch_up(self._conn, self._display_id)
            if rc != 0:
                raise MuMuIpcError(f"touch_up failed: {rc}")
        except Exception as e:
            logger.error(f"touch_up error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def finger_touch_down(self, finger_id: int, x: int, y: int):
        try:
            self._ensure_ready()
            tx, ty = self._map_xy(x, y)
            rc = self._dll.nemu_input_event_finger_touch_down(
                self._conn, self._display_id, int(finger_id), tx, ty
            )
            if rc != 0:
                raise MuMuIpcError(f"finger_touch_down failed: {rc}")
        except Exception as e:
            logger.error(f"finger_touch_down error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def finger_touch_up(self, finger_id: int):
        try:
            self._ensure_ready()
            rc = self._dll.nemu_input_event_finger_touch_up(
                self._conn, self._display_id, int(finger_id)
            )
            if rc != 0:
                raise MuMuIpcError(f"finger_touch_up failed: {rc}")
        except Exception as e:
            logger.error(f"finger_touch_up error: {e}")
            self._conn = 0
            self._display_id = -1
            self.device.exit()

    def tap(self, x: int, y: int, hold_time: float = 0.07):
        self.touch_down(x, y)
        time.sleep(hold_time)
        self.touch_up()

    def send_keyevent(self, key_code: int, hold_time: float = 0.1):
        self.key_down(key_code)
        time.sleep(hold_time)
        self.key_up(key_code)

    def back(self):
        self.send_keyevent(1)

    def swipe(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        duration: float = 0.5,
        steps: int = 0,
        fall: bool = True,
        lift: bool = True,
        update: bool = False,
        interval: float = 0.0,
        func: Callable[[np.ndarray], Any] = lambda _: None,
    ):
        """
        Simple swipe by progressive touch positions.

        - If steps==0, choose steps adaptively based on path length and duration.
        - 'update' optionally captures frame after swipe and invokes func(image).
        """
        self._ensure_ready()

        if fall:
            self.touch_down(x0, y0)

        # Compute adaptive steps if not provided
        if steps <= 0:
            # heuristic: ~ every 6-8 pixels or 120 Hz * duration
            dist = max(abs(x1 - x0), abs(y1 - y0))
            steps = max(6, min(120, int(dist / 8) or int(120 * duration)))

        dt = max(0.001, duration / steps)
        dx = (x1 - x0) / steps
        dy = (y1 - y0) / steps

        t0 = time.perf_counter()
        for i in range(1, steps + 1):
            tx = int(x0 + dx * i)
            ty = int(y0 + dy * i)
            self.touch_down(tx, ty)
            target = t0 + i * dt
            now = time.perf_counter()
            if now < target:
                time.sleep(target - now)

        if lift:
            self.touch_up()

        if update:
            img = self.capture_display()
            try:
                func(img)
            except Exception:
                pass
        if interval > 0:
            time.sleep(interval)

    def swipe_ext(
        self,
        points: list[tuple[int, int]],
        durations: list[int],
        update: bool = False,
        interval: float = 0.0,
        func: Callable[[np.ndarray], Any] = lambda _: None,
    ):
        if len(points) < 2 or len(durations) != len(points) - 1:
            raise ValueError(
                "swipe_ext requires at least 2 points and len(durations)==len(points)-1"
            )

        for i, (p0, p1, d_ms) in enumerate(zip(points[:-1], points[1:], durations)):
            self.swipe(
                p0[0],
                p0[1],
                p1[0],
                p1[1],
                duration=max(0.01, d_ms / 1000.0),
                fall=(i == 0),
                lift=(i == len(durations) - 1),
                update=(i == len(durations) - 1) and update,
                interval=interval if i == len(durations) - 1 else 0.0,
                func=func,
            )
