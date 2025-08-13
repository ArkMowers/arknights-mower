from __future__ import annotations

import gzip
import subprocess
import time
from datetime import datetime, timedelta
from typing import Optional

import cv2
import numpy as np

from arknights_mower import __rootdir__, __system__
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.maatouch import MaaTouch
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.image import bytes2img, img2bytes
from arknights_mower.utils.log import logger, save_screenshot
from arknights_mower.utils.network import get_new_port, is_port_in_use
from arknights_mower.utils.simulator import restart_simulator


class Device:
    """Android Device"""

    class Control:
        """Android Device Control"""

        def __init__(
            self, device: Device, client: ADBClient = None, touch_device: str = None
        ) -> None:
            self.device = device
            self.maatouch = None
            self.scrcpy = None

            if config.conf.touch_method == "maatouch":
                self.maatouch = MaaTouch(client)
            else:
                self.scrcpy = Scrcpy(client)

        def tap(self, point: tuple[int, int]) -> None:
            if self.maatouch:
                self.maatouch.tap([point], self.device.display_frames())
            elif self.scrcpy:
                self.scrcpy.tap(point[0], point[1])
            else:
                raise NotImplementedError

        def swipe(
            self, start: tuple[int, int], end: tuple[int, int], duration: int
        ) -> None:
            if self.maatouch:
                self.maatouch.swipe(
                    [start, end], self.device.display_frames(), duration=duration
                )
            elif self.scrcpy:
                self.scrcpy.swipe(start[0], start[1], end[0], end[1], duration / 1000)
            else:
                raise NotImplementedError

        def swipe_ext(
            self, points: list[tuple[int, int]], durations: list[int], up_wait: int
        ) -> None:
            if self.maatouch:
                self.maatouch.swipe(
                    points,
                    self.device.display_frames(),
                    duration=durations,
                    up_wait=up_wait,
                )
            elif self.scrcpy:
                total = len(durations)
                for idx, (S, E, D) in enumerate(
                    zip(points[:-1], points[1:], durations)
                ):
                    self.scrcpy.swipe(
                        S[0],
                        S[1],
                        E[0],
                        E[1],
                        D / 1000,
                        up_wait / 1000 if idx == total - 1 else 0,
                        fall=idx == 0,
                        lift=idx == total - 1,
                    )
            else:
                raise NotImplementedError

    def __init__(
        self, device_id: str = None, connect: str = None, touch_device: str = None
    ) -> None:
        self.device_id = device_id
        self.connect = connect
        self.touch_device = touch_device
        self.client = None
        self.control = None
        self.start()

    def start(self) -> None:
        self.client = ADBClient(self.device_id, self.connect)
        self.control = Device.Control(self, self.client)

    def run(self, cmd: str) -> Optional[bytes]:
        return self.client.run(cmd)

    def launch(self) -> None:
        """launch the application"""
        logger.info("明日方舟，启动！")

        tap = config.conf.tap_to_launch_game.enable
        x = config.conf.tap_to_launch_game.x
        y = config.conf.tap_to_launch_game.y

        if tap:
            self.run(f"input tap {x} {y}")
        else:
            self.run(f"am start -n {config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}")

    def exit(self) -> None:
        """exit the application"""
        logger.info("退出游戏")
        self.run(f"am force-stop {config.conf.APPNAME}")

    def return_home(self) -> None:
        """exit the application"""
        logger.info("切回主界面")
        self.send_keyevent(3)

    def send_keyevent(self, keycode: int) -> None:
        """send a key event"""
        logger.debug(f"keyevent: {keycode}")
        command = f"input keyevent {keycode}"
        self.run(command)

    def send_text(self, text: str) -> None:
        """send a text"""
        logger.debug(f"text: {repr(text)}")
        text = text.replace('"', '\\"')
        command = f'input text "{text}"'
        self.run(command)

    def is_app_running_in_background(self) -> bool:
        try:
            output = self.client.cmd_shell(f"pidof {config.conf.APPNAME}")
            return bool(output.strip())
        except Exception as e:
            logger.debug(f"检查应用是否在后台运行时出错：{e}")
            return False

    def bring_to_foreground(self):
        self.client.cmd_shell(
            f"am start -n {config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}"
        )

    def get_droidcast_classpath(self) -> str | None:
        # TODO: 退出时（并非结束mower线程时）关闭DroidCast进程、取消ADB转发
        try:
            out = self.client.cmd_shell("pm path com.rayworks.droidcast", decode=True)
        except Exception:
            logger.exception("无法获取CLASSPATH")
            return None
        prefix = "package:"
        postfix = ".apk"
        beg = out.index(prefix, 0)
        end = out.rfind(postfix)
        class_path = out[beg + len(prefix) : (end + len(postfix))].strip()
        class_path = "CLASSPATH=" + class_path
        logger.info(f"成功获取CLASSPATH：{class_path}")
        return class_path

    def start_droidcast(self) -> bool:
        class_path = self.get_droidcast_classpath()
        if not class_path:
            logger.info("安装DroidCast")
            apk_path = f"{__rootdir__}/vendor/droidcast/DroidCast-debug-1.2.1.apk"
            out = self.client.cmd(["install", apk_path], decode=True)
            if "Success" in out:
                logger.info("DroidCast安装完成，获取CLASSPATH")
            else:
                logger.error(f"DroidCast安装失败：{out}")
                return False
            class_path = self.get_droidcast_classpath()
            if not class_path:
                logger.error(f"无法获取CLASSPATH：{out}")
                return False
        port = config.droidcast.port
        if port != 0 and is_port_in_use(port):
            try:
                occupied_by_adb_forward = False
                forward_list = self.client.cmd("forward --list", True).strip().split()
                for host, pc_port, android_port in forward_list:
                    # 127.0.0.1:5555 tcp:60579 tcp:60579
                    if pc_port != android_port:
                        # 不是咱转发的，别乱动
                        continue
                    if pc_port == f"tcp:{port}":
                        occupied_by_adb_forward = True
                        break
                if not occupied_by_adb_forward:
                    port = 0
            except Exception as e:
                logger.exception(e)
        if port == 0:
            port = get_new_port()
            config.droidcast.port = port
            logger.info(f"更新DroidCast端口为{port}")
        else:
            logger.info(f"保持DroidCast端口为{port}")
        self.client.cmd(f"forward tcp:{port} tcp:{port}")
        logger.info("ADB端口转发成功，启动DroidCast")
        if config.droidcast.process is not None:
            config.droidcast.process.terminate()
        process = self.client.process(
            class_path,
            [
                "app_process",
                "/",
                "com.rayworks.droidcast.Main",
                f"--port={port}",
            ],
        )
        config.droidcast.process = process
        return True

    def screencap(self) -> bytes:
        start_time = datetime.now()
        min_time = config.screenshot_time + timedelta(
            milliseconds=config.conf.screenshot_interval
        )
        delta = (min_time - start_time).total_seconds()
        if delta > 0:
            time.sleep(delta)
            start_time = min_time

        if config.conf.droidcast.enable:
            session = config.droidcast.session
            while True:
                try:
                    port = config.droidcast.port
                    url = f"http://127.0.0.1:{port}/screenshot"
                    logger.debug(f"GET {url}")
                    r = session.get(url)
                    img = bytes2img(r.content)
                    if config.conf.droidcast.rotate:
                        img = cv2.rotate(img, cv2.ROTATE_180)
                    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    break
                except Exception as e:
                    logger.exception(e)
                    restart_simulator()
                    self.client.check_server_alive()
                    Session().connect(config.conf.adb)
                    self.start_droidcast()
                    if config.conf.touch_method == "scrcpy":
                        self.control.scrcpy = Scrcpy(self.client)
        elif config.conf.custom_screenshot.enable:
            command = config.conf.custom_screenshot.command
            while True:
                try:
                    data = subprocess.check_output(
                        command,
                        shell=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if __system__ == "windows"
                        else 0,
                    )
                    break
                except Exception as e:
                    logger.exception(e)
                    restart_simulator()
                    self.client.check_server_alive()
                    Session().connect(config.conf.adb)
                    if config.conf.touch_method == "scrcpy":
                        self.control.scrcpy = Scrcpy(self.client)
            img = bytes2img(data)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            command = "screencap 2>/dev/null | gzip -1"
            while True:
                try:
                    resp = self.run(command)
                    break
                except Exception as e:
                    logger.exception(e)
                    restart_simulator()
                    self.client.check_server_alive()
                    Session().connect(config.conf.adb)
                    if config.conf.touch_method == "scrcpy":
                        self.control.scrcpy = Scrcpy(self.client)
            data = gzip.decompress(resp)
            array = np.frombuffer(data[-1920 * 1080 * 4 :], np.uint8).reshape(
                1080, 1920, 4
            )
            img = cv2.cvtColor(array, cv2.COLOR_RGBA2RGB)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        screencap = img2bytes(img)
        save_screenshot(screencap)

        stop_time = datetime.now()
        config.screenshot_time = stop_time
        interval = (stop_time - start_time).total_seconds() * 1000
        if config.screenshot_avg is None:
            config.screenshot_avg = interval
        else:
            config.screenshot_avg = config.screenshot_avg * 0.9 + interval * 0.1
        if config.screenshot_count >= 100:
            config.screenshot_count = 0
            logger.info(
                f"截图用时{interval:.0f}ms 平均用时{config.screenshot_avg:.0f}ms"
            )
        else:
            config.screenshot_count += 1

        return screencap, img, gray

    def current_focus(self) -> str:
        """detect current focus app"""
        command = "dumpsys window | grep mCurrentFocus"
        line = self.run(command).decode("utf8")
        return line.strip()[:-1].split(" ")[-1]

    def display_frames(self) -> tuple[int, int, int]:
        """get display frames if in compatibility mode"""
        if not config.MNT_COMPATIBILITY_MODE:
            return None

        command = "dumpsys window | grep DisplayFrames"
        line = self.run(command).decode("utf8")
        """ eg. DisplayFrames w=1920 h=1080 r=3 """
        res = line.strip().replace("=", " ").split(" ")
        return int(res[2]), int(res[4]), int(res[6])

    def tap(self, point: tuple[int, int]) -> None:
        """tap"""
        logger.debug(f"tap: {point}")
        self.control.tap(point)

    def swipe(
        self, start: tuple[int, int], end: tuple[int, int], duration: int = 100
    ) -> None:
        """swipe"""
        logger.debug(f"swipe: {start} -> {end}, duration={duration}")
        self.control.swipe(start, end, duration)

    def swipe_ext(
        self, points: list[tuple[int, int]], durations: list[int], up_wait: int = 200
    ) -> None:
        """swipe_ext"""
        logger.debug(
            f"swipe_ext: points={points}, durations={durations}, up_wait={up_wait}"
        )
        self.control.swipe_ext(points, durations, up_wait)

    def check_current_focus(self) -> bool:
        """check if the application is in the foreground"""
        update = False
        while True:
            try:
                focus = self.current_focus()
                expected_focuses = [
                    f"{config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}",
                    "com.hypergryph.arknights.bilibili/com.gsc.welcome.WelcomeActivity",
                    "com.hypergryph.arknights.bilibili/com.gsc.auto_login.AutoLoginActivity",
                ]

                if focus not in expected_focuses:
                    if self.is_app_running_in_background():  # 你需要实现这个函数
                        self.bring_to_foreground()  # 你需要实现这个函数
                        csleep(2)
                    else:
                        self.exit()
                        self.launch()
                        csleep(10)
                    update = True
                return update
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(e)
                restart_simulator()
                self.client.check_server_alive()
                Session().connect(config.conf.adb)
                if config.conf.droidcast.enable:
                    self.start_droidcast()
                if config.conf.touch_method == "scrcpy":
                    self.control.scrcpy = Scrcpy(self.client)
                update = True

    def check_resolution(self) -> bool:
        """检查分辨率"""

        good_resolution = ["1920x1080", "1080x1920"]

        def match_resolution(resolution):
            return any(g in resolution for g in good_resolution)

        def show_error(resolution):
            logger.error(f"Mower仅支持1920x1080分辨率，模拟器分辨率为{resolution}")

        def extract_resolution(output_str):
            return output_str.partition("size:")[2].strip()

        output = self.client.cmd_shell("wm size", True)
        logger.debug(output.strip())

        physical_str, _, override_str = output.partition("Override")

        if override_str:
            if match_resolution(override_str):
                return True
            show_error(extract_resolution(override_str))
            return False
        if match_resolution(physical_str):
            return True
        show_error(extract_resolution(physical_str))
        return False
