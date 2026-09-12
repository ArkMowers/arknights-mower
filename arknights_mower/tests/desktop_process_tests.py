import logging
import logging.handlers
import os
import select
import signal
import subprocess
import sys
import threading
import unittest
from queue import Empty
from unittest import mock

from arknights_mower.utils import desktop_process
from webview_ui import close_child

ECHO_WORKER = """
import sys
from arknights_mower.utils.desktop_process import run_worker
def echo(channel, initial):
    channel.send(initial)
    while True:
        message = channel.recv()
        if message == 'exit':
            return
        channel.send(message)
run_worker(echo, sys.argv[1])
"""


LOG_WORKER = """
import sys
from arknights_mower.utils.desktop_process import run_worker
def log_message(channel, message, log_queue=None):
    from arknights_mower.utils import log
    log.bind_mp_queue(log_queue)
    assert log.fhlr is None, "child must not open runtime.log"
    log.logger.warning(message)
    channel.send("logged")
    assert channel.recv() == "exit"
run_worker(log_message, *sys.argv[1:])
"""


def watched_manager_helper(ready):
    import time

    desktop_process.watch_parent()
    ready.send(os.getpid())
    while True:
        time.sleep(1)


MANAGER_PARENT = """
import multiprocessing as mp
from arknights_mower.tests.desktop_process_tests import watched_manager_helper
parent, child = mp.Pipe()
helper = mp.get_context("spawn").Process(target=watched_manager_helper, args=(child,), daemon=True)
helper.start()
print(parent.recv(), flush=True)
helper.join()
"""


@unittest.skipIf(sys.platform == "win32", "macOS helper uses inherited POSIX pipes")
class DesktopProcessTests(unittest.TestCase):
    def test_real_worker_roundtrip_timeout_and_graceful_cleanup(self):
        # Exercise the real inherited pipe and process lifecycle, substituting
        # an echo handler for Cocoa so this check also runs without a display.
        popen = subprocess.Popen

        def launch(command, **options):
            return popen([sys.executable, "-c", ECHO_WORKER, command[-1]], **options)

        with mock.patch.object(desktop_process.subprocess, "Popen", side_effect=launch):
            process, channel = desktop_process.start_worker("window", "中文路径")
        try:
            self.assertEqual(channel.get(timeout=5), "中文路径")
            with self.assertRaises(Empty):
                channel.get(timeout=0.01)
            channel.put({"command": "folder", "path": "新建目录"})
            self.assertEqual(
                channel.get(timeout=5),
                {"command": "folder", "path": "新建目录"},
            )
            close_child(process, channel)
            self.assertEqual(process.process.returncode, 0)
            self.assertFalse(process.is_alive())
            self.assertTrue(channel.connection.closed)
        finally:
            close_child(process)

    def test_reopened_workers_deliver_logs_to_one_listener_without_tracker(self):
        from multiprocessing.resource_tracker import _resource_tracker

        before = _resource_tracker._pid
        records = []
        received = threading.Event()

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())
                received.set()

        queue = desktop_process.log_channel()
        listener = logging.handlers.QueueListener(queue, Handler())
        listener.start()
        popen = subprocess.Popen

        def launch(command, **options):
            return popen([sys.executable, "-c", LOG_WORKER, *command[-2:]], **options)

        try:
            for message in ("首次打开窗口", "重新打开窗口"):
                received.clear()
                with mock.patch.object(
                    desktop_process.subprocess, "Popen", side_effect=launch
                ):
                    process, channel = desktop_process.start_worker(
                        "window", message, log_queue=queue
                    )
                try:
                    self.assertEqual(channel.get(timeout=10), "logged")
                    self.assertTrue(received.wait(5))
                    self.assertEqual(records[-1], message)
                    close_child(process, channel)
                    self.assertEqual(process.process.returncode, 0)
                    self.assertFalse(queue.writer.closed)
                finally:
                    close_child(process)
            self.assertEqual(_resource_tracker._pid, before)
        finally:
            listener.stop()
            queue.close()
        self.assertTrue(queue.connection.closed)
        self.assertTrue(queue.writer.closed)

    def test_manager_helper_exits_when_its_parent_is_killed(self):
        controller = subprocess.Popen(
            [sys.executable, "-c", MANAGER_PARENT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        helper_pid = None
        try:
            self.assertTrue(select.select([controller.stdout], [], [], 10)[0])
            helper_pid = int(controller.stdout.readline().strip())
            controller.kill()
            # The helper inherits stdout/stderr. EOF proves it exited too;
            # daemon=True alone leaves these pipes open after the parent dies.
            controller.communicate(timeout=8)
        finally:
            if helper_pid is not None:
                try:
                    os.kill(helper_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if controller.poll() is None:
                controller.kill()
            controller.communicate(timeout=5)

    def test_failed_launch_closes_both_pipe_descriptors(self):
        parent, child = desktop_process.Pipe()
        with (
            mock.patch.object(desktop_process, "Pipe", return_value=(parent, child)),
            mock.patch.object(
                desktop_process.subprocess, "Popen", side_effect=OSError("cannot start")
            ),
            self.assertRaisesRegex(OSError, "cannot start"),
        ):
            desktop_process.start_worker("tray", "name", 1234, "http://localhost")
        self.assertTrue(parent.closed)
        self.assertTrue(child.closed)

    def test_macos_launcher_does_not_start_multiprocessing_tracker(self):
        import webview_ui

        with (
            mock.patch.object(sys, "platform", "darwin"),
            mock.patch.object(desktop_process, "start_worker") as launch,
            mock.patch.object(
                webview_ui.mp, "Process", side_effect=AssertionError("extra process")
            ),
            mock.patch.object(
                webview_ui.mp, "Queue", side_effect=AssertionError("shared semaphore")
            ),
        ):
            webview_ui.start_desktop_child("tray", "test", 1234, "http://localhost")
        launch.assert_called_once_with("tray", "test", 1234, "http://localhost")


if __name__ == "__main__":
    unittest.main()
