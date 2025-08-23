import socket
import subprocess
import time
from typing import Optional, Union

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.csleep import csleep
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.adb_client.utils import run_cmd
from arknights_mower.utils.log import logger


class Client:
    """ADB Client"""

    def __init__(
        self, device_id: str = None, connect: str = None, adb_bin: str = None
    ) -> None:
        self.device_id = device_id
        self.connect = connect
        self.adb_bin = adb_bin
        self.error_limit = 3
        self.__init_adb()
        self.__init_device()

    def __init_adb(self) -> None:
        if self.adb_bin is not None:
            return
        adb_bin = config.conf.maa_adb_path
        logger.debug(f"try adb binary: {adb_bin}")
        if self.__check_adb(adb_bin):
            self.adb_bin = adb_bin
            return
        raise RuntimeError("Can't start adb server")

    def __init_device(self) -> None:
        # wait for the newly started ADB server to probe emulators
        csleep(1)
        if self.device_id is None or self.device_id != config.conf.adb:
            self.device_id = self.__choose_devices()
        if self.device_id is None:
            if self.connect is None:
                Session().connect(config.conf.adb)
            else:
                Session().connect(self.connect)
            self.device_id = self.__choose_devices()
        elif self.connect is None:
            Session().connect(self.device_id)

        # if self.device_id is None or self.device_id not in config.ADB_DEVICE:
        #     if self.connect is None or self.device_id not in config.ADB_CONNECT:
        #         for connect in config.ADB_CONNECT:
        #             Session().connect(connect)
        #     else:
        #         Session().connect(self.connect)
        #     self.device_id = self.__choose_devices()
        logger.info(self.__available_devices())
        if self.device_id not in self.__available_devices():
            logger.error(
                "未检测到相应设备。请运行 `adb devices` 确认列表中列出了目标模拟器或设备。"
            )
            raise RuntimeError("Device connection failure")

    def __choose_devices(self) -> Optional[str]:
        """choose available devices"""
        devices = self.__available_devices()
        if config.conf.adb in devices:
            return config.conf.adb
        if len(devices) > 0 and config.conf.adb == "":
            logger.debug(devices[0])
            return devices[0]

    def __available_devices(self) -> list[str]:
        """return available devices"""
        return [x[0] for x in Session().devices_list() if x[1] != "offline"]

    def __exec(self, cmd: str, adb_bin: str = None) -> None:
        """exec command with adb_bin"""
        logger.debug(f"client.__exec: {cmd}")
        if adb_bin is None:
            adb_bin = self.adb_bin
        subprocess.run(
            [adb_bin, cmd],
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        )

    def __run(self, cmd: str, restart: bool = True) -> Optional[bytes]:
        """run command with Session"""
        error_limit = 3
        connect_retry = 2
        while True:
            try:
                return Session().run(cmd)
            except (socket.timeout, ConnectionRefusedError, RuntimeError):
                if restart and error_limit > 0:
                    error_limit -= 1
                    if self.device_id and connect_retry > 0:
                        connect_retry -= 1
                        self.__exec(f"disconnect {self.device_id}")
                        self.__exec(f"connect {self.device_id}")
                        time.sleep(0.5)
                    else:
                        self.__exec("kill-server")
                        self.__exec("start-server")
                        time.sleep(10)
                    continue
                return

    def check_server_alive(self, restart: bool = True) -> bool:
        """check adb server if it works"""
        return self.__run("host:version", restart) is not None

    def __check_adb(self, adb_bin: str) -> bool:
        """check adb_bin if it works"""
        try:
            self.__exec("start-server", adb_bin)
            if self.check_server_alive(False):
                return True
            self.__exec("kill-server", adb_bin)
            self.__exec("start-server", adb_bin)
            time.sleep(10)
            if self.check_server_alive(False):
                return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
        else:
            return False

    def session(self) -> Session:
        """get a session between adb client and adb server"""
        if not self.check_server_alive():
            raise RuntimeError("ADB server is not working")
        return Session().device(self.device_id)

    def run(self, cmd: str) -> Optional[bytes]:
        """run adb exec command"""
        logger.debug(f"command: {cmd}")
        error_limit = 3
        while True:
            try:
                resp = self.session().exec(cmd)
                break
            except (socket.timeout, ConnectionRefusedError, RuntimeError) as e:
                if error_limit > 0:
                    error_limit -= 1
                    # 只断开并重连当前设备，避免影响其他adb连接
                    if self.device_id:
                        self.__exec(f"disconnect {self.device_id}")
                        self.__exec(f"connect {self.device_id}")
                        time.sleep(3)
                        self.__init_device()
                    else:
                        self.__exec("kill-server")
                        self.__exec("start-server")
                        time.sleep(10)
                        self.__init_device()
                    continue
                raise e
        if len(resp) <= 256:
            logger.debug(f"response: {repr(resp)}")
        return resp

    def cmd(self, cmd: str | list[str], decode: bool = False) -> Union[bytes, str]:
        """run adb command with adb_bin"""
        if isinstance(cmd, str):
            cmd = cmd.split(" ")
        cmd = [self.adb_bin, "-s", self.device_id] + cmd
        return run_cmd(cmd, decode)

    def cmd_shell(self, cmd: str, decode: bool = False) -> Union[bytes, str]:
        """run adb shell command with adb_bin"""
        cmd = [self.adb_bin, "-s", self.device_id, "shell"] + cmd.split(" ")
        return run_cmd(cmd, decode)

    def cmd_push(self, filepath: str, target: str) -> None:
        """push file into device with adb_bin"""
        cmd = [self.adb_bin, "-s", self.device_id, "push", filepath, target]
        run_cmd(cmd)

    def process(
        self, path: str, args: list[str] = [], stderr: int = subprocess.DEVNULL
    ) -> subprocess.Popen:
        logger.debug(f"run process: {path}, args: {args}")
        cmd = [self.adb_bin, "-s", self.device_id, "shell", path] + args
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        )

    def push(self, target_path: str, target: bytes) -> None:
        """push file into device"""
        self.session().push(target_path, target)

    def stream(self, cmd: str) -> Socket:
        """run adb command, return socket"""
        return self.session().request(cmd, True).sock

    def stream_shell(self, cmd: str) -> Socket:
        """run adb shell command, return socket"""
        return self.stream("shell:" + cmd)

    def android_version(self) -> str:
        """get android_version"""
        return self.cmd_shell("getprop ro.build.version.release", True)
