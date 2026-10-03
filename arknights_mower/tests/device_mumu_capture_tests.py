"""Bounded persistent MuMu capture, replacing process and native I/O offline."""

import ctypes
import os
import unittest
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from arknights_mower.tests.device_mumu_frame_tests import NativeRenderer
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.mumu12ipc.capture import (
    MuMuCaptureSession,
    _capture_worker,
)
from arknights_mower.utils.device.mumu12ipc.core import MuMuIpcError, bind_display


class MuMuCaptureSessionTests(unittest.TestCase):
    def setUp(self):
        self.context = self.enterContext(
            patch(
                "arknights_mower.utils.device.native_capture.multiprocessing.get_context"
            )
        ).return_value
        self.context.RawArray.side_effect = lambda kind, size: (kind * size)()
        self.connection = MagicMock()
        self.now = 0.0

        def poll(timeout):
            if not self.connection.poll.return_value:
                self.now += timeout
            return self.connection.poll.return_value

        self.connection.poll.side_effect = poll
        self.enterContext(
            patch(
                "arknights_mower.utils.device.native_capture.time.monotonic",
                lambda: self.now,
            )
        )
        self.child = MagicMock()
        self.context.Pipe.return_value = self.connection, self.child
        self.process = self.context.Process.return_value
        self.process.pid = 123
        self.process.is_alive.return_value = False
        self.session = MuMuCaptureSession(
            SimpleNamespace(
                installation_path="MuMu",
                manager_path="MuMu/MuMuManager.exe",
                instance_id="3",
                game_package="com.hypergryph.arknights",
            )
        )
        self.addCleanup(self.session.close)

    def test_blocked_native_capture_obeys_remaining_budget_without_retry(self):
        self.connection.poll.return_value = False
        with device_io_budget(lambda: 1.25):
            with self.assertRaises(TimeoutError):
                self.session.capture_frame()
        self.assertLessEqual(self.connection.poll.call_args.args[0], 1.25)
        self.connection.send.assert_called_once_with("capture")
        self.process.start.assert_called_once_with()
        with self.assertRaises(TimeoutError):
            self.session.capture_frame()
        self.connection.send.assert_called_once_with("capture")

    def test_successive_frames_reuse_worker_and_preserve_previous_pixels(self):
        self.connection.poll.return_value = True
        self.connection.recv.return_value = ("ok", "", None, None)

        def write_frame(command):
            if command == "capture":
                buffer = self.context.Process.call_args.kwargs["args"][3]
                buffer[0] = self.connection.send.call_count * 20

        self.connection.send.side_effect = write_frame
        first = self.session.capture_frame()
        second = self.session.capture_frame()
        self.assertEqual(first.shape, (1080, 1920, 3))
        self.assertEqual(first.dtype, np.uint8)
        self.assertEqual(first[0, 0, 0], 20)
        self.assertEqual(second[0, 0, 0], 40)
        self.process.start.assert_called_once_with()
        self.context.Process.assert_called_once()
        self.assertLessEqual(self.connection.poll.call_args.args[0], 10)

    def test_dead_worker_has_actionable_error_and_is_not_restarted(self):
        self.connection.poll.return_value = True
        self.connection.recv.side_effect = EOFError()
        with self.assertRaisesRegex(MuMuIpcError, "工作进程"):
            self.session.capture_frame()
        self.process.start.assert_called_once_with()

    def test_close_reports_worker_still_alive_after_bounded_escalation(self):
        self.connection.poll.return_value = False
        with self.assertRaises(TimeoutError):
            self.session.capture_frame()
        self.process.is_alive.return_value = True
        with self.assertRaisesRegex(MuMuIpcError, "退出"):
            self.session.close()
        self.process.terminate.assert_called_once_with()
        self.process.kill.assert_called_once_with()
        self.process.close.assert_not_called()
        self.connection.close.assert_called_once_with()
        for call in self.process.join.call_args_list:
            self.assertLessEqual(call.kwargs["timeout"], 1)

    def test_native_failure_keeps_return_code_dimensions_and_selected_session(self):
        self.connection.poll.return_value = True
        self.connection.recv.return_value = ("error", "native -5", -5, (1280, 720))
        with self.assertRaises(MuMuIpcError) as caught:
            self.session.capture_frame()
        self.assertEqual(caught.exception.return_code, -5)
        self.assertEqual(caught.exception.actual_size, (1280, 720))
        with self.assertRaises(MuMuIpcError) as repeated:
            self.session.capture_frame()
        self.assertIs(repeated.exception, caught.exception)
        self.process.start.assert_called_once_with()
        self.connection.send.assert_called_once_with("capture")

    def test_close_is_idempotent_and_does_not_terminate_finished_worker(self):
        self.connection.poll.return_value = True
        self.connection.recv.return_value = ("ok", "", None, None)
        self.session.capture_frame()
        self.session.close()
        self.session.close()
        self.process.join.assert_called_once_with(timeout=1)
        self.process.terminate.assert_not_called()
        self.process.kill.assert_not_called()
        self.process.close.assert_called_once_with()
        self.child.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()
        with self.assertRaisesRegex(MuMuIpcError, "关闭"):
            self.session.capture_frame()

    def test_owner_mismatch_preserves_worker_pipe_and_native_session(self):
        self.connection.poll.return_value = True
        self.connection.recv.return_value = ("ok", "", None, None)
        self.session.capture_frame()
        self.session.owner_pid = os.getpid() + 1
        self.session.close()
        self.process.join.assert_not_called()
        self.process.terminate.assert_not_called()
        self.process.close.assert_not_called()
        self.connection.close.assert_not_called()
        with self.assertRaisesRegex(MuMuIpcError, "所有权"):
            self.session.capture_frame()
        self.session.owner_pid = os.getpid()
        self.session.close()
        self.process.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_shutdown_does_not_send_to_a_native_worker_that_might_not_read(self):
        self.connection.poll.return_value = False
        with self.assertRaises(TimeoutError):
            self.session.capture_frame()
        self.connection.send.reset_mock()
        self.session.close()
        self.connection.send.assert_not_called()
        self.connection.close.assert_called_once_with()

    def test_interrupt_wakes_capture_but_retains_worker_for_final_cleanup(self):
        polling = Event()
        tick = Event()

        def poll(timeout):
            polling.set()
            tick.wait(0.01)
            return False

        self.connection.poll.side_effect = poll
        errors = []

        def capture():
            try:
                self.session.capture_frame()
            except Exception as exc:
                errors.append(exc)

        worker = Thread(target=capture)
        worker.start()
        self.addCleanup(worker.join, 1)
        self.assertTrue(polling.wait(1))
        self.session.interrupt()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.process.join.assert_not_called()
        self.connection.close.assert_not_called()
        self.session.close()
        self.process.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_failed_process_start_releases_both_pipe_ends_and_process(self):
        self.process.start.side_effect = OSError("spawn failed")
        self.process.pid = None
        with self.assertRaisesRegex(OSError, "spawn failed"):
            self.session.capture_frame()
        self.session.close()
        self.child.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()
        self.process.close.assert_called_once_with()
        self.process.join.assert_not_called()
        self.process.terminate.assert_not_called()

    def test_failed_terminate_still_attempts_kill_and_releases_finished_process(self):
        self.connection.poll.return_value = False
        with self.assertRaises(TimeoutError):
            self.session.capture_frame()
        self.process.is_alive.return_value = True
        self.process.terminate.side_effect = OSError("terminate failed")

        def killed():
            self.process.is_alive.return_value = False

        self.process.kill.side_effect = killed
        with self.assertRaisesRegex(OSError, "terminate failed"):
            self.session.close()
        self.process.kill.assert_called_once_with()
        self.process.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()


