from __future__ import annotations

import atexit
import os
import subprocess
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from math import isfinite
from threading import Event, Lock, RLock
from typing import NamedTuple, Optional

import cv2

from arknights_mower import __system__
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import DEFAULT_LAUNCH_COMMAND
from arknights_mower.utils.config.device_profile import capture_compatibility_error
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.adb_client.server import guard_adb
from arknights_mower.utils.device.droidcast import DroidCastSession
from arknights_mower.utils.device.io_budget import (
    budget_sleep,
    device_io_budget,
    io_timeout,
)
from arknights_mower.utils.device.ldplayer_capture import LDCaptureSession
from arknights_mower.utils.device.maatouch import MaaTouch
from arknights_mower.utils.device.manager_io import run_command
from arknights_mower.utils.device.mumu12ipc.capture import MuMuCaptureSession
from arknights_mower.utils.device.mumu12ipc.input import MuMuInputSession as MuMu12IPC
from arknights_mower.utils.device.recovery import (
    DeviceRecoveryError,
    recover_connection,
)
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.device.screenshot import capture_adb_frame
from arknights_mower.utils.device.screenshot_backend import (
    ScreenshotFailure,
    ScreenshotSession,
    validate_frame,
)
from arknights_mower.utils.device.touch_backend import TouchFailure, touch_backends
from arknights_mower.utils.image import bytes2img
from arknights_mower.utils.log import (
    logger,
    save_screenshot_frame,
)


class _PreparedTouch(NamedTuple):
    points: list[tuple[int, int]]
    durations: list[int]
    up_wait: int
    display_frames: tuple[int, int, int] | None


