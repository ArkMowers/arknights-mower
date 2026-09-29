"""Application boundary for one explicitly bound device session.

Configuration stays in Conf. Adapters own device I/O; this boundary owns the
session and exposes outcomes without requiring callers to inspect log messages.
"""

import os
import subprocess
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from threading import Event, Lock, RLock
from typing import TYPE_CHECKING, Generic, Literal, Protocol, TypeVar, cast

import numpy as np

from arknights_mower import __system__
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.discovery import DiscoveryResult, DiscoveryService
from arknights_mower.utils.device.endpoint_identity import (
    AVD_PRESETS,
    InstanceBindingError,
)
from arknights_mower.utils.device.genymotion import genymotion_repair
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.preparation import (
    PreparationError,
    PreparationSession,
)
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.redroid import redroid_repair
from arknights_mower.utils.device.screenshot_backend import (
    ScreenshotFailure,
    ScreenshotSession,
    validate_frame,
)
from arknights_mower.utils.device.session import (
    DeviceSession,
    ReadinessResult,
    SessionFailure,
)
from arknights_mower.utils.device.touch_backend import TouchFailure, touch_backends
from arknights_mower.utils.log import logger

if TYPE_CHECKING:
    from arknights_mower.utils.config.conf import Conf
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.device.preflight import (
        PreflightError,
        PreflightResult,
        PreflightService,
    )


class DeviceConfiguration(Protocol):
    adb: str


class DeviceHandle(Protocol):
    device_id: str
    session_control: "DeviceControl | None"

    def close(self) -> None: ...
    def capture_frame(self) -> np.ndarray: ...
    def standard_frame(self) -> np.ndarray: ...
    def rebuild_screenshot(self) -> None: ...


D = TypeVar("D", bound=DeviceHandle)
T = TypeVar("T")
SessionState = Literal["idle", "starting", "connected", "failed", "cancelled", "closed"]
# Upper bound for the single release attempt taken once the gate is closed for
# good; process exit must not wait on a worker that still owns the lock.
_FINAL_RELEASE_TIMEOUT = 1.0


class DeviceAdapter(Protocol[D]):
    def open(
        self, configuration: DeviceConfiguration, *, connection_retries: int
    ) -> D: ...

    def open_verified(
        self, configuration: DeviceConfiguration, result: "PreflightResult"
    ) -> D: ...

    def rebind(self, device: D, result: "PreflightResult") -> None: ...


class LegacyDeviceAdapter:
    """Retain the existing Device, screenshot, input and connection behavior."""

    def open(
        self, configuration: DeviceConfiguration, *, connection_retries: int
    ) -> "Device":
        from arknights_mower.utils.device.device import Device

        # Legacy Device still reads the authoritative Conf itself. In particular,
        # leave device_id unset so its existing endpoint discovery also runs on
        # a one-attempt startup. The adapter contract is shared with test devices.
        return Device.create(connection_retries=connection_retries)

    def open_verified(
        self, configuration: DeviceConfiguration, result: "PreflightResult"
    ) -> "Device":
        from arknights_mower.utils.device.device import Device

        return Device(
            device_id=result.serial,
            adb_bin=result.adb_path,
            profile=configuration.device,
            strict_target=True,
            wait_for_device=False,
        )

    def rebind(self, device: "Device", result: "PreflightResult") -> None:
        device.rebind_target(
            result.serial, result.adb_path, game_package=result.game_package
        )


class PreflightRejected(MowerExit):
    """Stop the legacy worker without entering its simulator recovery loop."""

    def __init__(self, message: str, code: str = "preflight_failed"):
        super().__init__(message)
        self.code = code


def _is_device_verdict(error: BaseException) -> bool:
    """A classified device verdict is reported instead of ending the process.

    A readiness, preflight, preparation, capture or input failure carries a code
    naming the device condition the user has to change. Requesting application
    shutdown for it would turn a fixable setting into an exit, so only
    unclassified internal faults still do that.
    """
    return isinstance(
        error,
        (
            SessionFailure,
            PreflightRejected,
            PreparationError,
            ScreenshotFailure,
            TouchFailure,
        ),
    )


def prepare_droidcast_capture(adb_path, serial, profile):
    """Install the selected capture helper only for a validated runtime start."""
    from arknights_mower.utils.device.droidcast import DroidCastSession

    DroidCastSession(adb_path, serial).ensure_version(install=True)


def create_device_control() -> "DeviceControl[Device]":
    from arknights_mower.utils import config
    from arknights_mower.utils.device.avd import AVDController
    from arknights_mower.utils.device.genymotion import GenymotionController
    from arknights_mower.utils.device.preflight import PreflightService
    from arknights_mower.utils.device.preflight_io import ProductionPreflightIO
    from arknights_mower.utils.device.preparation_io import ProductionPreparationIO
    from arknights_mower.utils.device.preparation_store import (
        RecoveryStore,
        SerialLocks,
        preparation_root,
    )
    from arknights_mower.utils.device.redroid import RedroidController
    from arknights_mower.utils.device.session_io import (
        ProductionSessionADB,
        ProductionSimulator,
    )
    from arknights_mower.utils.device.waydroid import WaydroidController
    from arknights_mower.utils.device.windows_discovery import WindowsDiscoveryIO
    from arknights_mower.utils.lifecycle import shutdown

    if os.environ.get("MOWER_ANDROID") == "1":
        # Android's background display service owns its capture and transport.
        return DeviceControl(
            lambda: config.conf, LegacyDeviceAdapter(), on_fatal=shutdown.request
        )
    avd = AVDController()
    waydroid = WaydroidController()
    redroid = RedroidController()
    genymotion = GenymotionController()
    simulator = ProductionSimulator(
        avd=avd, waydroid=waydroid, redroid=redroid, genymotion=genymotion
    )
    return DeviceControl(
        lambda: config.conf,
        LegacyDeviceAdapter(),
        on_fatal=shutdown.request,
        preflight=PreflightService(ProductionPreflightIO(lambda: config.conf)),
        prepare_capture=prepare_droidcast_capture,
        session=DeviceSession(ProductionSessionADB(), simulator),
        discovery=DiscoveryService(
            WindowsDiscoveryIO(),
            simulator,
            avd=avd,
            waydroid=waydroid,
            redroid=redroid,
            genymotion=genymotion,
        ),
        avd=avd,
        redroid=redroid,
        genymotion=genymotion,
        preparation=PreparationSession(
            ProductionPreparationIO(),
            RecoveryStore(preparation_root()),
            SerialLocks(preparation_root()),
        ),
    )


