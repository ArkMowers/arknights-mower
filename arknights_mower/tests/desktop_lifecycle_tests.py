import os
import sys
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from flask import Flask

from arknights_mower import utils
from arknights_mower.utils import desktop_process, log, network, path, software_update
from arknights_mower.utils import update_runtime as runtime


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
                    patch.object(webview_ui, "start_desktop_child", side_effect=launch),
                    patch.object(software_update, "request_auto_check"),
                    patch.object(desktop_process, "log_channel", return_value=Mock()),
                    patch.multiple(
                        log,
                        init_file_logging=Mock(),
                        start_mp_listener=Mock(),
                        mp_listener=Mock(),
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
                self.assertEqual(len(launches), 2)
                recovered.get.assert_called_once()
                self.assertTrue(conf.stop_mower.is_set())
                registration.close.assert_called_once()
