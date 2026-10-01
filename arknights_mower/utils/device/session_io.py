"""Single-attempt, deadline-bounded I/O for the application device session."""

import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from arknights_mower.utils.device.adb_client.core import is_tcp_serial
from arknights_mower.utils.device.adb_client.server import (
    current_adb_server,
    emulator_connect_target,
    run_adb,
)
from arknights_mower.utils.device.bluestacks_endpoint import BlueStacksEndpointResolver
from arknights_mower.utils.device.endpoint_identity import (
    AVD_PRESETS,
    InstanceBindingError,
)
from arknights_mower.utils.device.genymotion import GenymotionController
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.ldplayer_endpoint import LDPlayerEndpointResolver
from arknights_mower.utils.device.manager_io import run_manager_command
from arknights_mower.utils.device.mumu12ipc.paths import resolve_mumu_paths
from arknights_mower.utils.device.mumu_discovery import (
    parse_mumu_instances,
    run_mumu_command,
)
from arknights_mower.utils.device.mumu_pro import MUMU_PRO_PRESET, MuMuProController
from arknights_mower.utils.device.nox_endpoint import NoxBindingReader
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO
from arknights_mower.utils.device.redroid import REDROID_PRESET, RedroidController
from arknights_mower.utils.device.screenshot import capture_adb_frame
from arknights_mower.utils.device.screenshot_backend import validate_frame
from arknights_mower.utils.device.session import InstanceObservation
from arknights_mower.utils.device.waydroid import WAYDROID_PRESET, WaydroidController
from arknights_mower.utils.path import resolve_config_path

# A polled read-only query is bounded to its own freshness: MuMu's ``info``
# answers the readiness poll, which repeats until the transaction deadline, so
# one slow answer is a wait rather than a reason to hold the whole budget.
QUERY_TIMEOUT = 3


class _CommandWindow:
    def __init__(self, run, monotonic, timeout, command_timeout=None):
        self._run = run
        self._monotonic = monotonic
        self._deadline = monotonic() + max(0, timeout)
        self._command_timeout = command_timeout

    def remaining(self) -> float:
        remaining = self._deadline - self._monotonic()
        if remaining <= 0:
            raise TimeoutError("设备会话操作时间预算已耗尽")
        return remaining

    def run(
        self, argv: list[str], timeout: float | None = None, *, raw_output: bool = False
    ) -> str | bytes:
        """One bounded command; an explicit timeout only tightens this window.

        A polled read-only query passes its own short bound, because an answer
        is only worth acting on while it is fresh. A lifecycle command passes
        none and spends what the session granted: MuMu's own ``launch_player``
        hands the instance to a cold-booting player and outlives a query-sized
        bound, so cutting it off ends a transaction that still has its whole
        budget, its remaining actions and nothing wrong with the device.
        """
        remaining = self.remaining()
        bound = self._command_timeout if timeout is None else timeout
        if bound is not None:
            remaining = min(remaining, bound)
        result = self._run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=remaining,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        result.check_returncode()
        error = result.stderr.decode("utf-8", "replace").strip()
        if re.search(r"\b(error|failed|failure|invalid)\b", error, re.I):
            raise RuntimeError(error)
        if raw_output:
            return result.stdout
        return result.stdout.decode("utf-8", "replace").strip()


class _DeadlinePreflightIO(ProductionPreflightIO):
    """Two bounded channels inside one deadline: vendor managers and pinned ADB.

    ``run_adb`` guards a command as if its binary were ADB, so a vendor manager
    routed through it is rejected while a shared server is running. The manager
    channel therefore keeps its own unguarded bounded runner.
    """

    def __init__(self, window, adb_window=None, read_configuration=None):
        super().__init__(read_configuration or (lambda: None))
        self._window = window
        self._adb_window = adb_window or window

    def _run(self, argv: list[str]) -> bytes:
        return self._window.run(argv).encode("utf-8")

    def _run_adb(self, argv: list[str]) -> bytes:
        return self._adb_window.run(argv).encode("utf-8")


def _read_runtime_configuration():
    from arknights_mower.utils import config

    return config.conf


