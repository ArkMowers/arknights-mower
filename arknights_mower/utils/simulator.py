import subprocess
from enum import Enum
from arknights_mower.utils.log import logger
import time


class Simulator_Type(Enum):
    Nox = "夜神"
    MuMu12 = "MuMu12"


def restart_simulator(data):
    index = data["index"]
    simulator_type = data["name"]
    cmd = ""
    if simulator_type in [Simulator_Type.Nox.value, Simulator_Type.MuMu12.value]:
        if simulator_type == Simulator_Type.Nox.value:
            cmd = "Nox.exe"
            if index >= 0:
                cmd += f' -clone:Nox_{data["index"]}'
            cmd += " -quit"
        elif simulator_type == Simulator_Type.MuMu12.value:
            cmd = "MuMuManager.exe api -v "
            if index >= 0:
                cmd += f'{data["index"]} '
            cmd += "shutdown_player"
        exec_cmd(cmd, data["simulator_folder"])
        logger.info(f'开始关闭{simulator_type}模拟器，等待2秒钟')
        time.sleep(2)
        if simulator_type == Simulator_Type.Nox.value:
            cmd = cmd.replace(' -quit', '')
        elif simulator_type == Simulator_Type.MuMu12.value:
            cmd = cmd.replace(' shutdown_player', ' launch_player')
        exec_cmd(cmd, data["simulator_folder"])
        logger.info(f'开始启动{simulator_type}模拟器，等待25秒钟')
        time.sleep(25)
    else:
        logger.warning(f"尚未支持{simulator_type}重启/自动启动")


def exec_cmd(cmd, folder_path):
    try:
        process = subprocess.Popen(cmd, shell=True, cwd=folder_path, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   universal_newlines=True)
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
