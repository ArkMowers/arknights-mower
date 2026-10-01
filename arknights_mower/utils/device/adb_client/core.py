import os
import re
import socket
import subprocess
from threading import Lock
from typing import Optional, Union
from weakref import WeakSet

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.config.device_profile import LEGACY_NAMES
from arknights_mower.utils.device.adb_client.server import (
    adb_command,
    adb_subprocess_options,
    guard_adb,
    run_adb,
)
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.adb_client.utils import run_cmd
from arknights_mower.utils.device.io_budget import budget_sleep as csleep
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.mumu_info import mumu_endpoint, select_mumu_instance
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import resolve_config_path


def is_tcp_serial(serial: str) -> bool:
    """ADB TCP endpoints have a host and numeric port; USB serials do not."""
    return bool(re.fullmatch(r"(?:\[[0-9a-fA-F:]+\]|[^:\s]+):\d+", serial))


def query_mumu_adb_port(simulator) -> Optional[str]:
    """查询 MuMu 管理器返回的目标实例当前 adb 地址。

    仅执行管理器 info 命令并读取 JSON，不连接或控制共享 ADB server。
    实例正在运行（Android 已启动）时返回「adb_host_ip:adb_port」；实例停止、管理器
    不可用或非 MuMu 模拟器时返回 None（表明目标未就绪，应由上层启动模拟器再重探）。
    adb_port 以管理器上报为准，避免按 16384+32*index 外推的端口与实际漂移不一致。
    """
    if simulator.name not in LEGACY_NAMES["windows.mumu12"]:
        return None
    manager = os.path.join(simulator.simulator_folder, "MuMuManager.exe")
    if not os.path.isfile(manager):
        # 部分安装版本管理器位于安装根目录的 shell 子目录
        manager = os.path.join(simulator.simulator_folder, "shell", "MuMuManager.exe")
    if not os.path.isfile(manager):
        manager = os.path.join(
            os.path.dirname(simulator.simulator_folder), "shell", "MuMuManager.exe"
        )
    if not os.path.isfile(manager):
        logger.debug(f"MuMuManager 不存在：{manager}")
        return None
    try:
        out = subprocess.run(
            [manager, "info", "-v", "all"],
            # 端口发现会反复执行；仅重定向输出不会隐藏 Windows 控制台。
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=io_timeout(5),
        ).stdout.strip()
        _, entry = select_mumu_instance(out, simulator.index)
        return mumu_endpoint(entry)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class Client:
    """ADB Client"""

    def __init__(
        self,
        device_id: str = None,
        connect: str = None,
        adb_bin: str = None,
        *,
        wait_for_device: bool = True,
        strict_target: bool = False,
    ) -> None:
        if strict_target and (not device_id or not device_id.strip()):
            raise ValueError("设备 serial 不能为空")
        self.device_id = device_id
        self.connect = connect
        self.adb_bin = adb_bin
        self.strict_target = strict_target
        self.error_limit = 3
        self.owner_pid = os.getpid()
        self._resource_lock = Lock()
        self._closed = False
        self._interrupted = False
        self._sessions = WeakSet()
        self._streams = WeakSet()
        self.__init_adb()
        self.__init_device(wait_for_device=wait_for_device)

    def __init_adb(self) -> None:
        if self.adb_bin is not None:
            return
        adb_bin = resolve_config_path(config.conf.maa_adb_path)
        logger.debug(f"try adb binary: {adb_bin}")
        if self.__check_adb(adb_bin):
            self.adb_bin = adb_bin
            return
        raise ConnectionError("Can't start adb server")

    def __init_device(self, *, wait_for_device: bool = True) -> None:
        if getattr(self, "strict_target", False):
            # The application has already verified this exact target and binary.
            # A changed list cannot authorize discovery or another transport.
            rows = Session().devices_list()
            matches = [state for serial, state in rows if serial == self.device_id]
            if matches != ["device"]:
                raise ConnectionError(
                    "Device connection failure: pinned target not ready"
                )
            return
        # wait for the newly started ADB server to probe emulators
        csleep(1)
        # 启动时先确认 adb server 已启动：走 adb.exe 命令路径可让未运行的 server 自动拉起，
        # 仅探活不依赖特定设备，避免因 disconnect 未注册设备抛错。拉起失败才抛。
        try:
            self.__exec("start-server")
        except (subprocess.CalledProcessError, OSError) as e:
            raise ConnectionError("Can't start adb server") from e
        self.__connect_device()
        # 模拟器重启/更新后设备可能尚未在 adb 就绪：端点可能会漂移、设备短暂离线或仍在注册。
        # 首次连接先快速探测，失败后由上层立即启动模拟器；重启后及运行中重连保留等待。
        attempts = (
            max(1, (int(config.conf.simulator.wait_time) + 1) // 2)
            if wait_for_device
            else 0
        )
        for _ in range(attempts):
            devices = self.__available_devices()
            if self.device_id in devices:
                logger.info(devices)
                return
            logger.debug(
                f"设备未就绪：{devices}，重新选择端口 {self.device_id or config.conf.adb}"
            )
            # 端口可能因模拟器重启/更新而漂移：重跑完整选择逻辑（重发现 + 认领存活设备）后重连。
            self.device_id = self.__choose_devices(devices)
            target = self.device_id or config.conf.adb
            if target and is_tcp_serial(target):
                Session().connect(target)
            csleep(2)
        devices = self.__available_devices()
        logger.info(devices)
        if self.device_id not in devices:
            logger.error(
                "未检测到相应设备。请运行 `adb devices` 确认列表中列出了目标模拟器或设备。"
            )
            raise ConnectionError("Device connection failure")

    def __connect_device(self) -> None:
        """选定 device_id 并建立到对应端点的连接（原 __init_device 的选中/连接逻辑）。"""
        if self.device_id is None or self.device_id != config.conf.adb:
            self.device_id = self.__choose_devices()
        if self.device_id is None:
            target = self.connect or config.conf.adb
            if target and is_tcp_serial(target):
                Session().connect(target)
            self.device_id = self.__choose_devices()
        elif self.connect is None and is_tcp_serial(self.device_id):
            Session().connect(self.device_id)

    def __choose_devices(self, devices: list[str] | None = None) -> Optional[str]:
        """choose available devices"""
        if devices is None:
            devices = self.__available_devices()
        if config.conf.adb in devices:
            return config.conf.adb
        # 配置端口不在线：重新发现模拟器当前真实 adb 端口（双模拟器下端口可能漂移或未连）
        target = self.refresh_target()
        if target in devices:
            return target

    def __available_devices(self) -> list[str]:
        """return available devices"""
        return [x[0] for x in Session().devices_list() if x[1] == "device"]

    def refresh_target(self) -> str:
        """重新发现目标模拟器当前 adb 端点并同步到 device_id / config.conf.adb。

        优先读取模拟器管理器上报的真实 adb_port（如 MuMu 双开时端口可能漂移），
        而不是一直连 config.conf.adb 里写死的端口；查询失败或实例未启动（无 adb
        字段）时保留现有 device_id，由上层重试/重启兜底。只在内存更新，不写回配置。
        """
        if getattr(self, "strict_target", False):
            return self.device_id
        discovered = query_mumu_adb_port(config.conf.simulator)
        if discovered is not None:
            config.conf.set_device_endpoint(discovered)
            self.device_id = discovered
        return self.device_id or config.conf.adb

    def __exec(self, cmd: str, adb_bin: str = None) -> None:
        """exec command with adb_bin"""
        logger.debug(f"client.__exec: {cmd}")
        if adb_bin is None:
            adb_bin = self.adb_bin
        # A guarded devices query starts an absent server without issuing an
        # unconditional global lifecycle command against an existing server.
        run_adb(
            [adb_bin, "devices" if cmd == "start-server" else cmd],
            run=subprocess.run,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
            timeout=io_timeout(10),
        )
        # Re-check the session deadline after the external command returns.
        io_timeout(10)

    def reconnect(self, *, wait_for_device: bool = True) -> None:
        """单次重连并确认目标上线；保留启动等待和 MuMu 端口重新发现。"""
        self._check_open()
        self.__init_device(wait_for_device=wait_for_device)

    def _check_open(self):
        if (
            getattr(self, "_closed", False)
            or getattr(self, "_interrupted", False)
            or getattr(self, "owner_pid", os.getpid()) != os.getpid()
        ):
            raise ConnectionError("ADB 会话已关闭或所有权不匹配")

    def check_server_alive(self) -> bool:
        """单次检查 ADB server；连接恢复统一由 Device 管理。"""
        session = Session()
        try:
            return session.run("host:version") is not None
        except (socket.timeout, ConnectionError, RuntimeError):
            return False
        finally:
            session.close()

    def __check_adb(self, adb_bin: str) -> bool:
        """check adb_bin if it works

        通过受版本守卫保护的探测启动尚未运行的 server。
        已运行的 server 不兼容时明确失败，不允许 ADB CLI 自动重启它。
        """
        if not adb_bin or not str(adb_bin).strip():
            return False
        try:
            self.__exec("start-server", adb_bin)
            return self.check_server_alive()
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            return False

    def session(self) -> Session:
        """get a session between adb client and adb server"""
        self._check_open()
        if not self.check_server_alive():
            raise ConnectionError("ADB server is not working")
        session = Session()
        with self._resource_lock:
            if self._closed or self._interrupted:
                session.close()
                raise ConnectionError("ADB 会话已关闭")
            self._sessions.add(session)
        try:
            return session.device(self.device_id)
        except BaseException:
            session.close()
            raise

    def close(self):
        """Interrupt this client's sockets without touching ADB transports."""
        if self.owner_pid != os.getpid():
            return
        with self._resource_lock:
            if self._closed:
                return
            self._closed = True
            resources = (*self._sessions, *self._streams)
            self._sessions.clear()
            self._streams.clear()
        errors = []
        for resource in resources:
            try:
                resource.close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]

    def interrupt_io(self):
        """Cancel socket operations; final close still owns every handle."""
        if self.owner_pid != os.getpid():
            return
        with self._resource_lock:
            if self._closed or self._interrupted:
                return
            self._interrupted = True
            resources = (*self._sessions, *self._streams)
        errors = []
        for resource in resources:
            try:
                resource.interrupt()
            except Exception as exc:
                errors.append(exc)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]

    def run(self, cmd: str) -> Optional[bytes]:
        """run adb exec command"""
        logger.debug(f"command: {cmd}")
        try:
            session = self.session()
        except Exception as exc:
            exc.input_not_sent = True
            raise
        try:
            resp = session.exec(cmd)
        finally:
            session.close()
        if len(resp) <= 256:
            logger.debug(f"response: {repr(resp)}")
        return resp

    def cmd(self, cmd: str | list[str], decode: bool = False) -> Union[bytes, str]:
        """run adb command with adb_bin"""
        self._check_open()
        if isinstance(cmd, str):
            cmd = cmd.split(" ")
        cmd = [self.adb_bin, "-s", self.device_id] + cmd
        return run_cmd(cmd, decode)

    def cmd_shell(self, cmd: str, decode: bool = False) -> Union[bytes, str]:
        """run adb shell command with adb_bin"""
        self._check_open()
        cmd = [self.adb_bin, "-s", self.device_id, "shell"] + cmd.split(" ")
        return run_cmd(cmd, decode)

    def cmd_push(self, filepath: str, target: str) -> None:
        """push file into device with adb_bin"""
        self._check_open()
        cmd = [self.adb_bin, "-s", self.device_id, "push", filepath, target]
        run_cmd(cmd)

    def process(
        self, path: str, args: list[str] = [], stderr: int = subprocess.DEVNULL
    ) -> subprocess.Popen:
        self._check_open()
        logger.debug(f"run process: {path}, args: {args}")
        cmd = [self.adb_bin, "-s", self.device_id, "shell", path] + args
        guard_adb(self.adb_bin, timeout=io_timeout(10), run=subprocess.run)
        return subprocess.Popen(
            adb_command(cmd),
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
            **adb_subprocess_options(),
        )

    def push(self, target_path: str, target: bytes) -> None:
        """push file into device"""
        session = self.session()
        try:
            session.push(target_path, target)
        finally:
            session.close()

    def stream(self, cmd: str) -> Socket:
        """run adb command, return socket"""
        session = self.session()
        try:
            session.request(cmd)
            with self._resource_lock:
                if self._closed or self._interrupted:
                    raise ConnectionError("ADB 会话已关闭")
                stream = session.detach()
                self._streams.add(stream)
                return stream
        finally:
            session.close()

    def stream_shell(self, cmd: str) -> Socket:
        """run adb shell command, return socket"""
        return self.stream("shell:" + cmd)

    def android_version(self) -> str:
        """get android_version"""
        return self.cmd_shell("getprop ro.build.version.release", True)
