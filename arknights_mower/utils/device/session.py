"""Bounded readiness and recovery for one immutable instance binding."""

import time
from dataclasses import dataclass
from threading import Event
from typing import Literal, Protocol

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.endpoint_identity import (
    CONFIRMED_START_PRESETS,
    VERIFIED_ENDPOINT_PRESETS,
    InstanceBindingError,
    InstanceEndpointPending,
)
from arknights_mower.utils.device.preflight import parse_display_size
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.log import logger

# The decoded frame the 1920x1080 templates require.
REQUIRED_DISPLAY_SIZE = [1920, 1080]
# A frame that is not the required canvas yet is a wait, not a failure: a game
# that has not rotated, or one still loading, resolves inside the same deadline.
# An unreadable size output stays terminal, because waiting cannot repair it.
RETRYABLE_WAIT_CODES = frozenset({"frame_failed"})
# The one failure that only says the transaction ran out of time; a verdict with
# an observed reason is more useful and replaces it wherever one exists.
BUDGET_EXHAUSTED = "设备恢复时间预算已耗尽"


def _one_line(text) -> str:
    """A verdict reason keeps its signal on one readable log line."""
    return " ".join(str(text).split())


Readiness = Literal["absent", "offline", "booting", "ready"]


@dataclass(frozen=True)
class InstanceObservation:
    state: Literal["unknown", "stopped", "running", "starting"]
    serial: str | None = None


@dataclass(frozen=True)
class ReadinessResult:
    state: Readiness
    serial: str
    adb_path: str = ""
    instance_state: str = "unknown"
    code: str = ""
    message: str = ""


DEFAULT_RECOVERY_ATTEMPTS: int = 3
DEFAULT_RECOVERY_TIMEOUT: float = 180.0
DEFAULT_LOCAL_WAIT: float = 10.0
DEFAULT_POLL_INTERVAL: float = 1.0
DEFAULT_SHUTDOWN_WAIT: float = 30.0


@dataclass(frozen=True)
class RecoveryPolicy:
    attempts: int = DEFAULT_RECOVERY_ATTEMPTS
    timeout: float = DEFAULT_RECOVERY_TIMEOUT
    local_wait: float = DEFAULT_LOCAL_WAIT
    poll_interval: float = DEFAULT_POLL_INTERVAL
    # A manager acknowledges a shutdown before the instance is gone. The launch
    # paired with that stop waits for this confirmed stopped state; MuMu's own
    # hung-player handoff outlives a 10 second local wait.
    shutdown_wait: float = DEFAULT_SHUTDOWN_WAIT

    def __post_init__(self):
        if (
            self.attempts < 0
            or self.timeout <= 0
            or self.local_wait < 0
            or self.poll_interval <= 0
            or self.shutdown_wait < 0
        ):
            raise ValueError("恢复次数不能为负，截止时间与轮询间隔必须为正")


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(csleep)


class SessionADB(Protocol):
    def resolve_adb(self, profile: DeviceProfile, timeout: float) -> str: ...
    def devices(self, adb_path: str, timeout: float) -> list[tuple[str, str]]: ...
    def boot_completed(self, adb_path: str, serial: str, timeout: float) -> str: ...
    def recover(self, adb_path: str, serial: str, timeout: float) -> bool: ...

    # Readiness probes are optional: a reduced adapter still reports transport,
    # boot and recovery, and only skips the display and first-frame conditions.
    def display_size(self, adb_path: str, serial: str, timeout: float) -> str: ...
    def frame_size(
        self, adb_path: str, serial: str, timeout: float
    ) -> tuple[int, int] | None: ...
    def standard_frame_size(
        self, adb_path: str, serial: str, timeout: float
    ) -> tuple[int, int] | None: ...


class Simulator(Protocol):
    def inspect(
        self, profile: DeviceProfile, timeout: float
    ) -> InstanceObservation: ...
    def start(self, profile: DeviceProfile, timeout: float) -> bool: ...
    def stop(self, profile: DeviceProfile, timeout: float) -> bool: ...


