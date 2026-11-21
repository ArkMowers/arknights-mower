from __future__ import annotations

import os
import socket
import struct
import threading
import time
from typing import Optional, Tuple

import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.io_budget import (
    budget_sleep,
    device_io_budget,
    touch_release_budget,
)
from arknights_mower.utils.device.scrcpy import const
from arknights_mower.utils.device.scrcpy.control import ControlSender
from arknights_mower.utils.log import logger

SCR_PATH = "/data/local/tmp/minitouch"


class ScrcpyCleanupError(RuntimeError):
    """Do not replace a server whose owned resources could not be closed."""

    cleanup_failed = True


class Client:
    def __init__(
        self,
        client: ADBClient,
        max_width: int = 0,
        bitrate: int = 8000000,
        max_fps: int = 0,
        flip: bool = False,
        block_frame: bool = False,
        stay_awake: bool = False,
        lock_screen_orientation: int = const.LOCK_SCREEN_ORIENTATION_UNLOCKED,
        displayid: Optional[int] = None,
        connection_timeout: int = 3000,
    ):
        """
        Create a scrcpy client, this client won't be started until you call the start function
        Args:
            client: ADB client
            max_width: frame width that will be broadcast from android server
            bitrate: bitrate
            max_fps: maximum fps, 0 means not limited (supported after android 10)
            flip: flip the video
            block_frame: only return nonempty frames, may block cv2 render thread
            stay_awake: keep Android device awake
            lock_screen_orientation: lock screen orientation, LOCK_SCREEN_ORIENTATION_*
            connection_timeout: timeout for connection, unit is ms
        """

        # User accessible
        self.client = client
        self.owner_pid = os.getpid()
        self.last_frame: Optional[np.ndarray] = None
        self.resolution: Optional[Tuple[int, int]] = None
        self.device_name: Optional[str] = None
        self.control = ControlSender(self)

        # Params
        self.flip = flip
        self.max_width = max_width
        self.bitrate = bitrate
        self.max_fps = max_fps
        self.block_frame = block_frame
        self.stay_awake = stay_awake
        self.lock_screen_orientation = lock_screen_orientation
        self.connection_timeout = connection_timeout
        self.displayid = displayid

        # Need to destroy
        self.__server_stream: Optional[Socket] = None
        self.__video_socket: Optional[Socket] = None
        self.control_socket: Optional[Socket] = None
        self.control_socket_lock = threading.RLock()
        self._resources_lock = threading.RLock()
        self._interrupted = False
        self._cleanup_error = None

        self.start()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    def __start_server(self) -> None:
        """
        Start server and get the connection
        """
        cmdline = f"CLASSPATH={SCR_PATH} app_process /data/local/tmp com.genymobile.scrcpy.Server 1.21 log_level=verbose control=true tunnel_forward=true"
        if self.displayid is not None:
            cmdline += f" display_id={self.displayid}"
        self._own_stream("_Client__server_stream", self.client.stream_shell(cmdline))
        # Wait for server to start
        response = self.__server_stream.recv(100)
        logger.debug(response)
        if b"[server]" not in response:
            raise ConnectionError(
                "Failed to start scrcpy-server: " + response.decode("utf-8", "ignore")
            )

    def __deploy_server(self) -> None:
        """
        Deploy server to android device
        """
        server_file_path = (
            __rootdir__
            / "vendor"
            / "scrcpy-server-novideo"
            / "scrcpy-server-novideo.jar"
        )
        server_buf = server_file_path.read_bytes()
        self.client.push(SCR_PATH, server_buf)
        self.__start_server()

    def __init_server_connection(self) -> None:
        """
        Connect to android server, there will be two sockets, video and control socket.
        This method will set: video_socket, control_socket, resolution variables
        """
        try:
            self._own_stream(
                "_Client__video_socket", self.client.stream("localabstract:scrcpy")
            )
        except socket.timeout:
            raise ConnectionError("Failed to connect scrcpy-server")

        dummy_byte = self.__video_socket.recv_exactly(1)
        if not len(dummy_byte) or dummy_byte != b"\x00":
            raise ConnectionError("Did not receive Dummy Byte!")

        try:
            self._own_stream(
                "control_socket", self.client.stream("localabstract:scrcpy")
            )
        except socket.timeout:
            raise ConnectionError("Failed to connect scrcpy-server")

        self.device_name = self.__video_socket.recv_exactly(64).decode("utf-8")
        self.device_name = self.device_name.rstrip("\x00")
        if not len(self.device_name):
            raise ConnectionError("Did not receive Device Name!")

        res = self.__video_socket.recv_exactly(4)
        self.resolution = struct.unpack(">HH", res)
        # self.__video_socket.setblocking(False)

    def start(self) -> None:
        """只建立一次连接；失败交由设备恢复入口统一重试。"""
        with self.control_socket_lock:
            if self.owner_pid != os.getpid() or self._interrupted:
                raise ConnectionError("scrcpy 会话已关闭或所有权不匹配")
            self.stop()
            deadline = time.monotonic() + self.connection_timeout / 1000

            def remaining():
                if self._interrupted:
                    raise ConnectionError("scrcpy 会话已关闭")
                seconds = deadline - time.monotonic()
                if seconds <= 0:
                    raise TimeoutError("scrcpy startup timed out")
                return seconds

            try:
                with device_io_budget(remaining):
                    budget_sleep(0)
                    self.__deploy_server()
                    budget_sleep(0.5)
                    self.__init_server_connection()
            except Exception:
                self.stop()
                raise

    def stop(self) -> None:
        """
        Stop listening (both threaded and blocked)
        """
        if self.owner_pid != os.getpid():
            return
        with self._resources_lock:
            streams = self.control_socket, self.__video_socket, self.__server_stream
            self.control_socket = self.__video_socket = self.__server_stream = None
            self.resolution = self.device_name = None
            errors = []
            for stream in streams:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception as error:
                        errors.append(error)
            if errors:
                self._cleanup_error = ScrcpyCleanupError(
                    "; ".join(str(error) for error in errors)
                )
                raise self._cleanup_error from errors[0]
            if self._cleanup_error is not None:
                raise self._cleanup_error

    def _own_stream(self, name, stream):
        with self._resources_lock:
            if self._interrupted:
                stream.close()
                raise ConnectionError("scrcpy 会话已关闭")
            setattr(self, name, stream)
            return stream

    def interrupt(self):
        """Cancel socket I/O without releasing the server before restoration."""
        if self.owner_pid != os.getpid():
            return
        with self._resources_lock:
            if self._interrupted:
                return
            self._interrupted = True
            streams = self.control_socket, self.__video_socket, self.__server_stream
        errors = []
        for stream in streams:
            if stream is not None:
                try:
                    stream.interrupt()
                except Exception as exc:
                    errors.append(exc)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]

    def check_adb_alive(self) -> bool:
        """check if adb server alive"""
        return self.client.check_server_alive()

    def check_control_alive(self) -> bool:
        """Detect control EOF without consuming data or sending input."""
        budget_sleep(0)
        if not self.control_socket_lock.acquire(blocking=False):
            raise TimeoutError("scrcpy 输入连接探测锁忙，连接状态未确认")
        try:
            if self.owner_pid != os.getpid() or self._interrupted:
                raise ConnectionError("scrcpy 会话已关闭或所有权不匹配")
            stream = self.control_socket
            connection = stream.sock if stream is not None else None
            if connection is None or connection.fileno() < 0:
                return False
            timeout = connection.gettimeout()
            try:
                connection.settimeout(0)
                alive = bool(connection.recv(1, socket.MSG_PEEK))
            except BlockingIOError:
                alive = True
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                alive = False
            except OSError:
                if connection.fileno() >= 0:
                    raise
                alive = False
            finally:
                if connection.fileno() >= 0:
                    try:
                        connection.settimeout(timeout)
                    except OSError:
                        if connection.fileno() >= 0:
                            raise
            budget_sleep(0)
            return alive and connection.fileno() >= 0
        finally:
            self.control_socket_lock.release()

    def tap(self, x: int, y: int) -> None:
        self.control.tap(x, y)

    def swipe(
        self,
        x0,
        y0,
        x1,
        y1,
        move_duraion: float = 1,
        hold_before_release: float = 0,
        fall: bool = True,
        lift: bool = True,
        before_release=None,
    ):
        with self.control.input_operation():
            frame_time = 1 / 60

            start_time = time.perf_counter()
            end_time = start_time + move_duraion
            fall and self.control.touch(x0, y0, const.ACTION_DOWN)
            step_time = time.perf_counter() - start_time
            if step_time < frame_time:
                budget_sleep(frame_time - step_time)
            while True:
                step_start = time.perf_counter()
                if step_start > end_time:
                    break
                time_progress = (step_start - start_time) / move_duraion
                self.control.touch(
                    int(x0 + (x1 - x0) * time_progress),
                    int(y0 + (y1 - y0) * time_progress),
                    const.ACTION_MOVE,
                )
                step_time = time.perf_counter() - step_start
                if step_time < frame_time:
                    budget_sleep(frame_time - step_time)
            self.control.touch(x1, y1, const.ACTION_MOVE)
            if before_release is None:
                if hold_before_release > 0:
                    budget_sleep(hold_before_release)
                lift and self.control.touch(x1, y1, const.ACTION_UP)
            elif lift:
                try:
                    before_release()
                finally:
                    with touch_release_budget():
                        self.control.touch(x1, y1, const.ACTION_UP)
