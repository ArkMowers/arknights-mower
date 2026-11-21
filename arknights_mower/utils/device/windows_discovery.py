"""Finite Windows installation discovery shared by supported vendor adapters."""

import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.manager_io import (
    MAX_INSTANCES,
    MAX_OUTPUT,
    run_manager_command,
)
from arknights_mower.utils.device.preflight import PreflightError

COMMAND_TIMEOUT = 3.0
VENDOR_BUDGET = 6.0

# A quoted command, or a bare executable followed by optional arguments.
UNINSTALL_EXECUTABLE = re.compile(
    r'^"([^"\r\n]+\.exe)"(?:\s+[^\r\n]*)?$|^([^"\r\n]+?\.exe)(?:\s+[^\r\n]*)?$',
    re.IGNORECASE,
)


def uninstall_executable(command):
    """Return the executable path of an UninstallString, or None when unusable.

    Registry command text is never executed, and trailing arguments are never
    treated as installation paths. A relative path is not evidence of a location.
    """
    if not isinstance(command, str) or any(
        character in command for character in "\x00\r\n"
    ):
        return None
    match = UNINSTALL_EXECUTABLE.fullmatch(command.strip())
    if match is None:
        return None
    executable = Path(match[1] or match[2])
    return executable if executable.is_absolute() else None


class RegistryValues:
    """Bounded value access on one opened registry entry."""

    def __init__(self, key, winreg):
        self._key = key
        self._winreg = winreg

    @property
    def handle(self):
        """The opened key, for callers that enumerate subkeys of it."""
        return self._key

    def get(self, name):
        try:
            return self._winreg.QueryValueEx(self._key, name)[0]
        except FileNotFoundError as exc:
            raise KeyError(name) from exc


