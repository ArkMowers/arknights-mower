from __future__ import annotations

import os
import time
import socket
# import random
from typing import Tuple, List

from .client import Client
from .utils import download_file, is_port_using
from .. import config
from ..log import logger, log_sync

MNT_PATH = '/data/local/tmp/minitouch'
MNT_PREBUILT_URL = 'https://github.com/williamfzc/stf-binaries/raw/master/node_modules/minitouch-prebuilt/prebuilt'
DEFAULT_HOST = '127.0.0.1'
DEFAULT_DELAY = 0.05


class CommandBuilder(object):
    """ Build command str for minitouch """

    def __init__(self) -> None:
        self.content = ''
        self.delay = 0

    def append(self, new_content: str) -> None:
        self.content += new_content + '\n'

    def commit(self) -> None:
        """ add minitouch command: 'c\n' """
        self.append('c')

    def wait(self, ms: int) -> None:
        """ add minitouch command: 'w <ms>\n' """
        self.append(f'w {ms}')
        self._delay += ms

    def up(self, contact_id: int) -> None:
        """ add minitouch command: 'u <contact_id>\n' """
        self.append(f'u {contact_id}')

    def down(self, contact_id: int, x: int, y: int, pressure: int) -> None:
        """ add minitouch command: 'd <contact_id> <x> <y> <pressure>\n' """
        self.append(f'd {contact_id} {x} {y} {pressure}')

    def move(self, contact_id: int, x: int, y: int, pressure: int) -> None:
        """ add minitouch command: 'm <contact_id> <x> <y> <pressure>\n' """
        self.append(f'm {contact_id} {x} {y} {pressure}')

    def publish(self, connection: MNTConnection):
        """ apply current commands to device """
        self.commit()
        logger.debug('send operation: %s' % self.content.replace('\n', '\\n'))
        connection.send(self.content)
        time.sleep(self.delay / 1000 + DEFAULT_DELAY)
        self.reset()

    def reset(self):
        """ clear current commands """
        self.content = ''


