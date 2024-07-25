import subprocess
from enum import Enum
from os import system

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.log import logger


class Simulator_Type(Enum):
    Nox = "夜神"
    MuMu12 = "MuMu12"
    Leidian9 = "雷电9"
    Waydroid = "Waydroid"
    ReDroid = "ReDroid"
    MuMuPro = "MuMuPro"
    Genymotion = "Genymotion"


def restart_simulator(stop=True, start=True):
    data = config.conf.simulator
    index = data.index
    simulator_type = data.name
    simulator_folder = data.simulator_folder
    wait_time = data.wait_time
    hotkey = data.hotkey
    cmd = ""
    blocking = False

    if simulator_type not in Simulator_Type:
        logger.warning(f"尚未支持{simulator_type}重启/自动启动")
        csleep(10)
        return

    if simulator_type == Simulator_Type.Nox.value:
        cmd = "Nox.exe"
        if int(index) >= 0:
            cmd += f" -clone:Nox_{index}"
        cmd += " -quit"
    elif simulator_type == Simulator_Type.MuMu12.value:
        cmd = "MuMuManager.exe api -v "
        if int(index) >= 0:
            cmd += f"{index} "
        cmd += "shutdown_player"
    elif simulator_type == Simulator_Type.Waydroid.value:
        cmd = "waydroid session stop"
    elif simulator_type == Simulator_Type.Leidian9.value:
        cmd = "ldconsole.exe quit --index "
        if int(index) >= 0:
            cmd += f"{index} "
        else:
            cmd += "0"
    elif simulator_type == Simulator_Type.ReDroid.value:
        cmd = f"docker stop {index} -t 0"
    elif simulator_type == Simulator_Type.MuMuPro.value:
        cmd = f"Contents/MacOS/mumutool close {index}"
    elif simulator_type == Simulator_Type.Genymotion.value:
        if __system__ == "windows":
            cmd = "gmtool.exe"
        elif __system__ == "darwin":
            cmd = "Contents/MacOS/gmtool"
        else:
            cmd = "./gmtool"
        cmd += f' admin stop "{index}"'
        blocking = True

    if stop:
        logger.info(f"关闭{simulator_type}模拟器")
        exec_cmd(cmd, simulator_folder, 3, blocking)
        if simulator_type == "MuMu12" and config.conf.fix_mumu12_adb_disconnect:
            logger.info("结束adb进程")
            system("taskkill /f /t /im adb.exe")

    if start:
        if simulator_type == Simulator_Type.Nox.value:
            cmd = cmd.replace(" -quit", "")
        elif simulator_type == Simulator_Type.MuMu12.value:
            cmd = cmd.replace(" shutdown_player", " launch_player")
        elif simulator_type == Simulator_Type.Waydroid.value:
            cmd = "waydroid show-full-ui"
        elif simulator_type == Simulator_Type.Leidian9.value:
            cmd = cmd.replace("quit", "launch")
        elif simulator_type == Simulator_Type.ReDroid.value:
            cmd = f"docker start {index}"
        elif simulator_type == Simulator_Type.MuMuPro.value:
            cmd = cmd.replace("close", "open")
        elif simulator_type == Simulator_Type.Genymotion.value:
            cmd = cmd.replace("stop", "start", 1)
        logger.info(f"启动{simulator_type}模拟器")
        exec_cmd(cmd, simulator_folder, wait_time, blocking)
        if hotkey:
            hotkey = hotkey.split("+")
            import pyautogui

            pyautogui.hotkey(*hotkey)


def exec_cmd(cmd, folder_path, wait_time, blocking):
    logger.debug(cmd)
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=folder_path,
        creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    if not blocking:
        csleep(wait_time)
        process.terminate()
        return
    while wait_time > 0:
        try:
            csleep(0)
            logger.debug(process.communicate(timeout=1))
            break
        except MowerExit:
            raise
        except subprocess.TimeoutExpired:
            wait_time -= 1