class WindowsInstallationDiscovery:
    """Vendor subclasses supply known sources, path validation and manager parsing."""

    def __init__(
        self,
        *,
        run=None,
        registry_paths=None,
        process_paths=None,
        fixed_paths=None,
        monotonic=time.monotonic,
        platform=None,
    ):
        self._run = run or run_manager_command
        self._registry_paths = registry_paths or self._read_registry_paths
        self._process_paths = process_paths or self._read_process_paths
        self._fixed_paths = fixed_paths or self._read_fixed_paths
        self._monotonic = monotonic
        self._platform = platform or ("windows" if os.name == "nt" else "other")

    @staticmethod
    def _read_fixed_paths():
        return []

    def _read_process_paths(self, deadline):
        # Names are fixed vendor metadata, never configuration or user input.
        process_filter = " OR ".join(f"Name='{name}'" for name in self.process_names)
        command = (
            "$ErrorActionPreference='Stop'; "
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            f'try {{ Get-CimInstance Win32_Process -Filter "{process_filter}" | '
            "ForEach-Object { if ($_.ExecutablePath) {$_.ExecutablePath} "
            "else {'@@MOWER_PROCESS_PERMISSION@@'} } } catch { "
            "if ($_.CategoryInfo.Category -eq 'PermissionDenied' -or "
            "$_.Exception.HResult -in @(-2147217405,-2147024891)) "
            "{'@@MOWER_PROCESS_PERMISSION@@'} else { throw } }"
        )
        powershell = (
            Path(os.environ.get("SystemRoot", "C:/Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        result = self._command(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
            max(0.001, deadline - self._monotonic()),
        )
        if len(result.stdout) > MAX_OUTPUT:
            raise ValueError("模拟器进程信息超过输出限制。")
        for line in result.stdout.decode("utf-8", "strict").splitlines():
            if line == "@@MOWER_PROCESS_PERMISSION@@":
                yield self._failure(PermissionError("无法读取模拟器进程路径"))
            elif line.strip():
                yield line.strip()

    @staticmethod
    def _iterate_registry_keys(base, names=None, failure=None):
        """Yield each readable registry entry in one fixed hive and view order.

        Only the documented uninstall records are opened; a missing key is not a
        failure, while an unreadable one keeps its repair error. Every supported
        vendor visits the same four combinations in this order. The caller owns
        ``failure`` so a vendor keeps its own repair fields and message.
        """
        import winreg

        if failure is None:
            failure = WindowsInstallationDiscovery._failure

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                paths = (
                    [base] if names is None else [base + "\\" + name for name in names]
                )
                for path in paths:
                    try:
                        with winreg.OpenKey(
                            hive, path, 0, winreg.KEY_READ | view
                        ) as entry:
                            yield RegistryValues(entry, winreg)
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        yield failure(exc)

    def _command(self, argv, timeout):
        completed = self._run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=min(COMMAND_TIMEOUT, timeout),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        completed.check_returncode()
        return completed

    def discover(self, profile):
        result = {"installations": [], "errors": []}
        if self._platform != "windows":
            return result
        deadline = self._monotonic() + VENDOR_BUDGET
        candidates = [
            path for path in (profile.manager_path, profile.installation_path) if path
        ]
        errors = []
        for source in (self._registry_paths, self._fixed_paths, self._process_paths):
            try:
                if self._monotonic() >= deadline:
                    raise TimeoutError
                values = (
                    source(deadline) if source == self._read_process_paths else source()
                )
                for value in values:
                    if self._monotonic() >= deadline:
                        raise TimeoutError
                    if isinstance(value, PreflightError):
                        errors.append(value)
                    else:
                        candidates.append(value)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(self._failure(exc))
        seen = set()
        count = 0
        for candidate in candidates:
            try:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise TimeoutError
                manager, root = self._manager_candidate(candidate)
                if manager is None:
                    continue
                identity = str(root).replace("\\", "/").casefold()
                if identity in seen:
                    continue
                seen.add(identity)
                instances, parse_errors = self._instances(manager, min(3, remaining))
                if self._monotonic() > deadline:
                    raise TimeoutError
                errors.extend(parse_errors)
                if count + len(instances) > MAX_INSTANCES:
                    errors.append(
                        PreflightError(
                            "discovery_limit", "本次每个产品最多保留 64 个实例。"
                        )
                    )
                instances = instances[: MAX_INSTANCES - count]
                count += len(instances)
                result["installations"].append(
                    {
                        "preset_id": self._preset_for(root),
                        "installation_path": str(root),
                        "manager_path": str(manager),
                        "instances": instances,
                    }
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(self._failure(exc))
                if deadline <= self._monotonic():
                    break
        result["errors"] = errors
        return result

    def _preset_for(self, root):
        return self.preset_id

    @classmethod
    def _product_name(cls):
        # A product without a manager command reports its own category instead.
        name = getattr(cls, "product", "")
        return name if isinstance(name, str) else ""

    @classmethod
    def _failure(cls, exc):
        if isinstance(exc, InstanceBindingError):
            # A verified source already named the exact repair field and code.
            return PreflightError(exc.code, str(exc), fields=exc.fields)
        name = cls._product_name()
        if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
            return PreflightError(
                "discovery_timeout",
                f"{name} 检测超时，请检查管理器后重试。"
                if name
                else f"检测超时，请检查管理器后重试：{exc}",
                fields=["manager_path"],
            )
        if isinstance(exc, PermissionError):
            return PreflightError(
                "discovery_permission",
                f"无法读取部分 {name} 安装信息，请检查路径访问权限。"
                if name
                else f"无法读取部分安装信息，请检查路径访问权限：{exc}",
                fields=["installation_path"]
                if name
                else ["installation_path", "config_path"],
            )
        return PreflightError(
            "manager_output",
            f"无法读取 {name} 实例：{exc}"
            if name
            else f"无法读取已注册的产品信息：{exc}",
            fields=["manager_path"] if name else ["config_path"],
        )


class WindowsDiscoveryIO:
    def __init__(self, vendors=None):
        if vendors is None:
            from arknights_mower.utils.device.bluestacks_discovery import (
                BlueStacksDiscoveryIO,
            )
            from arknights_mower.utils.device.ldplayer_discovery import (
                LDPlayerDiscoveryIO,
            )
            from arknights_mower.utils.device.mumu_discovery import MuMuDiscoveryIO
            from arknights_mower.utils.device.nox_discovery import NoxDiscoveryIO

            vendors = (
                MuMuDiscoveryIO(),
                LDPlayerDiscoveryIO(),
                NoxDiscoveryIO(),
                BlueStacksDiscoveryIO(),
            )
        self._vendors = vendors

    def discover(self, profile):
        result = {"installations": [], "errors": []}
        # Each vendor owns the same six-second budget; run them concurrently so
        # adding a second supported product does not double the discovery wait.
        with ThreadPoolExecutor(max_workers=len(self._vendors)) as executor:
            observations = executor.map(
                lambda vendor: self._vendor_result(vendor, profile), self._vendors
            )
            for observation in observations:
                result["installations"].extend(observation["installations"])
                result["errors"].extend(observation["errors"])
        return result

    @staticmethod
    def _vendor_result(vendor, profile):
        """One vendor's failure stays its own; the sweep still returns the rest.

        An unexpected error must become a structured repair entry instead of
        propagating out of the thread and failing the whole detection request.
        """
        try:
            return vendor.discover(profile)
        except Exception as exc:
            name = getattr(vendor, "product", vendor.__class__.__name__)
            return {
                "installations": [],
                "errors": [
                    PreflightError(
                        "discovery_failed",
                        f"{name} 检测失败：{exc}",
                        fields=["manager_path"],
                    )
                ],
            }
