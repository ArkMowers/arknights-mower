import os
import sys
import threading
import unittest
from contextlib import ExitStack
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from arknights_mower import utils
from arknights_mower.tests.device_application_tests import ManualAdapter, ManualDevice
from arknights_mower.utils import desktop_process, log, network, path, software_update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.lifecycle import Phase, Shutdown


class SharedShutdownTests(unittest.TestCase):
    def test_deferred_cleanup_is_retried_once_while_the_session_closes_for_good(self):
        events = []
        hold, entered = threading.Event(), threading.Event()

        class Adapter(ManualAdapter):
            def open(self, configuration, *, connection_retries):
                device = ManualDevice(configuration.adb)
                device.close = lambda: events.append("device released")
                return device

        control = DeviceControl(
            lambda: SimpleNamespace(
                adb="USB-123",
                device=DeviceProfile(
                    preset_id="manual.physical",
                    last_serial="USB-123",
                    adb_path="test-adb",
                ),
            ),
            Adapter(),
            preparation=SimpleNamespace(
                begin=lambda *args, **kwargs: None,
                close=lambda: events.append("restore"),
            ),
        )
        control.start(preparation_serial="USB-123").unwrap()

        def operation(active):
            entered.set()
            hold.wait(2)
            events.append("worker returned")

        worker = threading.Thread(target=lambda: control.execute(operation))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            # The gate closes while the worker owns the configuration lock, so
            # the running operation has no chance to compensate on its return.
            control.begin_shutdown()
            began = monotonic()
            outcome = control.close(timeout=0.01)
            self.assertEqual(outcome.error.code, "close_timeout")
            # A deferred close still returns at once instead of waiting for the
            # worker that owns the configuration lock.
            self.assertLess(monotonic() - began, 0.5)
            self.assertEqual(events, [])
        finally:
            hold.set()
            worker.join(2)
            # The exit sequence joins the worker, then retries the deferred
            # release once before the process is allowed to leave.
            outcome = control.final_release()
        self.assertTrue(outcome.ok, outcome.error)
        self.assertEqual(events, ["worker returned", "restore", "device released"])
        self.assertTrue(control.close().ok)
        self.assertEqual(events.count("device released"), 1)

    def test_final_release_keeps_the_record_when_the_owner_never_returns(self):
        entered, release = threading.Event(), threading.Event()
        events = []
        control = DeviceControl(
            lambda: SimpleNamespace(adb="USB-123"),
            ManualAdapter(),
        )
        device = control.start().value
        device.close = lambda: events.append("device released")

        def operation(active):
            entered.set()
            release.wait(3)

        worker = threading.Thread(target=lambda: control.execute(operation))
        worker.start()
        # Cleanups run in reverse registration order: release first, then join.
        self.addCleanup(worker.join, 2)
        self.addCleanup(release.set)
        try:
            self.assertTrue(entered.wait(1))
            control.begin_shutdown()
            self.assertEqual(control.close(timeout=0.01).error.code, "close_timeout")
            began = monotonic()
            outcome = control.final_release()
            self.assertEqual(outcome.error.code, "close_timeout")
            self.assertLess(monotonic() - began, 1.5)
            self.assertEqual(events, [])
        finally:
            release.set()
            worker.join(2)
        # The owner returned, so the record the exit attempt could not consume
        # is still there for the next release.
        self.assertTrue(control.final_release().ok)
        self.assertEqual(events, ["device released"])


