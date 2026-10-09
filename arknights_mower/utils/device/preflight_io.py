"""Bounded production I/O for the read-only device preflight.

No Device is constructed here: doing so also starts input services and legacy
recovery. Capture helpers belong to this invocation and are closed on exit.
"""

import ctypes
import multiprocessing
import os
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

from arknights_mower.utils.config.device_profile import capture_compatibility_error
from arknights_mower.utils.device.adb_client.core import is_tcp_serial
from arknights_mower.utils.device.adb_client.server import run_adb
from arknights_mower.utils.device.droidcast import DroidCastSession
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.ldplayer_capture import LDCaptureSession
from arknights_mower.utils.device.manager_io import run_command
from arknights_mower.utils.device.mumu12ipc.paths import resolve_mumu_paths
from arknights_mower.utils.device.mumu_info import (
    mumu_endpoint,
    normalize_mumu_endpoint,
    select_mumu_instance,
)
from arknights_mower.utils.device.owned import close_process
from arknights_mower.utils.device.screenshot import capture_adb_frame
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import resolve_config_path

COMMAND_TIMEOUT = 10


def decode_image(data: bytes) -> np.ndarray:
    decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("截图后端未返回可解码图像")
    return cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)


def custom_capture_argv(command: str, adb_path: str, serial: str) -> list[str]:
    """Keep a custom capture on the pinned ADB; never interpret a host shell."""
    argv = shlex.split(command, posix=os.name != "nt")
    argv = [value.strip('"') for value in argv]
    # This suffix is part of the old default and only suppresses stderr.
    argv = [value for value in argv if value not in {"2>/dev/null", "2>NUL"}]
    if not argv or any(value in {"|", "||", "&&", ";", ">", "<"} for value in argv):
        raise ValueError("自定义截图请填写可执行程序及参数，不支持主机 shell 组合命令")
    executable = Path(argv[0]).name.lower()
    if (
        executable in {"adb", "adb.exe", "hd-adb.exe", "nox_adb.exe"}
        or argv[0] == adb_path
    ):
        args = argv[1:]
        if args[:1] == ["-s"]:
            if len(args) < 3 or args[1] != serial:
                raise ValueError("自定义截图命令的 serial 必须与已选择设备一致")
            args = args[2:]
        if (
            len(args) < 2
            or args[0] not in {"shell", "exec-out"}
            or args[1] != "screencap"
        ):
            raise ValueError("自定义 ADB 截图只支持当前设备的 screencap 命令")
        if args[2:] not in ([], ["-p"]):
            raise ValueError("自定义 ADB 截图必须直接输出图像，仅支持 screencap -p")
        return [adb_path, "-s", serial, *args]
    return argv


def _capture_mumu_worker(
    emulator_root: str, instance: str, package: str, frame_buffer, succeeded, error
):
    """Isolate a possibly blocked vendor DLL from the preflight deadline.

    Reuse only its library binding. Legacy IPC recovery can launch the game or
    restart an emulator, so none of those entry points are called here.
    """
    from arknights_mower.utils.device.mumu12ipc.core import (
        MuMu12IPC,
        bind_display,
        capture_native_frame,
    )

    ipc = object.__new__(MuMu12IPC)
    ipc._conn = 0
    ipc._dll = None
    try:
        ipc._emu_root = emulator_root
        ipc._load_renderer()
        ipc._conn = ipc._dll.nemu_connect(emulator_root, int(instance))
        if ipc._conn <= 0:
            raise RuntimeError(f"MuMu IPC 无法连接已选择实例：原生返回码 {ipc._conn}")
        display_id = bind_display(ipc._dll, ipc._conn, package)

        size = 1920 * 1080 * 4
        buffer = (ctypes.c_ubyte * size)()
        frame = capture_native_frame(ipc._dll, ipc._conn, display_id, buffer)
        shared_frame = np.frombuffer(frame_buffer, np.uint8).reshape(1080, 1920, 3)
        np.copyto(shared_frame, frame)
        succeeded.value = True
    except Exception as exc:
        error.value = str(exc).encode("utf-8")[:1023]
    finally:
        if ipc._conn > 0:
            ipc._dll.nemu_disconnect(ipc._conn)


