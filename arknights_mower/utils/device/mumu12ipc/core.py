# MIT-licensed clean-room reimplementation for MuMu12 IPC bindings.
# This file intentionally avoids copying any GPL-licensed implementation details.
# It only binds to the public C API exposed by external_renderer_ipc.dll.

import ctypes
import json
import os
import re
import subprocess
import time
from typing import Any, Callable, Optional

import numpy as np

from arknights_mower.utils import config
from arknights_mower.utils.device.mumu12ipc.paths import resolve_mumu_paths
from arknights_mower.utils.log import logger
from arknights_mower.utils.update_runtime import hidden_console_options


class MuMuIpcError(RuntimeError):
    def __init__(self, message, *, return_code=None, actual_size=None):
        self.return_code = return_code
        self.actual_size = actual_size
        super().__init__(message)


def bind_display(dll, connection: int, package: str = "") -> int:
    """Return this instance's render display; a package binding is a fallback.

    The renderer resolves a display per package, so binding the game package
    failed with -1 whenever that app was not rendering, even while the emulator
    displayed fine. The instance's own display is 0 and serves both capture and
    input, so the emulator alone keeps the IPC channel usable.
    """
    whole = dll.nemu_get_display_id(connection, b"", 0)
    if whole >= 0:
        return whole
    bound = -1
    if package:
        bound = dll.nemu_get_display_id(connection, package.encode("utf-8"), 0)
        if bound >= 0:
            return bound
    raise MuMuIpcError(
        f"MuMu IPC 获取 Display ID 失败：实例显示 {whole}，游戏包 {bound}；"
        "请确认实例已启动并完成渲染后重试。",
        return_code=whole,
    )


