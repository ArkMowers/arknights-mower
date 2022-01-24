import os
import time
import socket
import typing
import subprocess
from typing import List, Union

from .session import Session
from .utils import download_file, run_cmd
from .. import config
from ..log import logger


class Client(object):
    """ ADB Client """

    def __init__(self, device_id: str = None, connect: str = None, adb_bin: str = None) -> None:
        self.device_id = device_id
        self.connect = connect
        self.adb_bin = adb_bin
        self.error_limit = 3
        self.__init_adb()
        self.__init_device()

    def __init_adb(self) -> None:
        if self.adb_bin is not None:
            return
        for adb_bin in config.ADB_BINARY:
            logger.debug(f'try adb binary: {adb_bin}')
            if self.__check_adb(adb_bin):
                self.adb_bin = adb_bin
                return
        if config.ADB_BUILDIN is None:
            self.__adb_buildin()
        if self.__check_adb(config.ADB_BUILDIN):
            self.adb_bin = config.ADB_BUILDIN
            return
        raise RuntimeError("Can't start adb server")

    def __init_device(self) -> None:
        # wait for the newly started ADB server to probe emulators
        time.sleep(0.5)
        if self.device_id is None:
            self.device_id = self.__choose_devices()
        if self.device_id is None:
            if self.connect is None:
                for connect in config.ADB_CONNECT:
                    Session().connect(connect)
            else:
                Session().connect(self.connect)
            self.device_id = self.__choose_devices()
        if self.device_id not in self.__available_devices():
            logger.error('未检测到相应设备。请运行 `adb devices` 确认列表中列出了目标模拟器或设备。')
            raise RuntimeError('Device connection failure')

    def __choose_devices(self) -> Union[str, None]:
        """ choose available devices """
        devices = self.__available_devices()
        for device in config.ADB_DEVICE:
            if device in devices:
                return device
        if len(devices) > 0:
            return devices[0]

    def __available_devices(self) -> List[str]:
        """ return available devices """
        return [x[0] for x in Session().devices_list() if x[1] != 'offline']

    def __exec(self, cmd: str, adb_bin: str = None) -> None:
        """ exec command with adb_bin """
        if adb_bin is None:
            adb_bin = self.adb_bin
        subprocess.run([adb_bin, cmd], check=True)

    def __run(self, cmd: str, restart: bool = True) -> Union[None, bytes]:
        """ run command with Session """
        error_limit = 3
        while True:
            try:
                return Session().run(cmd)
            except (socket.timeout, ConnectionRefusedError, RuntimeError):
                if restart and error_limit > 0:
                    error_limit -= 1
                    self.__exec('kill-server')
                    self.__exec('start-server')
                    continue
                return

    def __check_server_alive(self, restart: bool = True) -> bool:
        """ check adb server if it works """
        return self.__run('host:version', restart) is not None

    def __check_adb(self, adb_bin: str) -> bool:
        """ check adb_bin if it works """
        try:
            self.__exec('start-server', adb_bin)
            if self.__check_server_alive(False):
                return True
            self.__exec('kill-server', adb_bin)
            self.__exec('start-server', adb_bin)
            if self.__check_server_alive(False):
                return True
        except FileNotFoundError:
            return False
        except subprocess.CalledProcessError:
            return False
        else:
            return False

    def __adb_buildin(self):
        """ download adb_bin """
        raise NotImplementedError  # TODO

    def session(self) -> Session:
        """ get a session between adb client and adb server """
        if not self.__check_server_alive():
            raise RuntimeError('ADB server is not working')
        return Session().device(self.device_id)

    def run(self, cmd: str) -> bytes:
        """ run adb exec command """
        logger.debug(f'command: {cmd}')
        error_limit = 3
        while True:
            try:
                resp = self.session().exec(cmd)
                break
            except (socket.timeout, ConnectionRefusedError, RuntimeError) as e:
                if error_limit > 0:
                    error_limit -= 1
                    self.__exec('kill-server')
                    self.__exec('start-server')
                    self.__init_device()
                    continue
                raise e
        logger.debug(f'response: {repr(resp)}')
        return resp

    def shell(self, cmd: str, decode: bool = False) -> Union[bytes, str]:
        """ run adb shell command with adb_bin """
        cmd = [self.adb_bin, '-s', self.device_id, 'shell'] + cmd.split(' ')
        return run_cmd(cmd, decode)

    def shell_ext(self, cmd: str, decode: bool = False) -> Union[bytes, str]:
        """ run adb command with adb_bin """
        cmd = [self.adb_bin, '-s', self.device_id] + cmd.split(' ')
        return run_cmd(cmd, decode)

    def push(self, filepath: str, target: str) -> None:
        """ push file into device """
        cmd = [self.adb_bin, '-s', self.device_id, 'push', filepath, target]
        run_cmd(cmd)

    def process(self, path: str, args: List[str] = [], stderr: int = subprocess.DEVNULL) -> subprocess.Popen:
        logger.debug(f'run process: {path}, args: {args}')
        cmd = [self.adb_bin, '-s', self.device_id, 'shell', path] + args
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=stderr)
