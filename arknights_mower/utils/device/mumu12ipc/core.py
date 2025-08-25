import ctypes
import gc
import json
import os
import subprocess
import sys
import time
from functools import cached_property, wraps
from typing import Any, Callable

import numpy as np

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger
from arknights_mower.utils.simulator import restart_simulator


class BufferPool:
    def __init__(self, max_buffers=5):
        self.max_buffers = max_buffers
        self.buffers = {}

    def get_buffer(self):
        self.cleanup_buffers()
        for buffer in self.buffers.values():
            refcount = sys.getrefcount(buffer)
            if refcount <= 3:
                return buffer
        # 如果没有可复用的缓冲区，分配新的内存
        new_buffer = (ctypes.c_ubyte * 8294400)()
        self.buffers[id(new_buffer)] = new_buffer
        return new_buffer

    def cleanup_buffers(self):
        """
        超过最大数量时清理未被使用的缓冲区
        """
        if len(self.buffers) <= self.max_buffers:
            return
        elif len(self.buffers) >= 30:
            self.buffers.clear()
            gc.collect()
            return
        for id in list(self.buffers.keys()):
            refcount = sys.getrefcount(self.buffers[id])
            if refcount <= 2:
                del self.buffers[id]
                if len(self.buffers) <= self.max_buffers:
                    return


class NemuIpcIncompatible(Exception):
    pass


def retry_mumuipc(func):
    @wraps(func)
    def retry_wrapper(self, *args, **kwargs):
        for _ in range(3):
            try:
                return func(self, *args, **kwargs)
            except MowerExit:
                raise
            except RuntimeError as e:
                logger.exception(e)
                self.device.check_current_focus()
            except Exception as e:
                logger.exception(e)
                restart_simulator()

    return retry_wrapper