def capture_native_frame(dll, connection, display_id, buffer) -> np.ndarray:
    """Capture one native RGBA frame and preserve failure diagnostics."""
    width = ctypes.c_int(0)
    height = ctypes.c_int(0)
    result = dll.nemu_capture_display(
        connection,
        display_id,
        len(buffer),
        ctypes.byref(width),
        ctypes.byref(height),
        buffer,
    )
    actual_size = (width.value, height.value)
    if result != 0:
        raise MuMuIpcError(
            f"MuMu IPC 截图失败：原生返回码 {result}，实际尺寸 "
            f"{width.value}×{height.value}",
            return_code=result,
            actual_size=actual_size,
        )
    if actual_size != (1920, 1080):
        raise MuMuIpcError(
            f"MuMu IPC 实际帧尺寸错误：{width.value}×{height.value}，"
            "需要横屏 1920×1080；原生返回码 0",
            return_code=result,
            actual_size=actual_size,
        )
    pixels = np.frombuffer(buffer, dtype=np.uint8)
    if pixels.size != 1920 * 1080 * 4:
        raise MuMuIpcError(
            f"MuMu IPC 帧数据长度错误：{pixels.size}，需要 8294400；"
            "原生返回码 0，实际尺寸 1920×1080",
            return_code=result,
            actual_size=actual_size,
        )
    frame = pixels.reshape((1080, 1920, 4))
    # The native buffer is reused on the next capture; callers own this frame.
    return np.flipud(frame[:, :, :3]).copy()


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
        profile = getattr(config.conf, "device", None)
        self._emu_root, manager_path = resolve_mumu_paths(
            config.conf.simulator.simulator_folder,
            getattr(profile, "manager_path", ""),
        )

        self._index: int = int(config.conf.simulator.index)
        self._conn: int = 0
        self._display_id: int = -1
        self._app_index: int = (
            0  # 0 works for single-game bind; adjust if multi instance mapping needed
        )

        # Manager path (CLI JSON for version/status)
        if not os.path.isfile(manager_path):
            raise MuMuIpcError(
                f"MuMuManager.exe 不存在，请检查 simulator.simulator_folder "
                f"配置是否正确: {manager_path}"
            )
        self._manager = manager_path
        self._setting_info = None

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
            os.path.join(self._emu_root, "nx_main", "sdk", "external_renderer_ipc.dll"),
            os.path.join(self._emu_root, "sdk", "external_renderer_ipc.dll"),
            os.path.join(
                self._emu_root,
                "nx_device",
                "12.0",
                "shell",
                "sdk",
                "external_renderer_ipc.dll",
            ),
            os.path.join(
                self._emu_root,
                "nx_device",
                "15.0",
                "shell",
                "sdk",
                "external_renderer_ipc.dll",
            ),
            os.path.join(
                os.path.dirname(self._emu_root),
                "shell",
                "sdk",
                "external_renderer_ipc.dll",
            ),
            os.path.join(
                os.path.dirname(self._emu_root),
                "nx_main",
                "sdk",
                "external_renderer_ipc.dll",
            ),
            os.path.join(
                os.path.dirname(self._emu_root), "sdk", "external_renderer_ipc.dll"
            ),
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
                cmd,
                capture_output=True,
                text=True,
                check=True,
                **hidden_console_options(),
            ).stdout.strip()
            return json.loads(out)
        except Exception as e:
            raise Exception(f"MuMuManager `{subcmd}` failed: {e}")

    def get_setting_core_version(self):
        """获取模拟器 core_version 信息，只执行一次并缓存"""
        if self._setting_info is None:
            cmd = [
                self._manager,
                "setting",
                "-v",
                str(self._index),
                "get_key",
                "core_version",
            ]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    **hidden_console_options(),
                )
                output = result.stdout.strip()
                return output
                # logger.debug("MuMu setting info loaded and cached.")
            except Exception as e:
                logger.error(f"获取 MuMu setting 失败: {e}")
                raise
        return self._setting_info

    def _emu_version(self) -> tuple:
        """
        Returns (major, minor, patch) for decision-making. Caches coord mapping rule.
        """
        # data = self._manager_json("setting")
        version = self.get_setting_core_version()
        parts = tuple(int(x) for x in version.split(".")[:3])
        if self._is_new_coord is None:
            # MuMu 12 changed coordinate arguments since 4.1.21
            self._is_new_coord = parts >= (4, 1, 21)
        return parts

    def get_emulator_info(self):
        """获取模拟器运行状态（实时查询）"""
        cmd = [self._manager, "api", "-v", str(self._index), "player_state"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                **hidden_console_options(),
            )
            player_index = None
            found_condition = False
            stdout = result.stdout
            pattern1 = r"player index: (\d+)(?:\r\n|\r|\n)"
            match1 = re.search(pattern1, stdout)
            if match1:
                player_index = int(match1.group(1))
                found_condition = True
            if found_condition:
                if player_index == self._index:
                    pattern2 = r"state: state=([^\s\r\n]+)(?:\r\n|\r|\n|$)"
                    match2 = re.search(pattern2, stdout)
                    if match2:
                        return match2.group(1)
            raise
        except Exception as e:
            logger.error(f"获取 MuMu 模拟器 info 失败: {e}")
            raise

    def _emu_state(self) -> str:
        """
        'running' | 'launching' | 'stopped'
        """
        # info = self._manager_json("info")
        # if (
        #     info.get("is_android_started")
        #     or info.get("player_state") == "start_finished"
        # ):
        #     return "running"
        # if info.get("is_process_started"):
        #     return "launching"
        # return "stopped"
        data = self.get_emulator_info()
        if data == "start_finished":
            return "running"
        if data == "starting_vm":
            return "launching"
        if data == "starting_rom":
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
        result = self._dll.nemu_connect(path, self._index)
        if result <= 0:
            self._conn = 0
            raise MuMuIpcError(
                f"MuMu IPC 连接失败：原生返回码 {result}", return_code=result
            )
        self._conn = result
        logger.info("已连接 MuMu 截图增强引擎")

    def disconnect(self):
        """Release only this backend's current native connection."""
        connection = self._conn
        self._conn = 0
        self._display_id = -1
        if connection:
            self._dll.nemu_disconnect(connection)

    def get_display_id(self):
        """
        Bind the instance display; the configured package stays a fallback.
        """
        self._display_id = bind_display(self._dll, self._conn, config.conf.APPNAME)
        logger.debug(f"Display bound: id={self._display_id}")

    def _ensure_ready(self):
        """
        Initialize once; the screenshot caller owns the single rebuild budget.
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
        self._ensure_ready()
        self._ensure_buffer()
        return capture_native_frame(
            self._dll, self._conn, self._display_id, self._buffer
        )

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
        self._input_event("key_down", int(key_code))

    def key_up(self, key_code: int):
        self._input_event("key_up", int(key_code))

    def touch_down(self, x: int, y: int):
        self._input_event("touch_down", *self._map_xy(x, y))

    def touch_up(self):
        self._input_event("touch_up")

    def finger_touch_down(self, finger_id: int, x: int, y: int):
        self._input_event("finger_touch_down", int(finger_id), *self._map_xy(x, y))

    def finger_touch_up(self, finger_id: int):
        self._input_event("finger_touch_up", int(finger_id))

    def _input_event(self, event, *args):
        self._ensure_ready()
        result = getattr(self._dll, f"nemu_input_event_{event}")(
            self._conn, self._display_id, *args
        )
        if result != 0:
            # Keep ownership until Device closes the connection. Never swallow
            # an uncertain send or reconnect halfway through the same gesture.
            raise MuMuIpcError(f"{event} failed: {result}", return_code=result)

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
        steps: int = 30,
        fall: bool = True,
        lift: bool = True,
        interval: float = 0.0,
    ):
        if fall:
            self.touch_down(x0, y0)

        # 每步耗时
        dt = duration / steps

        for i in range(1, steps + 1):
            tx = int(x0 + (x1 - x0) * (i / steps))
            ty = int(y0 + (y1 - y0) * (i / steps))
            self.touch_down(tx, ty)
            time.sleep(dt)

        if lift:
            if interval:
                time.sleep(interval)
            self.touch_up()

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
                interval=interval if i == len(durations) - 1 else 0.0,
            )