PRESET_NAMES = {
    "windows.mumu12": "MuMu 12",
    "windows.ldplayer9": "雷电模拟器 9",
    "windows.ldplayer14": "雷电模拟器 14",
    "windows.nox": "夜神模拟器",
    "windows.bluestacks5": "BlueStacks 5",
    "macos.bluestacks_air": "BlueStacks Air",
    "macos.avd": "Android Virtual Device",
    "macos.mumu_pro": "MuMu Pro",
    "linux.waydroid": "Waydroid",
    "linux.avd": "Android Virtual Device",
    "linux.redroid": "redroid",
    "linux.genymotion": "Genymotion",
    "manual.other": "其他模拟器",
    "manual.physical": "实体设备",
}

BACKEND_NAMES = {
    "mumu_ipc": "MuMu 截图增强",
    "droidcast": "DroidCast",
    "scrcpy": "scrcpy",
    "maatouch": "MaaTouch",
    "adb_gzip": "ADB gzip",
    "custom": "自定义命令",
}

TOUCH_BACKEND_NAMES = {
    "mumu_ipc": "MuMu 自带触控",
    "scrcpy": "scrcpy",
    "maatouch": "MaaTouch",
}


class SessionFailure(DeviceRecoveryError):
    def __init__(self, observation: ReadinessResult, message: str):
        super().__init__(message)
        self.observation = observation


