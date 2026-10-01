"""Session policy at the application seam, with no host or device I/O."""

import unittest
from unittest.mock import Mock

import pytest

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.endpoint_identity import CONFIRMED_START_PRESETS
from arknights_mower.utils.device.preflight import PreflightError, PreflightResult
from arknights_mower.utils.device.preparation import PreparationSession
from arknights_mower.utils.device.session import (
    DeviceSession,
    RecoveryPolicy,
    SessionFailure,
)


class Preflight:
    def host_platform(self):
        return "windows"

    def check(self, profile):
        return PreflightResult(
            True,
            "windows",
            "ready",
            profile.last_serial,
            adb_path=profile.adb_path,
            game_package=profile.game_package,
        )


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ADB:
    def __init__(self):
        self.rows = []
        self.boot = "0"
        self.size = "Physical size: 1920x1080"
        self.frame = (1920, 1080)
        self.actions = []
        self.on_recover = lambda: None

    def resolve_adb(self, profile, timeout):
        return "verified-adb"

    def devices(self, adb_path, timeout):
        return self.rows

    def boot_completed(self, adb_path, serial, timeout):
        return self.boot

    def display_size(self, adb_path, serial, timeout):
        return self.size

    def frame_size(self, adb_path, serial, timeout):
        return self.frame

    def standard_frame_size(self, adb_path, serial, timeout):
        return self.frame

    def recover(self, adb_path, serial, timeout):
        self.actions.append(serial)
        self.on_recover()
        return True


class Simulator:
    def __init__(self):
        self.state = "unknown"
        self.serial = None
        self.actions = []
        self.bindings = []
        self.on_start = lambda: None

    def inspect(self, profile, timeout):
        from arknights_mower.utils.device.session import InstanceObservation

        self.bindings.append((profile.preset_id, profile.instance_id))
        return InstanceObservation(self.state, self.serial)

    def start(self, profile, timeout):
        self.actions.append("start")
        self.state = "starting"
        self.on_start()
        return True

    def stop(self, profile, timeout):
        self.actions.append("stop")
        self.state = "stopped"
        return True


class Adapter:
    def open_verified(self, configuration, result):
        return Handle(result.serial)

    def rebind(self, device, result):
        device.device_id = result.serial


class Handle:
    def __init__(self, serial):
        self.device_id = serial
        self.closed = False

    def close(self):
        self.closed = True


