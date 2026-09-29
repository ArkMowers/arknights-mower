"""MaaTouch cleanup through the application seam, replacing only device/process I/O."""

import io
import subprocess
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.maatouch.core import Client

POPEN = subprocess.Popen


class OwnedProcess:
    def __init__(self):
        self.stdout = io.StringIO("^ 10 1920 1080 255\n$ 123\n")
        self.stdin = io.StringIO()
        self.returncode = None
        self.events = []
        self.waits = []
        self.ignore_terminate = False
        self.ignore_eof = False
        self.terminate_error = None
        self.exit_on_eof = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.events.append("wait")
        self.waits.append(timeout)
        if self.stdin.closed and not self.ignore_eof:
            self.returncode = self.exit_on_eof
        if self.returncode is None:
            raise subprocess.TimeoutExpired("maatouch", timeout)
        return self.returncode

    def terminate(self):
        self.events.append("terminate")
        if self.terminate_error:
            raise self.terminate_error
        if not self.ignore_terminate:
            self.returncode = -15

    def kill(self):
        self.events.append("kill")
        self.returncode = -9


class DelayedHeader(io.StringIO):
    def readline(self, *args):
        threading.Event().wait(0.1)
        return super().readline(*args)


class DelayedWriter(io.StringIO):
    def __init__(self, *, fail=False):
        super().__init__()
        self.writes = []
        self.fail = fail

    def write(self, data):
        self.writes.append(data)
        if self.fail:
            raise BrokenPipeError("send result unknown")
        threading.Event().wait(0.1)
        return super().write(data)


class TouchDevice:
    device_id = "USB-123"

    def __init__(self):
        adb = SimpleNamespace(
            device_id=self.device_id,
            adb_bin="verified-adb",
            cmd_shell=lambda *args: "maatouch",
            check_server_alive=lambda: True,
        )
        self.touch = Client(adb)

    def tap(self):
        self.touch.tap([(400, 300)], (1920, 1080, 0))

    def long_tap(self):
        self.touch.tap([(400, 300)], (1920, 1080, 0), duration=10000)

    def interrupt_input(self):
        self.touch.close()

    def close(self):
        self.touch.close()