class Device:
    """Android Device"""

    class Control:
        """Android Device Control"""

        def __init__(
            self, device: Device, client: ADBClient = None, touch_device: str = None
        ) -> None:
            self.device = device
            self.owner_pid = os.getpid()
            self.maatouch = None
            self.mumu12IPC = None
            self.scrcpy = None
            self._close_lock = Lock()
            self._close_error = None
            self._interrupted = False
            self.profile = device.profile.model_copy(deep=True)
            backend = self.profile.touch_backend
            try:
                capability = next(
                    item
                    for item in touch_backends(self.profile, __system__)
                    if item["backend"] == backend
                )
                if not capability["available"]:
                    raise ValueError(capability["reason"])
                if backend == "mumu_ipc":
                    self.mumu12IPC = MuMu12IPC(device)
                elif backend == "maatouch":
                    self.maatouch = MaaTouch(client)
                else:
                    self.scrcpy = Scrcpy(client)
            except MowerExit:
                raise
            except Exception as exc:
                raise TouchFailure(self.profile, __system__, exc) from exc

        def close(self):
            if self.owner_pid != os.getpid():
                return
            with self._close_lock:
                if self._close_error is not None:
                    raise self._close_error

                errors = []
                resources = (
                    (self.scrcpy, "stop"),
                    (self.maatouch, "close"),
                    (self.mumu12IPC, "disconnect"),
                )
                self.scrcpy = self.maatouch = self.mumu12IPC = None
                for resource, method in resources:
                    if resource is not None:
                        try:
                            getattr(resource, method)()
                        except Exception as exc:
                            errors.append(exc)
                if errors:
                    for error in errors[1:]:
                        errors[0].add_note(str(error))
                    self._close_error = errors[0]
                    self._close_error.cleanup_failed = True
                    raise self._close_error

        def interrupt(self):
            if self.owner_pid != os.getpid():
                return
            with self._close_lock:
                if self._interrupted:
                    return
                self._interrupted = True
                helpers = self.scrcpy, self.maatouch, self.mumu12IPC
            errors = []
            for helper in helpers:
                if interrupt := getattr(helper, "interrupt", None):
                    try:
                        interrupt()
                    except Exception as exc:
                        errors.append(exc)
            if errors:
                for error in errors[1:]:
                    errors[0].add_note(str(error))
                raise errors[0]

        def tap(self, point: tuple[int, int], *, display_frames=None) -> None:
            if self.mumu12IPC:
                self.mumu12IPC.tap(point[0], point[1])
            elif self.maatouch:
                self.maatouch.tap([point], display_frames)
            elif self.scrcpy:
                self.scrcpy.tap(point[0], point[1])

            else:
                raise NotImplementedError

        def input_alive(self) -> bool:
            if self.scrcpy is not None:
                probe = getattr(self.scrcpy, "check_control_alive", None)
                return probe() if probe is not None else True
            return self.maatouch is not None or self.mumu12IPC is not None

        def swipe(
            self,
            start: tuple[int, int],
            end: tuple[int, int],
            duration: int,
            *,
            display_frames=None,
        ) -> None:
            if self.mumu12IPC:
                self.mumu12IPC.swipe(
                    start[0], start[1], end[0], end[1], duration=duration / 1000
                )
            elif self.maatouch:
                self.maatouch.swipe([start, end], display_frames, duration=duration)
            elif self.scrcpy:
                self.scrcpy.swipe(start[0], start[1], end[0], end[1], duration / 1000)

            else:
                raise NotImplementedError

        def swipe_ext(
            self,
            points: list[tuple[int, int]],
            durations: list[int],
            up_wait: int,
            *,
            display_frames=None,
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
                    display_frames,
                    duration=durations,
                    up_wait=up_wait,
                )
            elif self.scrcpy:
                sender = getattr(self.scrcpy, "control", None)
                with getattr(sender, "input_operation", nullcontext)():
                    total = len(durations)
                    for index, (start, end, duration) in enumerate(
                        zip(points[:-1], points[1:], durations)
                    ):
                        self.scrcpy.swipe(
                            start[0],
                            start[1],
                            end[0],
                            end[1],
                            duration / 1000,
                            up_wait / 1000 if index == total - 1 else 0,
                            fall=index == 0,
                            lift=index == total - 1,
                        )
            else:
                raise NotImplementedError

    def __init__(
        self,
        device_id: str = None,
        connect: str = None,
        touch_device: str = None,
        *,
        wait_for_device: bool = True,
        adb_bin: str = None,
        strict_target: bool = False,
        profile=None,
    ) -> None:
        if strict_target and (not device_id or not device_id.strip()):
            raise ValueError("设备 serial 不能为空")
        self.device_id = device_id
        self.adb_bin = adb_bin
        self.strict_target = strict_target
        self._profile = profile.model_copy(deep=True) if profile is not None else None
        self.connect = connect
        self.touch_device = touch_device
        self.client = None
        self.control = None
        self.owner_pid = os.getpid()
        self._resource_lock = RLock()
        self._interrupted = Event()
        self._close_error = None
        self._pending_cleanup = []
        self._interrupt_error = None
        self._recovery_active = False
        self._recovery_error = None
        try:
            self.start(wait_for_device=wait_for_device)
        except Exception:
            self.close()
            raise
        # 进程退出时释放 adb 资源，避免退出后 DroidCast/scrcpy 等常驻连接藕断丝连
        atexit.register(self.close)

    @property
    def profile(self):
        return getattr(self, "_profile", None) or config.conf.device

    @property
    def game_package(self):
        profile = getattr(self, "_profile", None)
        return profile.game_package if profile is not None else config.conf.APPNAME

    @classmethod
    def create(cls, *, connection_retries: int = 3) -> Device:
        """Legacy construction permits bounded local attempts only."""
        return recover_connection(
            lambda *, wait_for_device: cls(wait_for_device=wait_for_device),
            first_attempts=connection_retries,
            wait_for_device=connection_retries > 1,
        )

    @contextmanager
    def _recovery_scope(self):
        self._check_open()
        if config.stop_mower.is_set() or (
            getattr(self, "_interrupted", None) is not None
            and self._interrupted.is_set()
        ):
            raise MowerExit
        # 某些业务层会捕获 Exception；同一设备恢复耗尽后不能被它们重新开启恢复。
        if error := getattr(self, "_recovery_error", None):
            raise error
        previous = getattr(self, "_recovery_active", False)
        self._recovery_active = True
        try:
            yield
        except DeviceRecoveryError as e:
            self._recovery_error = e
            raise
        finally:
            self._recovery_active = previous

    def _check_open(self):
        owner = getattr(self, "owner_pid", os.getpid())
        interrupted = getattr(self, "_interrupted", None)
        if owner != os.getpid() or (interrupted is not None and interrupted.is_set()):
            raise MowerExit("设备会话已关闭或所有权不匹配")
        if error := getattr(self, "_close_error", None):
            raise error

    def _stop_control(self):
        control = getattr(self, "control", None)
        if control is None:
            return
        control.close()
        # Keep cleanup visible to a concurrent rebind until it has completed.
        # A failed cleanup also remains latched and cannot authorize replacement.
        if self.control is control:
            self.control = None

    def interrupt_input(self):
        """Unblock an owned input process before application close takes its lock."""
        self._stop_control()

    def interrupt_io(self):
        """Cancel I/O; retain helper ownership for cleanup after restoration."""
        if getattr(self, "owner_pid", None) != os.getpid():
            return
        with self._resource_lock:
            if self._interrupted.is_set():
                return
            self._interrupted.set()
            resources = (
                (self.control, "interrupt"),
                (getattr(self, "_mumu_capture", None), "interrupt"),
                (getattr(self, "_ld_capture", None), "interrupt"),
                (getattr(self, "_droidcast", None), "interrupt"),
                (self.client, "interrupt_io"),
            )
        errors = []
        for resource, method in resources:
            if interrupt := getattr(resource, method, None):
                try:
                    interrupt()
                except Exception as exc:
                    errors.append(exc)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            self._interrupt_error = errors[0]
            raise errors[0]

    def _connect_once(self, *, wait_for_device: bool = True) -> None:
        """一次完整连接：先确认 ADB 在线，再初始化截图和触控，各执行一次。"""
        with self._recovery_scope():
            try:
                self.close()
                if self.client is None:
                    options = {"wait_for_device": wait_for_device}
                    if getattr(self, "strict_target", False):
                        options.update(adb_bin=self.adb_bin, strict_target=True)
                    self.client = ADBClient(self.device_id, self.connect, **options)
                else:
                    self.client.reconnect(wait_for_device=wait_for_device)
                self.device_id = self.client.device_id
                if not self.check_resolution():
                    raise MowerExit
                if config.conf.droidcast.enable:
                    try:
                        if not self.start_droidcast():
                            raise ConnectionError("DroidCast启动失败")
                    except Exception as exc:
                        if getattr(self, "strict_target", False):
                            raise ScreenshotFailure(
                                config.conf.device, __system__, exc
                            ) from exc
                        raise
                if self.control is None:
                    self.control = Device.Control(self, self.client)
                self._check_open()
            except Exception:
                self.close()
                raise

    def start(self, *, wait_for_device: bool = True) -> None:
        self._connect_once(wait_for_device=wait_for_device)

    def rebind_target(self, serial: str, adb_path: str, *, game_package=None) -> None:
        """Rebuild this handle only after its application verified the endpoint."""
        self._check_open()
        if not serial.strip():
            raise ValueError("设备 serial 不能为空")
        if getattr(getattr(self, "_recovery_error", None), "cleanup_failed", False):
            raise self._recovery_error
        self.close()
        self._recovery_error = None
        self.control = None
        self.client = None
        self.device_id = serial
        self.adb_bin = adb_path
        self._profile = self.profile.model_copy(
            update={
                "last_serial": serial,
                "adb_path": adb_path,
                "game_package": game_package or self.game_package,
            }
        )
        self.strict_target = True
        self._connect_once(wait_for_device=False)

    def run(self, cmd: str) -> Optional[bytes]:
        return self.recover(lambda: self.client.run(cmd))

    def launch(self) -> None:
        """launch the application"""
        logger.info("明日方舟，启动！")

        launch_conf = config.conf.tap_to_launch_game
        mode = launch_conf.mode or ("tap" if launch_conf.enable else "adb")

        if mode == "tap":
            self._input_once(
                lambda: self.client.run(f"input tap {launch_conf.x} {launch_conf.y}"),
                transport="adb",
            )
        elif mode == "custom":
            command = launch_conf.command or DEFAULT_LAUNCH_COMMAND
            command = command.replace("{package}", self.game_package).replace(
                "{activity}", config.APP_ACTIVITY_NAME
            )
            logger.info("执行自定义启动命令")
            self.run(command)
        else:
            self.run(f"am start -n {self.game_package}/{config.APP_ACTIVITY_NAME}")

    def exit(self) -> None:
        """exit the application"""
        import traceback

        logger.info("退出游戏")
        logger.debug("device.exit 调用来源:\n" + "".join(traceback.format_stack()[:-1]))
        self.run(f"am force-stop {self.game_package}")

    def return_home(self) -> None:
        """exit the application"""
        logger.info("切回主界面")
        self.send_keyevent(3)

    def send_keyevent(self, keycode: int) -> None:
        """send a key event"""
        logger.debug(f"keyevent: {keycode}")
        if keycode == 4 and self.profile.touch_backend == "mumu_ipc":
            # Android BACK (4) maps to MuMu's native BACK (1) in back().
            self._input_once(lambda: self.control.mumu12IPC.back())
            return
        command = f"input keyevent {keycode}"
        self._input_once(lambda: self.client.run(command), transport="adb")

    def send_text(self, text: str) -> None:
        """send a text"""
        logger.debug(f"text: {repr(text)}")
        text = text.replace('"', '\\"')
        command = f'input text "{text}"'
        self._input_once(lambda: self.client.run(command), transport="adb")

    def is_app_running_in_background(self) -> bool:
        """检查游戏进程是否存活。"""
        try:
            # 同一条持久 adb 会话查询
            output = self.run(f"ps -A | grep {self.game_package} | grep -v grep")
            return bool(output and output.strip())
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception as e:
            logger.debug(f"检查应用是否在后台运行时出错：{e}")
            return False

    def bring_to_foreground(self):
        self.run(f"am start -n {self.game_package}/{config.APP_ACTIVITY_NAME}")

    def start_droidcast(self) -> bool:
        with getattr(self, "_resource_lock", nullcontext()):
            self._check_open()
            capture = getattr(self, "_droidcast", None)
            if capture is None:
                capture = DroidCastSession(
                    self.client.adb_bin,
                    self.device_id,
                    rotate=config.conf.droidcast.rotate,
                )
                self._droidcast = capture
        capture.start(install=True)
        if (
            getattr(self, "_interrupted", None) is not None
            and self._interrupted.is_set()
        ):
            capture.interrupt()
            self._check_open()
        return True

    def capture_frame(self):
        """One acquisition; the application owns retries and frame validation."""
        self._check_open()
        backend = self.profile.screenshot_backend
        if reason := capture_compatibility_error(
            self.profile.preset_id, backend, __system__
        ):
            raise ValueError(reason)
        if backend == "ld_native":
            with getattr(self, "_resource_lock", nullcontext()):
                self._check_open()
                if getattr(self, "_ld_capture", None) is None:
                    self._ld_capture = LDCaptureSession(
                        self.profile, self.client.adb_bin, self.device_id
                    )
                capture = self._ld_capture
            return self._validated(capture.capture_frame())
        if backend == "mumu_ipc":
            with getattr(self, "_resource_lock", nullcontext()):
                self._check_open()
                if getattr(self, "_mumu_capture", None) is None:
                    self._mumu_capture = MuMuCaptureSession(self.profile)
                capture = self._mumu_capture
            return self._validated(capture.capture_frame())
        if backend == "adb_gzip":
            return capture_adb_frame(self.client.adb_bin, self.device_id)
        if backend == "droidcast":
            if getattr(self, "_droidcast", None) is None:
                self.start_droidcast()
            return self._validated(self._droidcast.capture_frame())
        if backend == "custom":
            from arknights_mower.utils.device.preflight_io import custom_capture_argv

            argv = custom_capture_argv(
                config.conf.custom_screenshot.command,
                self.client.adb_bin,
                self.device_id,
            )
            timeout = io_timeout(10)
            if argv[0] == self.client.adb_bin:
                timeout = guard_adb(argv[0], timeout=timeout, run=run_command)
            data = run_command(
                argv,
                stdout=subprocess.PIPE,
                check=True,
                timeout=timeout,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
                if __system__ == "windows"
                else 0,
            ).stdout
            return bytes2img(data)
        raise ValueError(f"不支持的截图后端：{backend}")

    def standard_frame(self):
        """The plain ADB screencap used for degradation, on the same target."""
        self._check_open()
        return capture_adb_frame(self.client.adb_bin, self.device_id)

    @staticmethod
    def _validated(frame):
        """Classify an owned helper frame here, where the backend is known.

        A helper that answered with the wrong size has already done its own
        bounded rebuild, so the size error must reach the caller as a terminal
        verdict instead of entering the generic retry path.
        """
        validate_frame(frame)
        return frame

    def rebuild_screenshot(self):
        """Release/recreate only resources belonging to the selected capture."""
        self._check_open()
        backend = self.profile.screenshot_backend
        if backend == "ld_native":
            capture = getattr(self, "_ld_capture", None)
            if capture is not None:
                capture.close()
                self._ld_capture = None
        if backend == "mumu_ipc":
            capture = getattr(self, "_mumu_capture", None)
            if capture is not None:
                capture.close()
                self._mumu_capture = None
        elif backend == "droidcast":
            self.start_droidcast()
        # ADB and custom captures own only the bounded per-call connection or
        # process. A new acquisition naturally creates their next resource.

    def screencap(self):
        """Return current RGB/gray frames; persistence owns JPEG encoding."""
        from arknights_mower.utils.performance import effective_performance_profile

        start_time = datetime.now()
        screenshot_interval = config.conf.screenshot_interval
        if getattr(config.conf, "performance_mode", None) == "auto":
            screenshot_interval = effective_performance_profile(
                config.conf, config.screenshot_avg, config.screenshot_count
            ).screenshot_interval
        min_time = config.screenshot_time + timedelta(milliseconds=screenshot_interval)
        delta = (min_time - start_time).total_seconds()
        if delta > 0:
            time.sleep(delta)
            start_time = min_time

        if control := getattr(self, "session_control", None):
            img = control.capture().unwrap()
        elif (
            hasattr(self, "control")
            and hasattr(self.control, "mumu12IPC")
            and hasattr(self.control.mumu12IPC, "capture_display")
        ):
            img = self.control.mumu12IPC.capture_display()
        else:
            if not hasattr(self, "_screenshot"):
                self._screenshot = ScreenshotSession(config.conf.device, __system__)
            img = self._screenshot.capture(
                self.capture_frame, self.rebuild_screenshot, lambda: None
            )
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        stop_time = datetime.now()
        config.screenshot_time = stop_time
        interval = (stop_time - start_time).total_seconds() * 1000
        if config.screenshot_avg is None:
            config.screenshot_avg = interval
        else:
            config.screenshot_avg = config.screenshot_avg * 0.9 + interval * 0.1
        config.screenshot_count += 1
        if config.screenshot_count % 100 == 0:
            logger.info(
                f"截图用时{interval:.0f}ms 平均用时{config.screenshot_avg:.0f}ms"
            )

        save_screenshot_frame(img, capture_ms=interval)
        return None, img, gray

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
        self._input_once(
            lambda prepared: self.control.tap(
                prepared.points[0], display_frames=prepared.display_frames
            ),
            prepare=lambda: self._prepare_touch([point]),
        )

    def swipe(
        self, start: tuple[int, int], end: tuple[int, int], duration: int = 100
    ) -> None:
        """swipe"""
        logger.debug(f"swipe: {start} -> {end}, duration={duration}")
        self._input_once(
            lambda prepared: self.control.swipe(
                prepared.points[0],
                prepared.points[1],
                prepared.durations[0],
                display_frames=prepared.display_frames,
            ),
            prepare=lambda: self._prepare_touch([start, end], [duration]),
        )

    def swipe_ext(
        self, points: list[tuple[int, int]], durations: list[int], up_wait: int = 200
    ) -> None:
        """swipe_ext"""
        logger.debug(
            f"swipe_ext: points={points}, durations={durations}, up_wait={up_wait}"
        )
        self._input_once(
            lambda prepared: self.control.swipe_ext(
                prepared.points,
                prepared.durations,
                prepared.up_wait,
                display_frames=prepared.display_frames,
            ),
            prepare=lambda: self._prepare_touch(points, durations, up_wait),
        )

    def _prepare_touch(self, points, durations=None, up_wait=0):
        prepared_points = []
        for point in points:
            horizontal, vertical = point
            coordinates = int(horizontal), int(vertical)
            if any(not -(2**31) <= value < 2**31 for value in coordinates):
                raise ValueError("输入坐标超出有效范围")
            prepared_points.append(coordinates)
        if not prepared_points or (
            durations is not None and len(durations) + 1 != len(points)
        ):
            raise ValueError("输入路径与时长数量不匹配")
        prepared_durations = [float(duration) for duration in durations or []]
        prepared_wait = float(up_wait)
        if any(
            not isfinite(value) or value < 0
            for value in [*prepared_durations, prepared_wait]
        ):
            raise ValueError("输入时长必须为有限非负数")
        frames = None
        if self.profile.touch_backend == "maatouch":
            try:
                frames = self.display_frames()
            except MowerExit:
                raise
            except Exception as exc:
                raise TouchFailure(
                    self.profile,
                    __system__,
                    exc,
                    transport="adb",
                    phase="preparation",
                    retryable=isinstance(exc, (ConnectionError, TimeoutError)),
                ) from exc
        if frames is not None:
            width, height, rotation = frames
            if width <= 0 or height <= 0 or rotation not in (0, 1, 2, 3):
                raise ValueError("输入显示尺寸或旋转无效")
        elif self.profile.touch_backend == "maatouch" and config.MNT_COMPATIBILITY_MODE:
            raise ValueError("输入显示尺寸尚未确认")
        return _PreparedTouch(
            prepared_points,
            [int(duration) for duration in prepared_durations],
            int(prepared_wait),
            frames,
        )

    @contextmanager
    def _input_budget(self):
        deadline = time.monotonic() + self.profile.recovery_timeout

        def remaining():
            self._check_open()
            csleep(0)
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise TimeoutError("输入恢复时间预算已耗尽")
            return seconds

        with device_io_budget(remaining):
            yield

    def _input_once(self, operation, *, transport=None, prepare=None):
        """A transport error cannot tell us whether Android received the input."""

        def send():
            with self._recovery_scope():
                input_started = False
                try:
                    with self._input_budget():
                        if transport != "adb":
                            try:
                                needs_recovery = not self.input_alive()
                            except TouchFailure as probe_error:
                                if not probe_error.retryable:
                                    raise
                                needs_recovery = True
                            if needs_recovery:
                                control = getattr(self, "session_control", None)
                                if control is not None:
                                    control.recover().unwrap()
                                if not self.input_alive():
                                    raise TouchFailure(
                                        self.profile,
                                        __system__,
                                        ConnectionError("触控连接已断开，尚未发送输入"),
                                    )
                        prepared = prepare() if prepare is not None else None
                        input_started = True
                        return (
                            operation(prepared) if prepare is not None else operation()
                        )
                except (MowerExit, TouchFailure):
                    raise
                except Exception as exc:
                    if not input_started and isinstance(exc, DeviceRecoveryError):
                        raise
                    delivery_unknown = input_started and (
                        getattr(
                            exc,
                            "delivery_unknown",
                            getattr(exc, "input_not_sent", False) is not True,
                        )
                        is not False
                    )
                    failure = TouchFailure(
                        config.conf.device,
                        __system__,
                        exc,
                        delivery_unknown=delivery_unknown,
                        transport=transport,
                        phase="preparation",
                        retryable=not delivery_unknown
                        and isinstance(exc, (ConnectionError, TimeoutError)),
                    )
                    if delivery_unknown:
                        try:
                            self._stop_control()
                        except Exception as cleanup_error:
                            failure.cleanup_failed = True
                            failure.add_note(f"关闭触控后端失败：{cleanup_error}")
                    raise failure from exc

        control = getattr(self, "session_control", None)
        if control is not None and not control.executing:
            return control.execute(lambda device: send()).unwrap()
        return send()

    def input_alive(self) -> bool:
        self._check_open()
        try:
            with self._input_budget():
                for attempt in range(self.profile.recovery_attempts + 1):
                    budget_sleep(0)
                    if self.control is None:
                        return False
                    probe = getattr(self.control, "input_alive", None)
                    try:
                        return probe() if probe is not None else True
                    except TimeoutError:
                        if attempt >= self.profile.recovery_attempts:
                            raise
                        budget_sleep(min(0.1, self.profile.recovery_local_wait))
        except (MowerExit, TouchFailure):
            raise
        except Exception as exc:
            raise TouchFailure(
                self.profile,
                __system__,
                exc,
                phase="probe",
                retryable=isinstance(exc, TimeoutError),
            ) from exc

    def rebuild_input(self) -> bool:
        """Replace an independent input helper after Instance Binding verification."""
        self._check_open()
        if self.profile.touch_backend == "mumu_ipc":
            return False
        failure = getattr(self, "_recovery_error", None)
        if getattr(failure, "cleanup_failed", False):
            raise failure
        replacement = None
        try:
            with self._input_budget():
                if self.client is None or self.client.device_id != self.device_id:
                    raise ConnectionError("输入辅助连接缺少已验证的 ADB 目标")
                self._stop_control()
                budget_sleep(0)
                replacement = Device.Control(self, self.client)
                budget_sleep(0)
                with self._resource_lock:
                    self._check_open()
                    self.control = replacement
            if failure is not None:
                self._recovery_error = None
            return True
        except Exception as exc:
            if replacement is not None and self.control is not replacement:
                try:
                    replacement.close()
                except Exception as cleanup_error:
                    exc.cleanup_failed = True
                    exc.add_note(f"关闭未注册的触控后端失败：{cleanup_error}")
            if getattr(exc, "cleanup_failed", False):
                self._close_error = exc
            if isinstance(exc, (MowerExit, TouchFailure)):
                raise
            raise TouchFailure(self.profile, __system__, exc) from exc

    def resume_verified(self) -> None:
        """Release a failure only after application verifies the bound target."""
        with self._input_budget():
            failure = getattr(self, "_recovery_error", None)
            if getattr(failure, "cleanup_failed", False):
                raise failure
            self._recovery_error = None

    def close(self) -> None:
        """Release completed resources once and retain failed cleanup owners."""
        if getattr(self, "owner_pid", None) != os.getpid():
            return
        with self._resource_lock:
            resources = (
                *getattr(self, "_pending_cleanup", ()),
                (getattr(self, "_mumu_capture", None), "close"),
                (getattr(self, "_ld_capture", None), "close"),
                (getattr(self, "_droidcast", None), "close"),
                (self.control, "close"),
                (self.client, "close"),
            )
            self._mumu_capture = self._droidcast = self.control = self.client = None
            self._ld_capture = None
            # Failures outside close may lack a retained resource; they cannot
            # be cleared by successfully closing unrelated resources.
            if self._close_error is not None and not getattr(
                self, "_pending_cleanup", ()
            ):
                self._unowned_cleanup_error = self._close_error
            unowned_error = getattr(self, "_unowned_cleanup_error", None)
            errors = [unowned_error] if unowned_error is not None else []
            self._pending_cleanup = []
            for resource, method in resources:
                operation = getattr(resource, method, None)
                if operation is not None:
                    try:
                        operation()
                    except Exception as exc:
                        self._pending_cleanup.append((resource, method))
                        if exc not in errors:
                            errors.append(exc)
            if errors:
                if interrupt_error := getattr(self, "_interrupt_error", None):
                    errors[0].add_note(f"清理前中断 I/O 也失败：{interrupt_error}")
                for error in errors[1:]:
                    errors[0].add_note(str(error))
                self._close_error = errors[0]
                self._close_error.cleanup_failed = True
                raise self._close_error
            self._close_error = None
            self._interrupt_error = None

    def reconnect(self, *, retries: int = 3, restarts: int = 0) -> None:
        """Delegate lifecycle policy to the owning application session."""
        if control := getattr(self, "session_control", None):
            control.recover().unwrap()
            return
        if getattr(self, "_recovery_active", False):
            return self._connect_once()
        with self._recovery_scope():
            return recover_connection(
                self._connect_once,
                retries=retries,
                restarts=0 if getattr(self, "strict_target", False) else restarts,
            )

    def recover(self, func, retries: int = 3, restarts: int = 0):
        """正常操作失败后进入统一恢复；嵌套设备操作不再扩增重试次数。"""
        if control := getattr(self, "session_control", None):
            if control.executing or getattr(self, "_recovery_active", False):
                return func()
            return control.execute(lambda device: func()).unwrap()
        if getattr(self, "_recovery_active", False):
            return func()
        with self._recovery_scope():
            try:
                return func()
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as e:
                logger.warning(f"设备操作失败，开始重连：{e}")

            def retry_operation(*, wait_for_device):
                self._connect_once(wait_for_device=wait_for_device)
                # 连接失败不会继续访问设备；第三次重连成功也先验证操作再决定是否重启。
                return func()

            return recover_connection(
                retry_operation,
                retries=retries,
                restarts=0 if getattr(self, "strict_target", False) else restarts,
            )

    def check_current_focus(self) -> bool:
        """检查游戏前台状态，设备故障交回所属应用会话。"""
        update = False

        def check() -> bool:
            nonlocal update
            focus = self.current_focus()
            # 前台判定：package 前缀匹配（游戏包下任何界面都算前台，免疫新 activity）
            if focus.startswith(self.game_package + "/"):
                return update
            if self.is_app_running_in_background():
                logger.info("游戏不在前台，正在把游戏调到前台...")
                self.bring_to_foreground()
                csleep(2)
            else:
                # 游戏进程未运行，重新启动
                self.launch()
                csleep(10)
            update = True
            return update

        return self.recover(check)

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


# Android owns capture and input through the background display service.
if os.environ.get("MOWER_ANDROID") == "1":
    from mower_android.device import AndroidDevice as Device
