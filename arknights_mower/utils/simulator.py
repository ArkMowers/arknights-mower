import subprocess
from dataclasses import dataclass
from enum import Enum

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.core import query_mumu_adb_port
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.log import logger


class Simulator_Type(Enum):
    Nox = "夜神"
    MuMu12 = "MuMu12"
    Leidian9 = "雷电9"
    Waydroid = "Waydroid"
    ReDroid = "ReDroid"
    MuMuPro = "MuMuPro"
    Genymotion = "Genymotion"


@dataclass
class SimulatorCommandSet:
    stop: str
    start: str
    blocking: bool = False


def _clear_mumu_adb_transport() -> None:
    """关闭 MuMu12 时清理目标实例的 adb 传输，但不结束共享的 adb server。

    此前 `taskkill /f /t /im adb.exe` 会杀掉 5037 上的全局 adb server，使共用它的
    另一台模拟器一起掉线（双模拟器场景互相干扰）；改为仅断开当前实例的连接端点。
    """
    target = config.conf.adb
    adb_bin = config.conf.maa_adb_path
    if not target or not adb_bin:
        return
    try:
        subprocess.run(
            [adb_bin, "disconnect", target],
            check=False,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        )
        logger.info("结束adb进程（仅断开当前实例端点）")
    except (OSError, subprocess.SubprocessError):
        logger.debug("断开 MuMu adb 端点失败", exc_info=True)


def restart_simulator(stop: bool = True, start: bool = True) -> bool:
    return _restart_simulator(stop=stop, start=start, allow_retry=True)


def _restart_simulator(stop: bool, start: bool, allow_retry: bool) -> bool:
    data = config.conf.simulator
    simulator_type = data.name

    if simulator_type not in [item.value for item in Simulator_Type]:
        logger.warning(f"尚未支持{simulator_type}重启/自动启动")
        csleep(10)
        return False

    # 重启前先同步目标实例当前 adb 端点（端口可能漂移），供后续 wait_for_adb→adb_ready
    # 探测，避免一直探测 config.conf.adb 里已失效的旧端口
    discovered = query_mumu_adb_port(data)
    if discovered is not None:
        config.conf.adb = discovered

    commands = build_command_set(simulator_type, data.index)

    if stop:
        logger.info(f"关闭{simulator_type}模拟器")
        run_command(commands.stop, data.simulator_folder, 0, commands.blocking)
        if (
            simulator_type == Simulator_Type.MuMu12.value
            and config.conf.fix_mumu12_adb_disconnect
        ):
            _clear_mumu_adb_transport()

    if not start:
        return True

    csleep(3)
    logger.info(f"启动{simulator_type}模拟器")
    started = run_command(
        commands.start,
        data.simulator_folder,
        data.wait_time,
        commands.blocking,
    )
    if not started and allow_retry:
        logger.warning(f"{simulator_type}重启后ADB未恢复，重试一次")
        return _restart_simulator(stop=True, start=True, allow_retry=False)
    if not started:
        return False

    hotkey = data.hotkey.strip()
    if hotkey:
        import pyautogui

        pyautogui.FAILSAFE = False
        pyautogui.hotkey(*hotkey.split("+"))
    return True


def build_command_set(simulator_type: str, index) -> SimulatorCommandSet:
    idx = normalize_index(index)

    if simulator_type == Simulator_Type.Nox.value:
        base = "Nox.exe"
        if idx >= 0:
            base += f" -clone:Nox_{idx}"
        return SimulatorCommandSet(stop=f"{base} -quit", start=base)

    if simulator_type == Simulator_Type.MuMu12.value:
        cmd = "MuMuManager.exe api -v "
        if idx >= 0:
            cmd += f"{idx} "
        return SimulatorCommandSet(
            stop=cmd + "shutdown_player",
            start=cmd + "launch_player",
        )

    if simulator_type == Simulator_Type.Waydroid.value:
        return SimulatorCommandSet(
            stop="waydroid session stop",
            start="waydroid show-full-ui",
        )

    if simulator_type == Simulator_Type.Leidian9.value:
        if idx < 0:
            idx = 0
        return SimulatorCommandSet(
            stop=f"ldconsole.exe quit --index {idx}",
            start=f"ldconsole.exe launch --index {idx}",
        )

    if simulator_type == Simulator_Type.ReDroid.value:
        return SimulatorCommandSet(
            stop=f"docker stop {index} -t 0",
            start=f"docker start {index}",
        )

    if simulator_type == Simulator_Type.MuMuPro.value:
        return SimulatorCommandSet(
            stop=f"Contents/MacOS/mumutool close {index}",
            start=f"Contents/MacOS/mumutool open {index}",
        )

    if __system__ == "windows":
        gmtool = "gmtool.exe"
    elif __system__ == "darwin":
        gmtool = "Contents/MacOS/gmtool"
    else:
        gmtool = "./gmtool"
    return SimulatorCommandSet(
        stop=f'{gmtool} admin stop "{index}"',
        start=f'{gmtool} admin start "{index}"',
        blocking=True,
    )


def normalize_index(index) -> int:
    try:
        return int(index)
    except (TypeError, ValueError):
        return -1


def run_command(cmd: str, folder_path: str, wait_time: int, blocking: bool) -> bool:
    logger.debug(cmd)
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=folder_path or None,
        creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    if blocking:
        return wait_for_process(process, wait_time)
    if wait_time <= 0:
        return True
    return wait_for_adb(process, wait_time)


def wait_for_process(process: subprocess.Popen, wait_time: int) -> bool:
    while wait_time > 0:
        try:
            csleep(0)
            logger.debug(process.communicate(timeout=1))
            return process.returncode == 0
        except MowerExit:
            raise
        except subprocess.TimeoutExpired:
            wait_time -= 1
    return False


def wait_for_adb(process: subprocess.Popen, wait_time: int) -> bool:
    for _ in range(wait_time):
        try:
            if adb_ready():
                return True
        except MowerExit:
            raise
        except Exception as e:
            logger.debug(e)
        if process.poll() is not None and process.returncode not in (0, None):
            logger.debug(process.communicate())
        csleep(1)
    return adb_ready()


def adb_ready() -> bool:
    target = config.conf.adb
    if not target:
        return len(Session().devices_list()) > 0
    Session().connect(target, throw_error=True)
    devices = [
        device for device, status in Session().devices_list() if status != "offline"
    ]
    return target in devices
