from __future__ import annotations

import atexit
import gzip
import subprocess
import time
from datetime import datetime, timedelta
from typing import Optional

import cv2
import numpy as np

from arknights_mower import __rootdir__, __system__
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import DEFAULT_LAUNCH_COMMAND
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.maatouch import MaaTouch
from arknights_mower.utils.device.mumu12ipc.core import MuMu12IPC
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
            self.mumu12IPC = None
            self.scrcpy = None
            if config.conf.mumu12IPC:
                self.mumu12IPC = MuMu12IPC(device)
            elif config.conf.touch_method == "maatouch":
                self.maatouch = MaaTouch(client)
            else:
                self.scrcpy = Scrcpy(client)

        def tap(self, point: tuple[int, int]) -> None:
            if self.mumu12IPC:
                self.mumu12IPC.tap(point[0], point[1])
            elif self.maatouch:
                self.maatouch.tap([point], self.device.display_frames())
            elif self.scrcpy:
                self.scrcpy.tap(point[0], point[1])

            else:
                raise NotImplementedError

        def swipe(
            self, start: tuple[int, int], end: tuple[int, int], duration: int
        ) -> None:
            if self.mumu12IPC:
                self.mumu12IPC.swipe(
                    start[0], start[1], end[0], end[1], duration=duration / 1000
                )
            elif self.maatouch:
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
            if self.mumu12IPC:
                total = len(durations)
                for idx, (S, E, D) in enumerate(
                    zip(points[:-1], points[1:], durations)
                ):
                    self.mumu12IPC.swipe(
                        S[0],
                        S[1],
                        E[0],
                        E[1],
                        D / 1000,
                        fall=idx == 0,
                        lift=idx == total - 1,
                        interval=up_wait / 1000 if idx == total - 1 else 0,
                    )
            elif self.maatouch:
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
        # 进程退出时释放 adb 资源，避免退出后 DroidCast/scrcpy 等常驻连接藕断丝连
        atexit.register(self.close)

    def start(self) -> None:
        self.client = ADBClient(self.device_id, self.connect)
        self.control = Device.Control(self, self.client)

    def run(self, cmd: str) -> Optional[bytes]:
        return self.client.run(cmd)

    def launch(self) -> None:
        """launch the application"""
        logger.info("明日方舟，启动！")

        launch_conf = config.conf.tap_to_launch_game
        mode = launch_conf.mode or ("tap" if launch_conf.enable else "adb")

        if mode == "tap":
            self.run(f"input tap {launch_conf.x} {launch_conf.y}")
        elif mode == "custom":
            command = launch_conf.command or DEFAULT_LAUNCH_COMMAND
            command = command.replace("{package}", config.conf.APPNAME).replace(
                "{activity}", config.APP_ACTIVITY_NAME
            )
            logger.info("执行自定义启动命令")
            self.run(command)
        else:
            self.run(f"am start -n {config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}")

    def exit(self) -> None:
        """exit the application"""
        import traceback

        logger.info("退出游戏")
        logger.debug("device.exit 调用来源:\n" + "".join(traceback.format_stack()[:-1]))
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
        """检查游戏进程是否存活；无法判定时按「运行中」处理，避免误判重新拉起游戏。"""
        try:
            # 同一条持久 adb 会话查询，避免另起 adb.exe 进程的竞态假阴性（#159 根因）
            output = self.run(f"ps -A | grep {config.conf.APPNAME} | grep -v grep")
            if output.strip():
                return True
            # ps 查不到：只有 dumpsys package 能检出 force-stop（stopped=true）
            package = self.run(f"dumpsys package {config.conf.APPNAME}")
            if b"stopped=true" in package:
                return False
        except Exception as e:
            logger.debug(f"检查应用是否在后台运行时出错：{e}")
            return True
        # ps 查不到、又非 force-stop：无法判定，按「运行中」处理
        return True

    def bring_to_foreground(self):
        self.run(f"am start -n {config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}")

    def get_droidcast_classpath(self) -> str | None:
        # TODO: 退出时（并非结束mower线程时）关闭DroidCast进程、取消ADB转发
        try:
            out = self.client.cmd_shell("pm path com.rayworks.droidcast", decode=True)
        except subprocess.CalledProcessError as e:
            # Android 部分版本在包不存在时返回退出码 1，且没有输出。
            if e.returncode == 1 and e.output is not None and not e.output.strip():
                return None
            logger.exception("无法获取CLASSPATH")
            raise
        except Exception:
            logger.exception("无法获取CLASSPATH")
            raise
        if not out.strip():
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
            try:
                out = self.client.cmd(["install", apk_path], decode=True)
            except Exception as e:
                # 设备瞬时离线时 install 会失败：按「装不上」返回 False，不让重连崩
                logger.warning(f"DroidCast安装失败：{e}")
                return False
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
        occupied_by_adb_forward = False
        if port != 0 and is_port_in_use(port):
            try:
                forward_list = self.client.cmd("forward --list", True).splitlines()
                expected = [self.client.device_id, f"tcp:{port}", f"tcp:{port}"]
                occupied_by_adb_forward = any(
                    line.split() == expected for line in forward_list
                )
            except Exception as e:
                logger.exception(e)
            if not occupied_by_adb_forward:
                port = 0
        if port == 0:
            port = get_new_port()
            config.droidcast.port = port
            logger.info(f"更新DroidCast端口为{port}")
        else:
            logger.info(f"保持DroidCast端口为{port}")
        if not occupied_by_adb_forward:
            try:
                self.client.cmd(f"forward --no-rebind tcp:{port} tcp:{port}")
            except subprocess.CalledProcessError:
                # 选端口后仍可能发生占用，交由连接恢复流程重新分配。
                config.droidcast.port = 0
                raise
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

        if self.control.mumu12IPC:
            # 瞬时错误重建 IPC 重试；重试耗尽且设备无法连接时自动重启模拟器
            for _ in range(3):
                try:
                    img = self.control.mumu12IPC.capture_display()
                    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    break
                except MowerExit:
                    raise
                except Exception as e:
                    logger.exception(e)
                    self.control.mumu12IPC = MuMu12IPC(self.device)
            else:
                restart_simulator()
                self.control.mumu12IPC = MuMu12IPC(self.device)
                img = self.control.mumu12IPC.capture_display()
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        elif config.conf.droidcast.enable:
            session = config.droidcast.session

            def grab_droidcast() -> bytes:
                port = config.droidcast.port
                url = f"http://127.0.0.1:{port}/screenshot"
                return session.get(url).content

            img = bytes2img(self.recover(grab_droidcast))
            if config.conf.droidcast.rotate:
                img = cv2.rotate(img, cv2.ROTATE_180)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        elif config.conf.custom_screenshot.enable:
            command = config.conf.custom_screenshot.command

            def grab_custom() -> bytes:
                return subprocess.check_output(
                    command,
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if __system__ == "windows"
                    else 0,
                )

            data = self.recover(grab_custom)
            img = bytes2img(data)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            command = "screencap 2>/dev/null | gzip -1"
            resp = self.recover(lambda: self.run(command))
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

    def close(self) -> None:
        """释放 adb 相关资源（常驻子进程与 socket）。

        mower 的 DroidCast 截图子进程与 scrcpy 常驻连接都依赖模拟器连接；退出时不清理
        会一直占住（共享 adb socket 与 mower 所在目录），需关闭模拟器才释放。该方法由
        atexit 注册，进程退出时调用，幂等可重复调用。
        """
        try:
            process = getattr(config.droidcast, "process", None)
            if process is not None:
                process.terminate()
                config.droidcast.process = None
        except Exception:
            logger.debug("终止 DroidCast 进程失败", exc_info=True)
        try:
            if self.control is not None and self.control.scrcpy is not None:
                self.control.scrcpy.stop()
        except Exception:
            logger.debug("关闭 scrcpy 失败", exc_info=True)

    def reconnect(self) -> None:
        """重连 adb 会话 + 重初始化显示/触摸管线（不杀游戏、不重启模拟器）。

        先重新发现目标模拟器当前 adb 端点（如 MuMu 双开端口漂移），避免一直连
        config.conf.adb 里已失效的旧端口。"""
        self.client.check_server_alive()
        target = self.client.refresh_target()
        self.device_id = target
        Session().connect(target)
        if config.conf.droidcast.enable:
            if not self.start_droidcast():
                raise ConnectionError("DroidCast启动失败")
        if config.conf.touch_method == "scrcpy":
            self.control.scrcpy = Scrcpy(self.client)

    def _safe_reconnect(self) -> None:
        """重连失败不抛给上层，计入 recover 的重试/重启语义。"""
        try:
            self.reconnect()
        except Exception as e:
            logger.warning(f"重连失败：{e}")

    def recover(self, func, retries: int = 3, restarts: int = 2):
        """瞬时错误重连重试；重试耗尽且设备无法连接时自动重启模拟器；重启有上限。"""
        last_exc = None
        for _ in range(restarts):
            for _ in range(retries):
                try:
                    return func()
                except MowerExit:
                    raise
                except Exception as e:
                    last_exc = e
                    logger.warning(f"重试失败：{e}")
                    self._safe_reconnect()
            logger.warning(f"重试 {retries} 次仍失败，判定设备无法连接，自动重启模拟器")
            restart_simulator()
            self._safe_reconnect()
        raise ConnectionError(
            f"设备连不上，自动重启模拟器 {restarts} 次后仍失败"
        ) from last_exc

    def check_current_focus(self) -> bool:
        """检查游戏是否在前台；不在则切回/拉起；仅设备无法连接时才自动重启模拟器。"""
        update = False

        def check() -> bool:
            nonlocal update
            focus = self.current_focus()
            # 前台判定：package 前缀匹配（游戏包下任何界面都算前台，免疫新 activity）
            if focus.startswith(config.conf.APPNAME + "/"):
                return update
            if self.is_app_running_in_background():
                self.bring_to_foreground()
                csleep(2)
            else:
                # 游戏进程已停止（force-stop），重拉前台
                self.launch()
                csleep(10)
            update = True
            return update

        return self.recover(check, retries=3, restarts=3)

    def check_resolution(self) -> bool:
        """检查分辨率"""

        good_resolution = ["1920x1080", "1080x1920"]

        def match_resolution(resolution):
            return any(g in resolution for g in good_resolution)

        def show_error(resolution):
            logger.error(
                f"Mower仅支持模拟器1920x1080分辨率，当前模拟器分辨率为{resolution}，请调整模拟器的分辨率"
            )

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