class MuMuDisplayBindingTests(unittest.TestCase):
    """The instance display keeps IPC usable while the game is not running.

    MuMu resolves a display per package: binding the game package returned -1
    for a closed game even though the emulator itself rendered 1920x1080.
    """

    PACKAGE = "com.hypergryph.arknights"

    def test_instance_display_is_preferred_over_the_game_package(self):
        dll = MagicMock()
        dll.nemu_get_display_id.side_effect = [0, 5]
        self.assertEqual(bind_display(dll, 7, self.PACKAGE), 0)
        self.assertEqual(dll.nemu_get_display_id.call_count, 1)
        self.assertEqual(dll.nemu_get_display_id.call_args.args, (7, b"", 0))

    def test_game_package_remains_the_fallback(self):
        dll = MagicMock()
        dll.nemu_get_display_id.side_effect = [-1, 5]
        self.assertEqual(bind_display(dll, 7, self.PACKAGE), 5)
        self.assertEqual(
            dll.nemu_get_display_id.call_args.args, (7, self.PACKAGE.encode(), 0)
        )

    def test_no_available_display_reports_both_codes(self):
        dll = MagicMock()
        dll.nemu_get_display_id.side_effect = [-1, -1]
        with self.assertRaisesRegex(MuMuIpcError, "实例显示 -1，游戏包 -1"):
            bind_display(dll, 7, self.PACKAGE)


class MuMuCaptureWorkerTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("arknights_mower.utils.device.mumu12ipc.core.logger"))

    def run_worker(self, renderer, channel):
        dll = MagicMock()
        for name in (
            "nemu_connect",
            "nemu_disconnect",
            "nemu_get_display_id",
            "nemu_capture_display",
        ):
            getattr(dll, name).side_effect = getattr(renderer, name)
        shared = (ctypes.c_ubyte * (1920 * 1080 * 3))()
        with patch("ctypes.CDLL", return_value=dll):
            _capture_worker("MuMu", "3", "com.hypergryph.arknights", shared, channel)
        return shared, dll

    def test_worker_binds_the_instance_display_not_the_game_package(self):
        renderer = NativeRenderer()
        channel = MagicMock()
        channel.recv.side_effect = ["capture", EOFError()]
        _, dll = self.run_worker(renderer, channel)
        self.assertEqual(dll.nemu_get_display_id.call_args_list[0].args[1], b"")

    def test_native_worker_reuses_connection_for_black_and_color_frames(self):
        renderer = NativeRenderer()
        channel = MagicMock()
        channel.recv.side_effect = ["capture", "capture", "close"]

        def sent(message):
            self.assertEqual(message, ("ok", "", None, None))
            if channel.send.call_count == 1:
                renderer.pixels = ((0, 255, 31, 17, 255),)

        channel.send.side_effect = sent
        shared, dll = self.run_worker(renderer, channel)
        frame = np.frombuffer(shared, np.uint8).reshape(1080, 1920, 3)
        self.assertEqual(frame[1079, 0].tolist(), [255, 31, 17])
        self.assertEqual(dll.nemu_capture_display.call_count, 2)
        self.assertEqual(renderer.connect_calls, 1)
        self.assertEqual(renderer.disconnected, [7])
        channel.close.assert_called_once_with()

    def test_native_worker_sends_black_frame_successfully(self):
        renderer = NativeRenderer()
        channel = MagicMock()
        channel.recv.side_effect = ["capture", "close"]
        shared, _ = self.run_worker(renderer, channel)
        self.assertFalse(np.any(np.frombuffer(shared, np.uint8)))
        channel.send.assert_called_once_with(("ok", "", None, None))

    def test_native_worker_reports_capture_error_without_successful_frame(self):
        channel = MagicMock()
        channel.recv.return_value = "capture"
        renderer = NativeRenderer(code=-5, width=1280, height=720)
        _, dll = self.run_worker(renderer, channel)
        status, message, code, size = channel.send.call_args.args[0]
        self.assertEqual((status, code, size), ("error", -5, (1280, 720)))
        self.assertIn("-5", message)
        self.assertIn("1280×720", message)
        dll.nemu_capture_display.assert_called_once()
        self.assertEqual(renderer.disconnected, [7])

    def test_native_worker_reports_connection_code_without_disconnect_invalid_handle(
        self,
    ):
        channel = MagicMock()
        renderer = NativeRenderer(connection=-2)
        _, dll = self.run_worker(renderer, channel)
        status, message, code, size = channel.send.call_args.args[0]
        self.assertEqual((status, code, size), ("error", -2, None))
        self.assertIn("-2", message)
        self.assertEqual(renderer.disconnected, [])
        dll.nemu_capture_display.assert_not_called()

    def test_native_worker_bounds_error_message_when_library_loading_fails(self):
        channel = MagicMock()
        shared = (ctypes.c_ubyte * (1920 * 1080 * 3))()
        with patch("ctypes.CDLL", side_effect=OSError("dll failure " * 1024)):
            _capture_worker("MuMu", "3", "com.hypergryph.arknights", shared, channel)
        status, message, code, size = channel.send.call_args.args[0]
        self.assertEqual((status, code, size), ("error", None, None))
        self.assertLessEqual(len(message.encode("utf-8")), 1024)
        self.assertIn("Cannot load", message)
        channel.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
