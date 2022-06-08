from __future__ import annotations

import functools
import socket
import struct
import threading
import time
import traceback
from typing import Optional, Tuple

import numpy as np

from .... import __rootdir__
from ...log import logger
from ..adb_client import ADBClient
from ..adb_client.socket import Socket
from . import const
from .control import ControlSender

SCR_PATH = '/data/local/tmp/minitouch'


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
        self.control_socket_lock = threading.Lock()

        self.start()

    def __del__(self) -> None:
        self.stop()

    def __start_server(self) -> None:
        """
        Start server and get the connection
        """
        cmdline = f'CLASSPATH={SCR_PATH} app_process /data/local/tmp com.genymobile.scrcpy.Server 1.21 log_level=verbose control=true tunnel_forward=true'
        if self.displayid is not None:
            cmdline += f' display_id={self.displayid}'
        self.__server_stream: Socket = self.client.stream_shell(cmdline)
        # Wait for server to start
        response = self.__server_stream.recv(100)
        logger.debug(response)
        if b'[server]' not in response:
            raise ConnectionError(
                'Failed to start scrcpy-server: ' + response.decode('utf-8', 'ignore'))

    def __deploy_server(self) -> None:
        """
        Deploy server to android device
        """
        server_file_path = __rootdir__ / 'vendor' / \
            'scrcpy-server-novideo' / 'scrcpy-server-novideo.jar'
        server_buf = server_file_path.read_bytes()
        self.client.push(SCR_PATH, server_buf)
        self.__start_server()

    def __init_server_connection(self) -> None:
        """
        Connect to android server, there will be two sockets, video and control socket.
        This method will set: video_socket, control_socket, resolution variables
        """
        try:
            self.__video_socket = self.client.stream('localabstract:scrcpy')
        except socket.timeout:
            raise ConnectionError('Failed to connect scrcpy-server')

        dummy_byte = self.__video_socket.recv(1)
        if not len(dummy_byte) or dummy_byte != b'\x00':
            raise ConnectionError('Did not receive Dummy Byte!')

        try:
            self.control_socket = self.client.stream('localabstract:scrcpy')
        except socket.timeout:
            raise ConnectionError('Failed to connect scrcpy-server')

        self.device_name = self.__video_socket.recv(64).decode('utf-8')
        self.device_name = self.device_name.rstrip('\x00')
        if not len(self.device_name):
            raise ConnectionError('Did not receive Device Name!')

        res = self.__video_socket.recv(4)
        self.resolution = struct.unpack('>HH', res)
        # self.__video_socket.setblocking(False)

    def start(self) -> None:
        """
        Start listening video stream
        """
        try_count = 0
        while try_count < 3:
            try:
                self.__deploy_server()
                time.sleep(0.5)
                self.__init_server_connection()
                break
            except ConnectionError:
                logger.debug(traceback.format_exc())
                logger.warning('Failed to connect scrcpy-server.')
                self.stop()
                logger.warning('Try again in 10 seconds...')
                time.sleep(10)
                try_count += 1
        else:
            raise RuntimeError('Failed to connect scrcpy-server.')

    def stop(self) -> None:
        """
        Stop listening (both threaded and blocked)
        """
        if self.__server_stream is not None:
            self.__server_stream.close()
            self.__server_stream = None
        if self.control_socket is not None:
            self.control_socket.close()
            self.control_socket = None
        if self.__video_socket is not None:
            self.__video_socket.close()
            self.__video_socket = None

    def check_adb_alive(self) -> bool:
        """ check if adb server alive """
        return self.client.check_server_alive()

    def stable(f):
        @functools.wraps(f)
        def inner(self: Client, *args, **kwargs):
            try_count = 0
            while try_count < 3:
                try:
                    f(self, *args, **kwargs)
                    break
                except (ConnectionResetError, BrokenPipeError):
                    self.stop()
                    time.sleep(1)
                    self.check_adb_alive()
                    self.start()
                    try_count += 1
            else:
                raise RuntimeError('Failed to start scrcpy-server.')
        return inner

    @stable
    def tap(self, x: int, y: int) -> None:
        self.control.tap(x, y)

    @stable
    def swipe(self, x0, y0, x1, y1, move_duraion: float = 1, hold_before_release: float = 0, fall: bool = True, lift: bool = True):
        frame_time = 1 / 60

        start_time = time.perf_counter()
        end_time = start_time + move_duraion
        fall and self.control.touch(x0, y0, const.ACTION_DOWN)
        t1 = time.perf_counter()
        step_time = t1 - start_time
        if step_time < frame_time:
            time.sleep(frame_time - step_time)
        while True:
            t0 = time.perf_counter()
            if t0 > end_time:
                break
            time_progress = (t0 - start_time) / move_duraion
            path_progress = time_progress
            self.control.touch(int(x0 + (x1 - x0) * path_progress),
                               int(y0 + (y1 - y0) * path_progress), const.ACTION_MOVE)
            t1 = time.perf_counter()
            step_time = t1 - t0
            if step_time < frame_time:
                time.sleep(frame_time - step_time)
        self.control.touch(x1, y1, const.ACTION_MOVE)
        if hold_before_release > 0:
            time.sleep(hold_before_release)
        lift and self.control.touch(x1, y1, const.ACTION_UP)
