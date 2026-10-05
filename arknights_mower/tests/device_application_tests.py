"""Device sessions are exercised at the application boundary without device I/O."""

import importlib
import sys
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.application import DeviceControl, LegacyDeviceAdapter
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.recovery import DeviceRecoveryError


class ManualDevice:
    def __init__(self, serial):
        self.device_id = serial
        self.closed = False
        self.points = []

    def tap(self, point):
        if self.closed:
            raise ConnectionError("session is closed")
        self.points.append(point)
        return point

    def close(self):
        if self.closed:
            raise RuntimeError("device already released")
        self.closed = True


class ManualAdapter:
    def open(self, configuration, *, connection_retries):
        return ManualDevice(configuration.adb)


class DeviceControlTests(unittest.TestCase):
    def test_preflight_command_timeout_unlocks_settings_and_preserves_target(self):
        import subprocess

        from arknights_mower.tests.device_preflight_tests import PreflightIO
        from arknights_mower.utils.config.conf import Conf
        from arknights_mower.utils.device.preflight import PreflightService

        serial = "127.0.0.1:16416"
        configuration = Conf(
            device={
                "preset_id": "windows.mumu12",
                "instance_id": "1",
                "last_serial": serial,
                "adb_path": "manual-adb",
                "screenshot_backend": "mumu_ipc",
                "touch_backend": "mumu_ipc",
            }
        )
        saved_profile = configuration.device.model_dump()
        io = PreflightIO()
        io.host = "windows"
        io.targets = [(serial, "device")]
        adapter = MagicMock()
        control = DeviceControl(
            lambda: configuration, adapter, preflight=PreflightService(io)
        )
        self.addCleanup(control.close)

        def capture(*args):
            self.assertTrue(control.settings_status()["active"])
            raise subprocess.TimeoutExpired(
                ["MuMuManager.exe", "info", "-v", "all"], 0.5
            )

        io.capture_frame = capture
        with patch("arknights_mower.utils.device.application.logger.info") as info:
            result = control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "frame_failed")
        self.assertEqual(result.status, "failed")
        self.assertFalse(control.settings_status()["active"])
        self.assertIsNotNone(control.settings_status()["error"])
        self.assertEqual(configuration.device.model_dump(), saved_profile)
        adapter.open_verified.assert_not_called()
        info.assert_called_once_with("正在检查设备 ADB、游戏安装与截图...")

    def test_production_adapter_retains_discovery_on_one_attempt_startup(self):
        for online_serial in ("127.0.0.1:16384", "127.0.0.1:16416"):
            with (
                self.subTest(online_serial=online_serial),
                patch.object(config.conf, "adb", "127.0.0.1:16384"),
                patch.object(config.conf.droidcast, "enable", False),
                patch.object(config.droidcast, "process", None),
                patch.object(config.stop_mower, "is_set", return_value=False),
                patch.object(ADBClient, "_Client__check_adb", return_value=True),
                patch.object(ADBClient, "_Client__exec"),
                patch(
                    "arknights_mower.utils.device.adb_client.core.Session"
                ) as session,
                patch("arknights_mower.utils.device.adb_client.core.csleep"),
                patch(
                    "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port",
                    return_value=online_serial,
                ),
                patch(
                    "arknights_mower.utils.simulator.restart_simulator",
                    side_effect=AssertionError("an online target must not restart"),
                ),
                patch.object(
                    ADBClient, "cmd_shell", return_value="Physical size: 1920x1080"
                ),
                patch.object(Device, "Control"),
                patch("arknights_mower.utils.device.device.atexit.register"),
            ):
                # Keep the legacy ADB target selection/recovery path real; only
                # replace hardware I/O and touch helper construction.
                session.return_value.devices_list.return_value = [
                    (online_serial, "device")
                ]
                control = DeviceControl(lambda: config.conf, LegacyDeviceAdapter())
                self.addCleanup(control.close)
                result = control.start(connection_retries=1)
                self.assertTrue(result.ok, result.error)
                self.assertEqual(result.serial, online_serial)
                self.assertIsInstance(result.value, Device)
                self.assertTrue(control.close().ok)

    def test_manual_session_runs_existing_operations_and_closes(self):
        configuration = SimpleNamespace(adb="127.0.0.1:16384")
        control = DeviceControl(lambda: configuration, ManualAdapter())

        opened = control.start(connection_retries=1)
        self.assertTrue(opened.ok)
        self.assertEqual(opened.status, "connected")
        self.assertEqual(opened.serial, "127.0.0.1:16384")
        self.assertEqual(
            control.execute(lambda device: device.tap((480, 270))).value, (480, 270)
        )
        self.assertTrue(control.close().ok)
        self.assertTrue(opened.value.closed)
        self.assertEqual(control.status().status, "closed")
        self.assertEqual(
            control.execute(lambda device: device.tap((0, 0))).error.code, "not_started"
        )

    def test_repeated_close_does_not_release_a_device_again(self):
        control = DeviceControl(lambda: SimpleNamespace(adb="USB-123"), ManualAdapter())
        control.start()
        self.assertTrue(control.close().ok)
        self.assertTrue(control.close().ok)

    def test_start_errors_are_structured_and_preserve_legacy_exceptions(self):
        for error, code in (
            (ConnectionError("offline"), "start_failed"),
            (MowerExit(), "cancelled"),
            (DeviceRecoveryError("exhausted"), "recovery_exhausted"),
        ):
            with self.subTest(code=code):

                class FailingAdapter:
                    def open(self, configuration, *, connection_retries):
                        raise error

                control = DeviceControl(
                    lambda: SimpleNamespace(adb="USB-123"), FailingAdapter()
                )
                result = control.start()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.serial, "USB-123")
                with self.assertRaises(type(error)) as caught:
                    result.unwrap()
                self.assertIs(caught.exception, error)
                self.assertTrue(control.close().ok)

    def test_configuration_is_read_again_after_close(self):
        configuration = SimpleNamespace(adb="USB-123")
        control = DeviceControl(lambda: configuration, ManualAdapter())
        previous = control.start().value
        control.close()
        configuration.adb = "USB-456"
        self.assertEqual(control.start().serial, "USB-456")
        self.assertTrue(previous.closed)

    def test_configuration_read_failure_does_not_report_the_previous_target(self):
        available = True

        def read_configuration():
            if not available:
                raise ValueError("invalid configuration")
            return SimpleNamespace(adb="USB-123")

        control = DeviceControl(read_configuration, ManualAdapter())
        control.start()
        control.close()
        available = False
        result = control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "configuration_failed")
        self.assertEqual(result.serial, "")

    def test_cleanup_failure_is_observable_and_does_not_repeat_cleanup(self):
        class BrokenCleanupDevice(ManualDevice):
            def close(self):
                super().close()
                raise OSError("helper did not exit")

        class BrokenCleanupAdapter:
            def open(self, configuration, *, connection_retries):
                return BrokenCleanupDevice(configuration.adb)

        control = DeviceControl(
            lambda: SimpleNamespace(adb="USB-123"), BrokenCleanupAdapter()
        )
        control.start()
        result = control.close()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "close_failed")
        self.assertEqual(result.error.message, "helper did not exit")
        self.assertEqual(control.close(), result)

    def test_failed_input_is_reported_without_repeating_the_operation(self):
        control = DeviceControl(lambda: SimpleNamespace(adb="USB-123"), ManualAdapter())
        device = control.start().value

        def uncertain_input(device):
            device.tap((50, 60))
            raise ConnectionError("input result unknown")

        result = control.execute(uncertain_input)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "operation_failed")
        self.assertEqual(result.error.message, "input result unknown")
        self.assertEqual(device.points, [(50, 60)])
        self.assertTrue(control.close().ok)

    def test_results_follow_the_endpoint_changed_by_existing_device_recovery(self):
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds):
                control = DeviceControl(
                    lambda: SimpleNamespace(adb="127.0.0.1:16384"), ManualAdapter()
                )
                control.start()

                def recover(device):
                    device.device_id = "127.0.0.1:16416"
                    if not succeeds:
                        raise ConnectionError("operation failed after reconnect")

                self.assertEqual(control.execute(recover).serial, "127.0.0.1:16416")
                self.assertEqual(control.status().serial, "127.0.0.1:16416")
                self.assertEqual(control.start().serial, "127.0.0.1:16416")
                self.assertEqual(control.close().serial, "127.0.0.1:16416")


