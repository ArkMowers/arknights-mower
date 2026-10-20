import os
import sys
import threading
import unittest
from contextlib import ExitStack
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask, request

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
                conf.conf.resource_update.enable = False
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


class DesktopStartupTests(unittest.TestCase):
    def launch(
        self,
        *,
        automatic=True,
        resource=False,
        background=False,
        restart=False,
        resume_run="0",
        resume_mode="",
        resource_result=None,
        existing_install=False,
        cancel=None,
        token="",
        manager_port="0",
        restart_port="58100",
        updates_enabled=True,
        instance_name="",
        managed=True,
    ):
        import server as task_server
        import webview_ui

        with ExitStack() as stack:
            config = Mock()
            config.conf.webview.tray = True
            config.conf.webview.token = token
            config.conf.start_automatically = automatic
            config.conf.resource_update.enable = resource
            config.conf.resource_update.auto_update = resource
            config.updates_enabled = updates_enabled
            config.stop_mower = threading.Event()
            server = Mock(app=Flask(__name__))
            server.http_start = Mock()
            server.browser_open = Mock()
            tray_channel = Mock()
            tray_channel.get.side_effect = [
                "toggle",
                "toggle",
                "browser",
                "browser",
                "exit",
            ]
            server.desktop_child = Mock(return_value=(Mock(), tray_channel))
            server.start = Mock(wraps=task_server.start)
            stack.enter_context(patch.object(task_server, "app", server.app))
            server.resource_update.running.return_value = existing_install
            server.stop.return_value = "true"
            registration = Mock(record={})
            registration.shutdown_requested.return_value = False
            registration.take_commands.side_effect = [
                ["toggle"],
                ["toggle"],
                ["browser"],
                ["browser"],
                ["exit"],
            ]
            shutdown = Shutdown()
            events = []
            server.resource_update.thread.join.side_effect = lambda: events.append(
                "existing install finished"
            )

            def check_resource():
                events.append("check resource")
                if isinstance(resource_result, Exception):
                    raise resource_result
                return {"update_available": True}

            def install_resource():
                self.assertEqual(request.method, "POST")
                events.append("install resource")
                if cancel == "stop":
                    config.stop_mower.set()
                elif cancel == "shutdown":
                    shutdown.request("test")
                return resource_result or {"ok": True}

            server.get_resource_version.side_effect = check_resource
            server.install_resource.side_effect = install_resource

            def start_worker(mode, *, automatic=False):
                self.assertTrue(automatic)
                events.append(("start", mode))
                return True

            stack.enter_context(
                patch.object(task_server, "_start_mower", side_effect=start_worker)
            )
            workers = []

            def make_thread(*args, **kwargs):
                target = kwargs["target"]
                workers.append(target)
                return Mock(start=target)

            patches = [
                patch.dict(
                    os.environ,
                    {
                        "MOWER_BACKGROUND": "1" if background else "0",
                        "MOWER_MANAGED": "1" if managed else "0",
                        "MOWER_RESTART_JOB": "fixture" if restart else "",
                        "MOWER_RESTART_PORT": restart_port,
                        "MOWER_MANAGER_PORT": manager_port,
                        "MOWER_RESUME_RUN": resume_run,
                        "MOWER_RESUME_MODE": resume_mode,
                    },
                ),
                patch.dict(sys.modules, {"server": server}),
                patch.object(sys, "argv", ["mower", "", instance_name]),
                patch.object(sys, "platform", "darwin"),
                patch.object(utils, "config", config),
                patch.object(path, "global_space", ""),
                patch.object(runtime, "read_json", return_value={}),
                patch.object(runtime, "active_job", side_effect=[False, True, False]),
                patch.object(runtime, "unified_managers", return_value=[{}]),
                patch.object(runtime, "RuntimeRegistration", return_value=registration),
                patch.object(network, "is_port_in_use", side_effect=[False, True]),
                patch.object(webview_ui, "exit_if_webview_backend_missing"),
                patch.object(webview_ui, "close_child"),
                patch.object(webview_ui, "start_http_server", server.http_start),
                patch("arknights_mower.utils.lifecycle.shutdown", shutdown),
                patch.object(webview_ui, "start_desktop_child", server.desktop_child),
                patch.object(software_update, "request_auto_check"),
                patch.object(desktop_process, "log_channel", return_value=Mock()),
                patch.multiple(
                    log,
                    init_file_logging=Mock(),
                    start_mp_listener=Mock(),
                    close_logging=Mock(),
                    close_mp_logging=Mock(),
                    close_screenshot_store=Mock(),
                ),
                patch("threading.Thread", side_effect=make_thread),
                patch("time.sleep"),
                patch("webbrowser.open", server.browser_open),
            ]
            mocks = [stack.enter_context(item) for item in patches]
            webview_ui.run_desktop()
            self.assertTrue(server.app.config["DESKTOP_STARTUP_HANDLED"])
            if cancel != "shutdown":
                self.assertEqual(mocks[-1].call_count, 2)
            # Closing/reopening the window and opening browser tabs never queue
            # another worker; shutdown also cancels a delayed worker callback.
            self.assertLessEqual(len(workers), 1)
            for worker in workers:
                worker()
            return events, server

    def test_normal_autostart_admits_task_through_the_start_route(self):
        events, server = self.launch()
        self.assertEqual(events, [("start", "0")])
        server.start.assert_called_once_with("0", automatic=True)

    def test_browser_commands_and_tray_launch_keep_the_session_url_without_instance_name(
        self,
    ):
        instance_name = "测试实例 & + / ?"
        for managed in (False, True):
            for token in ("", "remote-secret"):
                with self.subTest(managed=managed, token=token):
                    _, server = self.launch(
                        automatic=False,
                        background=True,
                        managed=managed,
                        token=token,
                        instance_name=instance_name,
                    )
                    expected_url = f"http://127.0.0.1:58100?token={server.app.token}"
                    self.assertEqual(
                        [call.args for call in server.browser_open.call_args_list],
                        [(expected_url,), (expected_url,)],
                    )
                    launches = server.desktop_child.call_args_list
                    windows = [call for call in launches if call.args[0] == "window"]
                    self.assertEqual(len(windows), 1)
                    self.assertEqual(windows[0].args[2], instance_name)
                    self.assertEqual(windows[0].args[5], expected_url)
                    trays = [call for call in launches if call.args[0] == "tray"]
                    self.assertEqual(len(trays), int(not managed))
                    for call in trays:
                        self.assertEqual(call.args[1], instance_name)
                        self.assertEqual(call.args[3], expected_url)

    def test_managed_desktop_honors_explicit_and_random_ports_with_or_without_token(
        self,
    ):
        for token in ("", "remote-secret"):
            for manager_port, expected_port in (("58001", 58001), ("0", 32100)):
                with self.subTest(token=token, manager_port=manager_port):
                    with patch.object(network, "get_new_port", return_value=32100):
                        _, server = self.launch(
                            automatic=False,
                            token=token,
                            manager_port=manager_port,
                            restart_port="",
                        )
                    server.http_start.assert_called_once_with(
                        server.app, "0.0.0.0" if token else "127.0.0.1", expected_port
                    )

    def test_resource_install_finishes_before_the_single_process_start(self):
        for result in ({"ok": True}, {"ok": False}):
            with self.subTest(result=result):
                events, server = self.launch(resource=True, resource_result=result)
                self.assertEqual(
                    events, ["check resource", "install resource", ("start", "0")]
                )
                server.start.assert_called_once_with("0", automatic=True)

    def test_resource_check_error_keeps_existing_resources_and_starts(self):
        events, server = self.launch(resource=True, resource_result=OSError("offline"))
        self.assertEqual(events, ["check resource", ("start", "0")])
        server.install_resource.assert_not_called()

    def test_cached_page_install_finishes_before_process_task_admission(self):
        events, server = self.launch(
            resource=True, resource_result={"ok": False}, existing_install=True
        )
        self.assertEqual(
            events,
            [
                "check resource",
                "install resource",
                "existing install finished",
                ("start", "0"),
            ],
        )
        server.start.assert_called_once_with("0", automatic=True)

    def test_stop_or_shutdown_during_resource_install_cancels_pending_start(self):
        for cancel in ("stop", "shutdown"):
            with self.subTest(cancel=cancel):
                events, server = self.launch(resource=True, cancel=cancel)
                self.assertEqual(events, ["check resource", "install resource"])
                server.start.assert_not_called()

    def test_resource_automation_is_independent_of_task_autostart(self):
        events, server = self.launch(automatic=False, resource=True)
        self.assertEqual(events, ["check resource", "install resource"])
        server.start.assert_not_called()

    def test_disabled_updates_preserve_automatic_task_start_without_resource_maintenance(
        self,
    ):
        events, server = self.launch(resource=True, updates_enabled=False)
        self.assertEqual(events, [("start", "0")])
        server.get_resource_version.assert_not_called()
        server.install_resource.assert_not_called()

    def test_restart_policy_overrides_the_saved_autostart_option(self):
        for automatic in (False, True):
            for resume_run, mode, expected in (
                ("0", "preserve", None),
                ("1", "preserve", "2"),
                ("1", "", "2"),
                ("0", "0", "0"),
                ("0", "1", "1"),
            ):
                with self.subTest(
                    automatic=automatic, resume_run=resume_run, mode=mode
                ):
                    events, server = self.launch(
                        automatic=automatic,
                        restart=True,
                        resume_run=resume_run,
                        resume_mode=mode,
                    )
                    self.assertEqual(
                        events, [] if expected is None else [("start", expected)]
                    )
                    self.assertEqual(server.start.call_count, int(expected is not None))

    def test_software_update_autostart_uses_the_saved_option_and_normal_mode(self):
        for automatic in (False, True):
            with self.subTest(automatic=automatic):
                events, server = self.launch(
                    automatic=automatic,
                    restart=True,
                    resource=True,
                )
                expected = ["check resource", "install resource"]
                if automatic:
                    expected.append(("start", "0"))
                self.assertEqual(events, expected)
                self.assertEqual(server.start.call_count, int(automatic))
