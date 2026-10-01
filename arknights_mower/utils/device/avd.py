"""Official SDK discovery and explicit, owned AVD lifecycle operations.

AVD names are the binding. An emulator-N transport is only a current endpoint
after `adb -s emulator-N emu avd name` has verified that name. Normal recovery
cannot start or stop an AVD, and process ownership never authorizes app-exit
cleanup of the emulator.
"""

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from arknights_mower.utils.device.adb_client.server import (
    current_adb_server,
    emulator_connect_target,
    run_adb,
)
from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    parse_adb_devices,
)
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import (
    MAX_INSTANCES,
    MAX_OUTPUT,
    run_manager_command,
)
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.session import InstanceObservation
from arknights_mower.utils.path import resolve_config_path

AVD_NAME = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}"
EMULATOR_SERIAL = r"emulator-[0-9]{1,5}"
COMMAND_TIMEOUT = 3.0
DISCOVERY_TIMEOUT = 10.0


@dataclass
class _OwnedAVD:
    process: object
    serial: str = ""


class AVDController:
    def __init__(
        self,
        *,
        run=None,
        spawn=None,
        probe=None,
        monotonic=time.monotonic,
        environment=None,
        home=None,
        which=None,
    ):
        self.run = run or run_manager_command
        self.spawn = spawn or subprocess.Popen
        self.probe = probe
        self.monotonic = monotonic
        self.environment = os.environ if environment is None else environment
        self.home = Path.home() if home is None else Path(home)
        self.which = which or shutil.which
        self._owned = {}

    def _remaining(self, deadline):
        available = deadline - self.monotonic()
        if available <= 0:
            raise InstanceBindingError(
                "manager_timeout",
                "AVD 检测或启动时间预算已耗尽，请检查 Android SDK 与 ADB 后重试。",
                ["manager_path", "adb_path"],
            )
        return io_timeout(min(COMMAND_TIMEOUT, available))

    def _command(self, argv, deadline, *, adb=False):
        options = dict(
            timeout=self._remaining(deadline),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        command = " ".join(argv[1:])
        try:
            if adb:
                result = run_adb(
                    argv,
                    run=self.run,
                    probe=self.probe,
                    monotonic=self.monotonic,
                    **options,
                )
            else:
                result = self.run(argv, **options)
            result.check_returncode()
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise InstanceBindingError(
                "manager_timeout",
                f"Android SDK 命令 {command} 响应超时，请检查 SDK 与 ADB 后重试。",
                ["adb_path"] if adb else ["manager_path"],
            ) from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", None) or getattr(exc, "stdout", None)
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", "replace")
            raise InstanceBindingError(
                "manager_failed",
                f"Android SDK 命令 {command} 执行失败：{str(detail or exc)[:2048]}",
                ["adb_path"] if adb else ["manager_path"],
            ) from exc
        output = result.stdout or b""
        error = result.stderr or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        if isinstance(error, bytes):
            error = error.decode("utf-8", "replace")
        self._remaining(deadline)
        if len(output) + len(error) > MAX_OUTPUT:
            raise InstanceBindingError(
                "manager_output_invalid", "Android SDK 命令输出超过 1 MiB。", []
            )
        if re.search(
            r"^\s*(?:(?:ERROR|FATAL|PANIC|FAILURE)\s*[:|]"
            r"|(?:emulator|adb):\s*(?:error|failed|fatal)\b)",
            output + "\n" + error,
            re.I | re.M,
        ):
            raise InstanceBindingError(
                "manager_failed",
                f"Android SDK 命令 {command} 报错：{(error or output).strip()[:2048]}",
                ["adb_path"] if adb else ["manager_path"],
            )
        if error.strip() and not all(
            re.match(r"\s*(INFO|WARNING|DEBUG)\s*\|", line)
            for line in error.splitlines()
            if line.strip()
        ):
            raise InstanceBindingError(
                "manager_failed",
                f"Android SDK 命令 {command} 未成功：{error.strip()[:2048]}",
                ["adb_path"] if adb else ["manager_path"],
            )
        return output.strip()

    def _manager_candidates(self, profile, host):
        name = "emulator.exe" if host == "windows" else "emulator"
        if profile.manager_path.strip():
            return [Path(resolve_config_path(profile.manager_path))]
        if profile.installation_path.strip():
            root = Path(resolve_config_path(profile.installation_path))
            return [root / "emulator" / name, root / name]
        roots = [
            self.environment.get("ANDROID_SDK_ROOT"),
            self.environment.get("ANDROID_HOME"),
        ]
        if host == "macos":
            roots.append(self.home / "Library/Android/sdk")
        elif host == "linux":
            roots.append(self.home / "Android/Sdk")
        candidates = [Path(root) / "emulator" / name for root in roots if root]
        path = self.which(name)
        if path:
            candidates.append(Path(path))
        return candidates

    def _manager(self, profile, host, deadline):
        failures = []
        seen = set()
        for candidate in self._manager_candidates(profile, host):
            path = str(candidate.resolve())
            if path in seen:
                continue
            seen.add(path)
            if not candidate.is_file():
                continue
            if not os.access(candidate, os.X_OK):
                failures.append(
                    InstanceBindingError(
                        "discovery_permission_denied",
                        f"Android Emulator 程序不可执行：{path}。请检查执行权限。",
                        ["manager_path"],
                    )
                )
                continue
            try:
                output = self._command([path, "-version"], deadline)
                if not re.search(r"\bAndroid emulator version \d+\.\d+", output):
                    raise InstanceBindingError(
                        "invalid_sdk",
                        f"{path} 未返回官方 Android Emulator 版本，请指定 Android SDK 中的 emulator 程序。",
                        ["manager_path"],
                    )
                return path
            except InstanceBindingError as exc:
                failures.append(exc)
        if failures:
            raise failures[0]
        raise InstanceBindingError(
            "missing_sdk",
            "未找到 Android SDK Emulator。请通过 Android Studio 安装 Android Emulator，或指定 SDK 安装目录 / emulator 程序。",
            ["installation_path", "manager_path"],
        )

    def _names(self, manager, deadline):
        output = self._command([manager, "-list-avds"], deadline)
        names = []
        for line in output.splitlines():
            line = line.strip()
            if not line or re.match(r"(INFO|WARNING|DEBUG)\s*\|", line):
                continue
            if not re.fullmatch(AVD_NAME, line) or line in names:
                raise InstanceBindingError(
                    "manager_output_invalid",
                    f"Android SDK 返回的 AVD 列表无法识别：{line[:200]}。请在终端运行 emulator -list-avds 检查。",
                    ["manager_path"],
                )
            names.append(line)
            if len(names) > MAX_INSTANCES:
                raise InstanceBindingError(
                    "manager_output_invalid", "AVD 列表超过 64 个实例。", []
                )
        return names

    def discover(self, profile, host, timeout=DISCOVERY_TIMEOUT):
        result = {"installations": [], "errors": []}
        try:
            if host not in {"macos", "linux"}:
                raise InstanceBindingError(
                    "unsupported_host",
                    "AVD 自动发现仅适用于 macOS 与 Linux，其他平台请使用其他模拟器的高级手动配置。",
                    ["preset_id"],
                )
            deadline = self.monotonic() + max(timeout, 0)
            manager = self._manager(profile, host, deadline)
            names = self._names(manager, deadline)
            if not names:
                raise InstanceBindingError(
                    "no_avd",
                    "Android SDK 中没有 AVD，请先在 Android Studio Device Manager 中创建虚拟设备，再重新检测。",
                    [],
                )
            root = Path(manager).parent
            if root.name == "emulator":
                root = root.parent
            result["installations"].append(
                {
                    "preset_id": f"{host}.avd",
                    "installation_path": str(root),
                    "manager_path": manager,
                    "instances": [
                        {
                            "instance_id": name,
                            "instance_name": name,
                            "state": "unknown",
                            "serial": "",
                        }
                        for name in names
                    ],
                }
            )
        except InstanceBindingError as exc:
            result["errors"].append(
                PreflightError(exc.code, str(exc), fields=exc.fields)
            )
        except PermissionError as exc:
            result["errors"].append(
                PreflightError(
                    "discovery_permission_denied",
                    f"无法访问 Android SDK 路径：{exc}。请检查目录与程序访问权限，或选择当前用户可读取的 SDK。",
                    fields=["installation_path", "manager_path"],
                )
            )
        except OSError as exc:
            result["errors"].append(
                PreflightError(
                    "manager_failed",
                    f"无法读取 Android SDK 路径：{exc}。请检查 SDK 所在磁盘与目录，修正路径后重试。",
                    fields=["installation_path", "manager_path"],
                )
            )
        return result

    @staticmethod
    def _key(profile):
        if not re.fullmatch(AVD_NAME, profile.instance_id):
            raise InstanceBindingError(
                "instance_required", "请先选择一个明确的 AVD。", ["instance_id"]
            )
        if not profile.manager_path.strip():
            raise InstanceBindingError(
                "missing_sdk",
                "请重新检测并绑定 Android SDK Emulator。",
                ["manager_path"],
            )
        manager = Path(resolve_config_path(profile.manager_path)).resolve()
        if not manager.is_file() or not os.access(manager, os.X_OK):
            raise InstanceBindingError(
                "missing_sdk",
                "已绑定的 Android Emulator 不存在或不可执行。",
                ["manager_path"],
            )
        return (str(manager), profile.instance_id)

    @staticmethod
    def _early_exit(profile, owner):
        code = owner.process.poll()
        if code is not None:
            raise InstanceBindingError(
                "avd_start_failed",
                f"AVD {profile.instance_id} 的启动进程已退出（退出码 {code}）。请在终端运行 emulator -avd {profile.instance_id} 查看 SDK 启动诊断，并检查虚拟化与系统镜像。",
                [],
            )

    def inspect(self, profile, timeout):
        key = self._key(profile)
        if not profile.adb_path.strip():
            raise InstanceBindingError(
                "missing_adb", "请选择有效的 ADB。", ["adb_path"]
            )
        deadline = self.monotonic() + max(timeout, 0)
        owner = self._owned.get(key)
        if owner is not None:
            if owner.process.poll() is not None:
                del self._owned[key]
            self._early_exit(profile, owner)
        if current_adb_server() is not None:
            serial = (
                owner.serial
                if owner is not None and owner.serial
                else profile.last_serial
            )
            endpoint = emulator_connect_target(serial)
            if endpoint is not None:
                self._command(
                    [profile.adb_path, "connect", endpoint], deadline, adb=True
                )
        rows = parse_adb_devices(
            self._command(
                [profile.adb_path, "devices", "-l"], deadline, adb=True
            ).encode()
        )
        candidates = [
            serial for serial in rows if re.fullmatch(EMULATOR_SERIAL, serial)
        ]
        if len(candidates) > MAX_INSTANCES:
            raise InstanceBindingError(
                "endpoint_ambiguous",
                "在线 emulator transport 超过 64 个，无法安全确定目标。",
                [],
            )
        matches = []
        unresolved = False
        for serial in candidates:
            if len(rows[serial]) != 1:
                raise InstanceBindingError(
                    "endpoint_ambiguous",
                    f"ADB 返回重复的 emulator transport：{serial}。",
                    [],
                )
            if rows[serial] != ["device"]:
                unresolved = True
                continue
            try:
                output = self._command(
                    [profile.adb_path, "-s", serial, "emu", "avd", "name"],
                    deadline,
                    adb=True,
                )
            except InstanceBindingError as exc:
                if exc.code == "manager_timeout":
                    raise
                unresolved = True
                continue
            lines = output.splitlines()
            if (
                len(lines) != 2
                or lines[1].strip() != "OK"
                or not re.fullmatch(AVD_NAME, lines[0])
            ):
                unresolved = True
                continue
            if lines[0] == profile.instance_id:
                matches.append(serial)
        if len(matches) > 1:
            raise InstanceBindingError(
                "endpoint_ambiguous",
                "多个在线 transport 报告相同的 AVD 名称，无法安全选定目标。",
                [],
            )
        if matches:
            if owner is not None:
                self._early_exit(profile, owner)
                if not owner.serial:
                    owner.serial = matches[0]
            return InstanceObservation("running", matches[0])
        if owner is not None:
            self._early_exit(profile, owner)
        return InstanceObservation(
            "starting" if unresolved or owner is not None else "stopped"
        )

    def start(self, profile, timeout):
        raise InstanceBindingError(
            "start_confirmation_required",
            "启动 AVD 前必须由用户确认，请在设备设置中确认启动。",
            [],
        )

    def stop(self, profile, timeout):
        raise InstanceBindingError(
            "avd_restart_unsupported",
            "AVD 不会在恢复或应用退出时自动关闭，请检查所选 AVD 后重试。",
            [],
        )

    def start_confirmed(self, profile, timeout):
        deadline = self.monotonic() + max(timeout, 0)
        key = self._key(profile)
        owner = self._owned.get(key)
        if owner is not None and owner.process.poll() is not None:
            del self._owned[key]
        current = self.inspect(profile, self._remaining(deadline))
        if current.state == "running" and current.serial:
            # A user may have launched the target since opening the confirmation.
            # Observation permits preflight but never grants process ownership.
            return True
        if current.state != "stopped":
            raise InstanceBindingError(
                "avd_already_running",
                "AVD 已在运行或仍有未确认的 emulator transport，请等待并重新检测。",
                [],
            )
        manager = self._manager(profile, profile.preset_id.split(".", 1)[0], deadline)
        if manager != key[0]:
            raise InstanceBindingError(
                "binding_changed",
                "Android Emulator 路径在启动验证期间发生变化，请重新检测。",
                ["manager_path"],
            )
        if profile.instance_id not in self._names(manager, deadline):
            raise InstanceBindingError(
                "instance_missing",
                "已绑定的 AVD 不再存在，请重新检测并选择实例。",
                ["instance_id"],
            )
        self._remaining(deadline)
        try:
            process = self.spawn(
                [key[0], "-avd", profile.instance_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as exc:
            raise InstanceBindingError(
                "avd_start_failed",
                f"无法启动所选 AVD：{exc}。请在 Android Studio 中检查该实例。",
                [],
            ) from exc
        owner = _OwnedAVD(process)
        self._early_exit(profile, owner)
        self._owned[key] = owner
        return True

    def stop_owned(self, profile, timeout):
        """Called only by the explicit task-end setting, never normal close."""
        key = self._key(profile)
        owner = self._owned.get(key)
        if owner is None or owner.process.poll() is not None or not owner.serial:
            return False
        deadline = self.monotonic() + max(timeout, 0)
        observation = self.inspect(profile, self._remaining(deadline))
        if observation.serial != owner.serial or owner.process.poll() is not None:
            return False
        output = self._command(
            [profile.adb_path, "-s", owner.serial, "emu", "kill"], deadline, adb=True
        )
        if output.splitlines() not in (
            ["OK"],
            ["OK: killing emulator, bye bye"],
            ["OK: killing emulator, bye bye", "OK"],
        ):
            raise InstanceBindingError(
                "avd_stop_failed",
                "Android Emulator 未确认关闭所选实例，请手动检查。",
                [],
            )
        del self._owned[key]
        return True
