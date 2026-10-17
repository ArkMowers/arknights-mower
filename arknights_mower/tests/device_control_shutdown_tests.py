"""Application shutdown gates and ordered compensation at the public boundary."""

import unittest
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

from arknights_mower.tests.device_application_tests import ManualAdapter, ManualDevice
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import (
    ADB,
    Adapter,
    Clock,
    Preflight,
    Simulator,
)
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import (
    PreflightError,
    PreflightResult,
    PreflightService,
)
from arknights_mower.utils.device.screenshot_backend import ScreenshotFailure
from arknights_mower.utils.device.session import DeviceSession
from arknights_mower.utils.device.touch_backend import TouchFailure


def physical_configuration():
    return Conf(
        device={
            "preset_id": "manual.physical",
            "last_serial": "USB-123",
            "adb_path": "manual-adb",
            "screenshot_backend": "adb_gzip",
        }
    )


class DeviceControlShutdownTests(unittest.TestCase):
    def test_shutdown_permanently_rejects_device_start_and_recovery(self):
        control = DeviceControl(lambda: SimpleNamespace(adb="USB-123"), ManualAdapter())
        device = control.start().unwrap()
        control.begin_shutdown()
        self.assertEqual(control.start().error.code, "session_closing")
        self.assertEqual(control.recover().error.code, "session_closing")
        self.assertTrue(control.close().ok)
        self.assertTrue(device.closed)
        self.assertEqual(control.start().error.code, "session_closing")

    def test_shutdown_does_not_wait_for_live_io_and_compensates_when_it_returns(self):
        entered, release = Event(), Event()
        events = []
        preparation = SimpleNamespace(
            begin=lambda *args: None, close=lambda: events.append("restore")
        )
        control = DeviceControl(
            physical_configuration,
            ManualAdapter(),
            preparation=preparation,
        )
        device = control.start(preparation_serial="USB-123").unwrap()
        original_close = device.close

        def close_device():
            events.append("helpers")
            original_close()

        device.close = close_device

        def operation(device):
            entered.set()
            release.wait(2)

        worker = Thread(target=lambda: control.execute(operation))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            began = monotonic()
            control.begin_shutdown()
            self.assertEqual(control.start().error.code, "session_closing")
            self.assertEqual(control.recover().error.code, "session_closing")
            result = control.close(timeout=0.01)
            self.assertEqual(result.error.code, "close_timeout")
            self.assertLess(monotonic() - began, 0.5)
            self.assertEqual(events, [])
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(events, ["restore", "helpers"])
        self.assertTrue(control.close().ok)
        self.assertEqual(events, ["restore", "helpers"])

    def test_startup_failure_restores_before_helpers_and_notifies_shutdown_once(self):
        events = []
        devices = []
        failure = RuntimeError("invalid input surface")

        class Adapter:
            def open_verified(self, configuration, result):
                device = ManualDevice(result.serial)
                device.close = lambda: events.append("helpers")
                devices.append(device)
                return device

        def invalid_surface():
            raise failure

        control = DeviceControl(
            physical_configuration,
            Adapter(),
            preparation=SimpleNamespace(
                prepared_size=None,
                begin=lambda *args: None,
                validate=invalid_surface,
                close=lambda: events.append("restore"),
            ),
            preflight=SimpleNamespace(
                resolve_adb=lambda profile: "verified-adb",
                check=lambda *args, **kwargs: PreflightResult(
                    True,
                    "windows",
                    "ready",
                    "USB-123",
                    adb_path="verified-adb",
                    game_package="com.hypergryph.arknights",
                ),
            ),
            on_fatal=lambda reason: events.append(reason),
        )
        result = control.start(preparation_serial="USB-123")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "start_failed")
        self.assertIs(result.error.cause, failure)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].device_id, "USB-123")
        # An unclassified internal fault requests the coordinator, which joins
        # the worker before its DEVICE phase restores and releases resources.
        self.assertEqual(events, ["device_start_failed"])
        self.assertTrue(control.shutdown_requested)
        self.assertTrue(control.close().ok)
        self.assertEqual(events, ["device_start_failed", "restore", "helpers"])
        self.assertTrue(control.close().ok)
        self.assertEqual(control.start().error.code, "session_closing")
        self.assertEqual(events, ["device_start_failed", "restore", "helpers"])

    def test_input_and_capture_failures_are_reported_without_application_shutdown(self):
        profile = Conf().device
        for failure in (TouchFailure, ScreenshotFailure):
            with self.subTest(failure=failure.__name__):
                notifications = []
                control = DeviceControl(
                    lambda: SimpleNamespace(adb="USB-123"),
                    ManualAdapter(),
                    on_fatal=notifications.append,
                )
                control.start().unwrap()
                error = failure(profile, "windows", RuntimeError("backend failed"))

                def fail(device):
                    raise error

                result = control.execute(fail)
                self.assertIs(result.error.cause, error)
                # The half-open session releases its handle, but a backend the
                # user can reselect never asks the application to exit.
                self.assertEqual(notifications, [])
                self.assertFalse(control.shutdown_requested)
                self.assertTrue(control.close().ok)
                self.assertEqual(notifications, [])

    def test_preflight_rejection_releases_resources_without_application_shutdown(self):
        events = []

        class Adapter:
            def open_verified(self, configuration, result):
                raise AssertionError("rejected preflight must not create helpers")

        class RejectedPreflight:
            def host_platform(self):
                return "windows"

            def resolve_adb(self, profile):
                return profile.adb_path

            def check(self, profile, **options):
                return PreflightResult(
                    False,
                    "windows",
                    "failed",
                    profile.last_serial,
                    error=PreflightError("invalid_size", "必须为横屏 1920×1080"),
                )

        conf = physical_configuration()
        control = DeviceControl(
            lambda: conf,
            Adapter(),
            preparation=SimpleNamespace(
                prepared_size=None,
                begin=lambda *args: None,
                close=lambda: events.append("restore"),
                status=lambda: None,
            ),
            preflight=RejectedPreflight(),
            on_fatal=lambda reason: events.append(reason),
        )
        result = control.start(preparation_serial="USB-123")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_size")
        # The half-open session releases what it already owns, without asking
        # the application to exit.
        self.assertEqual(events, ["restore"])
        self.assertFalse(control.shutdown_requested)
        self.assertFalse(control.active)
        self.assertEqual(control.settings_status()["status"], "failed")
        self.assertTrue(control.close().ok)
        self.assertEqual(events, ["restore"])
        # The session stays failed for retry instead of reporting an exit.
        self.assertEqual(
            control.start(preparation_serial="USB-123").error.code, "invalid_size"
        )
        self.assertFalse(control.shutdown_requested)
        self.assertEqual(events, ["restore", "restore"])

    def test_unreadable_size_verdict_reports_without_application_shutdown(self):
        adb, simulator = ADB(), Simulator()
        adb.rows, adb.boot = [("USB-A", "device")], "1"
        # Session readiness accepts the reported size, so the read-only preflight
        # is where an unreadable size is still rejected.
        adb.size = "Physical size: not-a-size"
        io = PreflightIO()
        io.targets, io.boot = [("USB-A", "device")], "1"
        io.size = "Physical size: not-a-size"
        io.paths.add("verified-adb")
        conf = Conf(device={"last_serial": "USB-A", "adb_path": "manual-adb"})
        notifications = []
        control = DeviceControl(
            lambda: conf,
            Adapter(),
            preflight=PreflightService(io),
            session=DeviceSession(adb, simulator, clock=Clock()),
            on_fatal=notifications.append,
        )
        result = control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_size")
        # A device the user has to reconfigure is reported, never an exit.
        self.assertEqual(notifications, [])
        self.assertFalse(control.shutdown_requested)
        self.assertEqual(simulator.actions, [])

    def test_shutdown_rejects_explicit_simulator_start_without_reading_configuration(
        self,
    ):
        def unavailable_configuration():
            self.fail("shutdown must not inspect or start a device")

        control = DeviceControl(unavailable_configuration, ManualAdapter())
        control.begin_shutdown()
        for start in (
            control.start_avd,
            control.start_redroid,
            control.start_genymotion,
        ):
            self.assertEqual(start().error.code, "session_closing")
        self.assertFalse(control.stop_owned_avd())

    def test_interrupt_failure_does_not_skip_restoration_or_helpers(self):
        events = []
        preparation = SimpleNamespace(
            begin=lambda *args: None, close=lambda: events.append("restore")
        )
        control = DeviceControl(
            physical_configuration,
            ManualAdapter(),
            preparation=preparation,
        )
        device = control.start(preparation_serial="USB-123").unwrap()

        def interrupt():
            events.append("interrupt")
            raise OSError("interrupt failed")

        device.interrupt_io = interrupt
        device.close = lambda: events.append("helpers")
        control.begin_shutdown()
        control.interrupt_io()
        self.assertTrue(control.close().ok)
        self.assertTrue(control.close().ok)
        self.assertEqual(events, ["interrupt", "restore", "helpers"])

    def test_shutdown_during_adapter_start_releases_the_late_device_once(self):
        entered, release = Event(), Event()
        devices = []

        class Adapter:
            def open(self, configuration, *, connection_retries):
                entered.set()
                release.wait(2)
                device = ManualDevice(configuration.adb)
                devices.append(device)
                return device

        control = DeviceControl(lambda: SimpleNamespace(adb="USB-123"), Adapter())
        results = []
        worker = Thread(target=lambda: results.append(control.start()))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            control.begin_shutdown()
            self.assertEqual(control.close(timeout=0.01).error.code, "close_timeout")
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(results[0].ok)
        self.assertTrue(devices[0].closed)
        self.assertTrue(control.close().ok)

    def test_restoration_failure_does_not_skip_owned_helper_cleanup(self):
        events = []

        def restore():
            events.append("restore")
            raise OSError("device offline; compensation retained")

        control = DeviceControl(
            physical_configuration,
            ManualAdapter(),
            preparation=SimpleNamespace(begin=lambda *args: None, close=restore),
        )
        device = control.start(preparation_serial="USB-123").unwrap()
        device.close = lambda: events.append("helpers")
        self.assertFalse(control.close().ok)
        self.assertFalse(control.close().ok)
        self.assertEqual(events, ["restore", "helpers"])

    def test_session_shutdown_stops_recovery_before_any_adapter_io(self):
        session = DeviceSession(None, None)
        profile = Conf().device
        session.bind(profile)
        session.begin_shutdown()
        with self.assertRaises(MowerExit):
            session.ensure_ready()
        with self.assertRaises(MowerExit):
            session.bind(profile)

    def test_recovery_verdict_keeps_the_device_and_does_not_request_shutdown(self):
        adb, simulator = ADB(), Simulator()
        adb.rows, adb.boot = [("USB-A", "device")], "1"
        conf = Conf(device={"last_serial": "USB-A"})
        notifications = []
        control = DeviceControl(
            lambda: conf,
            Adapter(),
            preflight=Preflight(),
            session=DeviceSession(adb, simulator, clock=Clock()),
            on_fatal=notifications.append,
        )
        device = control.start().unwrap()
        adb.rows = [("USB-A", "unauthorized")]
        self.assertEqual(control.recover().error.code, "device_unauthorized")
        # An unauthorized transport is reported for the user to fix; the session
        # releases what it owns without asking the application to exit.
        self.assertEqual(notifications, [])
        self.assertFalse(control.shutdown_requested)
        self.assertFalse(device.closed)
        self.assertEqual(simulator.actions, [])
        # The application stays alive: the verdict is latched for the user to fix
        # and reported again instead of the process having requested an exit.
        self.assertEqual(control.start().error.code, "device_unauthorized")
        self.assertFalse(control.shutdown_requested)
        self.assertTrue(control.close().ok)

    def test_worker_finally_leaves_verdict_cleanup_to_the_session_owner(self):
        from contextlib import nullcontext
        from unittest.mock import patch

        from arknights_mower import __main__ as mower

        notifications = []
        control = DeviceControl(
            lambda: SimpleNamespace(adb="USB-123"),
            ManualAdapter(),
            on_fatal=notifications.append,
        )
        devices = []

        def work(*args):
            device = control.start().unwrap()
            devices.append(device)

            def fail(device):
                raise TouchFailure(Conf().device, "windows", RuntimeError("input"))

            control.execute(fail)

        with (
            patch.object(mower, "device_control", control),
            patch.object(mower, "_main", side_effect=work),
            patch.object(mower, "resource_task_session", side_effect=nullcontext),
        ):
            mower.main({})
        # A verdict the user can act on releases the handle and records it,
        # without asking the application to exit.
        self.assertEqual(notifications, [])
        self.assertFalse(control.shutdown_requested)
        self.assertTrue(devices[0].closed)
        self.assertTrue(control.close().ok)


if __name__ == "__main__":
    unittest.main()