class SessionResolutionTests(unittest.TestCase):
    def test_verified_runtime_package_never_changes_saved_selections(self):
        from arknights_mower.tests.device_session_tests import ADB, Clock, Simulator
        from arknights_mower.utils.config.conf import Conf
        from arknights_mower.utils.device.preflight import PreflightResult
        from arknights_mower.utils.device.session import DeviceSession

        for initialization_fails in (False, True):
            with self.subTest(initialization_fails=initialization_fails):
                conf = Conf(
                    device={
                        "last_serial": "USB-A",
                        "game_package": "com.hypergryph.arknights",
                        "game_package_confirmed": True,
                    }
                )
                before = conf.model_dump()
                adb, simulator = ADB(), Simulator()
                adb.rows, adb.boot = [("USB-B", "device")], "1"
                simulator.state, simulator.serial = "running", "USB-B"
                preflight = SimpleNamespace(
                    check=lambda profile, **kwargs: PreflightResult(
                        True,
                        "windows",
                        "ready",
                        profile.last_serial,
                        adb_path="verified-adb",
                        game_package="com.hypergryph.arknights.bilibili",
                    )
                )
                control = DeviceControl(
                    lambda: conf,
                    LegacyDeviceAdapter(),
                    preflight=preflight,
                    session=DeviceSession(adb, simulator, clock=Clock()),
                )
                with (
                    patch.object(
                        Device,
                        "start",
                        side_effect=RuntimeError("touch failed")
                        if initialization_fails
                        else None,
                    ),
                    patch("arknights_mower.utils.device.device.atexit.register"),
                ):
                    result = control.start()
                self.assertEqual(result.ok, not initialization_fails)
                self.assertEqual(conf.model_dump(), before)
                self.assertEqual(
                    conf.updated({"debug": True}).device.model_dump(), before["device"]
                )
                if result.ok:
                    device = result.value
                    device.run = MagicMock()
                    device.exit()
                    device.run.assert_called_with(
                        "am force-stop com.hypergryph.arknights.bilibili"
                    )
                    self.assertEqual(
                        device.game_package, "com.hypergryph.arknights.bilibili"
                    )
                    self.assertEqual(device.profile.last_serial, "USB-B")
                    with patch.object(config, "conf", conf):
                        device.launch()
                    device.run.assert_called_with(
                        f"am start -n com.hypergryph.arknights.bilibili/{config.APP_ACTIVITY_NAME}"
                    )
                control.close()

    def test_manual_preset_passes_the_bound_session_adb_to_preflight(self):
        from arknights_mower.tests.device_session_tests import (
            ADB,
            Adapter,
            Clock,
            Simulator,
        )
        from arknights_mower.utils.config.conf import Conf
        from arknights_mower.utils.device.session import DeviceSession

        conf = Conf(device={"last_serial": "USB-A"})
        adb, simulator = ADB(), Simulator()
        adb.rows, adb.boot = [("USB-A", "device")], "1"
        calls = []

        class RecordingPreflight:
            def check(self, profile, **options):
                calls.append((profile.last_serial, options.get("resolved_adb")))
                return SimpleNamespace(
                    ok=False, error=SimpleNamespace(message="incomplete")
                )

        session = DeviceSession(adb, simulator, clock=Clock())
        control = DeviceControl(
            lambda: conf,
            Adapter(),
            preflight=RecordingPreflight(),
            session=session,
        )
        self.assertFalse(control.start().ok)
        # capture and readiness can only agree if both use the bound resolution.
        self.assertEqual(calls, [("USB-A", "verified-adb")])