class MaaTouchApplicationTests(unittest.TestCase):
    def setUp(self):
        self.processes = []

        def create_process(*args, **kwargs):
            process = OwnedProcess()
            self.processes.append(process)
            return process

        self.factory = self.enterContext(
            patch(
                "arknights_mower.utils.device.maatouch.session.subprocess.Popen",
                side_effect=create_process,
            )
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=None,
            )
        )
        self.control = DeviceControl(
            lambda: SimpleNamespace(adb="USB-123"),
            SimpleNamespace(open=lambda *args, **kwargs: TouchDevice()),
        )
        self.addCleanup(self.control.close)
        self.assertTrue(self.control.start().ok)

    def test_each_operation_waits_for_its_process_and_releases_pipes(self):
        self.assertTrue(self.control.execute(lambda device: device.tap()).ok)
        self.assertTrue(self.control.execute(lambda device: device.tap()).ok)
        self.assertEqual(len(self.processes), 2)
        for process in self.processes:
            self.assertEqual(process.events, ["wait"])
            self.assertEqual(process.returncode, 0)
            self.assertTrue(process.stdin.closed)
            self.assertTrue(process.stdout.closed)
            self.assertTrue(all(0 < timeout <= 1 for timeout in process.waits))
        self.assertTrue(self.control.close().ok)
        self.assertTrue(self.control.close().ok)

    def test_handshake_timeout_reaps_the_process_without_sending_input(self):
        process = OwnedProcess()
        process.stdout = DelayedHeader("^ 10 1920 1080 255\n$ 123\n")
        self.factory.side_effect = None
        self.factory.return_value = process
        with device_io_budget(lambda: 0.01):
            result = self.control.execute(lambda device: device.tap())
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error.cause, TimeoutError)
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertEqual(self.factory.call_count, 1)

    def test_send_timeout_does_not_repeat_input_and_releases_process(self):
        process = OwnedProcess()
        process.stdin = DelayedWriter()
        self.factory.side_effect = None
        self.factory.return_value = process
        with device_io_budget(lambda: 0.02):
            result = self.control.execute(lambda device: device.tap())
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error.cause, TimeoutError)
        self.assertEqual(len(process.stdin.writes), 1)
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertEqual(self.factory.call_count, 1)

    def test_broken_send_keeps_original_error_if_cleanup_also_fails(self):
        process = OwnedProcess()
        process.stdin = DelayedWriter(fail=True)
        process.ignore_eof = True
        process.terminate_error = OSError("cannot terminate")
        self.factory.side_effect = None
        self.factory.return_value = process
        result = self.control.execute(lambda device: device.tap())
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error.cause, BrokenPipeError)
        self.assertIn("cannot terminate", "".join(result.error.cause.__notes__))
        self.assertTrue(result.error.cause.cleanup_failed)
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.execute(lambda device: device.tap()).ok)
        self.assertEqual(len(process.stdin.writes), 1)
        self.assertEqual(process.events, ["wait", "terminate", "wait", "kill", "wait"])
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)

    def test_malformed_handshake_releases_process_and_never_sends_input(self):
        for header in (
            "bad\n",
            "^ 10 -1 1080 255\n$ 123\n",
            "^ 10 1920 1080 255\n$ 0\n",
        ):
            with self.subTest(header=header):
                process = OwnedProcess()
                process.stdout = io.StringIO(header)
                self.factory.side_effect = None
                self.factory.return_value = process
                result = self.control.execute(lambda device: device.tap())
                self.assertFalse(result.ok)
                self.assertIsInstance(result.error.cause, ConnectionError)
                self.assertIsNotNone(process.poll())
                self.assertTrue(process.stdin.closed)
                self.assertTrue(process.stdout.closed)

    def test_live_process_is_killed_only_after_bounded_wait_and_terminate(self):
        process = OwnedProcess()
        process.ignore_eof = True
        process.ignore_terminate = True
        self.factory.side_effect = None
        self.factory.return_value = process
        self.assertTrue(self.control.execute(lambda device: device.tap()).ok)
        self.assertEqual(process.events, ["wait", "terminate", "wait", "kill", "wait"])
        self.assertEqual(process.returncode, -9)
        self.assertTrue(all(0 < timeout <= 1 for timeout in process.waits))

    def test_long_action_wait_consumes_deadline_and_reaps_process(self):
        with device_io_budget(lambda: 0.02):
            result = self.control.execute(lambda device: device.long_tap())
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error.cause, TimeoutError)
        self.assertEqual(len(self.processes), 1)
        self.assertIsNotNone(self.processes[0].poll())

    def test_abnormal_exit_on_eof_is_reported_without_retry(self):
        process = OwnedProcess()
        process.exit_on_eof = 3
        self.factory.side_effect = None
        self.factory.return_value = process
        result = self.control.execute(lambda device: device.tap())
        self.assertFalse(result.ok)
        self.assertIn("3", str(result.error.cause))
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(process.events, ["wait"])

    def test_real_host_process_exits_gracefully_after_each_operation(self):
        processes = []

        def spawn(*args, **kwargs):
            process = POPEN(
                [
                    sys.executable,
                    "-u",
                    "-c",
                    "import sys; print('^ 10 1920 1080 255'); print('$ 123'); sys.stdin.read()",
                ],
                **kwargs,
            )
            processes.append(process)
            return process

        self.factory.side_effect = spawn
        for _ in range(2):
            result = self.control.execute(lambda device: device.tap())
            self.assertTrue(result.ok, result.error)
        self.assertEqual(len(processes), 2)
        for process in processes:
            self.assertEqual(process.poll(), 0)
            self.assertTrue(process.stdin.closed)
            self.assertTrue(process.stdout.closed)

    def test_real_host_process_with_blocked_header_is_reaped_on_timeout(self):
        processes = []

        def spawn(*args, **kwargs):
            process = POPEN(
                [sys.executable, "-u", "-c", "import time; time.sleep(60)"],
                **kwargs,
            )
            processes.append(process)
            return process

        self.factory.side_effect = spawn
        with device_io_budget(lambda: 0.03):
            result = self.control.execute(lambda device: device.tap())
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error.cause, TimeoutError)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdin.closed)
        self.assertTrue(processes[0].stdout.closed)

    def test_application_close_interrupts_handshake_and_rejects_new_operations(self):
        process = OwnedProcess()
        entered = threading.Event()
        released = threading.Event()

        class BlockingHeader(io.StringIO):
            def readline(self, *args):
                entered.set()
                released.wait(2)
                return super().readline(*args)

        process.stdout = BlockingHeader("^ 10 1920 1080 255\n$ 123\n")
        terminate = process.terminate

        def release_process():
            terminate()
            released.set()

        process.terminate = release_process
        self.factory.side_effect = None
        self.factory.return_value = process
        results = []
        worker = threading.Thread(
            target=lambda: results.append(
                self.control.execute(lambda device: device.tap())
            )
        )
        worker.start()
        self.addCleanup(released.set)
        self.addCleanup(worker.join, 2)
        self.assertTrue(entered.wait(1))
        self.assertTrue(self.control.close().ok)
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertFalse(results[0].ok)
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(self.control.close().ok)
        self.assertFalse(self.control.execute(lambda device: device.tap()).ok)
        self.assertEqual(self.factory.call_count, 1)


if __name__ == "__main__":
    unittest.main()