class DeviceSession:
    def __init__(
        self,
        adb: SessionADB,
        simulator: Simulator,
        *,
        clock: Clock | None = None,
        policy: RecoveryPolicy | None = None,
    ):
        self.adb = adb
        self.simulator = simulator
        self.clock = clock or SystemClock()
        self.default_policy = policy or RecoveryPolicy()
        self._policy = self.default_policy
        self.profile: DeviceProfile | None = None
        self.adb_path = ""
        self.last = ReadinessResult("absent", "")
        self.actions = 0
        # Reported logical size of the last observation; informational only,
        # because the decoded frame is what the templates depend on.
        self._display_size: list[int] | None = None
        self._observation_key = None
        self._deadline: float | None = None
        self._launched_at: float | None = None
        self._startup_wait = 30.0
        self._shutdown = Event()

    @property
    def policy(self) -> RecoveryPolicy:
        return self._policy

    @policy.setter
    def policy(self, value: RecoveryPolicy) -> None:
        """Replace the current and default budgets; bind overrides only the current one."""
        self._policy = value
        self.default_policy = value

    def begin_shutdown(self) -> None:
        self._shutdown.set()

    def remaining(self) -> float:
        if self._deadline is None:
            raise RuntimeError("设备恢复预算尚未开始")
        return self._remaining(self._deadline)

    def begin_budget(self, *, deadline: float | None = None) -> float:
        """Establish one Recovery Budget before preparation or readiness I/O."""
        if deadline is None:
            deadline = self.clock.monotonic() + self.policy.timeout
        self._deadline = deadline
        self.actions = 0
        return deadline

    def resolve_adb(self, deadline: float) -> str:
        """Resolve the bound transport once within the caller's Recovery Budget."""
        if self.profile is None:
            raise RuntimeError("设备实例尚未绑定")
        remaining = self._remaining(deadline)
        if not self.adb_path:
            resolved = self.adb.resolve_adb(self.profile, remaining)
            self._remaining(deadline)
            self.adb_path = resolved
        return self.adb_path

    def bind(
        self,
        profile: DeviceProfile,
        *,
        resolved_adb: str | None = None,
        policy: RecoveryPolicy | None = None,
        startup_wait: float = 30.0,
    ) -> None:
        if self._shutdown.is_set():
            raise MowerExit("设备会话正在关闭")
        if self.profile is None or any(
            getattr(self.profile, field) != getattr(profile, field)
            for field in (
                "preset_id",
                "installation_path",
                "manager_path",
                "config_path",
                "instance_id",
                "instance_uuid",
                "topology_fingerprint",
            )
        ):
            self._launched_at = None
        self._startup_wait = max(0, startup_wait)
        if policy is not None:
            self.policy = policy
        elif (
            profile.recovery_timeout != DEFAULT_RECOVERY_TIMEOUT
            or profile.recovery_attempts != DEFAULT_RECOVERY_ATTEMPTS
            or profile.recovery_local_wait != DEFAULT_LOCAL_WAIT
            or profile.recovery_shutdown_wait != DEFAULT_SHUTDOWN_WAIT
        ):
            self._policy = RecoveryPolicy(
                attempts=profile.recovery_attempts,
                timeout=profile.recovery_timeout,
                local_wait=profile.recovery_local_wait,
                shutdown_wait=profile.recovery_shutdown_wait,
                poll_interval=self.default_policy.poll_interval,
            )
        else:
            self._policy = self.default_policy
        self.profile = profile.model_copy(deep=True)
        self.adb_path = resolved_adb or ""
        self.last = ReadinessResult("absent", profile.last_serial)
        self._observation_key = None
        # A new binding has observed nothing yet: the previous run's reading
        # must not be reported as this session's display.
        self._display_size = None
        preset_name = PRESET_NAMES.get(profile.preset_id, profile.preset_id)
        screenshot_name = BACKEND_NAMES.get(
            profile.screenshot_backend, profile.screenshot_backend
        )
        touch_name = TOUCH_BACKEND_NAMES.get(
            profile.touch_backend, profile.touch_backend
        )
        instance_desc = f"（{profile.instance_name}）" if profile.instance_name else ""
        target_desc = (
            f"ADB serial {profile.last_serial.strip() or '未填写'}"
            if profile.preset_id == "macos.mumu_pro"
            and not profile.topology_fingerprint
            else f"多开实例 {profile.instance_id}{instance_desc}"
        )
        logger.info(
            f"使用设备：{preset_name} {target_desc}，截图后端 "
            f"{screenshot_name}，触控后端 {touch_name}"
        )
        logger.debug(
            f"设备会话预算：超时保护 {self.policy.timeout:g} 秒，"
            f"最大重试 {self.policy.attempts} 次，重试间隔 {self.policy.local_wait:g} 秒"
        )
        # The first-frame probe reads the selection this session is bound to.
        propagate = getattr(self.adb, "bind", None)
        if propagate is not None:
            propagate(self.profile)

    def _remaining(self, deadline: float) -> float:
        if self._shutdown.is_set():
            raise MowerExit("设备会话正在关闭")
        # The production clock checks the worker's cancellation event.
        self.clock.sleep(0)
        remaining = deadline - self.clock.monotonic()
        if remaining <= 0:
            raise SessionFailure(self.last, BUDGET_EXHAUSTED)
        return remaining

    def observe(
        self, deadline: float | None = None, *, frame_probe=None
    ) -> ReadinessResult:
        if self._shutdown.is_set():
            raise MowerExit("设备会话正在关闭")
        try:
            result = self._observe(deadline, frame_probe=frame_probe)
        except (MowerExit, SessionFailure):
            raise
        except SharedADBError as exc:
            self.last = ReadinessResult(
                "offline",
                self.last.serial,
                self.adb_path,
                code="adb_server_unavailable",
                message=str(exc),
            )
            result = self.last
        except Exception as exc:
            self.last = ReadinessResult(
                "offline",
                self.last.serial,
                self.adb_path,
                self.last.instance_state,
                code="transport_probe_failed",
                message=str(exc),
            )
            result = self.last
        self._report_observation(result)
        return result

    def _format_human_observation(self, observation: ReadinessResult) -> str:
        """One sentence for what this observation means, empty when it says nothing."""
        state = observation.state
        instance_state = observation.instance_state
        code = observation.code
        reason = _one_line(observation.message)

        if state == "ready":
            if observation.serial:
                return f"设备已连接（{observation.serial}）"
            return "设备已连接就绪"
        if state == "booting":
            if code == "frame_failed":
                return "设备已连接，正在等待有效画面..."
            return "模拟器正在启动中，等待系统就绪..."
        if state == "offline":
            return "设备离线，正在连接设备 ADB 端口..."
        if state == "absent":
            if instance_state == "stopped":
                return "模拟器未启动"
            if code == "missing_adb":
                return f"未找到 ADB 调试工具：{reason or '请检查 ADB 配置'}"
            return "正在连接设备 ADB 端口..."
        if reason:
            return f"设备状态：{state}（{reason}）"
        return f"设备状态：{state}"

    def _flow_names_state(self, observation: ReadinessResult) -> bool:
        """States the connection flow names itself instead of the observation.

        A ready verdict is reported once by ``ensure_ready`` after the display
        gate, and a stopped instance is named by the launch that follows it.
        Printing these here as well is what split one state change into the
        "模拟器未启动" plus "正在尝试恢复设备连接" pair.
        """
        if observation.state == "ready":
            return True
        return observation.state == "absent" and observation.instance_state == "stopped"

    def _report_observation(self, observation):
        """A readiness verdict keeps a reason in the log for every change."""
        key = (observation.state, observation.instance_state, observation.code)
        summary = (
            f"设备观察：state={observation.state} "
            f"实例={observation.instance_state or 'unknown'} "
            f"serial={observation.serial or '-'}"
        )
        if observation.code:
            summary += f" code={observation.code}"
        reason = _one_line(observation.message)
        if reason:
            summary += f"：{reason}"
        display = (
            f" 显示={'x'.join(map(str, self._display_size))}"
            if self._display_size
            else ""
        )
        logger.debug(f"{summary}{display}")
        if key == self._observation_key:
            return
        self._observation_key = key
        if self._flow_names_state(observation):
            return
        human_text = self._format_human_observation(observation)
        if human_text:
            logger.info(human_text)

    def _observe(
        self, deadline: float | None = None, *, frame_probe=None
    ) -> ReadinessResult:
        if self.profile is None:
            raise RuntimeError("设备实例尚未绑定")
        if deadline is None:
            deadline = self.clock.monotonic() + self.policy.timeout
        profile = self.profile
        # Vendor endpoint identity is checked through this exact ADB client,
        # so resolve it before asking the manager to inspect the binding.
        if profile.preset_id in VERIFIED_ENDPOINT_PRESETS:
            if not self.adb_path:
                try:
                    self.resolve_adb(deadline)
                except (MowerExit, SessionFailure, SharedADBError):
                    raise
                except Exception as exc:
                    self.last = ReadinessResult(
                        "absent", "", code="missing_adb", message=str(exc)
                    )
                    return self.last
            profile = profile.model_copy(update={"adb_path": self.adb_path})
        try:
            instance = self.simulator.inspect(profile, self._remaining(deadline))
        except (MowerExit, SessionFailure, SharedADBError):
            raise
        except InstanceEndpointPending as exc:
            # The manager confirmed the VM, but its ADB candidate is not yet
            # verified. Wait within the existing budget without exposing a
            # serial that could connect/recover an unrelated online device.
            self.last = ReadinessResult(
                "offline" if exc.code == "device_offline" else "absent",
                "",
                self.adb_path,
                instance_state="starting",
                message=str(exc),
            )
            return self.last
        except InstanceBindingError as exc:
            self.last = ReadinessResult(
                "offline", "", self.adb_path, code=exc.code, message=str(exc)
            )
            return self.last
        except Exception as exc:
            self.last = ReadinessResult(
                "offline", "", self.adb_path, code="binding_failed", message=str(exc)
            )
            return self.last
        serial = (
            instance.serial or ""
            if instance.state != "unknown"
            else profile.last_serial.strip()
        )
        if instance.serial:
            serial = instance.serial
        self.last = ReadinessResult("absent", serial, self.adb_path, instance.state)
        if not serial and instance.state == "unknown":
            self.last = ReadinessResult(
                "absent", "", code="target_required", message="请选择明确的设备 serial"
            )
            return self.last
        if not self.adb_path:
            try:
                self.resolve_adb(deadline)
            except (MowerExit, SessionFailure):
                raise
            except Exception as exc:
                self.last = ReadinessResult(
                    "absent", serial, code="missing_adb", message=str(exc)
                )
                return self.last
        if not serial:
            if profile.preset_id == "macos.mumu_pro" and instance.state == "starting":
                self.last = ReadinessResult("booting", "", self.adb_path, "starting")
            return self.last
        states = [
            state
            for target, state in self.adb.devices(
                self.adb_path, self._remaining(deadline)
            )
            if target == serial
        ]
        state: Readiness = "absent"
        code = ""
        if states:
            state = "offline"
            if len(states) != 1:
                code = "target_ambiguous"
            elif states[0] == "unauthorized":
                code = "device_unauthorized"
            elif states[0] == "device":
                boot = self.adb.boot_completed(
                    self.adb_path, serial, self._remaining(deadline)
                )
                state = "ready" if boot.strip() == "1" else "booting"
                if state == "ready":
                    return self._confirm_display(
                        serial, instance.state, deadline, frame_probe
                    )
        self._remaining(deadline)
        self.last = ReadinessResult(state, serial, self.adb_path, instance.state, code)
        return self.last

    def _confirm_display(self, serial, instance_state, deadline, frame_probe=None):
        """The decoded frame decides readiness; the reported size only informs.

        A tablet presentation or a not-yet-rotated game can report a portrait
        logical size while it already renders landscape. The 1920x1080 templates
        depend on the frame, so the frame is what is gated here.
        """
        self._observe_display(serial, deadline)
        ok, code, message = self._frame_ready(serial, deadline, frame_probe)
        if not ok:
            self.last = ReadinessResult(
                "booting", serial, self.adb_path, instance_state, code, message
            )
            return self.last
        self.last = ReadinessResult(
            "ready", serial, self.adb_path, instance_state, "", ""
        )
        return self.last

    def _observe_display(self, serial, deadline):
        """Record the reported logical size; never reject on it alone."""
        # Never keep a previous reading when this observation does not produce one.
        self._display_size = None
        probe = getattr(self.adb, "display_size", None)
        if probe is None:
            return
        try:
            output = probe(self.adb_path, serial, self._remaining(deadline))
        except (MowerExit, SessionFailure):
            raise
        except Exception:
            return
        if not isinstance(output, str):
            return
        try:
            dimensions = parse_display_size(output)
        except ValueError:
            return
        override = dimensions.get("Override")
        self._display_size = (
            override if override is not None else dimensions["Physical"]
        )

    def _frame_ready(self, serial, deadline, frame_probe=None):
        probe = frame_probe or getattr(self.adb, "frame_size", None)
        if probe is None:
            return False, "frame_failed", "无法取得有效首帧，请确认目标设备画面后重试。"
        try:
            size = probe(self.adb_path, serial, self._remaining(deadline))
        except (MowerExit, SessionFailure):
            raise
        except Exception as exc:
            return False, "frame_failed", str(exc) or "无法取得有效首帧。"
        if not isinstance(size, (list, tuple)) or list(size) != REQUIRED_DISPLAY_SIZE:
            return (
                False,
                "frame_failed",
                "截图实际帧不是横屏 1920×1080，请修正显示设置后重试。",
            )
        return True, "", ""

    def ensure_ready(
        self, *, deadline: float | None = None, frame_probe=None
    ) -> ReadinessResult:
        """One transaction; every action and wait uses this single deadline."""
        if deadline is None or deadline != self._deadline:
            deadline = self.begin_budget(deadline=deadline)
        logger.debug(
            f"开始设备就绪检查：超时保护 {self.policy.timeout:g} 秒，"
            f"最大重试 {self.policy.attempts} 次"
        )
        try:
            ready = self._ensure_ready(deadline, frame_probe)
        except SessionFailure as exc:
            logger.error(f"设备未能成功就绪：{exc}")
            raise
        instance_state_label = {
            "running": "运行中",
            "stopped": "已停止",
            "starting": "启动中",
            "unknown": "状态未知",
        }.get(ready.instance_state, ready.instance_state)
        display_str = ""
        if self._display_size:
            w, h = self._display_size
            if (w, h) == (1080, 1920):
                display_str = "，分辨率 1920x1080"
            else:
                display_str = f"，分辨率 {w}x{h}"
        logger.info(
            f"连接成功：{ready.serial}（实例{instance_state_label}{display_str}）"
        )
        return ready

    def _ensure_ready(self, deadline: float, frame_probe=None) -> ReadinessResult:
        if (
            self.profile.preset_id == "macos.mumu_pro"
            and self.profile.topology_fingerprint
        ):
            prepare = getattr(self.simulator, "prepare_mumu_pro", None)
            if prepare is not None:
                try:
                    prepare(self.profile, self._remaining(deadline))
                except InstanceBindingError as exc:
                    self.last = ReadinessResult(
                        "offline", "", self.adb_path, code=exc.code, message=str(exc)
                    )
                    raise SessionFailure(self.last, str(exc)) from exc
        observation = self.observe(deadline, frame_probe=frame_probe)
        self._check_observation(observation)
        if observation.state == "ready":
            return observation
        if (
            self.profile.preset_id == "macos.mumu_pro"
            and not self.profile.topology_fingerprint
            and observation.instance_state == "stopped"
        ):
            raise SessionFailure(
                observation,
                "MuMu Pro 实例尚未启动，请在模拟器中手动启动后重试。",
            )
        if observation.code == "frame_failed" and observation.serial:
            # The instance and its transport are healthy; only the decoded
            # canvas is missing (a game that is not running cannot render one).
            # A complete restart cannot repair that and destroys the only state
            # that could satisfy the gate, so local recovery stays local.
            logger.warning(
                "设备已连接但未获取到有效画面（暂不重启模拟器）："
                f"{_one_line(observation.message) or observation.code}"
            )
        if self.profile.preset_id in CONFIRMED_START_PRESETS:
            if observation.instance_state == "stopped":
                self.last = ReadinessResult(
                    "absent",
                    "",
                    self.adb_path,
                    "stopped",
                    "start_confirmation_required",
                    "模拟器未启动，请在设备设置中确认启动已绑定的实例。",
                )
                raise SessionFailure(self.last, self.last.message)
            # Explicit launch consent is never reused for a full restart.
            return self._wait_ready(deadline, connect=True, frame_probe=frame_probe)
        if observation.instance_state == "stopped":
            # One state change reads as one sentence: the launch completes the
            # observation instead of a counter-heavy retry line following it.
            logger.info(
                f"{self._format_human_observation(observation)}，正在启动模拟器..."
            )
            self._action(
                self._launch,
                deadline,
                starting=True,
            )
            return self._wait_ready(deadline, connect=True, frame_probe=frame_probe)
        # Reserve one action for a complete restart only when the manager has
        # positively identified this running/starting instance. A canvas that
        # is not there yet never justifies one.
        frame_only = observation.code == "frame_failed" and bool(observation.serial)
        restartable = (
            observation.instance_state in {"running", "starting"}
            and (
                self.profile.preset_id != "macos.mumu_pro"
                or bool(self.profile.topology_fingerprint)
            )
            and not frame_only
        )
        local_actions = (
            max(1, self.policy.attempts - 2)
            if restartable and self.policy.attempts
            else self.policy.attempts
        )
        for _ in range(local_actions):
            # Only an unknown transport skips endpoint recovery; a target that is
            # reachable but not showing the required canvas still reconnects.
            if observation.serial and observation.code != "transport_probe_failed":
                self._action(
                    lambda timeout: self.adb.recover(
                        self.adb_path, observation.serial, timeout
                    ),
                    deadline,
                    required=False,
                )
            else:
                # Waiting is also an attempt; it cannot create an unbounded
                # sequence when no endpoint is available yet.
                self._action(lambda timeout: True, deadline)
            observation = self._wait_local(deadline, frame_probe=frame_probe)
            if observation.state == "ready":
                return observation
        if restartable and self._launched_at is not None:
            protected_until = self._launched_at + self._startup_wait
            if self.clock.monotonic() < protected_until:
                logger.info("模拟器仍在启动保护时间内，等待设备就绪后再判断是否重启")
                observation = self._wait_local(
                    deadline, until=protected_until, frame_probe=frame_probe
                )
                if observation.state == "ready":
                    return observation
        if observation.instance_state == "stopped":
            if (
                self.profile.preset_id == "macos.mumu_pro"
                and not self.profile.topology_fingerprint
            ):
                raise SessionFailure(
                    observation,
                    "MuMu Pro 实例尚未启动，请在模拟器中手动启动后重试。",
                )
            logger.info(
                f"{self._format_human_observation(observation)}，正在启动模拟器..."
            )
            self._action(
                self._launch,
                deadline,
                starting=True,
            )
            return self._wait_ready(deadline, connect=True, frame_probe=frame_probe)
        frame_only = observation.code == "frame_failed" and bool(observation.serial)
        if (
            restartable
            and observation.instance_state in {"running", "starting"}
            and not frame_only
        ):
            # A stop and its paired start form ONE complete restart. Each
            # command still receives only the remaining transaction time.
            def restart(timeout):
                logger.info("检测到设备无响应，正在尝试关闭模拟器...")
                if not self.simulator.stop(self.profile, timeout):
                    return False
                # The manager reports the shutdown before the instance is gone:
                # a launch issued inside that window is rejected, so only the
                # confirmed stopped state authorizes the paired start.
                if not self._await_stopped(deadline):
                    raise SessionFailure(
                        self.last,
                        f"实例关停未在 {self.policy.shutdown_wait:g} 秒内确认，"
                        "已取消本次自动重启。",
                    )
                logger.info("模拟器已完全退出，正在重新启动模拟器...")
                return self._launch(self._remaining(deadline))

            self._action(restart, deadline)
            return self._wait_ready(deadline, connect=True, frame_probe=frame_probe)
        raise SessionFailure(
            observation,
            "设备未能就绪："
            f"{_one_line(observation.message) or observation.code or '恢复次数预算已耗尽'}",
        )

    def _await_stopped(self, deadline) -> bool:
        """Only the manager's own stopped state authorizes the paired launch."""
        until = min(deadline, self.clock.monotonic() + self.policy.shutdown_wait)
        logger.info(
            f"等待模拟器完全退出（最长等待 {self.policy.shutdown_wait:g} 秒）..."
        )
        while True:
            self._remaining(deadline)
            try:
                state = self.simulator.inspect(
                    self.profile, self._remaining(deadline)
                ).state
            except (MowerExit, SessionFailure):
                raise
            except Exception as exc:
                # A transient unreadable state is not a confirmed stop: the
                # manager's own status is incomplete while the instance closes.
                state = "unknown"
                logger.debug(f"关停确认期间无法读取实例状态：{exc}")
            if state == "stopped":
                logger.info("模拟器已完全退出，准备启动")
                return True
            if self.clock.monotonic() >= until:
                logger.warning(
                    f"等待模拟器退出超时（{self.policy.shutdown_wait:g} 秒未响应）"
                )
                return False
            self.clock.sleep(
                min(self.policy.poll_interval, until - self.clock.monotonic())
            )

    def _launch(self, timeout):
        # Record issuance even if the manager's acknowledgement is uncertain.
        self._launched_at = self.clock.monotonic()
        return self.simulator.start(self.profile, timeout)

    def _wait_local(self, deadline, *, until=None, frame_probe=None):
        if until is None:
            until = self.clock.monotonic() + self.policy.local_wait
        until = min(deadline, until)
        while True:
            observation = self.observe(deadline, frame_probe=frame_probe)
            self._check_observation(observation)
            if observation.state == "ready" or self.clock.monotonic() >= until:
                return observation
            self.clock.sleep(
                min(self.policy.poll_interval, until - self.clock.monotonic())
            )

    def _check_observation(self, observation):
        if (
            observation.code
            and observation.code != "transport_probe_failed"
            and observation.code not in RETRYABLE_WAIT_CODES
        ):
            raise SessionFailure(observation, observation.message or observation.code)

    def _action(self, operation, deadline, *, required=True, starting=False):
        self._remaining(deadline)
        if self.actions >= self.policy.attempts:
            raise SessionFailure(self.last, "设备恢复次数预算已耗尽")
        self.actions += 1
        # Attempt counters and budgets are diagnostics. The user-visible flow
        # names each state change once, never per retry.
        logger.debug(
            f"设备恢复动作 {self.actions}/{self.policy.attempts}："
            f"{'启动实例' if starting else '重连设备'}"
        )
        try:
            succeeded = operation(self._remaining(deadline))
        except (MowerExit, SessionFailure):
            raise
        except InstanceBindingError as exc:
            self.last = ReadinessResult(
                "offline", "", self.adb_path, code=exc.code, message=str(exc)
            )
            raise SessionFailure(self.last, str(exc)) from exc
        except SharedADBError as exc:
            if getattr(exc, "cleanup_failed", False):
                raise
            logger.error(f"设备恢复动作失败（ADB 服务）：{exc}")
            self.last = ReadinessResult(
                "offline",
                self.last.serial,
                self.adb_path,
                code="adb_server_unavailable",
                message=str(exc),
            )
            raise SessionFailure(self.last, str(exc)) from exc
        except Exception as exc:
            logger.warning(f"设备恢复动作出错：{exc}")
            if required:
                raise SessionFailure(self.last, f"设备恢复命令失败：{exc}") from exc
            succeeded = False
        self._remaining(deadline)
        logger.debug(
            f"设备恢复动作 {self.actions}/{self.policy.attempts} 结果：{succeeded}"
        )
        if required and not succeeded:
            raise SessionFailure(self.last, "设备恢复命令失败")
        return succeeded

    def _wait_ready(self, deadline, *, connect=False, frame_probe=None):
        connected = set()
        while True:
            try:
                observation = self.observe(deadline, frame_probe=frame_probe)
                self._check_observation(observation)
                if observation.state == "ready":
                    return observation
                if (
                    connect
                    and observation.serial
                    and observation.state != "booting"
                    and observation.serial not in connected
                    and self.actions < self.policy.attempts
                ):
                    recovered = self._action(
                        lambda timeout: self.adb.recover(
                            self.adb_path, observation.serial, timeout
                        ),
                        deadline,
                        required=False,
                    )
                    if recovered:
                        connected.add(observation.serial)
                    else:
                        observation = self._wait_local(
                            deadline, frame_probe=frame_probe
                        )
                        if observation.state == "ready":
                            return observation
                self.clock.sleep(
                    min(self.policy.poll_interval, self._remaining(deadline))
                )
            except SessionFailure as exc:
                if str(exc) != BUDGET_EXHAUSTED:
                    raise
                # The reason the target never became ready is the verdict the
                # user has to act on; a bare budget message hides it.
                raise self._not_ready_failure(exc) from exc

    def _not_ready_failure(self, exc):
        # The reason the target never became ready is the verdict the user has
        # to act on. A state that carries no message still carries a sentence.
        detail = (
            _one_line(self.last.message)
            or self.last.code
            or self._format_human_observation(self.last)
        )
        if not detail:
            return exc
        code = f"（{self.last.code}）" if self.last.code else ""
        return SessionFailure(self.last, f"{exc}；最后一次观察：{detail}{code}")