class StartupProtectionTests(unittest.TestCase):
    def start_instance(self, wait=30, timeout=180):
        clock, adb, simulator = Clock(), ADB(), Simulator()
        conf = Conf(
            simulator={"name": "MuMu12", "index": "0", "wait_time": wait},
            device={
                "preset_id": "windows.mumu12",
                "instance_id": "0",
                "last_serial": "USB-A",
                "recovery_timeout": timeout,
            },
        )
        events = []
        start, stop = simulator.start, simulator.stop

        def launch(profile, timeout):
            events.append(("start", clock.now))
            return start(profile, timeout)

        def shutdown(profile, timeout):
            events.append(("stop", clock.now))
            return stop(profile, timeout)

        def ready():
            simulator.state, simulator.serial = "running", "USB-A"
            adb.rows, adb.boot = [("USB-A", "device")], "1"

        simulator.start, simulator.stop = launch, shutdown
        simulator.on_start = ready
        simulator.state = "stopped"
        control = DeviceControl(
            lambda: conf,
            Adapter(),
            session=DeviceSession(adb, simulator, clock=clock),
            preflight=Preflight(),
        )
        self.addCleanup(control.close)
        self.assertTrue(control.start().ok)
        adb.rows = [("USB-A", "offline")]
        return control, clock, adb, conf, events

    def test_recent_launch_preserves_configured_wait_before_every_restart(self):
        for wait in (30, 47):
            with self.subTest(wait=wait):
                control, clock, adb, conf, events = self.start_instance(wait=wait)
                self.assertTrue(control.recover().ok)
                self.assertEqual(
                    events, [("start", 0), ("stop", wait), ("start", wait)]
                )
                adb.rows = [("USB-A", "offline")]
                self.assertTrue(control.recover().ok)
                self.assertEqual(events[-2:], [("stop", 2 * wait), ("start", 2 * wait)])

    def test_recovery_during_startup_protection_avoids_restart(self):
        control, clock, adb, conf, events = self.start_instance()
        sleep = clock.sleep

        def recover_later(seconds):
            sleep(seconds)
            if clock.now >= 20:
                adb.rows = [("USB-A", "device")]

        clock.sleep = recover_later
        self.assertTrue(control.recover().ok)
        self.assertEqual(clock.now, 20)
        self.assertEqual(events, [("start", 0)])

    def test_startup_protection_exhausts_budget_without_an_early_stop(self):
        control, clock, adb, conf, events = self.start_instance(timeout=15)
        result = control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(clock.now, 15)
        self.assertEqual(events, [("start", 0)])

    def test_transport_recovery_with_missing_frame_does_not_authorize_restart(self):
        control, clock, adb, conf, events = self.start_instance()
        sleep = clock.sleep

        def transport_ready(seconds):
            sleep(seconds)
            if clock.now >= 20:
                adb.rows, adb.frame = [("USB-A", "device")], None

        clock.sleep = transport_ready
        result = control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "frame_failed")
        self.assertEqual(events, [("start", 0)])

    def test_uncertain_reconnect_stays_failed_after_protected_wait(self):
        control, clock, adb, conf, events = self.start_instance()
        adb.recover = Mock(return_value=False)
        sleep = clock.sleep

        def ready_later(seconds):
            sleep(seconds)
            if clock.now >= 20:
                adb.rows = [("USB-A", "device")]

        clock.sleep = ready_later
        result = control.recover()
        self.assertFalse(result.ok)
        self.assertIn("设备恢复命令未确认成功", result.error.message)
        self.assertEqual(events, [("start", 0)])

    def test_startup_protection_respects_cancellation(self):
        from arknights_mower.utils.csleep import MowerExit

        control, clock, adb, conf, events = self.start_instance()
        sleep = clock.sleep

        def cancel_later(seconds):
            sleep(seconds)
            if clock.now >= 20:
                raise MowerExit

        clock.sleep = cancel_later
        self.assertFalse(control.recover().ok)
        self.assertEqual(events, [("start", 0)])

    def test_same_binding_keeps_protection_across_close_and_reopen(self):
        control, clock, adb, conf, events = self.start_instance()
        control.close()
        self.assertTrue(control.start().ok)
        self.assertEqual(events[-2:], [("stop", 30), ("start", 30)])

    def test_changed_binding_does_not_inherit_previous_launch(self):
        control, clock, adb, conf, events = self.start_instance()
        control.close()
        conf.device.instance_id = "1"
        self.assertTrue(control.start().ok)
        self.assertEqual(events[-2:], [("stop", 10), ("start", 10)])

    def test_elapsed_startup_protection_does_not_add_another_wait(self):
        control, clock, adb, conf, events = self.start_instance()
        clock.now = 40
        self.assertTrue(control.recover().ok)
        self.assertEqual(events[-2:], [("stop", 50), ("start", 50)])