@dataclass(frozen=True)
class DeviceError:
    code: str
    message: str
    cause: Exception = field(repr=False, compare=False)


@dataclass(frozen=True)
class DeviceResult(Generic[T]):
    ok: bool
    status: SessionState
    serial: str
    value: T | None = None
    error: DeviceError | None = None
    readiness: ReadinessResult | None = None

    def unwrap(self) -> T:
        """Compatibility boundary for callers using the existing exceptions."""
        if self.error is not None:
            raise self.error.cause
        return cast(T, self.value)


class DeviceControl(Generic[D]):
    def __init__(
        self,
        read_configuration: Callable[[], DeviceConfiguration],
        adapter: DeviceAdapter[D],
        *,
        preflight: "PreflightService | None" = None,
        session: DeviceSession | None = None,
        preparation: PreparationSession | None = None,
        discovery: DiscoveryService | None = None,
        avd=None,
        redroid=None,
        genymotion=None,
        prepare_capture: Callable | None = None,
        on_fatal: Callable[[str], None] | None = None,
    ):
        self._on_fatal = on_fatal
        self._fatal_notified = False
        self._read_configuration = read_configuration
        self._adapter = adapter
        self._preflight = preflight
        self._prepare_capture = prepare_capture
        self._session = session
        self._preparation = preparation
        self._discovery = discovery
        self._avd = avd
        self._redroid = redroid
        self._genymotion = genymotion
        self._run_authorization: str | None = None
        self._run_active = False
        self._session_error: Exception | None = None
        self._last_error: dict | None = None
        self._screenshot: ScreenshotSession | None = None
        self._executing = False
        self._last_preflight: PreflightResult | None = None
        self._device: D | None = None
        self._serial = ""
        self._state: SessionState = "idle"
        self._close_result: DeviceResult[None] | None = None
        self._helper_cleanup_error: Exception | None = None
        self._close_guard = Lock()
        self._closing_count = 0
        self._shutdown = Event()
        self._pending_close = Event()
        self._deferred_close = False
        self._interrupted_device = None
        # Configuration writes and session transitions share this lock. The
        # server takes it after its configuration/backup lock, never before.
        self.configuration_lock = RLock()

    @contextmanager
    def _configuration(self):
        self.configuration_lock.acquire()
        try:
            yield
        finally:
            # Pair release with the timeout handoff: either the closing caller
            # acquires the lock, or this operation owns the deferred cleanup.
            with self._close_guard:
                deferred = self._deferred_close
                if not deferred:
                    self.configuration_lock.release()
            if deferred:
                try:
                    self._close()
                finally:
                    self.configuration_lock.release()

    @property
    def active(self) -> bool:
        return self._device is not None or self._state == "starting"

    def configuration_changes_target(self, proposed) -> bool:
        current = self._read_configuration()
        return current.device.model_dump(
            exclude={"game_package_confirmed"}
        ) != proposed.device.model_dump(exclude={"game_package_confirmed"}) or any(
            getattr(current, field) != getattr(proposed, field)
            for field in ("droidcast", "custom_screenshot")
        )

    def status(self) -> DeviceResult[None]:
        return DeviceResult(True, self._state, self.serial, readiness=self._readiness)

    @property
    def _readiness(self) -> ReadinessResult | None:
        return self._session.last if self._session else None

    @property
    def executing(self) -> bool:
        return self._executing

    @property
    def run_active(self) -> bool:
        return self._run_active

    def readiness(self) -> ReadinessResult:
        with self._configuration():
            if self._session is None:
                raise RuntimeError("未配置设备会话适配器")
            if not self.active:
                self._session.bind(self._read_configuration().device)
            return self._session.observe()

    def settings_status(self) -> dict:
        from arknights_mower.utils.device.session_io import MANAGED_INSTANCE_PRESETS

        status = {
            "host_platform": (
                self._preflight.host_platform()
                if self._preflight is not None
                else "macos"
                if __system__ == "darwin"
                else __system__
            ),
            "active": self.active,
            "status": self._state,
            "serial": self.serial,
            "readiness": asdict(self._readiness) if self._readiness else None,
            "preparation": self._preparation.status() if self._preparation else None,
            "error": self._last_error,
            "preflight": (
                self._last_preflight.to_dict() if self._last_preflight else None
            ),
            # The settings UI offers its start action from this list, so the set of
            # presets that can launch a bound instance has one home.
            "managed_instance_presets": sorted(MANAGED_INSTANCE_PRESETS),
        }
        profile = getattr(self._read_configuration(), "device", None)
        if profile is not None:
            status["touch_backends"] = touch_backends(profile, status["host_platform"])
            status["touch_backend_profile"] = profile.preset_id
            # A degraded capture backend stays visible for the rest of the
            # session instead of silently replacing the selected one.
            status["screenshot_backend"] = {
                "selected": profile.screenshot_backend,
                "effective": (
                    self._screenshot.backend
                    if self._screenshot is not None
                    else profile.screenshot_backend
                ),
                "degraded": bool(self._screenshot and self._screenshot.degraded),
            }
        return status

    def preflight(
        self,
        configuration: "Conf | None" = None,
        *,
        confirmed_package: str | None = None,
    ) -> "PreflightResult":
        from arknights_mower.utils.device.preflight import (
            PreflightError,
            PreflightResult,
        )

        with self._configuration():
            if self.active:
                return PreflightResult(
                    False,
                    self.settings_status()["host_platform"],
                    "connected",
                    self.serial,
                    error=PreflightError(
                        "device_session_active",
                        "请停止当前任务后重新检测设备。",
                        "stop",
                        [],
                    ),
                )
            if self._preflight is None:
                raise RuntimeError("未配置设备检测适配器")
            configuration = configuration or self._read_configuration()
            if (
                configuration.device.preset_id == "macos.mumu_pro"
                and configuration.device.topology_fingerprint
                and self._discovery is None
            ):
                self._last_preflight = PreflightResult(
                    False,
                    self._preflight.host_platform(),
                    "failed",
                    "",
                    error=PreflightError(
                        "binding_failed",
                        "缺少 MuMu Pro 实例核验器，请重新检测实例。",
                        fields=["instance_id"],
                    ),
                )
                return self._last_preflight
            if self._discovery is not None and configuration.device.preset_id in {
                "windows.mumu12",
                "windows.ldplayer9",
                "windows.ldplayer14",
                "windows.nox",
                "windows.bluestacks5",
                "macos.bluestacks_air",
                "macos.mumu_pro",
                "linux.waydroid",
                "linux.redroid",
                "linux.genymotion",
                *AVD_PRESETS,
            }:
                self._last_preflight = self._discovery.check_binding(
                    configuration.device,
                    self._preflight,
                    confirmed_package=confirmed_package,
                )
            else:
                self._last_preflight = self._preflight.check(
                    configuration.device, confirmed_package=confirmed_package
                )
            return self._last_preflight

    def prepare_mumu_pro_manager(self, configuration: "Conf") -> "PreflightResult":
        """Explicit detection action; the read-only routes never call it implicitly."""
        from arknights_mower.utils.device.preflight import (
            PreflightError,
            PreflightResult,
        )
        from arknights_mower.utils.device.session_io import ProductionSimulator

        with self._configuration():
            host = self.settings_status()["host_platform"]
            result = PreflightResult(False, host, "failed", "")
            if self._shutdown.is_set() or self._pending_close.is_set():
                result.error = PreflightError("session_closing", "设备会话正在关闭")
            elif self.active or self._run_active:
                result.error = PreflightError(
                    "device_session_active", "请停止当前任务后检测实例。", "stop"
                )
            elif host != "macos" or configuration.device.preset_id != "macos.mumu_pro":
                result.error = PreflightError(
                    "start_unsupported",
                    "此管理服务启动操作仅支持 macOS MuMu Pro。",
                    fields=["preset_id"],
                )
            else:
                try:
                    simulator = (
                        self._session.simulator
                        if self._session
                        else ProductionSimulator()
                    )
                    simulator.prepare_mumu_pro(configuration.device, 6)
                    result.ok = True
                except MowerExit:
                    raise
                except Exception as exc:
                    result.error = self._launch_error("mumu_pro", exc)
            return result

    def discover(
        self, configuration: "Conf | None" = None
    ) -> "DiscoveryResult | PreflightResult":
        from arknights_mower.utils.device.preflight import PreflightError

        with self._configuration():
            host = self.settings_status()["host_platform"]
            if self.active:
                return DiscoveryResult(
                    host,
                    error=PreflightError(
                        "device_session_active",
                        "请停止当前任务后重新检测设备。",
                        "stop",
                    ),
                )
            if self._discovery is None:
                raise RuntimeError("未配置设备发现适配器")
            configuration = configuration or self._read_configuration()
            return self._discovery.discover(configuration.device, host, self._preflight)

    def start_avd(
        self,
        configuration: "Conf | None" = None,
        *,
        confirmed_instance: str | None = None,
        confirmed_package: str | None = None,
    ) -> "PreflightResult":
        return self._start_confirmed(
            "avd",
            self._avd,
            AVD_PRESETS,
            configuration,
            confirmed_instance=confirmed_instance,
            confirmed_package=confirmed_package,
        )

    def start_redroid(
        self,
        configuration: "Conf | None" = None,
        *,
        confirmed_instance: str | None = None,
        confirmed_package: str | None = None,
    ) -> "PreflightResult":
        return self._start_confirmed(
            "redroid",
            self._redroid,
            {"linux.redroid"},
            configuration,
            confirmed_instance=confirmed_instance,
            confirmed_package=confirmed_package,
        )

    def start_genymotion(
        self,
        configuration: "Conf | None" = None,
        *,
        confirmed_instance: str | None = None,
        confirmed_package: str | None = None,
    ) -> "PreflightResult":
        return self._start_confirmed(
            "genymotion",
            self._genymotion,
            {"linux.genymotion"},
            configuration,
            confirmed_instance=confirmed_instance,
            confirmed_package=confirmed_package,
        )

    def start_bound(
        self,
        configuration: "Conf | None" = None,
        *,
        confirmed_package: str | None = None,
    ) -> "PreflightResult":
        """Launch the bound instance through its own manager, then verify it.

        The session starts a stopped instance on its way to readiness, so this
        action runs exactly the path a scheduled start runs: the preset's own
        manager command, the session's single bulk budget, and the same identity
        check afterwards. Nothing here is persisted; the caller saves the
        verified endpoint through /conf.
        """
        from arknights_mower.utils.device.preflight import (
            PreflightError,
            PreflightResult,
        )
        from arknights_mower.utils.device.session_io import MANAGED_INSTANCE_PRESETS

        if self._shutdown.is_set() or self._pending_close.is_set():
            # Reject before the configuration lock: a closing process must not wait
            # on a lock that the close path itself may hold.
            return PreflightResult(
                False,
                "",
                "failed",
                self.serial,
                error=PreflightError("session_closing", "设备会话正在关闭"),
            )
        with self._configuration():
            host = self.settings_status()["host_platform"]
            configuration = configuration or self._read_configuration()
            profile = configuration.device
            result = PreflightResult(False, host, "failed", profile.last_serial.strip())
            if self._shutdown.is_set() or self._pending_close.is_set():
                result.error = PreflightError("session_closing", "设备会话正在关闭")
            elif self.active or self._run_active:
                result.error = PreflightError(
                    "device_session_active", "请停止当前任务后启动实例。", "stop"
                )
            elif (
                profile.preset_id not in MANAGED_INSTANCE_PRESETS
                or not profile.preset_id.startswith(f"{host}.")
            ):
                result.error = PreflightError(
                    "start_unsupported",
                    "该预设没有可供 mower 使用的多开管理器，请在模拟器中手动启动后重新测试连接。",
                    fields=["preset_id"],
                )
            elif (
                profile.preset_id == "macos.mumu_pro"
                and not profile.topology_fingerprint
            ):
                result.error = PreflightError(
                    "mumu_pro_selection_required",
                    "请先检测并选择 MuMu Pro 实例，再启动该实例。",
                    fields=["instance_id", "topology_fingerprint"],
                )
            elif self._session is None or self._preflight is None:
                result.error = PreflightError(
                    "start_unavailable", "未配置实例启动适配器。"
                )
            else:
                try:
                    result = self._launch_and_verify(
                        profile,
                        product="instance",
                        launch=None,
                        confirmed_package=confirmed_package,
                        startup_wait=getattr(
                            getattr(configuration, "simulator", None), "wait_time", 30
                        ),
                    )
                except MowerExit:
                    raise
                except Exception as exc:
                    result.error = self._launch_error("instance", exc)
            self._last_preflight = result
            return result

    def _launch_and_verify(
        self,
        profile,
        *,
        product: str,
        launch,
        confirmed_package: str | None,
        startup_wait: float = 30.0,
    ) -> "PreflightResult":
        """The bounded launch-and-verify body every start action shares.

        ``launch`` is the product's own controller step. A preset whose manager the
        session drives passes ``None``, because the session starts its own stopped
        instance on the way to readiness. One monotonic budget covers the whole
        transaction, and only the manager's own report may name the endpoint.
        """
        self._session.bind(profile, startup_wait=startup_wait)
        clock = self._session.clock
        deadline = clock.monotonic() + self._session.policy.timeout

        def remaining():
            if self._shutdown.is_set() or self._pending_close.is_set():
                raise MowerExit("设备会话正在关闭")
            timeout = deadline - clock.monotonic()
            if timeout <= 0:
                raise TimeoutError("实例启动与检测时间预算已耗尽，请检查实例后重试。")
            return timeout

        with device_io_budget(remaining):
            try:
                adb_path = self._preflight.resolve_adb(profile)
            except ValueError as exc:
                raise InstanceBindingError(
                    "missing_adb", str(exc), ["adb_path"]
                ) from exc
            profile = profile.model_copy(update={"adb_path": adb_path})
            if launch is not None and not launch(profile, remaining()):
                raise InstanceBindingError(
                    f"{product}_start_failed",
                    "实例启动未成功，请检查该实例后重试。",
                    [],
                )
            self._session.bind(
                profile, resolved_adb=adb_path, startup_wait=startup_wait
            )
            ready = self._session.ensure_ready(deadline=deadline)
            verified = profile.model_copy(update={"last_serial": ready.serial})
            return self._preflight.check(
                verified,
                confirmed_package=confirmed_package,
                resolved_adb=adb_path,
                prepare_capture=self._prepare_capture,
            )

    @staticmethod
    def _launch_error(product: str, exc: Exception) -> "PreflightError":
        """Map one launch failure onto the structured device error."""
        from arknights_mower.utils.device.preflight import PreflightError

        if isinstance(exc, InstanceBindingError):
            if product == "redroid":
                return redroid_repair(exc)
            if product == "genymotion":
                return genymotion_repair(exc)
            return PreflightError(exc.code, str(exc), fields=exc.fields)
        if isinstance(exc, SharedADBError):
            return PreflightError(
                "adb_server_unavailable", str(exc), fields=["adb_path"]
            )
        if isinstance(exc, SessionFailure):
            code = exc.observation.code or f"{product}_start_failed"
            if product == "redroid":
                return redroid_repair(InstanceBindingError(code, str(exc), []))
            if product == "genymotion" and code.startswith(
                ("genymotion_", "manager_", "discovery_")
            ):
                return genymotion_repair(InstanceBindingError(code, str(exc), []))
            return PreflightError(code, str(exc))
        if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
            return PreflightError(f"{product}_start_timeout", str(exc))
        return PreflightError(f"{product}_start_failed", str(exc))

    def _start_confirmed(
        self,
        product,
        controller,
        presets,
        configuration,
        *,
        confirmed_instance,
        confirmed_package,
    ) -> "PreflightResult":
        """One explicit launch consent; never stored or reused by scheduled starts."""
        from arknights_mower.utils.device.preflight import (
            PreflightError,
            PreflightResult,
        )

        if self._shutdown.is_set() or self._pending_close.is_set():
            return PreflightResult(
                False,
                "",
                "failed",
                self.serial,
                error=PreflightError("session_closing", "设备会话正在关闭"),
            )
        with self._configuration():
            host = self.settings_status()["host_platform"]
            profile = (configuration or self._read_configuration()).device
            result = PreflightResult(False, host, "failed", "")
            if self._shutdown.is_set() or self._pending_close.is_set():
                result.error = PreflightError("session_closing", "设备会话正在关闭")
            elif self.active or self._run_active:
                result.error = PreflightError(
                    "device_session_active", "请停止当前任务后启动实例。", "stop"
                )
            elif (
                profile.preset_id not in presets
                or profile.preset_id != f"{host}.{product}"
            ):
                result.error = PreflightError(
                    "unsupported_host",
                    "实例启动仅支持对应的本机环境预设。",
                    fields=["preset_id"],
                )
            elif not confirmed_instance or confirmed_instance != profile.instance_id:
                result.error = PreflightError(
                    "start_confirmation_required",
                    "启动前请确认已选择的实例。",
                    "confirm",
                )
            elif controller is None or self._session is None or self._preflight is None:
                result.error = PreflightError(
                    f"{product}_unavailable", "未配置实例启动适配器。"
                )
            else:
                try:
                    result = self._launch_and_verify(
                        profile,
                        product=product,
                        launch=lambda bound, timeout: controller.start_confirmed(
                            bound, timeout
                        ),
                        confirmed_package=confirmed_package,
                    )
                except MowerExit:
                    raise
                except Exception as exc:
                    result.error = self._launch_error(product, exc)
            self._last_preflight = result
            return result

    def stop_bound_mumu_pro(self) -> bool:
        """Apply explicit idle shutdown to the verified selected MuMu Pro instance."""
        if self._shutdown.is_set() or self._pending_close.is_set():
            return False
        with self._configuration():
            conf = self._read_configuration()
            if (
                not conf.close_simulator_when_idle
                or conf.device.preset_id != "macos.mumu_pro"
                or not conf.device.topology_fingerprint
                or self._session is None
                or self._shutdown.is_set()
                or self._pending_close.is_set()
            ):
                return False
            return self._session.simulator.stop(conf.device, 10)

    def stop_owned_avd(self) -> bool:
        """Explicit task-end policy, separate from ordinary application close."""
        if self._shutdown.is_set():
            return False
        with self._configuration():
            conf = self._read_configuration()
            if (
                self._shutdown.is_set()
                or not conf.close_simulator_when_idle
                or conf.device.preset_id not in AVD_PRESETS
                or self._avd is None
            ):
                return False
            return self._avd.stop_owned(conf.device, 10)

    @property
    def serial(self) -> str:
        return self._device.device_id if self._device is not None else self._serial

    @contextmanager
    def run(self, *, preparation_serial: str | None = None):
        """Own authorization and cleanup for one whole scheduling run."""
        if self._shutdown.is_set() or self._pending_close.is_set():
            self._closing_failure().unwrap()
        if self.active:
            self.close().unwrap()
        else:
            # A previous offline close is retried by begin's compensation,
            # rather than treating its cached result as a permanent failure.
            self.close()
        self._run_active = True
        self._run_authorization = preparation_serial
        try:
            yield
        finally:
            self._run_authorization = None
            if not self.shutdown_requested:
                self.close()
            self._run_active = False

    def start(
        self, *, connection_retries: int = 3, preparation_serial: str | None = None
    ) -> DeviceResult[D]:
        if self._shutdown.is_set() or self._pending_close.is_set():
            return self._closing_failure()
        with self._configuration():
            authorization = preparation_serial or self._run_authorization
            self._run_authorization = None
            return self._start(
                connection_retries=connection_retries, preparation_serial=authorization
            )

    def _start(
        self, *, connection_retries: int, preparation_serial: str | None = None
    ) -> DeviceResult[D]:
        if (
            self._shutdown.is_set()
            or self._pending_close.is_set()
            or self._closing_count
        ):
            return self._closing_failure()
        if self._helper_cleanup_error is not None:
            return self._failure("close_failed", self._helper_cleanup_error)
        if self._session_error is not None:
            return self._failure("session_failed", self._session_error)
        if self._device is not None:
            return DeviceResult(True, self._state, self.serial, self._device)
        self._close_result = None
        self._last_error = None
        self._last_preflight = None
        self._serial = ""
        try:
            configuration = self._read_configuration()
            self._serial = configuration.adb
        except Exception as exc:
            self._close_failure(exc, "device_start_failed")
            self._state = "failed"
            return self._failure("configuration_failed", exc)
        try:
            profile = getattr(configuration, "device", None)
            if preparation_serial is not None and (
                self._preparation is None
                or profile.preset_id != "manual.physical"
                or preparation_serial != profile.last_serial.strip()
            ):
                raise PreparationError(
                    "preparation_not_authorized",
                    "本次临时整备授权与所选实体设备不一致。",
                )
            if self._session is not None:
                self._state = "starting"
                self._session.bind(
                    profile,
                    startup_wait=getattr(
                        getattr(configuration, "simulator", None), "wait_time", 30
                    ),
                )
                deadline = self._session.begin_budget()
            if self._preparation is not None:
                with self._io_budget():
                    try:
                        if self._session is not None:
                            resolved_adb = self._session.resolve_adb(deadline)
                        elif self._preflight is not None:
                            resolved_adb = self._preflight.resolve_adb(profile)
                        else:
                            resolved_adb = profile.adb_path
                    except (MowerExit, SessionFailure):
                        raise
                    except SharedADBError as exc:
                        raise PreflightRejected(
                            str(exc), "adb_server_unavailable"
                        ) from exc
                    except Exception as exc:
                        raise PreflightRejected(str(exc), "missing_adb") from exc
                    profile = profile.model_copy(update={"adb_path": resolved_adb})
                    self._preparation.begin(profile, preparation_serial)
            if self._session is not None:
                ready = self._session.ensure_ready(deadline=deadline)
                self._serial = ready.serial
                profile = profile.model_copy(
                    update={"last_serial": ready.serial, "adb_path": ready.adb_path}
                )
            if self._preflight is not None:
                self._state = "starting"
                with self._io_budget():
                    result = self._check_profile(profile)
                self._last_preflight = result
                if not result.ok:
                    raise PreflightRejected(result.error.message, result.error.code)
                # Verified runtime selections belong to this device's copy.
                runtime_configuration = configuration.model_copy(deep=True)
                runtime_configuration.device = profile.model_copy(
                    update={
                        "game_package": result.game_package,
                        "last_serial": result.serial,
                        "adb_path": result.adb_path,
                    }
                )
                runtime_configuration.sync_legacy_device_fields()
                if (
                    self._shutdown.is_set()
                    or self._pending_close.is_set()
                    or self._closing_count
                ):
                    raise MowerExit("设备会话正在关闭")
                with self._io_budget():
                    self._device = self._adapter.open_verified(
                        runtime_configuration, result
                    )
                    if self._preparation is not None:
                        self._preparation.validate()
            else:
                with self._io_budget():
                    self._device = self._adapter.open(
                        configuration, connection_retries=connection_retries
                    )
            if self._shutdown.is_set() or self._pending_close.is_set():
                raise MowerExit("设备会话正在关闭")
        except BaseException as exc:
            self._close_failure(exc, "device_start_failed")
            if not isinstance(exc, Exception):
                raise
            self._state = (
                "cancelled"
                if isinstance(exc, MowerExit)
                and not isinstance(exc, (PreflightRejected, PreparationError))
                else "failed"
            )
            if self._session is not None or isinstance(exc, TouchFailure):
                self._session_error = exc
            return self._failure("start_failed", exc)
        if self._session is not None:
            self._device.session_control = self
        self._serial = self._device.device_id
        self._state = "connected"
        return DeviceResult(
            True, self._state, self.serial, self._device, readiness=self._readiness
        )

    def _check_profile(self, profile):
        capture_options = {}
        if (
            profile.screenshot_backend == "droidcast"
            and self._prepare_capture is not None
        ):
            capture_options["prepare_capture"] = self._prepare_capture
        # The bound session already resolved and validated its ADB executable.
        # Reuse it for every preset so capture and preflight cannot disagree.
        bound_adb = getattr(self._session, "adb_path", "") or ""
        if (
            profile.preset_id == "macos.bluestacks_air"
            or (profile.preset_id == "macos.mumu_pro" and profile.topology_fingerprint)
        ) and self._discovery is not None:
            return self._discovery.check_binding(
                profile,
                self._preflight,
                resolved_adb=bound_adb or None,
                **capture_options,
            )
        if bound_adb:
            capture_options["resolved_adb"] = bound_adb
        prepared_size = self._preparation.prepared_size if self._preparation else None
        if prepared_size is not None:
            capture_options["prepared_size"] = prepared_size
        return self._checked(self._preflight.check, profile, capture_options)

    @staticmethod
    def _checked(check, profile, options):
        """A preflight adapter without session resolution still gets checked."""
        try:
            return check(profile, **options)
        except TypeError as exc:
            if "resolved_adb" not in options or "resolved_adb" not in str(exc):
                raise
        remaining = {
            key: value for key, value in options.items() if key != "resolved_adb"
        }
        return check(profile, **remaining)

    def _close_failure(self, error: BaseException, reason: str) -> None:
        cancelled = isinstance(error, MowerExit) and not isinstance(
            error, (PreflightRejected, PreparationError)
        )
        # A readiness or preflight verdict is deterministic user configuration,
        # not a fatal session fault: report it, release resources and keep
        # running so the settings UI can show the repair action.
        notify = (
            self._on_fatal is not None
            and not cancelled
            and not _is_device_verdict(error)
        )
        if notify:
            self.begin_shutdown()
        if getattr(error, "cleanup_failed", False):
            self._helper_cleanup_error = error
        if notify and not self._fatal_notified:
            self._fatal_notified = True
            try:
                self._on_fatal(reason)
            except Exception:
                logger.exception("请求应用关闭失败")
                result = self.close()
                if result.error is not None:
                    error.add_note(result.error.message)
            else:
                # The coordinator first signals and joins the worker. Its
                # DEVICE phase then restores preparation and releases helpers.
                return
        if self.shutdown_requested:
            return
        # A concurrent caller is already interrupting I/O and waiting for this
        # operation. Let it clean up after this lock is released.
        if not self._closing_count:
            result = self.close()
        else:
            result = None
        if result is not None and result.error is not None:
            error.add_note(f"关闭失败的设备会话时出错：{result.error.message}")

    def _io_budget(self):
        def remaining():
            if self._shutdown.is_set() or self._pending_close.is_set():
                raise MowerExit("设备会话正在关闭")
            if self._session is not None:
                try:
                    return self._session.remaining()
                except RuntimeError:
                    return 30.0
            return 30.0

        return device_io_budget(remaining)

    def execute(self, operation: Callable[[D], T]) -> DeviceResult[T]:
        """Never repeat an operation whose delivery may already have succeeded."""
        if self._shutdown.is_set() or self._pending_close.is_set():
            return self._closing_failure()
        with self._configuration():
            return self._execute(operation)

    def capture(self) -> DeviceResult[np.ndarray]:
        """Capture may be repeated, but only within the selected backend budget."""
        if self._shutdown.is_set() or self._pending_close.is_set():
            return self._closing_failure()
        with self._configuration():
            recovering_capture = False
            if self._screenshot is None:
                self._screenshot = ScreenshotSession(
                    self._read_configuration().device,
                    self.settings_status()["host_platform"],
                )

            def rebuild():
                if (
                    self._shutdown.is_set()
                    or self._pending_close.is_set()
                    or self._closing_count
                ):
                    raise MowerExit("设备会话正在关闭")
                with self._io_budget():
                    self._device.rebuild_screenshot()

            def recover():
                nonlocal recovering_capture
                if self._session is not None:
                    serial = self.serial
                    frame_probe = (
                        self._session.adb.standard_frame_size
                        if self._screenshot.backend == "droidcast"
                        else None
                    )
                    self.recover(frame_probe=frame_probe).unwrap()
                    recovering_capture = True
                    return bool(self._session.actions or self.serial != serial)
                return False

            def capture():
                with self._io_budget() if recovering_capture else nullcontext():
                    return self._device.capture_frame()

            def standard_adb():
                if self._session is not None and not recovering_capture:
                    self._session.begin_budget()
                with self._io_budget():
                    return self._standard_adb_ready()

            return self._execute(
                lambda device: self._screenshot.capture(
                    capture, rebuild, recover, standard_adb
                )
            )

    def _standard_adb_ready(self) -> np.ndarray:
        """Verify the bound target and return the same standard ADB frame."""
        from arknights_mower.utils.device.preflight import ScreenshotUnavailable

        if (
            self._shutdown.is_set()
            or self._pending_close.is_set()
            or self._closing_count
        ):
            raise MowerExit("设备会话正在关闭")
        if self._session is None:
            return self._device.standard_frame()
        frame = None
        failure = None

        def probe(adb_path, serial, timeout):
            nonlocal frame, failure
            try:
                if serial != self.serial:
                    raise ScreenshotUnavailable("目标端点已改变，不能复用当前截图连接")
                frame = validate_frame(self._device.standard_frame())
                return frame.shape[1], frame.shape[0]
            except Exception as exc:
                failure = exc
                raise

        deadline = self._session.clock.monotonic() + self._session.remaining()
        ready = self._session.observe(deadline=deadline, frame_probe=probe)
        if failure is not None:
            raise failure
        if ready.state != "ready":
            raise ScreenshotUnavailable("目标设备不再就绪，不能降级到标准 ADB 截图")
        return frame

    def _execute(self, operation: Callable[[D], T]) -> DeviceResult[T]:
        if (
            self._shutdown.is_set()
            or self._pending_close.is_set()
            or self._closing_count
        ):
            return self._closing_failure()
        if self._helper_cleanup_error is not None:
            return self._failure("close_failed", self._helper_cleanup_error)
        if self._session_error is not None:
            return self._failure("session_failed", self._session_error)
        if self._device is None:
            return self._failure("not_started", RuntimeError("设备会话尚未建立"))
        previous = self._executing
        self._executing = True
        try:
            value = operation(self._device)
        except Exception as exc:
            if isinstance(exc, TouchFailure):
                if self._session is not None:
                    try:
                        self._session.observe()
                    except Exception as readiness_error:
                        exc.add_note(f"输入失败后检查设备状态失败：{readiness_error}")
                self._close_failure(exc, "fatal_session_error")
                self._session_error = exc
                self._state = "failed"
                return self._failure(exc.code, exc)
            if isinstance(exc, ScreenshotFailure):
                self._close_failure(exc, "fatal_session_error")
                self._session_error = exc
                self._state = "failed"
                return self._failure(exc.code, exc)
            if isinstance(exc, DeviceRecoveryError):
                self._close_failure(exc, "fatal_session_error")
                self._session_error = exc
                self._state = "failed"
                return self._failure("recovery_failed", exc)
            if isinstance(exc, MowerExit):
                if not self.shutdown_requested:
                    self.close()
                return self._failure("operation_failed", exc)
            if self._session is not None and not isinstance(exc, MowerExit):
                # Recovery rechecks readiness before any mutation; a healthy
                # target keeps capture, input and custom failures in the backend.
                recovered = self.recover()
                if not recovered.ok:
                    return recovered
            return self._failure("operation_failed", exc)
        finally:
            self._executing = previous
        return DeviceResult(
            True, self._state, self.serial, value, readiness=self._readiness
        )

    def recover(self, *, frame_probe=None) -> DeviceResult[D]:
        if self._shutdown.is_set() or self._pending_close.is_set():
            return self._closing_failure()
        with self._configuration():
            if (
                self._shutdown.is_set()
                or self._pending_close.is_set()
                or self._closing_count
            ):
                return self._closing_failure()
            if self._helper_cleanup_error is not None:
                return self._failure("close_failed", self._helper_cleanup_error)
            if self._session_error is not None:
                return self._failure("session_failed", self._session_error)
            if self._device is None:
                return self._start(connection_retries=1)
            if self._session is None:
                return self._failure(
                    "recovery_unavailable", RuntimeError("未配置设备会话适配器")
                )
            try:
                ready = self._session.ensure_ready(frame_probe=frame_probe)
                if (
                    self._shutdown.is_set()
                    or self._pending_close.is_set()
                    or self._closing_count
                ):
                    raise MowerExit("设备会话正在关闭")
                # A ready target needs no backend rebuild. If recovery took an
                # action or changed endpoints, validate before reusing helpers.
                if self._session.actions or ready.serial != self.serial:
                    if (
                        self._preparation is not None
                        and self._preparation.prepared_size
                    ):
                        raise PreparationError(
                            "preparation_interrupted",
                            "设备重连后结束本次临时整备并恢复原值，请重新授权启动。",
                        )
                    profile = self._session.profile.model_copy(
                        update={
                            "last_serial": ready.serial,
                            "adb_path": ready.adb_path,
                        }
                    )
                    if self._preparation is not None and ready.serial != self.serial:
                        self._preparation.close()
                        with self._io_budget():
                            self._preparation.begin(profile)
                    with self._io_budget():
                        result = self._check_profile(profile)
                    self._last_preflight = result
                    if not result.ok:
                        raise PreflightRejected(result.error.message, result.error.code)
                    if (
                        self._shutdown.is_set()
                        or self._pending_close.is_set()
                        or self._closing_count
                    ):
                        raise MowerExit("设备会话正在关闭")
                    with self._io_budget():
                        self._adapter.rebind(self._device, result)
                self._state = "connected"
                return DeviceResult(
                    True, self._state, self.serial, self._device, readiness=ready
                )
            except Exception as exc:
                self._close_failure(exc, "fatal_session_error")
                self._session_error = exc
                self._state = (
                    "cancelled"
                    if isinstance(exc, MowerExit)
                    and not isinstance(exc, (PreflightRejected, PreparationError))
                    else "failed"
                )
                return self._failure("recovery_failed", exc)

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown.is_set()

    def begin_shutdown(self) -> None:
        """Permanently reject device work without waiting for configuration I/O."""
        self._shutdown.set()
        if self._session is not None:
            self._session.begin_shutdown()

    def close(self, *, timeout: float = 5.0) -> DeviceResult[None]:
        # Count nested/concurrent closes without holding this guard over I/O or
        # configuration_lock: a cancelled worker may itself call close().
        with self._close_guard:
            self._closing_count += 1
        try:
            self._pending_close.set()
            self.interrupt_io()
            if not self.configuration_lock.acquire(timeout=max(0, timeout)):
                with self._close_guard:
                    self._deferred_close = True
                    acquired = self.configuration_lock.acquire(blocking=False)
                if acquired:
                    try:
                        return self._close()
                    finally:
                        self.configuration_lock.release()
                error = TimeoutError(
                    "设备工作仍在结束；恢复记录已保留，工作返回后继续清理"
                )
                logger.error(str(error))
                return self._failure("close_timeout", error)
            try:
                return self._close()
            finally:
                self.configuration_lock.release()
        finally:
            with self._close_guard:
                self._closing_count -= 1

    def final_release(self) -> DeviceResult[None]:
        """Retry a deferred close once at exit; a live holder keeps the record."""
        with self._close_guard:
            if not self._deferred_close:
                return self._close()
            self._deferred_close = False
        if not self._acquire_for_final_release():
            # The owner still holds the lock, so the record stays deferred and a
            # later return of that operation remains the next chance to clean up.
            with self._close_guard:
                self._deferred_close = True
            error = TimeoutError("设备工作仍在结束；本次退出不再等待，恢复记录继续保留")
            logger.error(str(error))
            return self._failure("close_timeout", error)
        try:
            return self._close()
        finally:
            self.configuration_lock.release()

    def _closing_failure(self):
        return self._failure("session_closing", RuntimeError("设备会话正在关闭"))

    def _acquire_for_final_release(self) -> bool:
        """Wait once, for the exit budget, on the lock a deferred cleanup needs."""
        return self.configuration_lock.acquire(timeout=_FINAL_RELEASE_TIMEOUT)

    def interrupt_io(self) -> None:
        """Interrupt only the current owned device, without waiting for its lock."""
        with self._close_guard:
            device = self._device
            if device is None or device is self._interrupted_device:
                return
            self._interrupted_device = device
        interrupt = getattr(device, "interrupt_io", None) or getattr(
            device, "interrupt_input", None
        )
        if interrupt is not None:
            try:
                interrupt()
            except Exception as exc:
                self._helper_cleanup_error = exc
                logger.debug("中断设备 I/O 失败，继续清理自有资源", exc_info=True)

    def _close(self) -> DeviceResult[None]:
        self._deferred_close = False
        self._session_error = None
        if self._close_result is not None:
            self._pending_close.clear()
            return self._close_result
        self._serial = self.serial
        device, self._device = self._device, None
        self._state = "closed"
        self._screenshot = None
        errors = [self._helper_cleanup_error] if self._helper_cleanup_error else []
        for owner in (self._preparation, device):
            try:
                if owner is not None:
                    owner.close()
            except Exception as exc:
                logger.debug("关闭设备自有资源失败，继续后续清理", exc_info=True)
                if owner is device:
                    self._helper_cleanup_error = exc
                if exc not in errors:
                    errors.append(exc)
        if errors:
            self._state = "failed"
            for error in errors[1:]:
                errors[0].add_note(str(error))
            self._close_result = self._failure("close_failed", errors[0])
        else:
            self._close_result = DeviceResult(True, self._state, self._serial)
        self._pending_close.clear()
        return self._close_result

    def _failure(self, code: str, exc: Exception) -> DeviceResult:
        if getattr(exc, "cleanup_failed", False):
            self._helper_cleanup_error = exc
        if isinstance(exc, (PreflightRejected, PreparationError)):
            code = exc.code
        elif isinstance(exc, MowerExit):
            code = "cancelled"
        elif isinstance(exc, DeviceRecoveryError):
            code = "recovery_exhausted"
            if isinstance(exc, SessionFailure) and exc.observation.code in {
                # A readiness verdict the settings UI can act on; anything else
                # stays reported as an exhausted recovery.
                "invalid_size",
                "frame_failed",
                "frame_size_mismatch",
                "device_unauthorized",
                "target_ambiguous",
                "binding_failed",
                "binding_changed",
                "topology_changed",
                "manager_output",
                "endpoint_unresolved",
                "endpoint_ambiguous",
                "endpoint_unreachable",
                "endpoint_mismatch",
                "config_invalid",
                "missing_config",
                "missing_installation",
                "instance_required",
                "instance_missing",
                "adb_disabled",
                "discovery_permission",
                "device_offline",
                "missing_adb",
                "target_required",
                "adb_server_unavailable",
                "start_confirmation_required",
                "avd_start_failed",
                "avd_start_timeout",
                "redroid_start_failed",
                "redroid_start_timeout",
                "docker_unavailable",
                "redroid_manual_required",
                "redroid_binding_changed",
                "no_redroid",
                "genymotion_unavailable",
                "genymotion_version_unsupported",
                "genymotion_binding_changed",
                "no_genymotion",
                "unsupported_host",
                "mumu_pro_manual_required",
                "mumu_pro_manager_missing",
                "mumu_pro_manager_stopped",
                "mumu_pro_manager_start_failed",
                "mumu_pro_output_invalid",
                "mumu_pro_selection_required",
                "mumu_pro_binding_changed",
                "mumu_pro_instance_error",
                "mumu_pro_action_timeout",
                "mumu_pro_action_failed",
                "waydroid_binding_changed",
                "waydroid_uninitialized",
                "waydroid_status_failed",
                "waydroid_session_unavailable",
                "waydroid_container_not_running",
                "manager_timeout",
                "manager_output_invalid",
                "discovery_permission_denied",
            }:
                code = exc.observation.code
        if (
            isinstance(exc, PreflightRejected)
            and self._last_preflight is not None
            and self._last_preflight.error is not None
        ):
            self._last_error = asdict(self._last_preflight.error)
        elif isinstance(exc, (ScreenshotFailure, TouchFailure)):
            code = exc.code
            self._last_error = exc.to_dict()
        else:
            self._last_error = {"code": code, "message": str(exc) or type(exc).__name__}
        return DeviceResult(
            False,
            self._state,
            self.serial,
            error=DeviceError(code, str(exc) or type(exc).__name__, exc),
            readiness=self._readiness,
        )