class WorkerDeviceSessionTests(unittest.TestCase):
    def setUp(self):
        # SKLand performs unrelated network I/O at import time.
        with patch.dict(sys.modules, {"arknights_mower.utils.skland": MagicMock()}):
            self.main = importlib.import_module("arknights_mower.__main__")
        self.control = DeviceControl(
            lambda: SimpleNamespace(adb="USB-123"), ManualAdapter()
        )
        self.enterContext(
            patch.object(self.main, "device_control", self.control, create=True)
        )
        self.enterContext(patch.object(self.main, "resource_task_session", nullcontext))

    def test_worker_exit_closes_the_opened_session(self):
        opened = self.control.start()
        with patch.object(self.main, "_main", return_value="finished"):
            self.assertEqual(self.main.main({}), "finished")
        self.assertTrue(opened.value.closed)

    def test_worker_failure_or_cancellation_closes_the_opened_session(self):
        for error in (RuntimeError("worker failed"), MowerExit(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                opened = self.control.start()
                with (
                    patch.object(self.main, "_main", side_effect=error),
                    self.assertRaises(type(error)) as caught,
                ):
                    self.main.main({})
                self.assertIs(caught.exception, error)
                self.assertTrue(opened.value.closed)

    def test_initialization_injects_a_session_and_releases_the_previous_one(self):
        previous = self.control.start().value
        with (
            patch.object(
                self.main,
                "BaseSchedulerSolver",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch(
                "arknights_mower.utils.operators.build_global_plan",
                return_value=({}, {}),
            ) as build_plan,
        ):
            scheduler = self.main.initialize([])
        build_plan.assert_called_once_with(include_source=True)
        self.assertTrue(previous.closed)
        self.assertIs(scheduler.device, self.control.start().value)
        self.assertEqual(scheduler.device.tap((200, 100)), (200, 100))
        self.control.close()

    def test_initialization_failure_closes_the_session_before_retry(self):
        with (
            patch.object(
                self.main,
                "BaseSchedulerSolver",
                side_effect=RuntimeError("recognition failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "recognition failed"),
        ):
            self.main.initialize([])
        self.assertEqual(self.control.status().status, "closed")


if __name__ == "__main__":
    unittest.main()
