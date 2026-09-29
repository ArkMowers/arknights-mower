import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.device.adb_client.core import is_tcp_serial
from arknights_mower.utils.device.adb_client.server import SharedADBError, run_adb
from arknights_mower.utils.log import logger


class Simulator_Type(Enum):
    Nox = "夜神"
    MuMu12 = "MuMu12"
    Leidian9 = "雷电9"
    Leidian14 = "雷电14"
    Waydroid = "Waydroid"
    ReDroid = "ReDroid"
    MuMuPro = "MuMuPro"
    Genymotion = "Genymotion"


@dataclass
class SimulatorCommandSet:
    stop: list[str]
    start: list[str]
    blocking: bool = False


def _clear_mumu_adb_transport() -> None:
    """仅断开活动设备会话验证过的 MuMu TCP 端点，保留共享 ADB 服务。"""
    from arknights_mower.__main__ import device_control

    def disconnect(device):
        client = device.client
        if client is None:
            return
        target, adb_bin = client.device_id, client.adb_bin
        if not target or not adb_bin or not is_tcp_serial(target):
            return
        try:
            run_adb(
                [adb_bin, "disconnect", target],
                run=subprocess.run,
                check=False,
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
                if __system__ == "windows"
                else 0,
            )
            logger.info("已断开当前 MuMu 实例的 ADB 端点")
        except (OSError, subprocess.SubprocessError, SharedADBError):
            logger.debug("断开 MuMu adb 端点失败", exc_info=True)

    # The session lock keeps the verified client bound until cleanup completes.
    # A closed session skips cleanup instead of reusing its saved endpoint.
    device_control.execute(disconnect)


def restart_simulator(stop: bool = True, start: bool = True) -> bool:
    """Compatibility entry: application sessions decide startup and recovery.

    A stop-only request is the user's explicit idle shutdown policy.
    """
    if config.conf.device.preset_id == "manual.physical":
        return False
    if start:
        from arknights_mower.__main__ import device_control

        result = device_control.recover() if stop else device_control.start()
        result.unwrap()
        return result.ok
    if not stop:
        return True
    if config.conf.device.preset_id in {"macos.avd", "linux.avd"}:
        from arknights_mower.__main__ import device_control

        return device_control.stop_owned_avd()
    data = config.conf.simulator
    simulator_type = data.name
    if simulator_type not in [item.value for item in Simulator_Type]:
        logger.warning(f"尚未支持{simulator_type}自动关闭")
        return False
    try:
        commands = build_command_set(simulator_type, data.index)
    except ValueError as exc:
        logger.warning(str(exc))
        return False
    logger.info(f"关闭{simulator_type}模拟器")
    stopped = run_command(commands.stop, data.simulator_folder, 10, True)
    if (
        stopped
        and simulator_type == Simulator_Type.MuMu12.value
        and config.conf.fix_mumu12_adb_disconnect
    ):
        _clear_mumu_adb_transport()
    return stopped


def build_command_set(simulator_type: str, index) -> SimulatorCommandSet:
    if simulator_type == Simulator_Type.Waydroid.value:
        return SimulatorCommandSet(
            stop=["waydroid", "session", "stop"],
            start=["waydroid", "show-full-ui"],
        )
    identifier = str(index).strip() if index is not None else ""
    if not identifier or identifier.startswith("-") or "\x00" in identifier:
        raise ValueError("模拟器操作需要有效的实例标识。")
    idx = normalize_index(index)

    if simulator_type == Simulator_Type.Nox.value:
        if idx < 0:
            raise ValueError("夜神操作需要有效的实例索引。")
        base = ["Nox.exe", f"-clone:Nox_{idx}"]
        return SimulatorCommandSet(stop=[*base, "-quit"], start=base)

    if simulator_type == Simulator_Type.MuMu12.value:
        if idx < 0:
            raise ValueError("MuMu 操作需要有效的实例索引。")
        cmd = ["MuMuManager.exe", "api", "-v", str(idx)]
        return SimulatorCommandSet(
            stop=[*cmd, "shutdown_player"],
            start=[*cmd, "launch_player"],
        )

    if simulator_type in {
        Simulator_Type.Leidian9.value,
        Simulator_Type.Leidian14.value,
    }:
        if idx < 0:
            raise ValueError("雷电操作需要有效的实例索引。")
        return SimulatorCommandSet(
            stop=["ldconsole.exe", "quit", "--index", str(idx)],
            start=["ldconsole.exe", "launch", "--index", str(idx)],
        )

    if simulator_type == Simulator_Type.ReDroid.value:
        return SimulatorCommandSet(
            stop=["docker", "stop", "-t", "0", identifier],
            start=["docker", "start", identifier],
        )

    if simulator_type == Simulator_Type.MuMuPro.value:
        return SimulatorCommandSet(
            stop=["Contents/MacOS/mumutool", "close", identifier],
            start=["Contents/MacOS/mumutool", "open", identifier],
        )

    if simulator_type != Simulator_Type.Genymotion.value:
        raise ValueError("不支持的模拟器类型。")
    if __system__ == "windows":
        gmtool = "gmtool.exe"
    elif __system__ == "darwin":
        gmtool = "Contents/MacOS/gmtool"
    else:
        gmtool = "./gmtool"
    return SimulatorCommandSet(
        stop=[gmtool, "admin", "stop", identifier],
        start=[gmtool, "admin", "start", identifier],
        blocking=True,
    )


def normalize_index(index) -> int:
    if isinstance(index, str) and index.startswith("Nox_"):
        index = index.removeprefix("Nox_")
    try:
        return int(index)
    except (TypeError, ValueError):
        return -1


def run_command(
    cmd: list[str], folder_path: str, wait_time: int, blocking: bool
) -> bool:
    logger.debug(cmd)
    try:
        argv = list(cmd)
        if folder_path:
            executable = Path(folder_path) / argv[0]
            if executable.is_file():
                argv[0] = str(executable.resolve())
        process = subprocess.run(
            argv,
            shell=False,
            cwd=folder_path or None,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
            capture_output=True,
            text=True,
            timeout=max(1, wait_time),
        )
        logger.debug((process.stdout, process.stderr))
        return process.returncode == 0
    except (OSError, subprocess.SubprocessError):
        logger.debug("模拟器命令失败", exc_info=True)
        return False
