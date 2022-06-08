from __future__ import annotations

import os
import time
# import random
from typing import Union

from ... import config
from ...log import log_sync, logger
from ..adb_client import ADBClient
from ..utils import download_file
from .command import CommandBuilder
from .session import Session

# MNT_PREBUILT_URL = 'https://github.com/williamfzc/stf-binaries/raw/master/node_modules/minitouch-prebuilt/prebuilt'
MNT_PREBUILT_URL = 'https://oss.nano.ac/arknights_mower/minitouch'
MNT_PATH = '/data/local/tmp/minitouch'


class Client(object):
    """ Use minitouch to control Android devices easily """

    def __init__(self, client: ADBClient, touch_device: str = config.MNT_TOUCH_DEVICE) -> None:
        self.client = client
        self.touch_device = touch_device
        self.process = None
        self.start()

    def start(self) -> None:
        self.__install()
        self.__server()

    def __del__(self) -> None:
        self.stop()

    def stop(self) -> None:
        self.__server_stop()

    def __install(self) -> None:
        """ install minitouch for android devices """
        self.abi = self.__get_abi()
        if self.__is_mnt_existed():
            logger.debug(
                f'minitouch already existed in {self.client.device_id}')
        else:
            self.__download_mnt()

    def __get_abi(self) -> str:
        """ query device ABI """
        abi = self.client.cmd_shell('getprop ro.product.cpu.abi', True).strip()
        logger.debug(f'device_abi: {abi}')
        return abi

    def __is_mnt_existed(self) -> bool:
        """ check if minitouch is existed in the device """
        file_list = self.client.cmd_shell('ls /data/local/tmp', True)
        return 'minitouch' in file_list

    def __download_mnt(self) -> None:
        """ download minitouch """
        url = f'{MNT_PREBUILT_URL}/{self.abi}/bin/minitouch'
        logger.info(f'minitouch url: {url}')
        mnt_path = download_file(url)

        # push and grant
        self.client.cmd_push(mnt_path, MNT_PATH)
        self.client.cmd_shell(f'chmod 777 {MNT_PATH}')
        logger.info('minitouch already installed in {MNT_PATH}')

        # remove temp
        os.remove(mnt_path)

    def __server(self) -> None:
        """ execute minitouch with adb shell """
        # self.port = self.__get_port()
        self.port = config.MNT_PORT
        self.__forward_port()
        self.process = None
        r, self.stderr = os.pipe()
        log_sync('minitouch', r).start()
        self.__start_mnt()

        # make sure minitouch is up
        time.sleep(1)
        if not self.check_mnt_alive(False):
            raise RuntimeError('minitouch did not work. see https://github.com/Konano/arknights-mower/issues/82')

    def __server_stop(self) -> None:
        """ stop minitouch """
        self.process and self.process.kill()

    # def __get_port(cls) -> int:
    #     """ get a random port from port set """
    #     while True:
    #         port = random.choice(list(range(20000, 21000)))
    #         if is_port_using(DEFAULT_HOST, port):
    #             return port

    def __forward_port(self) -> None:
        """ allow pc access minitouch with port """
        output = self.client.cmd(
            f'forward tcp:{self.port} localabstract:minitouch')
        logger.debug(f'output: {output}')

    def __start_mnt(self) -> None:
        """ fork a process to start minitouch on android """
        if self.touch_device is None:
            self.process = self.client.process('/data/local/tmp/minitouch', [], self.stderr)
        else:
            self.process = self.client.process('/data/local/tmp/minitouch', ['-d', self.touch_device], self.stderr)

    def check_mnt_alive(self, restart: bool = True) -> bool:
        """ check if minitouch process alive """
        if self.process and self.process.poll() is None:
            return True
        elif restart:
            self.__server_stop()
            self.__forward_port()
            self.__start_mnt()
            time.sleep(1)
            if not (self.process and self.process.poll() is None):
                raise RuntimeError('minitouch did not work. see https://github.com/Konano/arknights-mower/issues/82')
            return True
        return False

    def check_adb_alive(self) -> bool:
        """ check if adb server alive """
        return self.client.check_server_alive()

    def convert_coordinate(self, point: tuple[int, int], display_frames: tuple[int, int, int], max_x: int, max_y: int) -> tuple[int, int]:
        """
        check compatibility mode and convert coordinate
        see details: https://github.com/Konano/arknights-mower/issues/85
        """
        if not config.MNT_COMPATIBILITY_MODE:
            return point
        x, y = point
        w, h, r = display_frames
        if r == 1:
            return [(h - y) * max_x // h, x * max_y // w]
        if r == 3:
            return [y * max_x // h, (w - x) * max_y // w]
        logger.debug(f'warning: unexpected rotation parameter: display_frames({w}, {h}, {r})')
        return point

    def tap(self, points: list[tuple[int, int]], display_frames: tuple[int, int, int], pressure: int = 100, duration: int = None, lift: bool = True) -> None:
        """
        tap on screen with pressure and duration

        :param points: list[int], look like [(x1, y1), (x2, y2), ...]
        :param display_frames: tuple[int, int, int], which means [weight, high, rotation] by "adb shell dumpsys window | grep DisplayFrames"
        :param pressure: default to 100
        :param duration: in milliseconds
        :param lift: if True, "lift" the touch point
        """
        self.check_adb_alive()
        self.check_mnt_alive()

        builder = CommandBuilder()
        points = [list(map(int, point)) for point in points]
        with Session(self.port) as conn:
            for id, point in enumerate(points):
                x, y = self.convert_coordinate(point, display_frames, int(conn.max_x), int(conn.max_y))
                builder.down(id, x, y, pressure)
            builder.commit()

            if duration:
                builder.wait(duration)
                builder.commit()

            if lift:
                for id in range(len(points)):
                    builder.up(id)

            builder.publish(conn)

    def __swipe(self, points: list[tuple[int, int]], display_frames: tuple[int, int, int], pressure: int = 100, duration: Union[list[int], int] = None, up_wait: int = 0, fall: bool = True, lift: bool = True) -> None:
        """
        swipe between points one by one, with pressure and duration

        :param points: list, look like [(x1, y1), (x2, y2), ...]
        :param display_frames: tuple[int, int, int], which means [weight, high, rotation] by "adb shell dumpsys window | grep DisplayFrames"
        :param pressure: default to 100
        :param duration: in milliseconds
        :param up_wait: in milliseconds
        :param fall: if True, "fall" the first touch point
        :param lift: if True, "lift" the last touch point
        """
        self.check_adb_alive()
        self.check_mnt_alive()

        points = [list(map(int, point)) for point in points]
        if not isinstance(duration, list):
            duration = [duration] * (len(points) - 1)
        assert len(duration) + 1 == len(points)

        builder = CommandBuilder()
        with Session(self.port) as conn:
            if fall:
                x, y = self.convert_coordinate(points[0], display_frames, int(conn.max_x), int(conn.max_y))
                builder.down(0, x, y, pressure)
                builder.publish(conn)

            for idx, point in enumerate(points[1:]):
                x, y = self.convert_coordinate(point, display_frames, int(conn.max_x), int(conn.max_y))
                builder.move(0, x, y, pressure)
                if duration[idx-1]:
                    builder.wait(duration[idx-1])
                builder.commit()
            builder.publish(conn)

            if lift:
                builder.up(0)
                if up_wait:
                    builder.wait(up_wait)
                builder.publish(conn)

    def swipe(self, points: list[tuple[int, int]], display_frames: tuple[int, int, int], pressure: int = 100, duration: Union[list[int], int] = None, up_wait: int = 0, part: int = 10, fall: bool = True, lift: bool = True) -> None:
        """
        swipe between points one by one, with pressure and duration
        it will split distance between points into pieces

        :param points: list, look like [(x1, y1), (x2, y2), ...]
        :param display_frames: tuple[int, int, int], which means [weight, high, rotation] by "adb shell dumpsys window | grep DisplayFrames"
        :param pressure: default to 100
        :param duration: in milliseconds
        :param up_wait: in milliseconds
        :param part: default to 10
        :param fall: if True, "fall" the first touch point
        :param lift: if True, "lift" the last touch point
        """
        points = [list(map(int, point)) for point in points]
        if not isinstance(duration, list):
            duration = [duration] * (len(points) - 1)
        assert len(duration) + 1 == len(points)
        
        new_points = [points[0]]
        new_duration = []
        for id in range(1, len(points)):
            pre_point = points[id-1]
            cur_point = points[id]
            offset = (
                (cur_point[0] - pre_point[0]) // part,
                (cur_point[1] - pre_point[1]) // part,
            )
            new_points += [
                (pre_point[0] + i * offset[0], pre_point[1] + i * offset[1])
                for i in range(1, part+1)
            ]
            if duration[id-1] is None:
                new_duration += [None] * part
            else:
                new_duration += [duration[id-1] // part] * part
        self.__swipe(new_points, display_frames, pressure, new_duration, up_wait, fall, lift)