class DeviceSessionTests(unittest.TestCase):
    def setUp(self):
        from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy

        self.clock, self.adb, self.simulator = Clock(), ADB(), Simulator()
        self.conf = Conf(device={"last_serial": "USB-A"})
        self.session = DeviceSession(
            self.adb,
            self.simulator,
            clock=self.clock,
            policy=RecoveryPolicy(
                attempts=3, timeout=12, local_wait=2, poll_interval=1
            ),
        )
        self.control = DeviceControl(
            lambda: self.conf, Adapter(), session=self.session, preflight=Preflight()
        )

    def test_readiness_requires_exact_transport_and_completed_boot(self):
        for rows, boot, expected in (
            ([("OTHER", "device")], "1", "absent"),
            ([("USB-A", "offline")], "1", "offline"),
            ([("USB-A", "device")], "0", "booting"),
            ([("USB-A", "device")], "1", "ready"),
        ):
            with self.subTest(state=expected):
                self.adb.rows, self.adb.boot = rows, boot
                self.assertEqual(self.control.readiness().state, expected)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])

    def test_ready_is_decided_by_the_decoded_frame_not_the_reported_size(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        for size, frame, state, code in (
            # A tablet presentation or a not-yet-rotated game reports portrait
            # while it already renders the landscape frame the templates need.
            ("Physical size: 1080x1920", (1920, 1080), "ready", ""),
            ("Physical size: 1280x720", (1920, 1080), "ready", ""),
            (
                "Physical size: 2560x1440\nOverride size: 1920x1080",
                (1920, 1080),
                "ready",
                "",
            ),
            # The frame itself still gates readiness.
            ("Physical size: 1920x1080", (720, 1280), "booting", "frame_failed"),
            ("Physical size: 1920x1080", None, "booting", "frame_failed"),
            ("Physical size: 1080x1920", (1080, 1920), "booting", "frame_failed"),
        ):
            with self.subTest(size=size, frame=frame):
                self.adb.size, self.adb.frame = size, frame
                readiness = self.control.readiness()
                self.assertEqual(readiness.state, state)
                self.assertEqual(readiness.code, code)
        self.adb.size = "Physical size: 1920x1080"
        self.adb.frame = (1920, 1080)
        self.assertEqual(self.control.readiness().state, "ready")

    def test_reduced_adapter_without_display_probes_is_not_ready(self):
        class OnlyTransport:
            """An adapter that never implemented the optional readiness probes."""

            def resolve_adb(self, profile, timeout):
                return "verified-adb"

            def devices(self, adb_path, timeout):
                return [("USB-A", "device")]

            def boot_completed(self, adb_path, serial, timeout):
                return "1"

            def recover(self, adb_path, serial, timeout):
                return True

        session = DeviceSession(OnlyTransport(), self.simulator, clock=self.clock)
        control = DeviceControl(
            lambda: self.conf, Adapter(), session=session, preflight=Preflight()
        )
        readiness = control.readiness()
        self.assertEqual(readiness.state, "booting")
        # Without the frame probe there is no evidence the 1920x1080 templates
        # line up, so the target never reports ready.
        self.assertEqual(readiness.code, "frame_failed")

    def test_a_frame_that_is_not_ready_yet_is_waited_for_within_the_deadline(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        # A just-started game still renders portrait; it rotates a moment later.
        self.adb.frame = (1080, 1920)
        # The fixtures advance on the same call the session already makes.
        self.adb.on_recover = lambda: setattr(self.adb, "frame", (1920, 1080))
        result = self.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "USB-A")
        # Waiting for the canvas must not restart the instance.
        self.assertEqual(self.simulator.actions, [])

    def test_local_failure_allows_one_restart_and_verifies_new_endpoint(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]

        def restarted():
            self.simulator.state, self.simulator.serial = "running", "USB-B"
            self.adb.rows, self.adb.boot = [("USB-B", "device")], "1"

        self.simulator.on_start = restarted
        result = self.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "USB-B")
        self.assertEqual(self.simulator.actions, ["stop", "start"])
        self.assertLessEqual(self.session.actions, 3)

    def test_confirmed_stopped_instance_starts_once_without_stop(self):
        self.simulator.state = "stopped"

        def started():
            self.simulator.state = "running"
            self.simulator.serial = "127.0.0.1:16416"
            self.adb.rows = [("127.0.0.1:16416", "device")]
            self.adb.boot = "1"

        self.simulator.on_start = started
        result = self.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:16416")
        self.assertEqual(self.simulator.actions, ["start"])

    def test_local_transport_recovery_avoids_complete_restart(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]

        def reconnected():
            self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"

        self.adb.on_recover = reconnected
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.adb.actions, ["USB-A"])
        self.assertEqual(self.simulator.actions, [])

    def test_runtime_failure_rechecks_readiness_without_repeating_input(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        self.assertTrue(self.control.start().ok)
        delivered = []

        def input_failure(device):
            delivered.append(device.device_id)
            raise RuntimeError("delivery unknown")

        result = self.control.execute(input_failure)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "operation_failed")
        self.assertEqual(delivered, ["USB-A"])
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(result.readiness.state, "ready")

    def test_recovery_rebinds_existing_handle_to_same_instance_new_endpoint(self):
        self.conf.device.instance_id = "2"
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        before = self.conf.model_dump()
        handle = self.control.start().unwrap()
        self.simulator.serial = "USB-B"
        self.adb.rows = [("OTHER", "device"), ("USB-B", "offline")]

        def reconnect():
            self.adb.rows = [("USB-B", "device")]

        self.adb.on_recover = reconnect
        result = self.control.recover()
        self.assertTrue(result.ok, result.error)
        self.assertIs(result.value, handle)
        self.assertEqual(handle.device_id, "USB-B")
        self.assertEqual(self.conf.model_dump(), before)
        self.assertEqual(self.adb.actions, ["USB-B"])
        self.assertEqual(set(self.simulator.bindings), {("manual.other", "2")})

    def test_stopped_startup_has_one_deadline_and_no_restart(self):
        self.simulator.state = "stopped"
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "recovery_exhausted")
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertEqual(self.clock.now, 12)
        # An outer handler cannot open another recovery transaction.
        self.assertFalse(self.control.recover().ok)
        self.assertFalse(self.control.start().ok)
        self.assertEqual(self.simulator.actions, ["start"])

    def test_failed_final_validation_cannot_restart_twice(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(self.simulator.actions, ["stop", "start"])
        self.assertEqual(result.error.code, "recovery_exhausted")
        self.assertLessEqual(self.session.actions, 3)
        self.assertLessEqual(self.clock.now, 12)

    def test_no_action_can_begin_after_time_or_count_budget_is_exhausted(self):
        from arknights_mower.utils.device.session import RecoveryPolicy

        self.session.policy = RecoveryPolicy(attempts=0, timeout=12)
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]
        self.assertFalse(self.control.start().ok)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])

    def test_unauthorized_target_requires_explicit_retry_without_recovery(self):
        self.adb.rows = [("USB-A", "unauthorized"), ("OTHER", "device")]
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "device_unauthorized")
        self.assertEqual(result.readiness.state, "offline")
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])

    def test_boot_probe_failure_keeps_the_instance_and_recovers_in_place(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "device")]
        self.adb.boot = "0"
        probes = {"count": 0}

        def booting(*args):
            probes["count"] += 1
            # The probe itself only fails while the system is still booting.
            if probes["count"] == 1:
                raise ConnectionError("transport closed")
            return "1"

        self.adb.boot_completed = booting
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.simulator.actions, [])

    def test_failed_local_command_can_escalate_but_cannot_claim_success(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]
        self.adb.recover = lambda *args: False

        def restarted():
            self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"

        self.simulator.on_start = restarted
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.simulator.actions, ["stop", "start"])

    def test_changed_instance_state_does_not_stop_an_already_stopped_instance(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"

        def disconnected():
            self.simulator.state = "stopped"

        self.adb.on_recover = disconnected
        self.control.start()
        self.assertEqual(self.simulator.actions, ["start"])

    def test_failed_final_preflight_latches_until_explicit_close(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"

        class InvalidFrame(Preflight):
            def check(self, profile):
                return PreflightResult(
                    False,
                    "windows",
                    "failed",
                    profile.last_serial,
                    error=PreflightError("frame_failed", "invalid frame"),
                )

        self.control = DeviceControl(
            lambda: self.conf, Adapter(), session=self.session, preflight=InvalidFrame()
        )
        initial = self.control.start()
        observations = len(self.simulator.bindings)
        self.assertEqual(initial.error.code, "frame_failed")
        self.assertEqual(self.control.start().error.code, "frame_failed")
        self.assertEqual(self.control.recover().error.code, "frame_failed")
        self.assertEqual(len(self.simulator.bindings), observations)

    def test_final_validation_and_helper_open_share_remaining_deadline(self):
        from arknights_mower.utils.device.io_budget import io_timeout

        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        clock = self.clock
        observed = []

        class SlowPreflight(Preflight):
            def check(self, profile):
                observed.append(io_timeout(100))
                clock.sleep(10)
                return super().check(profile)

        class SlowAdapter(Adapter):
            def open_verified(self, configuration, result):
                observed.append(io_timeout(100))
                clock.sleep(3)
                return super().open_verified(configuration, result)

        self.control = DeviceControl(
            lambda: self.conf,
            SlowAdapter(),
            session=self.session,
            preflight=SlowPreflight(),
        )
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "recovery_exhausted")
        self.assertEqual(observed, [12, 2])
        self.assertFalse(self.control.active)

    def test_new_run_starts_after_the_previous_budget_expires(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        store, locks = Mock(), Mock()
        store.load.return_value = None
        self.control._preparation = PreparationSession(Mock(), store, locks)
        for delay in (0, 11, 12, 471):
            with self.subTest(delay=delay):
                self.clock.sleep(delay)
                with self.control.run():
                    result = self.control.start()
                    self.assertTrue(result.ok, result.error)
                    self.assertEqual(self.session.remaining(), 12)
                    self.assertEqual(result.serial, "USB-A")
                self.assertTrue(result.value.closed)
        self.assertEqual(locks.acquire.call_count, 4)
        self.assertEqual(locks.acquire.return_value.close.call_count, 4)

    def test_preparation_and_readiness_share_the_startup_budget(self):
        from arknights_mower.utils.device.io_budget import io_timeout

        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        observed = []
        store = Mock()

        def load(serial):
            observed.append(io_timeout(100))
            self.clock.sleep(5)
            return None

        store.load.side_effect = load
        self.control._preparation = PreparationSession(Mock(), store, Mock())
        original_inspect = self.simulator.inspect

        def inspect(profile, timeout):
            observed.append(timeout)
            return original_inspect(profile, timeout)

        self.simulator.inspect = inspect
        with self.control.run():
            result = self.control.start()
            self.assertTrue(result.ok, result.error)
            self.assertEqual(observed, [12, 7])
            self.assertEqual(self.session.remaining(), 7)

    def test_preparation_exhaustion_stops_before_device_probes(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        store, locks = Mock(), Mock()

        def load(serial):
            self.clock.sleep(12)
            return None

        store.load.side_effect = load
        self.control._preparation = PreparationSession(Mock(), store, locks)
        with self.control.run():
            result = self.control.start()
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "recovery_exhausted")
            self.assertEqual(self.simulator.bindings, [])
            self.assertEqual(self.adb.actions, [])
            locks.acquire.return_value.close.assert_called_once()

    def test_unconfirmed_stop_cancels_the_paired_launch(self):
        from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy

        class NeverStops(Simulator):
            """The manager acknowledged the stop but never reports it done."""

            def stop(self, profile, timeout):
                self.actions.append("stop")
                self.state = "starting"
                return True

        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]
        simulator = NeverStops()
        simulator.state, simulator.serial = "running", "USB-A"
        session = DeviceSession(
            self.adb,
            simulator,
            clock=self.clock,
            policy=RecoveryPolicy(
                attempts=3,
                timeout=60,
                local_wait=2,
                poll_interval=1,
                shutdown_wait=5,
            ),
        )
        control = DeviceControl(
            lambda: self.conf, Adapter(), session=session, preflight=Preflight()
        )
        result = control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "recovery_exhausted")
        # Waiting is bounded and a launch into the unconfirmed window is refused.
        self.assertEqual(simulator.actions, ["stop"])
        self.assertLessEqual(self.clock.now, 10)
        self.assertIn("实例关停未在 5 秒内确认", str(result.error.message))

    def test_incompatible_shared_server_never_becomes_an_emulator_restart(self):
        from arknights_mower.utils.device.adb_client.server import SharedADBError

        self.simulator.state, self.simulator.serial = "running", "USB-A"

        def incompatible(*args):
            raise SharedADBError("server version mismatch")

        self.adb.devices = incompatible
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "adb_server_unavailable")
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])

    def test_missing_canvas_is_reported_without_restarting_the_instance(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"

        def unavailable(*args):
            raise RuntimeError(
                "MuMu IPC 获取 Display ID 失败：实例显示 -1，游戏包 -1；"
                "请确认实例已启动并完成渲染后重试。"
            )

        self.adb.frame_size = unavailable
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "frame_failed")
        self.assertIn("请确认实例已启动并完成渲染后重试", result.error.message)
        # Restarting the emulator kills the game this gate needs: never do it.
        self.assertEqual(self.simulator.actions, [])

    def test_budget_exhaustion_reports_the_last_observed_reason(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        # The game never rotates to the canvas this transaction requires.
        self.adb.frame = (1080, 1920)
        result = self.control.start()
        self.assertFalse(result.ok)
        # The verdict names the condition to fix instead of only running out.
        self.assertEqual(result.error.code, "frame_failed")
        self.assertIn("截图实际帧不是横屏 1920×1080", result.error.message)

    def test_readiness_decisions_are_logged(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        with self.assertLogs("arknights_mower.utils.log", level="INFO") as logs:
            self.assertTrue(self.control.start().ok)
        text = "\n".join(logs.output)
        self.assertIn("使用设备", text)
        self.assertIn("连接成功：USB-A（实例状态未知，分辨率 1920x1080）", text)
        # One verdict per state change: the ready observation is not repeated as
        # a second connection line, and no attempt counter is printed.
        self.assertNotIn("设备已连接（USB-A）", text)
        self.assertNotIn("开始设备就绪检查", text)

    def test_a_stopped_instance_and_its_launch_are_one_line(self):
        self.simulator.state = "stopped"

        def started():
            self.simulator.state, self.simulator.serial = "running", "USB-A"
            self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"

        self.simulator.on_start = started
        with self.assertLogs("arknights_mower.utils.log", level="INFO") as logs:
            self.assertTrue(self.control.start().ok)
        text = "\n".join(logs.output)
        self.assertIn("模拟器未启动，正在启动模拟器...", text)
        self.assertNotIn("正在尝试恢复设备连接", text)
        self.assertNotIn("(1/3)", text)
        self.assertIn("连接成功：USB-A（实例运行中，分辨率 1920x1080）", text)

    def test_connecting_to_the_adb_port_is_one_line_without_counters(self):
        self.simulator.state, self.simulator.serial = "running", "USB-A"
        self.adb.rows = [("USB-A", "offline")]

        def reconnected():
            self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"

        self.adb.on_recover = reconnected
        with self.assertLogs("arknights_mower.utils.log", level="INFO") as logs:
            self.assertTrue(self.control.start().ok)
        text = "\n".join(logs.output)
        self.assertIn("设备离线，正在连接设备 ADB 端口...", text)
        self.assertNotIn("正在检测设备连接", text)
        self.assertNotIn("正在尝试恢复设备连接", text)

    def test_technical_observation_logged_to_debug(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        with self.assertLogs("arknights_mower.utils.log", level="DEBUG") as logs:
            self.session.bind(self.conf.device)
            self.session.observe()
        text = "\n".join(logs.output)
        self.assertIn("设备观察：state=ready", text)

    def test_a_new_binding_never_reports_the_previous_run_display(self):
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.session._display_size, [1920, 1080])
        # The next run binds the same session to an instance that is not running.
        # It has no display to report, and the previous run's reading was shown
        # as this observation's own, which is what a stopped instance printed.
        self.simulator.state, self.simulator.serial = "stopped", None
        with self.assertLogs("arknights_mower.utils.log", level="DEBUG") as logs:
            self.session.bind(self.session.profile)
            self.session.observe()
        text = "\n".join(logs.output)
        self.assertIn("设备观察：state=absent 实例=stopped", text)
        self.assertNotIn("显示=", text)


@pytest.mark.parametrize(
    "preset_id",
    [
        "windows.mumu12",
        "windows.ldplayer9",
        "windows.ldplayer14",
        "windows.nox",
        "macos.mumu_pro",
        "linux.waydroid",
        *sorted(CONFIRMED_START_PRESETS),
    ],
)
@pytest.mark.parametrize("phase", ["startup", "runtime"])
class TestStartupReconnectBudget:
    @pytest.fixture(autouse=True)
    def setup_session(self, preset_id, phase):
        self.clock, self.adb, self.simulator = Clock(), ADB(), Simulator()
        self.preset_id = preset_id
        self.launch_actions = [] if preset_id in CONFIRMED_START_PRESETS else ["start"]
        self.serial = "127.0.0.1:16416"
        self.other_serial = "127.0.0.1:16384"
        self.conf = Conf(
            device={
                "preset_id": preset_id,
                "instance_id": "1",
                "topology_fingerprint": "a" * 64,
                "last_serial": self.serial,
            }
        )
        self.profile_before = self.conf.device.model_dump()
        self.adb.rows = [(self.other_serial, "device"), (self.serial, "device")]
        self.adb.boot = "1"
        self.simulator.state, self.simulator.serial = "running", self.serial
        self.session = DeviceSession(
            self.adb,
            self.simulator,
            clock=self.clock,
            policy=RecoveryPolicy(
                attempts=3, timeout=180, local_wait=10, poll_interval=1
            ),
        )
        self.session.bind(self.conf.device)
        if phase == "runtime":
            assert self.session.ensure_ready().serial == self.serial
        self.clock.sleep(40)
        self.simulator.state = "stopped" if self.launch_actions else "starting"
        self.simulator.serial = None if self.launch_actions else self.serial
        self.adb.rows = [(self.other_serial, "device")]

        def started():
            self.simulator.state, self.simulator.serial = "starting", self.serial

        self.simulator.on_start = started

    def test_startup_readiness_retries_rejected_reconnect(self):
        attempts = []

        def reconnect(adb_path, serial, timeout):
            attempts.append((adb_path, serial, timeout, self.clock.now))
            self.clock.sleep(10.8)
            if len(attempts) == 1:
                return False
            self.adb.rows.append((self.serial, "device"))
            self.simulator.state = "running"
            return True

        self.adb.recover = Mock(side_effect=reconnect)
        assert self.session.ensure_ready().serial == self.serial
        assert self.simulator.actions == self.launch_actions
        assert self.session.actions == len(self.launch_actions) + 2
        assert len(attempts) == 2
        assert all(attempt[:2] == ("verified-adb", self.serial) for attempt in attempts)
        assert attempts[1][3] - attempts[0][3] >= 20.8
        assert attempts[1][2] < attempts[0][2]
        assert self.session._deadline == 220
        assert self.clock.now < 220
        assert set(self.simulator.bindings) == {(self.preset_id, "1")}
        assert self.conf.device.model_dump() == self.profile_before
        assert self.session.profile.model_dump() == self.profile_before
        assert (self.other_serial, "device") in self.adb.rows

    def test_rejected_reconnect_allows_verified_local_readiness(self):
        self.adb.recover = Mock(return_value=False)
        devices = self.adb.devices

        def ready_later(adb_path, timeout):
            if self.clock.now >= 44:
                self.adb.rows = [
                    (self.other_serial, "device"),
                    (self.serial, "device"),
                ]
                self.simulator.state = "running"
            return devices(adb_path, timeout)

        self.adb.devices = ready_later
        assert self.session.ensure_ready().serial == self.serial
        self.adb.recover.assert_called_once_with("verified-adb", self.serial, 180)
        assert self.clock.now == 44
        assert self.session.actions == len(self.launch_actions) + 1
        assert self.simulator.actions == self.launch_actions

    def test_reconnect_failure_keeps_one_deadline_and_target(self):
        self.adb.recover = Mock(return_value=False)
        with pytest.raises(SessionFailure) as failure:
            self.session.ensure_ready()
        assert "设备恢复时间预算已耗尽" in str(failure.value)
        assert failure.value.observation.serial == self.serial
        assert self.clock.now == 220
        assert self.session.actions == 3
        assert self.simulator.actions == self.launch_actions
        assert self.adb.recover.call_count == 3 - len(self.launch_actions)
        assert all(
            call.args[:2] == ("verified-adb", self.serial)
            for call in self.adb.recover.call_args_list
        )
        assert self.conf.device.model_dump() == self.profile_before
        assert self.adb.rows == [(self.other_serial, "device")]

    def test_binding_change_stops_before_reconnect_retry(self):
        from arknights_mower.utils.device.endpoint_identity import InstanceBindingError

        self.adb.recover = Mock(return_value=False)
        inspect = self.simulator.inspect

        def changed_binding(profile, timeout):
            if self.clock.now >= 42:
                raise InstanceBindingError("binding_changed", "实例身份已变化")
            return inspect(profile, timeout)

        self.simulator.inspect = changed_binding
        with pytest.raises(SessionFailure) as failure:
            self.session.ensure_ready()
        assert failure.value.observation.code == "binding_changed"
        self.adb.recover.assert_called_once()
        assert self.simulator.actions == self.launch_actions
        assert self.clock.now == 42

    def test_shared_adb_failure_is_terminal(self):
        from arknights_mower.utils.device.adb_client.server import SharedADBError

        self.adb.recover = Mock(side_effect=SharedADBError("共享 ADB 服务不可用"))
        with pytest.raises(SessionFailure) as failure:
            self.session.ensure_ready()
        assert failure.value.observation.code == "adb_server_unavailable"
        self.adb.recover.assert_called_once()
        assert self.simulator.actions == self.launch_actions
        assert self.clock.now == 40

    def test_shutdown_during_local_wait_prevents_retry(self):
        from arknights_mower.utils.csleep import MowerExit

        self.adb.recover = Mock(return_value=False)
        sleep = self.clock.sleep

        def stop_when_waiting(seconds):
            sleep(seconds)
            if seconds > 0:
                self.session.begin_shutdown()

        self.clock.sleep = stop_when_waiting
        with pytest.raises(MowerExit):
            self.session.ensure_ready()
        self.adb.recover.assert_called_once()
        assert self.simulator.actions == self.launch_actions
        assert self.clock.now == 41


@pytest.mark.parametrize("preset_id", sorted(CONFIRMED_START_PRESETS))
def test_stopped_confirmed_start_presets_never_reuse_launch_consent(preset_id):
    clock, adb, simulator = Clock(), ADB(), Simulator()
    profile = Conf(device={"preset_id": preset_id, "instance_id": "1"}).device
    simulator.state = "stopped"
    adb.recover = Mock()
    session = DeviceSession(adb, simulator, clock=clock)
    session.bind(profile)
    with pytest.raises(SessionFailure) as failure:
        session.ensure_ready()
    assert failure.value.observation.code == "start_confirmation_required"
    adb.recover.assert_not_called()
    assert simulator.actions == []


if __name__ == "__main__":
    unittest.main()
