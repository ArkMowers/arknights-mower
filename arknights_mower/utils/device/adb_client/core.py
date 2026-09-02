import json
import os
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


def query_mumu_adb_port(simulator) -> Optional[str]:
    """查询 MuMu 管理器返回的目标实例当前 adb 地址。

    实例正在运行（Android 已启动）时返回「adb_host_ip:adb_port」；实例停止、管理器
    不可用或非 MuMu 模拟器时返回 None（表明目标未就绪，应由上层启动模拟器再重探）。
    adb_port 以管理器上报为准，避免按 16384+32*index 外推的端口与实际漂移不一致。
    """
    if simulator.name != "MuMu12":
        return None
    manager = os.path.join(simulator.simulator_folder, "MuMuManager.exe")
    if not os.path.isfile(manager):
        # 部分安装版本管理器位于安装根目录的 shell 子目录
        manager = os.path.join(
            os.path.dirname(simulator.simulator_folder), "shell", "MuMuManager.exe"
        )
    if not os.path.isfile(manager):
        logger.debug(f"MuMuManager 不存在：{manager}")
        return None
    try:
        out = subprocess.run(
            [manager, "info", "-v", "all"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        ).stdout.strip()
        instances = json.loads(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None
    target = str(simulator.index)
    if isinstance(instances, dict):
        entry = instances.get(target)
        if entry is None:
            return None
    else:
        entry = next((x for x in instances if str(x.get("index")) == target), None)
        if entry is None:
            return None
    port = entry.get("adb_port")
    if not port:
        # 实例存在但未启动/无 adb 字段：当前没有可连接的端点
        return None
    host = entry.get("adb_host_ip") or "127.0.0.1"
    return f"{host}:{port}"


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
        # 启动时先确认 adb server 已启动：走 adb.exe 命令路径可让未运行的 server 自动拉起，
        # 仅探活不依赖特定设备，避免因 disconnect 未注册设备抛错。拉起失败才抛。
        try:
            self.__exec("start-server")
        except (subprocess.CalledProcessError, OSError) as e:
            raise RuntimeError("Can't start adb server") from e
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
        # 配置端口不在线：重新发现模拟器当前真实 adb 端口（双模拟器下端口可能漂移或未连）
        target = self.refresh_target()
        if target in self.__available_devices():
            return target
        if len(devices) > 0 and config.conf.adb == "":
            logger.debug(devices[0])
            return devices[0]

    def __available_devices(self) -> list[str]:
        """return available devices"""
        return [x[0] for x in Session().devices_list() if x[1] != "offline"]

    def refresh_target(self) -> str:
        """重新发现目标模拟器当前 adb 端点并同步到 device_id / config.conf.adb。

        优先读取模拟器管理器上报的真实 adb_port（如 MuMu 双开时端口可能漂移），
        而不是一直连 config.conf.adb 里写死的端口；查询失败或实例未启动（无 adb
        字段）时保留现有 device_id，由上层重试/重启兜底。只在内存更新，不写回配置。
        """
        discovered = query_mumu_adb_port(config.conf.simulator)
        if discovered is not None:
            config.conf.adb = discovered
            self.device_id = discovered
        return self.device_id or config.conf.adb

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

    def _reconnect_device(self) -> None:
        """断开并重连当前设备（走 adb server 5037）。

        设备未注册或离线时 disconnect/connect 会以非零码退出，属瞬态，不应打断重连
        流程；此前直接用 check=True 抛 CalledProcessError，会在恢复循环里冒泡出来。
        """
        try:
            self.__exec(f"disconnect {self.device_id}")
        except (subprocess.CalledProcessError, OSError):
            logger.debug(f"disconnect {self.device_id} 失败（设备可能未注册）")
        try:
            self.__exec(f"connect {self.device_id}")
        except (subprocess.CalledProcessError, OSError):
            logger.debug(f"connect {self.device_id} 失败")

    def __run(self, cmd: str, restart: bool = True) -> Optional[bytes]:
        """run command with Session"""
        error_limit = 3
        connect_retry = 2
        while True:
            try:
                return Session().run(cmd)
            except (socket.timeout, ConnectionError, RuntimeError):
                if restart and error_limit > 0:
                    error_limit -= 1
                    if self.device_id and connect_retry > 0:
                        connect_retry -= 1
                        self.refresh_target()
                        self._reconnect_device()
                        time.sleep(0.5)
                    else:
                        # 只 start-server：未运行的 server 由 adb 客户端自动拉起；
                        # 显式 kill-server 会中断本可恢复的 server 会话（放大瞬时故障）
                        self.__exec("start-server")
                        time.sleep(10)
                    continue
                return

    def check_server_alive(self, restart: bool = True) -> bool:
        """check adb server if it works"""
        return self.__run("host:version", restart) is not None

    def __check_adb(self, adb_bin: str) -> bool:
        """check adb_bin if it works

        只用 start-server（幂等，不会打断已运行的 adb server）。不做 kill-server：
        重启全局 5037 server 会把共用它的另一台模拟器也踢下线（双模拟器场景互相干扰）。
        """
        try:
            self.__exec("start-server", adb_bin)
            return self.check_server_alive(False)
        except (FileNotFoundError, subprocess.CalledProcessError):
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
            except (socket.timeout, ConnectionError, RuntimeError) as e:
                # b'closed' 是 base ConnectionError（非 ConnectionRefusedError 子类），
                # 漏掉会冒泡到 check_current_focus 的 restart_simulator，杀掉运行中的游戏
                if error_limit > 0:
                    error_limit -= 1
                    # 只断开并重连当前设备，避免影响其他adb连接
                    if self.device_id:
                        self.refresh_target()
                        self._reconnect_device()
                        time.sleep(3)
                        self.__init_device()
                    else:
                        # 只 start-server：未运行的 server 由 adb 客户端自动拉起；
                        # 显式 kill-server 会中断本可恢复的 server 会话（放大瞬时故障）
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
