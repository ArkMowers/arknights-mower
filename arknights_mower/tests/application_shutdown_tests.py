"""Application exit contract with injected resource/process adapters."""

import os
import unittest
from threading import Event, Thread
from unittest.mock import patch

from arknights_mower.utils.lifecycle import Phase, Shutdown


class ApplicationShutdownTests(unittest.TestCase):
    def test_failure_does_not_skip_later_resources_or_repeat_cleanup(self):
        closed = []
        shutdown = Shutdown()
        shutdown.own("ui", lambda: closed.append("ui"), Phase.UI)

        def restore():
            closed.append("restore")
            raise OSError("device offline")

        shutdown.own("preparation", restore, Phase.DEVICE)
        shutdown.own("helpers", lambda: closed.append("helpers"), Phase.DEVICE)
        shutdown.own(
            "screenshots", lambda: closed.append("screenshots"), Phase.SCREENSHOTS
        )
        shutdown.close("tray")
        shutdown.close("ctrl_c")
        self.assertEqual(closed, ["restore", "helpers", "screenshots", "ui"])
        self.assertEqual(len(shutdown.errors), 1)
        self.assertTrue(shutdown.closing)

    def test_owner_mismatch_is_not_cleaned(self):
        closed = []
        shutdown = Shutdown()
        resource = shutdown.own("foreign", lambda: closed.append("wrong"), Phase.UI)
        resource.owner_pid = os.getpid() + 1
        shutdown.close()
        self.assertEqual(closed, [])

    def test_partial_initialization_and_late_registration_are_closed_once(self):
        closed = []
        shutdown = Shutdown()
        shutdown.close("startup_failure")
        shutdown.own("late", lambda: closed.append("late"), Phase.UI)
        shutdown.own("late", lambda: closed.append("duplicate"), Phase.UI)
        shutdown.close()
        self.assertEqual(closed, ["late"])

    def test_concurrent_exit_waits_for_the_single_cleanup(self):
        entered, release, returned = Event(), Event(), Event()
        shutdown = Shutdown()

        def cleanup():
            entered.set()
            release.wait(2)

        shutdown.own("worker", cleanup, Phase.WORKER)
        first = Thread(target=shutdown.close)
        second = Thread(target=lambda: (shutdown.close(), returned.set()))
        first.start()
        self.assertTrue(entered.wait(1))
        second.start()
        self.assertFalse(returned.wait(0.05))
        release.set()
        first.join(1)
        second.join(1)
        self.assertTrue(returned.is_set())


class Child:
    def __init__(self, alive=False, exits_on_join=True):
        self.pid = 123
        self.alive = alive
        self.exits_on_join = exits_on_join
        self.events = []

    def is_alive(self):
        self.events.append("liveness")
        return self.alive

    def join(self, timeout):
        self.events.append("join")
        if self.exits_on_join:
            self.alive = False

    def terminate(self):
        self.events.append("terminate")
        self.alive = False

    def kill(self):
        self.events.append("kill")
        self.alive = False

    def close(self):
        self.events.append("handle")


class ChildShutdownTests(unittest.TestCase):
    def setUp(self):
        self.shutdown = Shutdown()
        self.enterContext(
            patch("arknights_mower.utils.lifecycle.shutdown", self.shutdown)
        )

    def test_exited_and_joined_children_are_not_terminated(self):
        from webview_ui import close_child, own_child

        for alive in (False, True):
            child = Child(alive)
            own_child(child)
            close_child(child)
            close_child(child)
            self.assertNotIn("terminate", child.events)
            self.assertEqual(child.events.count("join"), 1)
            self.assertEqual(child.events.count("handle"), 1)

    def test_join_timeout_checks_liveness_before_terminate(self):
        from webview_ui import close_child, own_child

        child = Child(True, False)
        own_child(child)
        close_child(child)
        self.assertEqual(child.events[:3], ["join", "liveness", "terminate"])

    def test_unregistered_or_changed_process_is_untouched(self):
        from webview_ui import close_child, own_child

        foreign = Child(True)
        close_child(foreign)
        self.assertEqual(foreign.events, [])
        own_child(foreign)
        foreign.pid = 456
        close_child(foreign)
        self.assertEqual(foreign.events, [])

    def test_pipe_read_end_failure_still_closes_write_end_once(self):
        from unittest.mock import Mock

        from arknights_mower.utils.desktop_process import Channel

        reader, writer = Mock(), Mock()
        reader.close.side_effect = OSError("read handle failure")
        channel = Channel(reader, writer)
        with self.assertRaises(OSError):
            channel.close()
        channel.close()
        reader.close.assert_called_once()
        writer.close.assert_called_once()

    def test_failed_initial_pipe_send_joins_exited_owned_child_without_terminate(self):
        from unittest.mock import Mock

        from arknights_mower.utils import desktop_process

        child = Mock(pid=123)
        child.poll.return_value = 0
        with (
            patch.object(desktop_process.subprocess, "Popen", return_value=child),
            patch.object(desktop_process.Channel, "send", side_effect=OSError("pipe")),
            self.assertRaisesRegex(OSError, "pipe"),
        ):
            desktop_process.start_worker("window", "test")
        child.wait.assert_called_once_with(1)
        child.terminate.assert_not_called()
        child.kill.assert_not_called()

    def test_initial_send_and_pipe_close_failure_still_reaps_child(self):
        from unittest.mock import Mock

        from arknights_mower.utils import desktop_process

        process = Mock(pid=123)
        process.poll.return_value = 0
        parent, child = Mock(), Mock()
        child.fileno.return_value = 7
        parent.send.side_effect = OSError("startup send failed")
        parent.close.side_effect = OSError("pipe close failed")
        with (
            patch.object(desktop_process, "Pipe", return_value=(parent, child)),
            patch.object(desktop_process.subprocess, "Popen", return_value=process),
            self.assertRaisesRegex(OSError, "startup send failed") as failure,
        ):
            desktop_process.start_worker("window", "test")
        self.assertIn("pipe close failed", " ".join(failure.exception.__notes__))
        process.wait.assert_called_once_with(1)
        process.terminate.assert_not_called()
        parent.close.assert_called_once()
        child.close.assert_called_once()