class TrayRecoveryTests(unittest.TestCase):
    def test_tray_crash_or_launch_failure_keeps_instance_alive_until_explicit_exit(
        self,
    ):
        import webview_ui

        for fails_to_launch in (False, True):
            with self.subTest(fails_to_launch=fails_to_launch), ExitStack() as stack:
                conf = Mock()
                conf.conf.webview.tray = True
                conf.conf.webview.token = ""
                conf.conf.start_automatically = False
                conf.stop_mower = threading.Event()
                server = Mock(app=Flask(__name__))
                exit_events = []
                shutdown = Shutdown()

                def register_shutdown(lifecycle):
                    lifecycle.own("signal", conf.stop_mower.set, Phase.SIGNAL)
                    lifecycle.own(
                        "worker", lambda: server._stop_mower(timeout=10), Phase.WORKER
                    )

                server.register_shutdown.side_effect = register_shutdown

                def stop_worker(timeout):
                    self.assertTrue(conf.stop_mower.is_set())
                    self.assertEqual(timeout, 10)
                    exit_events.append("worker restored")
                    return True

                server._stop_mower.side_effect = stop_worker
                registration = Mock(record={})
                registration.shutdown_requested.return_value = False
                parent, child = desktop_process.Pipe()
                broken = desktop_process.Channel(parent)
                child.close()
                stack.callback(broken.close)
                clock = [0]
                launches = []
                recovered = Mock()
                recovered.get.return_value = "exit"

                def launch(*args, **kwargs):
                    self.assertFalse(conf.stop_mower.is_set())
                    registration.close.assert_not_called()
                    self.assertEqual(args[0], "tray")
                    launches.append(clock[0])
                    if len(launches) == 1:
                        if fails_to_launch:
                            raise OSError("tray executable unavailable")
                        return Mock(), broken
                    self.assertGreaterEqual(clock[0], 5)
                    return Mock(), recovered

                patches = [
                    patch.dict(
                        os.environ,
                        {
                            "MOWER_BACKGROUND": "1",
                            "MOWER_MANAGED": "0",
                            "MOWER_RESTART_JOB": "",
                            "MOWER_RESTART_PORT": "58100",
                        },
                    ),
                    patch.dict(sys.modules, {"server": server}),
                    patch.object(sys, "argv", ["mower"]),
                    patch.object(sys, "platform", "darwin"),
                    patch.object(utils, "config", conf),
                    patch.object(path, "global_space", ""),
                    patch.object(runtime, "read_json", return_value={}),
                    patch.object(runtime, "active_job", return_value=False),
                    patch.object(
                        runtime, "RuntimeRegistration", return_value=registration
                    ),
                    patch.object(network, "is_port_in_use", side_effect=[False, True]),
                    patch.object(webview_ui, "exit_if_webview_backend_missing"),
                    patch.object(webview_ui, "close_child"),
                    patch.object(webview_ui, "start_http_server"),
                    patch("arknights_mower.utils.lifecycle.shutdown", shutdown),
                    patch.object(webview_ui, "start_desktop_child", side_effect=launch),
                    patch.object(software_update, "request_auto_check"),
                    patch.object(desktop_process, "log_channel", return_value=Mock()),
                    patch.multiple(
                        log,
                        init_file_logging=Mock(),
                        start_mp_listener=Mock(),
                        close_logging=Mock(
                            side_effect=lambda: exit_events.append("logging stopped")
                        ),
                        close_mp_logging=Mock(),
                        close_screenshot_store=Mock(
                            side_effect=lambda: exit_events.append("screenshots closed")
                        ),
                        mp_listener=Mock(
                            stop=lambda: exit_events.append("logging stopped")
                        ),
                    ),
                    patch("threading.Thread"),
                    patch("time.monotonic", side_effect=lambda: clock[0]),
                    patch(
                        "time.sleep",
                        side_effect=lambda seconds: clock.__setitem__(
                            0, clock[0] + seconds
                        ),
                    ),
                ]
                for item in patches:
                    stack.enter_context(item)
                webview_ui.run_desktop()
                self.assertTrue(server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"])
                self.assertTrue(server.app.token)
                self.assertEqual(len(launches), 2)
                recovered.get.assert_called_once()
                self.assertTrue(conf.stop_mower.is_set())
                self.assertEqual(
                    exit_events,
                    ["worker restored", "screenshots closed", "logging stopped"],
                )
                registration.close.assert_called_once()
