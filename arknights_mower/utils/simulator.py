import subprocess
from enum import Enum
from os import system

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.log import logger


class Simulator_Type(Enum):
    Nox = "夜神"
    MuMu12 = "MuMu12"
    Leidian9 = "雷电9"
    Waydroid = "Waydroid"
    ReDroid = "ReDroid"
    MuMuPro = "MuMuPro"
    Genymotion = "GenyMotion"


def restart_simulator(stop=True, start=True):
    from arknights_mower.utils.solver import BaseSolver

    data = config.conf["simulator"]
    index = data["index"]
    simulator_type = data["name"]
    cmd = ""

    if simulator_type in [
        Simulator_Type.Nox.value,
        Simulator_Type.MuMu12.value,
        Simulator_Type.Leidian9.value,
        Simulator_Type.Waydroid.value,
        Simulator_Type.ReDroid.value,
        Simulator_Type.MuMuPro.value,
        Simulator_Type.Genymotion.value,
    ]:
        if simulator_type == Simulator_Type.Nox.value:
            cmd = "Nox.exe"
            if int(index) >= 0:
                cmd += f' -clone:Nox_{data["index"]}'
            cmd += " -quit"
        elif simulator_type == Simulator_Type.MuMu12.value:
            cmd = "MuMuManager.exe api -v "
            if int(index) >= 0:
                cmd += f'{data["index"]} '
            cmd += "shutdown_player"
        elif simulator_type == Simulator_Type.Waydroid.value:
            cmd = "waydroid session stop"
        elif simulator_type == Simulator_Type.Leidian9.value:
            cmd = "ldconsole.exe quit --index "
            if int(index) >= 0:
                cmd += f'{data["index"]} '
            else:
                cmd += "0"
        elif simulator_type == Simulator_Type.ReDroid.value:
            cmd = f"docker stop {data['index']} -t 0"
        elif simulator_type == Simulator_Type.MuMuPro.value:
            cmd = f"Contents/MacOS/mumutool close {data['index']}"
        elif simulator_type == Simulator_Type.Genymotion.value:
            cmd = f"gmtool admin start {data['index']}"
        if stop:
            exec_cmd(cmd, data["simulator_folder"])
            logger.info(f"关闭{simulator_type}模拟器")
            if data["name"] == "MuMu12" and config.fix_mumu12_adb_disconnect:
                system("taskkill /f /t /im adb.exe")
                logger.info("结束adb进程")
            BaseSolver.csleep(2)
        if simulator_type == Simulator_Type.Nox.value:
            cmd = cmd.replace(" -quit", "")
        elif simulator_type == Simulator_Type.MuMu12.value:
            cmd = cmd.replace(" shutdown_player", " launch_player")
        elif simulator_type == Simulator_Type.Waydroid.value:
            cmd = "waydroid show-full-ui"
        elif simulator_type == Simulator_Type.Leidian9.value:
            cmd = cmd.replace("quit", "launch")
        elif simulator_type == Simulator_Type.ReDroid.value:
            cmd = f"docker start {data['index']}"
        elif simulator_type == Simulator_Type.MuMuPro.value:
            cmd = cmd.replace("close", "open")
        elif simulator_type == Simulator_Type.Genymotion.value:
            cmd = f"gmtool admin stop {data['index']}"
        if start:
            exec_cmd(cmd, data["simulator_folder"])
            logger.info(f"开始启动{simulator_type}模拟器，等待{data['wait_time']}秒")
            BaseSolver.csleep(data["wait_time"])
    else:
        logger.warning(f"尚未支持{simulator_type}重启/自动启动")
        BaseSolver.csleep()


def exec_cmd(cmd, folder_path):
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        )
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
