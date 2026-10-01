"""Versioned DroidCast installation and resources owned by one mower session."""

import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from threading import Event, RLock

import cv2
import numpy as np
import requests
from urllib3.exceptions import HTTPError, ReadTimeoutError

from arknights_mower import __rootdir__
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import (
    adb_command,
    adb_subprocess_options,
    guard_adb,
    run_adb,
)
from arknights_mower.utils.device.io_budget import budget_sleep, io_timeout
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.network import get_new_port

PACKAGE = "com.rayworks.droidcast"
VERSION = "1.3.0"
VERSION_CODE = 146
APK = Path(__rootdir__) / "vendor/droidcast/DroidCast-debug-1.3.0.apk"
COMMAND_TIMEOUT = 10
INSTALL_TIMEOUT = 60
START_TIMEOUT = 10
MAX_IMAGE_BYTES = 16 * 1024 * 1024
# Ownership is claimed when the mapping is created, so the steady state only
# needs a bounded tripwire. Reading the mapping costs one ADB subprocess
# (measured 70-107ms under load); doing it per frame put that inside the
# capture hot path. A change is refused on the next read at the latest, so it
# can stay unseen for at most this many frames.
MAPPING_CHECK_FRAMES = 20


class DroidCastError(RuntimeError):
    def __init__(self, code, message):
        self.code = f"droidcast_{code}"
        super().__init__(message)