class MuMu12IPC:
    def __init__(self, device):
        self.device = device
        norm = os.path.normpath(config.conf.simulator.simulator_folder)
        if os.path.basename(norm).lower() == "shell":
            self.emulator_folder = os.path.dirname(norm)
        else:
            self.emulator_folder = norm
        self.instanse_index = int(config.conf.simulator.index)
        self.connection = 0
        self.display_id = -1
        self.app_index = 0
        self.buffer_pool = BufferPool(10)
        self.manager_path = config.conf.simulator.simulator_folder + "MuMuManager.exe"
        self._setting_info = None
        # 加载动态链接库
        dll_path = os.path.join(
            self.emulator_folder, "shell", "sdk", "external_renderer_ipc.dll"
        )
        try:
            self.external_renderer = ctypes.CDLL(dll_path)
        except OSError as e:
            logger.error(e)
            if not os.path.exists(dll_path):
                raise NemuIpcIncompatible(
                    f"文件不存在: {dll_path}, 请检查模拟器文件夹是否正确"
                    f"NemuIpc requires MuMu12 version >= 3.8.13, please check your version"
                )
            else:
                raise NemuIpcIncompatible(
                    f"ipc_dll={dll_path} exists, but cannot be loaded"
                )

        # 定义函数原型
        self.external_renderer.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        self.external_renderer.nemu_connect.restype = ctypes.c_int

        self.external_renderer.nemu_disconnect.argtypes = [ctypes.c_int]
        self.external_renderer.nemu_disconnect.restype = None

        self.external_renderer.nemu_get_display_id.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_get_display_id.restype = ctypes.c_int

        self.external_renderer.nemu_capture_display.argtypes = [
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self.external_renderer.nemu_capture_display.restype = ctypes.c_int
        self.external_renderer.nemu_input_event_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_input_event_touch_down.restype = ctypes.c_int

        self.external_renderer.nemu_input_event_touch_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_input_event_touch_up.restype = ctypes.c_int

        self.external_renderer.nemu_input_event_finger_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_input_event_finger_touch_down.restype = ctypes.c_int

        self.external_renderer.nemu_input_event_finger_touch_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_input_event_finger_touch_up.restype = ctypes.c_int

        self.external_renderer.nemu_input_event_key_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_input_event_key_down.restype = ctypes.c_int

        self.external_renderer.nemu_input_event_key_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.external_renderer.nemu_input_event_key_up.restype = ctypes.c_int

    def get_setting_info(self):
        """获取模拟器 setting 信息，只执行一次并缓存"""
        if self._setting_info is None:
            cmd = [self.manager_path, "setting", "-v", str(self.instanse_index), "-a"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                output = result.stdout.strip()
                self._setting_info = json.loads(output)
                logger.debug("MuMu setting info loaded and cached.")
            except Exception as e:
                logger.error(f"获取 MuMu setting 失败: {e}")
                raise
        return self._setting_info

    def get_field_value(self, data, key):
        return data.get(key)

    def emulator_version(self) -> list[int]:
        version = self.get_field_value(self.get_setting_info(), "core_version")
        return [int(v) for v in version.split(".")]

    def get_emulator_info(self):
        """获取模拟器运行状态（实时查询）"""
        cmd = [self.manager_path, "info", "-v", str(self.instanse_index), "-a"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            return json.loads(output)
        except Exception as e:
            logger.error(f"获取 MuMu 模拟器 info 失败: {e}")
            raise

    def emulator_status(self) -> str:
        data = self.get_emulator_info()
        android = self.get_field_value(data, "is_android_started")
        process = self.get_field_value(data, "is_process_started")
        state = self.get_field_value(data, "player_state")

        if android or state == "start_finished":
            return "running"
        if process:
            return "launching"
        return "stopped"

    @cached_property
    def is_new_version(self):
        version = self.emulator_version()
        target = [4, 1, 21]
        for i in range(3):
            if version[i] < target[i]:
                return False
            elif version[i] > target[i]:
                return True
        return True

    def connect(self):
        "连接到 emulator"
        if self.emulator_status() != "running":
            raise Exception("模拟器未启动，请启动模拟器")
        logger.debug(
            f"尝试连接 MuMu: path={self.emulator_folder}, instanse_index={self.instanse_index}"
        )

        self.connection = self.external_renderer.nemu_connect(
            ctypes.c_wchar_p(self.emulator_folder),
            self.instanse_index,
        )
        if self.connection == 0:
            raise Exception("连接模拟器失败，请启动模拟器")
        logger.info("MuMu截图增强连接模拟器成功")

    def get_display_id(self):
        pkg_name = config.conf.APPNAME.encode("utf-8")  # 替换为实际包名
        self.display_id = self.external_renderer.nemu_get_display_id(
            self.connection, pkg_name, self.app_index
        )
        if self.display_id < 0:
            logger.error(f"获取Display ID失败: {self.display_id}")
            raise RuntimeError("获取Display ID失败")
        logger.debug(f"获取Display ID成功: {self.display_id}")

    @retry_mumuipc
    def check_status(self):
        if self.connection == 0:
            self.connect()
        if self.display_id < 0:
            self.get_display_id()

    def capture_display(self) -> np.ndarray:
        self.check_status()
        pixels = self.buffer_pool.get_buffer()
        result = self.external_renderer.nemu_capture_display(
            self.connection,
            self.display_id,
            8294400,
            ctypes.byref(ctypes.c_int(1920)),
            ctypes.byref(ctypes.c_int(1080)),
            pixels,
        )
        if result != 0:
            logger.error(f"获取截图失败: {result}")
            self.connection = 0
            self.display_id = -1
            self.device.exit()
            return np.zeros((1080, 1920, 3), dtype=np.uint8)
        image = np.frombuffer(pixels, dtype=np.uint8).reshape((1080, 1920, 4))[:, :, :3]
        image = np.flipud(image)  # 翻转
        return image

    def key_down(self, key_code: int):
        """按下键盘按键"""
        self.check_status()
        result = self.external_renderer.nemu_input_event_key_down(
            self.connection, self.display_id, key_code
        )
        if result != 0:
            self.connection = 0
            self.display_id = -1
            self.device.exit()

    def key_up(self, key_code: int):
        """释放键盘按键"""
        self.check_status()
        result = self.external_renderer.nemu_input_event_key_up(
            self.connection, self.display_id, key_code
        )
        if result != 0:
            self.connection = 0
            self.display_id = -1
            self.device.exit()

    # 单点触控
    def touch_down(self, x: int, y: int):
        self.check_status()
        result = (
            self.external_renderer.nemu_input_event_touch_down(
                self.connection, self.display_id, int(x), int(y)
            )
            if self.is_new_version
            else self.external_renderer.nemu_input_event_touch_down(
                self.connection, self.display_id, int(1080 - y), int(x)
            )
        )
        # mumu12版本4.1.21之后的版本修改了坐标参数
        if result != 0:
            self.connection = 0
            self.display_id = -1
            self.device.exit()

    def touch_up(self):
        self.check_status()
        result = self.external_renderer.nemu_input_event_touch_up(
            self.connection, self.display_id
        )
        if result != 0:
            self.connection = 0
            self.display_id = -1
            self.device.exit()

    # 多点触控
    def finger_touch_down(self, finger_id: int, x: int, y: int):
        self.check_status()
        result = self.external_renderer.nemu_input_event_finger_touch_down(
            self.connection, self.display_id, finger_id, int(1080 - y), int(x)
        )
        if result != 0:
            self.connection = 0
            self.display_id = -1
            self.device.exit()

    def finger_touch_up(self, finger_id: int):
        self.check_status()
        result = self.external_renderer.nemu_input_event_finger_touch_up(
            self.connection, self.display_id, finger_id
        )
        if result != 0:
            self.connection = 0
            self.display_id = -1
            self.device.exit()

    def tap(self, x, y, hold_time: float = 0.07) -> None:
        """
        Tap on screen
        Args:
            x: horizontal position
            y: vertical position
            hold_time: hold time
        """
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
        self, x0: int, y0: int, x1: int, y1: int, duration: float = 0.5, steps: int = 10
    ):
        """
        简单滑动实现（基于 touch_down / touch_up）
        Args:
            x0, y0: 起点坐标
            x1, y1: 终点坐标
            duration: 滑动总时长（秒）
            steps: 分成多少步滑动，越大越平滑
        """
        self.check_status()

        self.touch_down(x0, y0)

        dx = (x1 - x0) / steps
        dy = (y1 - y0) / steps
        delay = duration / steps

        for i in range(1, steps + 1):
            nx, ny = int(x0 + dx * i), int(y0 + dy * i)
            self.touch_down(nx, ny)  # 重复调用 touch_down 模拟滑动
            time.sleep(delay)
        self.touch_up()

    def swipe_ext(
        self,
        points: list[tuple[int, int]],
        durations: list[int],
        update: bool = False,
        interval: float = 0,
        func: Callable[[np.ndarray], Any] = lambda _: None,
    ):
        """
        多段滑动（扩展版）
        Args:
            points (list[tuple[int,int]]): 一系列坐标点 [(x0,y0), (x1,y1), ...]
            durations (list[int]): 每一段滑动的时长（毫秒），数量应比 points 少 1
            update (bool): 是否在最后一段完成后进行截图更新
            interval (float): 完成后额外等待时间
            func (Callable): 处理截图的函数，仅在最后一段时生效
        """
        if len(points) < 2:
            raise ValueError("至少需要两个点才能进行 swipe_ext()")
        if len(durations) != len(points) - 1:
            raise ValueError("durations 数量必须比 points 少 1")

        total = len(durations)
        result = None

        for idx, (S, E, D) in enumerate(zip(points[:-1], points[1:], durations)):
            first = idx == 0
            last = idx == total - 1
            result = self.swipe(
                x0=S[0],
                y0=S[1],
                x1=E[0],
                y1=E[1],
                duration=D / 1000.0,  # 毫秒 → 秒
                steps=10,
            )
            if first:
                self.touch_down(S[0], S[1])
            if last:
                self.touch_up()
                if update:
                    image = self.capture_display()
                    func(image)
                if interval > 0:
                    time.sleep(interval)
        return result

    def kill_server(self):
        if self.connection != 0:
            self.external_renderer.nemu_disconnect(self.connection)
            logger.debug(f"Disconnected from emulator: handle={self.connection}")
            self.connection = 0
            self.display_id = -1
            self.buffer_pool.buffers.clear()
        else:
            logger.warning("No active connection to disconnect.")

    def reset_when_exit(self):
        self.display_id = -1