class DesktopExitTests(unittest.TestCase):
    def test_every_exit_and_partial_startup_use_registered_cleanup(self):
        import sys
        from contextlib import ExitStack
        from types import SimpleNamespace
        from unittest.mock import Mock

        import webview_ui
        from arknights_mower import utils
        from arknights_mower.utils import log, network, path, software_update
        from arknights_mower.utils import update_runtime as runtime

        for entry in ("tray", "window", "ctrl_c", "startup_failure", "fatal_session"):
            with self.subTest(entry=entry), ExitStack() as stack:
                shutdown = Shutdown()
                stopped = Event()
                events = []
                conf = SimpleNamespace(
                    conf=SimpleNamespace(
                        webview=SimpleNamespace(
                            tray=entry != "window", token="", port=58111
                        ),
                        start_automatically=False,
                    ),
                    stop_mower=stopped,
                    webview_process=None,
                    parent_conn=None,
                )
                registration = Mock(record={})
                registration.shutdown_requested.return_value = False
                server = Mock()
                server.app.config = {}

                def register(lifecycle):
                    lifecycle.own("gate", lambda: events.append("gate"), Phase.GATE)
                    lifecycle.own("signal", stopped.set, Phase.SIGNAL)
                    lifecycle.own("io", lambda: events.append("io"), Phase.INTERRUPT)
                    lifecycle.own(
                        "worker", lambda: events.append("worker"), Phase.WORKER
                    )
                    lifecycle.own(
                        "restore", lambda: events.append("restore"), Phase.DEVICE
                    )

                server.register_shutdown.side_effect = register

                def message(timeout):
                    if entry == "ctrl_c":
                        raise KeyboardInterrupt()
                    if entry == "fatal_session":
                        shutdown.request("fatal_session")
                        return ""
                    return "exit"

                def launch(kind, *args, **kwargs):
                    child = Child(alive=kind != "window")
                    channel = Mock()
                    channel.get.side_effect = message
                    # Production factory registers each allocation immediately.
                    webview_ui.own_child(child)
                    webview_ui.own_channel(channel)
                    return child, channel

                patches = [
                    patch.dict(
                        os.environ,
                        {
                            "MOWER_BACKGROUND": "0",
                            "MOWER_MANAGED": "0",
                            "MOWER_RESTART_PORT": "58111",
                            "MOWER_RESUME_MODE": "",
                        },
                    ),
                    patch.dict(sys.modules, {"server": server}),
                    patch.object(sys, "argv", ["mower"]),
                    patch.object(sys, "platform", "win32"),
                    patch.object(utils, "config", conf),
                    patch.object(path, "global_space", ""),
                    patch.object(runtime, "read_json", return_value={}),
                    patch.object(runtime, "active_job", return_value=False),
                    patch.object(
                        runtime, "RuntimeRegistration", return_value=registration
                    ),
                    patch.object(
                        network,
                        "is_port_in_use",
                        side_effect=[entry == "startup_failure", True],
                    ),
                    patch.object(webview_ui, "exit_if_webview_backend_missing"),
                    patch.object(webview_ui, "start_http_server"),
                    patch.object(webview_ui, "start_desktop_child", side_effect=launch),
                    patch.object(software_update, "request_auto_check"),
                    patch("arknights_mower.utils.lifecycle.shutdown", shutdown),
                    patch.multiple(
                        log,
                        init_file_logging=Mock(),
                        start_mp_listener=Mock(),
                        close_mp_logging=Mock(),
                        close_logging=Mock(),
                        close_screenshot_store=Mock(
                            side_effect=lambda: events.append("screenshots")
                        ),
                    ),
                ]
                for item in patches:
                    stack.enter_context(item)
                if entry == "startup_failure":
                    with self.assertRaisesRegex(RuntimeError, "已被占用"):
                        webview_ui.run_desktop()
                    self.assertEqual(events, ["screenshots"])
                else:
                    webview_ui.run_desktop()
                    self.assertTrue(stopped.is_set())
                    self.assertEqual(
                        events, ["gate", "io", "worker", "restore", "screenshots"]
                    )
                self.assertTrue(shutdown.closing)
                registration.close.assert_called_once()
                self.assertEqual(shutdown.reason, entry)
                self.assertEqual(shutdown.errors, [])


if __name__ == "__main__":
    unittest.main()
