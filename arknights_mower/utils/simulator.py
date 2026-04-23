import subprocess
import time
from enum import Enum
from os import system
from collections import deque

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


class RestartBackoff:
    def __init__(self):
        # 记录最近 20 次的时间戳
        self._history = deque(maxlen=20)

        # 策略规则: (时间窗口s, 累计次数阈值, 惩罚等待s)
        # 建议：由强到弱排列，匹配到最强规则即停止
        self._rules = [
            (1800, 10, 120),  # 30分钟内10次 -> 停2分钟 (严重)
            (600, 5, 30),  # 10分钟内5次  -> 停30秒 (中等)
            (120, 2, 5),  # 2分钟内2次   -> 停5秒 (轻微)
        ]

    def check_and_delay(self):
        """
        核心调用入口：
        1. 记录当前重启时间
        2. 检查是否触发频率限制
        3. 执行同步等待
        """
        now = time.time()
        self._history.append(now)

        # 如果只有一次记录，无需检查直接返回
        if len(self._history) < 2:
            return

        delay_seconds = 0
        triggered_rule = None

        # 从最严格的规则开始匹配
        for window, threshold, penalty in self._rules:
            # 计算在该窗口内的尝试次数
            count_in_window = sum(1 for ts in self._history if now - ts <= window)

            if count_in_window >= threshold:
                delay_seconds = penalty
                triggered_rule = (window, count_in_window)
                break  # 匹配到最严厉的规则，直接跳出

        if delay_seconds > 0:
            window_min = triggered_rule[0] // 60
            logger.warning(
                f"检测到异常重启频率: {window_min}分钟内尝试{triggered_rule[1]}次。 "
                f"系统将强制冷却 {delay_seconds}s 以保护后端服务。"
            )
            # 同步等待
            csleep(delay_seconds)
            logger.info("冷却结束，尝试重新启动...")


_restart_backoff = RestartBackoff()


def restart_simulator(stop=True, start=True):
    _restart_backoff.check_and_delay()
    data = config.conf.simulator
    index = data.index
    simulator_type = data.name
    simulator_folder = data.simulator_folder
    wait_time = data.wait_time
    hotkey = data.hotkey
    cmd = ""
    blocking = False

    if simulator_type not in [types.value for types in Simulator_Type]:
        logger.warning(f"尚未支持{simulator_type}重启/自动启动")
        csleep(10)
        return False

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

            pyautogui.FAILSAFE = False
            pyautogui.hotkey(*hotkey)
    return True


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