class _FrameProbeIO(_DeadlinePreflightIO):
    """A missing ADB server ends the first-frame probe instead of raising."""

    def _run_adb(self, argv: list[str]) -> bytes:
        try:
            return super()._run_adb(argv)
        except Exception:
            return b""

    def _capture_droidcast(self, adb_path: str, serial: str) -> np.ndarray:
        from arknights_mower.utils.device.droidcast import DroidCastSession

        capture = DroidCastSession(
            adb_path, serial, rotate=self._read_configuration().droidcast.rotate
        )
        try:
            capture.start(install=True)
            return capture.capture_frame()
        finally:
            capture.close()


class ProductionSessionADB:
    def __init__(
        self,
        *,
        run=None,
        probe=None,
        monotonic=time.monotonic,
        read_configuration=None,
        frame=None,
    ):
        def guarded_run(argv, **kwargs):
            return run_adb(argv, run=run, probe=probe, monotonic=monotonic, **kwargs)

        self._run = guarded_run
        # A vendor manager is not ADB: it must never reach the shared-server guard.
        self._manager_run = run or subprocess.run
        self._monotonic = monotonic
        self._profile = None
        self._read_configuration = read_configuration or _read_runtime_configuration
        # An injected sampler replaces the real decode, so a fake host can stand
        # in for a target whose capture helper is not part of the test.
        self._frame = frame or self._capture_frame

    def bind(self, profile) -> None:
        """Remember the bound selection so the frame probe reads one profile."""
        self._profile = profile.model_copy(deep=True)

    def _adb_window(self, timeout):
        """The pinned transport keeps the shared-server guard."""
        return _CommandWindow(self._run, self._monotonic, timeout)

    def _manager_window(self, timeout):
        """Vendor manager commands use their own bounded, unguarded runner."""
        return _CommandWindow(self._manager_run, self._monotonic, timeout)

    def _preflight_io(self, timeout, *, frame=False):
        factory = _FrameProbeIO if frame else _DeadlinePreflightIO
        return factory(
            self._manager_window(timeout),
            self._adb_window(timeout),
            read_configuration=self._read_configuration,
        )

    def resolve_adb(self, profile, timeout: float) -> str:
        window = self._adb_window(timeout)
        io = self._preflight_io(timeout)
        sources = (
            lambda: [profile.adb_path] if profile.adb_path.strip() else [],
            lambda: io.product_adb_paths(profile),
            io.sdk_adb_paths,
            io.path_adb_paths,
        )
        seen = set()
        for source in sources:
            for candidate in source():
                window.remaining()
                path = io.normalize_adb_path(candidate)
                if path in seen:
                    continue
                seen.add(path)
                try:
                    valid = io.validate_adb(path)
                except (RuntimeError, ValueError):
                    valid = False
                window.remaining()
                if valid:
                    return path
        raise RuntimeError("没有可用的 ADB，请指定有效的 ADB 程序")

    def devices(self, adb_path: str, timeout: float) -> list[tuple[str, str]]:
        output = self._adb_window(timeout).run([adb_path, "devices"])
        if "List of devices attached" not in output:
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

    def boot_completed(self, adb_path: str, serial: str, timeout: float) -> str:
        if not serial.strip():
            raise ValueError("设备 serial 不能为空")
        return self._adb_window(timeout).run(
            [adb_path, "-s", serial, "shell", "getprop", "sys.boot_completed"]
        )

    def display_size(self, adb_path: str, serial: str, timeout: float) -> str:
        if not serial.strip():
            raise ValueError("设备 serial 不能为空")
        return self._adb_window(timeout).run(
            [adb_path, "-s", serial, "shell", "wm", "size"]
        )

    def frame_size(self, adb_path: str, serial: str, timeout: float):
        """One decoded frame through the selected backend, inside one deadline."""
        return self._frame(adb_path, serial, timeout)

    def standard_frame_size(self, adb_path: str, serial: str, timeout: float):
        """Verify the bound endpoint without starting the selected capture helper."""
        window = self._adb_window(timeout)
        with device_io_budget(window.remaining):
            frame = validate_frame(capture_adb_frame(adb_path, serial))
            return frame.shape[1], frame.shape[0]

    def _capture_frame(self, adb_path: str, serial: str, timeout: float):
        if self._profile is None:
            raise RuntimeError("设备实例尚未绑定")
        deadline = time.monotonic() + max(0.0, timeout)
        with device_io_budget(lambda: max(0.0, deadline - time.monotonic())):
            io = self._preflight_io(timeout, frame=True)
            frame = validate_frame(io.capture_frame(adb_path, serial, self._profile))
            return (frame.shape[1], frame.shape[0])

    def recover(self, adb_path: str, serial: str, timeout: float) -> bool:
        if not serial.strip():
            raise ValueError("设备 serial 不能为空")
        window = self._adb_window(timeout)
        if current_adb_server() is not None and (
            endpoint := emulator_connect_target(serial)
        ):
            output = window.run([adb_path, "connect", endpoint])
            console_port, adb_port = endpoint.removeprefix("emu:").split(",")
            return output in {
                f"Connected to emulator on ports {console_port},{adb_port}",
                f"Emulator already registered on port {adb_port}",
            }
        if is_tcp_serial(serial):
            missing = f"error: no such device '{serial}'"
            try:
                disconnected = window.run([adb_path, "disconnect", serial])
            except subprocess.CalledProcessError as exc:
                response = (
                    (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()
                )
                if response != missing:
                    raise
                disconnected = missing
            except RuntimeError as exc:
                if str(exc) != missing:
                    raise
                disconnected = missing
            if disconnected not in {f"disconnected {serial}", missing}:
                return False
            connected = window.run([adb_path, "connect", serial])
            return connected in {
                f"connected to {serial}",
                f"already connected to {serial}",
            }
        output = window.run([adb_path, "-s", serial, "reconnect"])
        return bool(
            re.fullmatch(
                rf"reconnecting(?: {re.escape(serial)}(?: \[(device|offline)\])?)?",
                output,
            )
        )


def _manager_succeeded(output, instance_id):
    if re.search(r"\b(error|failed|failure|invalid|not found)\b", output, re.I):
        return False
    if output.startswith("{"):
        result = json.loads(output)
        if instance_id in result:
            result = result[instance_id]
        if not isinstance(result, dict):
            return False
        for key in ("code", "err_code", "error_code", "result_code"):
            if key in result and result[key] != 0:
                return False
    return True


def _numeric_index(profile):
    if not profile.instance_id.isdecimal():
        raise ValueError("模拟器实例编号必须为非负整数")


def _signed_exit_code(code: int) -> int:
    """A negative vendor code reaches Python as an unsigned 32-bit value."""
    return code - (1 << 32) if code > 0x7FFFFFFF else code


class _InstanceManager:
    def __init__(self, profile, window):
        self.profile = profile
        self.window = window
        manager = self.locate_manager(profile)
        if not manager or not Path(resolve_config_path(manager)).is_file():
            raise ValueError("找不到已绑定实例的管理程序")
        self.manager = str(Path(resolve_config_path(manager)).resolve())

    def command(self, argv, operation):
        """One owned lifecycle command; its exit code is the vendor's verdict.

        A manager rejects an invalid lifecycle request by exiting non-zero
        without stderr. Naming the operation and the signed code keeps that
        failure inside this boundary instead of leaking a subprocess exception.
        """
        try:
            return self.window.run(argv)
        except subprocess.CalledProcessError as exc:
            code = _signed_exit_code(exc.returncode)
            raise RuntimeError(
                f"模拟器{operation}命令被拒绝（退出码 {code}），"
                "请检查模拟器管理器后重试。"
            ) from exc


class _MuMuManager(_InstanceManager):
    def locate_manager(self, profile):
        _numeric_index(profile)
        return resolve_mumu_paths(profile.installation_path, profile.manager_path)[1]

    def act(self, start):
        if not start:
            self.inspect()
        # A lifecycle action, not a query: MuMu hands the instance to a player
        # that is still cold-booting, so the command gets the transaction time.
        output = self.command(
            [
                self.manager,
                "api",
                "-v",
                self.profile.instance_id,
                "launch_player" if start else "shutdown_player",
            ],
            "启动" if start else "关闭",
        )
        return _manager_succeeded(output, self.profile.instance_id)

    def inspect(self):
        profile = self.profile
        query_timeout = getattr(profile, "manager_query_timeout", QUERY_TIMEOUT)
        output = self.window.run(
            [self.manager, "info", "-v", profile.instance_id], timeout=query_timeout
        )
        try:
            instances, _ = parse_mumu_instances(
                output, profile.instance_id, profile.instance_name
            )
        except ValueError as exc:
            if isinstance(exc, InstanceBindingError):
                raise
            # The saved index alone cannot prove this is still the saved instance;
            # a re-created index must send the caller back to detection.
            raise InstanceBindingError(
                "binding_changed",
                f"已绑定的 MuMu 实例无法确认，请重新查找并选择实例：{exc}",
                ["instance_id", "instance_name"],
            ) from exc
        instance = instances[0]
        return InstanceObservation(instance["state"], instance["serial"] or None)


class _LDPlayerManager(_InstanceManager):
    def locate_manager(self, profile):
        from arknights_mower.utils.device.ldplayer_discovery import (
            locate_ldplayer_manager,
        )

        _numeric_index(profile)
        manager, _ = locate_ldplayer_manager(
            profile.manager_path or profile.installation_path
        )
        return str(manager) if manager else ""

    def act(self, start):
        if not start:
            from arknights_mower.utils.device.ldplayer_discovery import (
                parse_ldplayer_instances,
            )

            listing = self.window.run([self.manager, "list2"], raw_output=True)
            try:
                parse_ldplayer_instances(
                    listing, self.profile.instance_id, self.profile.instance_name
                )
            except (ValueError, csv.Error) as exc:
                raise InstanceBindingError(
                    "binding_changed", str(exc), ["instance_id", "instance_name"]
                ) from exc
        output = self.command(
            [
                self.manager,
                "launch" if start else "quit",
                "--index",
                self.profile.instance_id,
            ],
            "启动" if start else "关闭",
        )
        return _manager_succeeded(output, self.profile.instance_id)

    def inspect(self):
        return self.endpoint_resolver.inspect(
            self.profile, self.manager, self.window.remaining()
        )


class _NoxManager(_InstanceManager):
    def locate_manager(self, profile):
        from arknights_mower.utils.device.nox_discovery import locate_nox_manager

        manager, _ = locate_nox_manager(
            profile.manager_path or profile.installation_path
        )
        return str(manager) if manager else ""

    def act(self, start):
        current = self.binding_reader.open(
            self.profile, self.manager, self.window.remaining()
        )
        instance = current.instance()
        if start:
            argv = [self.manager, "launch", f"-name:{instance['instance_name']}"]
        else:
            player = Path(self.manager).parent / "Nox.exe"
            if not player.is_file():
                raise ValueError("夜神安装缺少 Nox.exe，无法关闭已绑定实例。")
            argv = [str(player), f"-clone:{self.profile.instance_id}", "-quit"]
        output = current.command(argv)
        return _manager_succeeded(
            output.decode("utf-8", "replace"), self.profile.instance_id
        )

    def inspect(self):
        return self.binding_reader.inspect(
            self.profile, self.manager, self.window.remaining()
        )


_INSTANCE_MANAGERS = {
    "windows.mumu12": _MuMuManager,
    "windows.ldplayer9": _LDPlayerManager,
    "windows.ldplayer14": _LDPlayerManager,
    "windows.nox": _NoxManager,
}

# Presets whose own multi-instance manager can launch an already bound instance.
MANAGED_INSTANCE_PRESETS = frozenset(_INSTANCE_MANAGERS) | {
    MUMU_PRO_PRESET,
    WAYDROID_PRESET,
}


class ProductionSimulator:
    """Only confirmed manager state authorizes an instance lifecycle action."""

    def __init__(
        self,
        *,
        run=None,
        spawn=None,
        monotonic=time.monotonic,
        probe=None,
        listener_ports=None,
        avd=None,
        waydroid=None,
        redroid=None,
        genymotion=None,
    ):
        self._run = run or subprocess.run
        self._monotonic = monotonic
        self._avd = avd
        self._redroid = redroid or RedroidController(run=run, monotonic=monotonic)
        self._genymotion = genymotion or GenymotionController(
            run=run, monotonic=monotonic
        )
        self._waydroid = waydroid or WaydroidController(
            run=run, spawn=spawn, monotonic=monotonic
        )
        self._ldplayer_resolver = LDPlayerEndpointResolver(
            run=run, probe=probe, monotonic=monotonic, listener_ports=listener_ports
        )
        self._nox_reader = NoxBindingReader(run=run, probe=probe, monotonic=monotonic)
        self._bluestacks_resolver = BlueStacksEndpointResolver(
            run=run, probe=probe, monotonic=monotonic
        )
        self._mumu_pro = MuMuProController(run=self._run, monotonic=monotonic)

    def prepare_mumu_pro(self, profile, timeout=6):
        return self._mumu_pro.prepare_manager(profile, timeout)

    def discover_mumu_pro(self, profile, timeout=6):
        return self._mumu_pro.discover(profile, timeout)

    def _adapter(self, profile, timeout):
        factory = _INSTANCE_MANAGERS.get(profile.preset_id)
        if factory is None:
            return None
        run = self._run
        if factory is _MuMuManager and run is subprocess.run:
            run = run_mumu_command
        if factory is _LDPlayerManager and run is subprocess.run:
            run = run_manager_command
        query_timeout = getattr(profile, "manager_query_timeout", 3.0)
        adapter = factory(
            profile,
            _CommandWindow(
                run,
                self._monotonic,
                timeout,
                command_timeout=query_timeout if factory is _LDPlayerManager else None,
            ),
        )
        if factory is _LDPlayerManager:
            adapter.endpoint_resolver = self._ldplayer_resolver
        if factory is _NoxManager:
            adapter.binding_reader = self._nox_reader
        return adapter

    def start(self, profile, timeout: float) -> bool:
        if profile.preset_id == MUMU_PRO_PRESET:
            started = self._mumu_pro.start(profile, timeout)
        elif profile.preset_id == "linux.genymotion":
            started = self._genymotion.start(profile, timeout)
        elif profile.preset_id == REDROID_PRESET:
            started = self._redroid.start(profile, timeout)
        elif profile.preset_id == WAYDROID_PRESET:
            started = self._waydroid.start(profile, timeout)
        elif profile.preset_id in AVD_PRESETS and self._avd is not None:
            started = self._avd.start(profile, timeout)
        else:
            adapter = self._adapter(profile, timeout)
            started = adapter.act(True) if adapter else False
        if started and getattr(profile, "simulator_hotkey", None):
            from arknights_mower.utils.device.window import trigger_simulator_boss_key

            delay = getattr(profile, "simulator_hotkey_delay", 3.0)
            trigger_simulator_boss_key(profile.simulator_hotkey, delay=delay)
        return started

    def stop(self, profile, timeout: float) -> bool:
        if profile.preset_id == MUMU_PRO_PRESET:
            return self._mumu_pro.stop(profile, timeout)
        if profile.preset_id == "linux.genymotion":
            return self._genymotion.stop(profile, timeout)
        if profile.preset_id == REDROID_PRESET:
            return self._redroid.stop(profile, timeout)
        if profile.preset_id == WAYDROID_PRESET:
            return self._waydroid.stop(profile, timeout)
        if profile.preset_id in AVD_PRESETS and self._avd is not None:
            return self._avd.stop(profile, timeout)
        adapter = self._adapter(profile, timeout)
        return adapter.act(False) if adapter else False

    def inspect(self, profile, timeout: float) -> InstanceObservation:
        if profile.preset_id == MUMU_PRO_PRESET:
            return self._mumu_pro.inspect(profile, timeout)
        if profile.preset_id == "linux.genymotion":
            return self._genymotion.inspect(profile, timeout)
        if profile.preset_id == REDROID_PRESET:
            return self._redroid.inspect(profile, timeout)
        if profile.preset_id == WAYDROID_PRESET:
            return self._waydroid.inspect(profile, timeout)
        if profile.preset_id in AVD_PRESETS and self._avd is not None:
            return self._avd.inspect(profile, timeout)
        if profile.preset_id == "windows.bluestacks5":
            return self._bluestacks_resolver.inspect(profile, timeout)
        adapter = self._adapter(profile, timeout)
        return adapter.inspect() if adapter else InstanceObservation("unknown")