class MiniTouch(object):
    """ Use minitouch to control Android devices easily """

    def __init__(self, client: Client, touch_device: str = config.ADB_TOUCH_DEVICE) -> None:
        self.client = client
        self.touch_device = touch_device
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
        abi = self.client.shell('getprop ro.product.cpu.abi', True).strip()
        logger.debug(f'device_abi: {abi}')
        return abi

    def __is_mnt_existed(self) -> bool:
        """ check if minitouch is existed in the device """
        file_list = self.client.shell('ls /data/local/tmp', True)
        return 'minitouch' in file_list

    def __download_mnt(self) -> None:
        """ download minitouch """
        url = f'{MNT_PREBUILT_URL}/{self.abi}/bin/minitouch'
        logger.info(f'minitouch url: {url}')
        mnt_path = download_file(url)

        # push and grant
        self.client.push(mnt_path, MNT_PATH)
        self.client.shell(f'chmod 777 {MNT_PATH}')
        logger.info('minitouch already installed in {MNT_PATH}')

        # remove temp
        os.remove(mnt_path)

    def __server(self) -> None:
        """ execute minitouch with adb shell """
        # self.port = self.__get_port()
        self.port = config.ADB_MNT_PORT
        self.__forward_port()
        self.process = None
        r, self.stderr = os.pipe()
        log_sync('minitouch', r).start()
        self.__start_mnt()

        # make sure minitouch is up
        time.sleep(1)
        assert (
            self.check_mnt_alive(False)
        ), "minitouch did not work. see https://github.com/williamfzc/pyminitouch/issues/11"

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
        output = self.client.shell_ext(
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
            assert (
                self.process and self.process.poll() is None
            ), "minitouch did not work. see https://github.com/williamfzc/pyminitouch/issues/11"
            return True
        return False

    def check_server_alive(self) -> bool:
        """ check if adb server alive """
        return self.client.check_server_alive()

    def tap(self, points: List[Tuple[int, int]], pressure: int = 100, duration: int = None, lift: bool = True) -> None:
        """
        tap on screen with pressure and duration

        :param points: list[int], look like [(x1, y1), (x2, y2), ...]
        :param pressure: default to 100
        :param duration: in milliseconds
        :param lift: if True, "lift" the touch point
        """
        self.check_server_alive()
        self.check_mnt_alive()

        builder = CommandBuilder()
        points = [list(map(int, point)) for point in points]
        for id, point in enumerate(points):
            x, y = point
            builder.down(id, x, y, pressure)
        builder.commit()

        if duration:
            builder.wait(duration)
            builder.commit()

        if lift:
            for id in range(len(points)):
                builder.up(id)

        with MNTConnection(self.port) as conn:
            builder.publish(conn)

    def swipe(self, points: List[Tuple[int, int]], pressure: int = 100, duration: int = None, fall: bool = True, lift: bool = True) -> None:
        """
        swipe between points one by one, with pressure and duration

        :param points: list, look like [(x1, y1), (x2, y2), ...]
        :param pressure: default to 100
        :param duration: in milliseconds
        :param fall: if True, "fall" the first touch point
        :param lift: if True, "lift" the last touch point
        """
        self.check_server_alive()
        self.check_mnt_alive()

        builder = CommandBuilder()
        points = [list(map(int, point)) for point in points]
        with MNTConnection(self.port) as conn:
            if fall:
                x, y = points[0]
                builder.down(0, x, y, pressure)
                builder.publish(conn)

            for point in points:
                x, y = point
                builder.move(0, x, y, pressure)
                if duration:
                    builder.wait(duration)
                builder.commit()
            builder.publish(conn)

            if lift:
                builder.up(0)
                builder.publish(conn)

    def smooth_swipe(self, points: List[Tuple[int, int]], pressure: int = 100, duration: int = None, part: int = 10, fall: bool = True, lift: bool = True) -> None:
        """
        swipe between points one by one, with pressure and duration
        it will split distance between points into pieces

        :param points: list, look like [(x1, y1), (x2, y2), ...]
        :param pressure: default to 100
        :param duration: in milliseconds
        :param part: default to 10
        :param fall: if True, "fall" the first touch point
        :param lift: if True, "lift" the last touch point
        """
        points = [list(map(int, point)) for point in points]
        new_points = [points[0]]
        for id in range(1, len(points)):
            pre_point = points[id - 1]
            cur_point = points[id]
            offset = (
                (cur_point[0] - pre_point[0]) // part,
                (cur_point[1] - pre_point[1]) // part,
            )
            new_points += [
                (pre_point[0] + i * offset[0], pre_point[1] + i * offset[1])
                for i in range(1, part)
            ]
        self.swipe(new_points, pressure, duration // part, fall, lift)


class MNTConnection(object):
    """ manage socket connection between pc and android """

    def __init__(self, port: int, buf_size: int = 0) -> None:
        self.port = port
        self.buf_size = buf_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((DEFAULT_HOST, port))
        socket_out = self.sock.makefile()

        # v <version>
        # protocol version, usually it is 1. needn't use this
        socket_out.readline()

        # ^ <max-contacts> <max-x> <max-y> <max-pressure>
        _, max_contacts, max_x, max_y, max_pressure, *_ = (
            socket_out.readline().strip().split(' '))
        self.max_contacts = max_contacts
        self.max_x = max_x
        self.max_y = max_y
        self.max_pressure = max_pressure

        # $ <pid>
        _, pid = socket_out.readline().strip().split(' ')
        self.pid = pid

        logger.debug(
            f'minitouch running on port: {self.port}, pid: {self.pid}')
        logger.debug(
            f'max_contact: {max_contacts}; max_x: {max_x}; max_y: {max_y}; max_pressure: {max_pressure}')

    def __enter__(self) -> MNTConnection:
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        pass

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        """ cancel connection """
        self.sock and self.sock.close()
        self.sock = None

    def send(self, content: str) -> bytes:
        content = content.encode('utf8')
        self.sock.sendall(content)
        return self.sock.recv(self.buf_size)