class ProductionPreflightIO:
    def __init__(self, read_configuration=None):
        if read_configuration is None:
            from arknights_mower.utils import config

            def read_configuration():
                return config.conf

        self._read_configuration = read_configuration

    def host_platform(self) -> str:
        return {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(
            platform.system(), "unknown"
        )

    def installation_exists(self, path: str) -> bool:
        return bool(path.strip()) and Path(resolve_config_path(path)).exists()

    def product_adb_paths(self, profile) -> list[str]:
        if not profile.installation_path or profile.preset_id.startswith("manual."):
            return []
        root = Path(resolve_config_path(profile.installation_path))
        locations = {
            "windows.mumu12": (
                "adb.exe",
                "shell/adb.exe",
                "nx_main/adb.exe",
                "nx_device/12.0/shell/adb.exe",
                "nx_device/15.0/shell/adb.exe",
            ),
            "windows.ldplayer9": ("adb.exe",),
            "windows.ldplayer14": ("adb.exe",),
            "windows.nox": ("nox_adb.exe", "bin/nox_adb.exe", "adb.exe"),
            "windows.bluestacks5": ("HD-Adb.exe",),
            "macos.bluestacks_air": ("Contents/MacOS/hd-adb",),
            "macos.mumu_pro": ("Contents/MacOS/adb",),
            "macos.avd": ("platform-tools/adb",),
            "linux.avd": ("platform-tools/adb",),
            "linux.genymotion": ("tools/adb",),
        }
        return [
            str(root / relative) for relative in locations.get(profile.preset_id, ())
        ]

    def sdk_adb_paths(self) -> list[str]:
        roots = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
        host = self.host_platform()
        if host == "windows":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                roots.append(str(Path(local) / "Android/Sdk"))
        elif host == "macos":
            roots.append(str(Path.home() / "Library/Android/sdk"))
        elif host == "linux":
            roots.append(str(Path.home() / "Android/Sdk"))
        name = "adb.exe" if host == "windows" else "adb"
        return [str(Path(root) / "platform-tools" / name) for root in roots if root]

    def path_adb_paths(self) -> list[str]:
        path = shutil.which("adb")
        return [path] if path else []

    def _run(self, argv: list[str]) -> bytes:
        timeout = io_timeout(COMMAND_TIMEOUT)
        logger.debug(f"设备预检命令开始：{argv}，超时 {timeout:.3f} 秒")
        output = run_command(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        ).stdout
        logger.debug(f"设备预检命令完成：{argv}")
        return output

    def _adb(self, adb_path: str, serial: str, args: list[str]) -> bytes:
        if not serial.strip():
            raise ValueError("设备 serial 不能为空")
        return self._run_adb([adb_path, "-s", serial, *args])

    def _run_adb(self, argv: list[str], *, maximum: float | None = None) -> bytes:
        timeout = io_timeout(COMMAND_TIMEOUT if maximum is None else maximum)
        logger.debug(f"设备预检 ADB 命令开始：{argv}，超时 {timeout:.3f} 秒")
        output = run_adb(
            argv,
            run=run_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        ).stdout
        logger.debug(f"设备预检 ADB 命令完成：{argv}")
        return output

    def performance_info(self, adb_path: str, serial: str) -> dict[str, int]:
        """Read Android-visible resources on the verified target within three seconds."""
        if not serial.strip():
            raise ValueError("设备 serial 不能为空")
        output = self._run_adb(
            [
                adb_path,
                "-s",
                serial,
                "shell",
                "cat /sys/devices/system/cpu/online; cat /proc/meminfo",
            ],
            maximum=3,
        ).decode("utf-8", "replace")
        lines = output.strip().splitlines()
        if not lines or not re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", lines[0]):
            raise ValueError("无法读取设备在线 CPU")
        cpus = set()
        for part in lines[0].split(","):
            bounds = [int(value) for value in part.split("-")]
            start, end = bounds[0], bounds[-1]
            if not 0 <= start <= end < 1024:
                raise ValueError("设备在线 CPU 范围无效")
            for cpu in range(start, end + 1):
                if cpu in cpus:
                    raise ValueError("设备在线 CPU 范围重复")
                cpus.add(cpu)
        totals = re.findall(r"^MemTotal:\s+(\d+) kB\s*$", output, re.MULTILINE)
        if len(totals) != 1 or int(totals[0]) < 1024:
            raise ValueError("无法读取设备内存总量")
        return {"cpu_cores": len(cpus), "memory_mb": int(totals[0]) // 1024}

    def validate_adb(self, path: str) -> bool:
        try:
            output = self._run([str(resolve_config_path(path)), "version"])
            return bool(re.search(rb"Android Debug Bridge version \d+\.\d+", output))
        except (OSError, subprocess.SubprocessError):
            return False

    def normalize_adb_path(self, path: str) -> str:
        return str(Path(resolve_config_path(path)).resolve())

    def devices(self, adb_path: str, serial: str) -> list[tuple[str, str]]:
        def read_devices():
            output = self._run_adb([adb_path, "devices"]).decode("utf-8", "replace")
            if (
                not output.splitlines()
                or output.splitlines()[0].strip() != "List of devices attached"
            ):
                raise ValueError("ADB 未返回有效设备列表")
            rows = []
            for line in output.splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[1] in {
                    "device",
                    "offline",
                    "unauthorized",
                    "recovery",
                    "sideload",
                    "bootloader",
                    "no",
                }:
                    rows.append((fields[0], fields[1]))
            return rows

        rows = read_devices()
        if (
            serial
            and is_tcp_serial(serial)
            and not any(row[0] == serial for row in rows)
        ):
            connected = (
                self._run_adb([adb_path, "connect", serial])
                .decode("utf-8", "replace")
                .strip()
            )
            if connected not in {
                f"connected to {serial}",
                f"already connected to {serial}",
            }:
                raise ValueError(
                    "ADB 未确认目标端点连接成功，请检查地址与 ADB 开关后重试"
                )
            rows = read_devices()
        return rows

    def boot_completed(self, adb_path: str, serial: str) -> str:
        return self._adb(
            adb_path, serial, ["shell", "getprop", "sys.boot_completed"]
        ).decode("utf-8", "replace")

    def display_size(self, adb_path: str, serial: str) -> str:
        return self._adb(adb_path, serial, ["shell", "wm", "size"]).decode(
            "utf-8", "replace"
        )

    def packages(self, adb_path: str, serial: str) -> list[str]:
        output = self._adb(
            adb_path, serial, ["shell", "pm", "list", "packages"]
        ).decode("utf-8", "replace")
        return [
            line.removeprefix("package:").strip()
            for line in output.splitlines()
            if line.startswith("package:")
        ]

    def capture_frame(self, adb_path: str, serial: str, profile) -> np.ndarray:
        if reason := capture_compatibility_error(
            profile.preset_id, profile.screenshot_backend, self.host_platform()
        ):
            raise ValueError(reason)
        if profile.screenshot_backend == "ld_native":
            capture = LDCaptureSession(profile, adb_path, serial)
            try:
                return capture.capture_frame()
            finally:
                capture.close()
        if profile.screenshot_backend == "adb_gzip":
            return capture_adb_frame(adb_path, serial)
        if profile.screenshot_backend == "custom":
            command = self._read_configuration().custom_screenshot.command
            argv = custom_capture_argv(command, adb_path, serial)
            return decode_image(
                self._run_adb(argv) if argv[0] == adb_path else self._run(argv)
            )
        if profile.screenshot_backend == "droidcast":
            return self._capture_droidcast(adb_path, serial)
        if profile.screenshot_backend == "mumu_ipc":
            return self._capture_mumu(profile, serial)
        raise ValueError(f"截图后端尚不可用：{profile.screenshot_backend}")

    def _capture_mumu(self, profile, serial: str) -> np.ndarray:
        if not is_tcp_serial(serial):
            raise ValueError("MuMu IPC 必须绑定经过验证的模拟器实例端点")
        root, manager = resolve_mumu_paths(
            profile.installation_path, profile.manager_path
        )
        actual_instance_id, entry = select_mumu_instance(
            self._run([manager, "info", "-v", "all"]),
            profile.instance_id,
            profile.instance_name,
        )
        endpoint = mumu_endpoint(entry)
        if normalize_mumu_endpoint(endpoint) != normalize_mumu_endpoint(serial):
            raise ValueError("MuMu IPC 实例端点与已选择设备 serial 不一致，请重新绑定")
        context = multiprocessing.get_context("spawn")
        frame_buffer = context.RawArray(ctypes.c_ubyte, 1920 * 1080 * 3)
        succeeded = context.RawValue(ctypes.c_bool, False)
        error = context.RawArray(ctypes.c_char, 1024)
        process = context.Process(
            target=_capture_mumu_worker,
            args=(
                root,
                actual_instance_id,
                profile.game_package,
                frame_buffer,
                succeeded,
                error,
            ),
            daemon=True,
        )
        owner_pid = os.getpid()
        try:
            process.start()
            process.join(timeout=io_timeout(COMMAND_TIMEOUT))
            if process.is_alive():
                raise TimeoutError("MuMu IPC 未在限定时间返回首帧")
            # A completed worker can still finish after the session deadline.
            io_timeout(COMMAND_TIMEOUT)
            if process.exitcode != 0 or not succeeded.value:
                message = error.value.decode("utf-8", "replace")
                raise RuntimeError(message or "MuMu IPC 首帧工作进程未成功完成")
            return np.frombuffer(frame_buffer, np.uint8).reshape(1080, 1920, 3).copy()
        finally:
            close_process(process, owner_pid)

    def _capture_droidcast(self, adb_path: str, serial: str) -> np.ndarray:
        capture = DroidCastSession(
            adb_path, serial, rotate=self._read_configuration().droidcast.rotate
        )
        try:
            capture.start(install=False)
            return capture.capture_frame()
        finally:
            capture.close()