class DroidCastSession:
    def __init__(self, adb_path: str, serial: str, *, rotate=False):
        if not adb_path or not serial.strip():
            raise ValueError("DroidCast 必须绑定明确的 ADB 和设备 serial")
        self.adb_path, self.serial, self.rotate = adb_path, serial, rotate
        self.owner = os.getpid()
        self.name = "mower-droidcast-" + uuid.uuid4().hex
        self.port = None
        self.process = None
        self.http = None
        self.starting = False
        # Zero makes the next frame read the mapping.
        self._frames_until_mapping_check = 0
        self._state_lock = RLock()
        self._interrupted = Event()
        self._cleanup_error = None

    def _adb(
        self,
        args,
        *,
        stage,
        timeout=COMMAND_TIMEOUT,
        cleanup=False,
        missing_ok=False,
        runner=None,
    ):
        if not cleanup and self._interrupted.is_set():
            raise DroidCastError("closed", "DroidCast 会话正在关闭")
        selector = [] if args == ["forward", "--list"] else ["-s", self.serial]
        try:
            return run_adb(
                [self.adb_path, *selector, *args],
                run=runner or subprocess.run,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=timeout if cleanup else io_timeout(timeout),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ).stdout
        except (MowerExit, DeviceRecoveryError):
            raise
        except subprocess.CalledProcessError as exc:
            if (
                missing_ok
                and exc.returncode == 1
                and not (exc.stdout or b"").strip()
                and (
                    exc.stdout is not None
                    and not (exc.stderr or b"").strip()
                    or cleanup
                    and (exc.stderr or b"").strip()
                    in {
                        f"adb: device '{self.serial}' not found".encode(),
                        f"error: device '{self.serial}' not found".encode(),
                    }
                )
            ):
                return b""
            detail = (exc.stdout or b"") + (exc.stderr or b"")
            raise DroidCastError(
                stage, detail.decode("utf-8", "replace")[:1000] or str(exc)
            ) from exc
        except Exception as exc:
            raise DroidCastError(stage, f"DroidCast {stage} 失败或超时：{exc}") from exc

    def ensure_version(self, *, install=False):
        """Read-only by default; replacement never uninstalls another signature."""
        output = self._adb(
            ["shell", "pm", "path", PACKAGE], stage="version_failed", missing_ok=True
        )
        path = None
        if output.strip():
            paths = output.decode("utf-8", "replace").splitlines()
            if len(paths) != 1 or not re.fullmatch(r"package:/[^\r\n]+\.apk", paths[0]):
                raise DroidCastError("version_failed", "无法确认 DroidCast APK 路径")
            path = paths[0].removeprefix("package:")
            package = self._adb(
                ["shell", "dumpsys", "package", PACKAGE], stage="version_failed"
            ).decode("utf-8", "replace")
            names = set(re.findall(r"\bversionName=(\S+)", package))
            codes = set(re.findall(r"\bversionCode=(\d+)", package))
            if names == {VERSION} and codes == {str(VERSION_CODE)}:
                return path
            if len(names) != 1 or len(codes) != 1:
                raise DroidCastError(
                    "version_failed",
                    "无法确认已安装的 DroidCast 版本，请检查设备包管理器",
                )
            if int(next(iter(codes))) > VERSION_CODE:
                raise DroidCastError(
                    "version_failed",
                    "设备上的 DroidCast 比附带的 1.3.0 更新；请自行确认版本，不会自动降级",
                )
        if not install:
            raise DroidCastError(
                "version_required",
                "需要 DroidCast 1.3.0。测试截图不会自动安装应用；启动任务时会自动安装兼容版本，也可手动安装随附的 APK。",
            )
        try:
            output = self._adb(
                ["install", "-r", str(APK)],
                stage="install_failed",
                timeout=INSTALL_TIMEOUT,
            )
            detail = output.decode("utf-8", "replace")
        except DroidCastError as exc:
            detail = str(exc)
            if "INSTALL_FAILED_DEPRECATED_SDK_VERSION" in detail:
                try:
                    output = self._adb(
                        ["install", "-r", "--bypass-low-target-sdk-block", str(APK)],
                        stage="install_failed",
                        timeout=INSTALL_TIMEOUT,
                    )
                    detail = output.decode("utf-8", "replace")
                except DroidCastError as exc2:
                    detail = str(exc2)
            if (
                "INSTALL_FAILED_UPDATE_INCOMPATIBLE" not in detail
                and "INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES" not in detail
                and detail.strip().splitlines()[-1:] != ["Success"]
            ):
                raise
        if (
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in detail
            or "INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES" in detail
        ):
            raise DroidCastError(
                "signature_conflict",
                "DroidCast 签名冲突，未卸载已有应用。请停止使用该助手的程序，在目标设备设置中确认并手动卸载 com.rayworks.droidcast 后重试，或选择其他截图后端。卸载会移除该应用的数据。",
            )
        if detail.strip().splitlines()[-1:] != ["Success"]:
            raise DroidCastError(
                "install_failed", f"DroidCast 安装未成功：{detail[:1000]}"
            )
        return self.ensure_version(install=False)

    def start(self, *, install=False):
        with self._state_lock:
            if self._interrupted.is_set():
                raise DroidCastError("closed", "DroidCast 会话正在关闭")
            result = self._start(install=install)
            # This claim is about to be used by a frame: the first capture after
            # a start or a rebuild proves the mapping it just created.
            self._frames_until_mapping_check = 0
            return result

    def _start(self, *, install=False):
        if self.owner != os.getpid():
            raise DroidCastError(
                "ownership_conflict", "不能重建其他 mower 进程的 DroidCast 会话"
            )
        self.close()
        path = self.ensure_version(install=install)
        self.name = "mower-droidcast-" + uuid.uuid4().hex
        port = get_new_port()
        try:
            self._create_forward(port)
            guard_adb(
                self.adb_path, timeout=io_timeout(COMMAND_TIMEOUT), run=subprocess.run
            )
            self.process = subprocess.Popen(
                adb_command(
                    [
                        self.adb_path,
                        "-s",
                        self.serial,
                        "shell",
                        f"CLASSPATH={shlex.quote(path)}",
                        "app_process",
                        "/",
                        f"--nice-name={self.name}",
                        f"{PACKAGE}.Main",
                        f"--port={port}",
                    ]
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                **adb_subprocess_options(),
            )
            self.http = requests.Session()
            self.http.trust_env = False
            self.starting = True
            if self._interrupted.is_set():
                raise DroidCastError("closed", "DroidCast 会话正在关闭")
        except BaseException as exc:
            try:
                self.close()
            except Exception as cleanup_error:
                exc.add_note(f"DroidCast 清理失败：{cleanup_error}")
            if not isinstance(exc, Exception) or isinstance(
                exc, (DroidCastError, MowerExit, DeviceRecoveryError)
            ):
                raise
            raise DroidCastError(
                "start_failed", f"DroidCast helper 启动失败：{exc}"
            ) from exc

    def _create_forward(self, port):
        args = ["forward", "--no-rebind", f"tcp:{port}", f"tcp:{port}"]
        expected = [self.adb_path, "-s", self.serial, *args]

        def record_success(argv, **options):
            result = subprocess.run(argv, **options)
            if argv == adb_command(expected) and result.returncode == 0:
                # run_adb checks its deadline again after the command returns.
                # Preserve confirmed ownership even if that check then fails.
                self.port = port
            return result

        self._adb(args, stage="forward_failed", runner=record_success)
        self.port = port

    def _mapping_matches(self, *, cleanup=False):
        rows = self._adb(
            ["forward", "--list"], stage="forward_failed", cleanup=cleanup
        ).decode("utf-8", "replace")
        expected = [self.serial, f"tcp:{self.port}", f"tcp:{self.port}"]
        matched = False
        for row in rows.splitlines():
            entry = row.split()
            if not entry:
                continue
            if len(entry) != 3 or any(
                not re.fullmatch(r"[^:\s]+:\S+", endpoint) for endpoint in entry[1:]
            ):
                raise DroidCastError(
                    "cleanup_failed" if cleanup else "forward_failed",
                    "DroidCast 转发清单格式无效，无法确认自有映射",
                )
            matched = matched or entry == expected
        return matched

    def _arm_mapping_check(self):
        """Read the mapping on the first frame of every interval.

        The counter is a countdown consumed once per frame, so arming it with
        one less than the interval makes the interval itself the distance
        between two reads and the longest a change can stay unseen.
        """
        self._frames_until_mapping_check = MAPPING_CHECK_FRAMES - 1

    def _verify_owned_mapping(self):
        """Read the mapping for the first frame after a claim, then on a cadence.

        ``start()`` claims the mapping before any frame, so the first frame
        proves that claim here. A changed mapping still raises
        ``forward_failed``, which the application answers with one rebuild;
        only how long a change can stay unseen widens, and by at most
        ``MAPPING_CHECK_FRAMES``.
        """
        self._frames_until_mapping_check -= 1
        if self._frames_until_mapping_check > 0:
            return
        if not self._mapping_matches():
            raise DroidCastError(
                "forward_failed", "DroidCast forward 映射已经改变，请重建所选截图会话"
            )
        self._arm_mapping_check()

    def capture_frame(self):
        if self.owner != os.getpid() or self._interrupted.is_set():
            raise DroidCastError("closed", "DroidCast 会话已关闭或所有权不匹配")
        if self.process is None or self.http is None:
            raise DroidCastError("start_failed", "DroidCast helper 尚未启动")
        deadline = time.monotonic() + io_timeout(START_TIMEOUT)
        self._verify_owned_mapping()
        while True:
            if self._interrupted.is_set():
                raise DroidCastError("closed", "DroidCast 会话正在关闭")
            remaining = min(io_timeout(START_TIMEOUT), deadline - time.monotonic())
            if remaining <= 0:
                raise DroidCastError(
                    "start_timeout", "DroidCast 未在限定时间提供截图服务"
                )
            if self.process.poll() is not None:
                raise DroidCastError("start_failed", "DroidCast helper 提前退出")
            response = None
            try:
                # The helper's default payload is JPEG. Asking for
                # `?format=png` costs 180-290ms per frame on the measured
                # device (1828KiB/388ms against 1008KiB/177ms) while the decoded
                # frame stays equivalent for recognition: gray SSIM 0.9996 and
                # 3.4% of pixels differing by more than 8/255. The default is
                # also the request the pre-refactor capture path made.
                response = self.http.get(
                    f"http://127.0.0.1:{self.port}/screenshot",
                    timeout=(min(2, remaining), min(3, remaining)),
                    stream=True,
                    allow_redirects=False,
                )
                if response.status_code != 200:
                    raise DroidCastError(
                        "http_failed", f"DroidCast HTTP 状态码 {response.status_code}"
                    )
                data = bytearray()
                while True:
                    if self._interrupted.is_set():
                        raise DroidCastError("closed", "DroidCast 会话正在关闭")
                    if time.monotonic() >= deadline:
                        raise DroidCastError(
                            "http_timeout", "DroidCast HTTP 读取超过限定时间"
                        )
                    chunk = response.raw.read1(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise DroidCastError(
                            "http_failed", "DroidCast 图像超过 16 MiB 上限"
                        )
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    raise DroidCastError("frame_failed", "DroidCast 未返回可解码图像")
                self.starting = False
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return cv2.rotate(frame, cv2.ROTATE_180) if self.rotate else frame
            except (requests.Timeout, ReadTimeoutError, TimeoutError) as exc:
                raise DroidCastError(
                    "http_timeout", "DroidCast HTTP 连接或读取超时，请检查助手后重试"
                ) from exc
            except requests.ConnectionError as exc:
                if not self.starting:
                    raise DroidCastError(
                        "http_failed", f"DroidCast HTTP 连接失败：{exc}"
                    ) from exc
                budget_sleep(min(0.1, max(0, deadline - time.monotonic())))
            except (requests.RequestException, HTTPError, OSError) as exc:
                raise DroidCastError(
                    "http_failed", f"DroidCast HTTP 读取失败：{exc}"
                ) from exc
            finally:
                if response is not None:
                    response.close()

    def close(self):
        with self._state_lock:
            if self.owner != os.getpid():
                return
            if self._cleanup_error is not None:
                raise self._cleanup_error
            try:
                self._close()
            except Exception as exc:
                self._cleanup_error = exc
                self._cleanup_error.cleanup_failed = True
                raise

    def interrupt(self):
        if self.owner != os.getpid():
            return
        self._interrupted.set()

    def _close(self):
        """A changed mapping or process identity is never claimed or removed."""
        if self.owner != os.getpid():
            return
        errors = []
        process, self.process = self.process, None
        if process is not None:
            try:
                pids = self._adb(
                    ["shell", "pidof", self.name],
                    stage="cleanup_failed",
                    cleanup=True,
                    missing_ok=True,
                ).split()
                for pid in pids:
                    if not pid.isdigit():
                        raise DroidCastError(
                            "cleanup_failed", "DroidCast PID 查询结果无效"
                        )
                    identity = self._adb(
                        ["shell", "cat", f"/proc/{pid.decode()}/cmdline"],
                        stage="cleanup_failed",
                        cleanup=True,
                        missing_ok=True,
                    )
                    if identity.split(b"\0", 1)[0] == self.name.encode():
                        self._adb(
                            ["shell", "kill", pid.decode()],
                            stage="cleanup_failed",
                            cleanup=True,
                            missing_ok=True,
                        )
            except Exception as exc:
                errors.append(exc)
            try:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=2)
            except Exception as exc:
                errors.append(exc)
        if self.port is not None:
            try:
                if self._mapping_matches(cleanup=True):
                    try:
                        self._adb(
                            ["forward", "--remove", f"tcp:{self.port}"],
                            stage="cleanup_failed",
                            cleanup=True,
                        )
                    except DroidCastError:
                        if self._mapping_matches(cleanup=True):
                            raise
            except Exception as exc:
                errors.append(exc)
            finally:
                self.port = None
        if self.http is not None:
            try:
                self.http.close()
            except Exception as exc:
                errors.append(exc)
            self.http = None
        if errors:
            raise DroidCastError(
                "cleanup_failed", "；".join(str(error) for error in errors)
            )
