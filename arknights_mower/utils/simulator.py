import subprocess
from arknights_mower.utils.log import logger
import time


def restart_simulator(data):
    index = data["index"]
    simulator_type = data["name"]
    if simulator_type == "夜神":
        cmd = "Nox.exe"
        # 多开需要传入 {"index":"4"} 4为夜神多开器的最左边的编号
        if index>=0:
            cmd += f' -clone:Nox_{data["index"]}'
        cmd += " -quit"
        try:
            process = subprocess.Popen(cmd, shell=True, cwd= data["simulator_folder"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       universal_newlines=True)
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        logger.info(f'开始关闭{simulator_type}模拟器，等待2秒钟')
        time.sleep(2)
        cmd = cmd.replace(' -quit', '')
        try:
            process = subprocess.Popen(cmd, shell=True, cwd= data["simulator_folder"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       universal_newlines=True)
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        logger.info(f'开始启动{simulator_type}模拟器，等待25秒钟')
        time.sleep(25)
    else:
        logger.warning(f"尚未支持{simulator_type}重启/自动启动")
