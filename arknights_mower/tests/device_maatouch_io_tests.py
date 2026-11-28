"""MaaTouch pipe completion through its public session boundary."""

import io
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from arknights_mower.tests.device_maatouch_tests import OwnedProcess
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.maatouch.session import Session


class MaaTouchIOTests(unittest.TestCase):
    def open_session(self, process):
        self.enterContext(
            patch("arknights_mower.utils.device.maatouch.session.guard_adb")
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.device.maatouch.session.subprocess.Popen",
                return_value=process,
            )
        )
        session = Session(SimpleNamespace(adb_bin="verified-adb", device_id="USB-123"))
        self.addCleanup(session.close)
        return session

    def test_handshake_and_send_completion_wake_a_waiting_caller(self):
        caller_waiting = threading.Event()
        awakened = []
        caller = threading.get_ident()

        class ObservedEvent:
            def __init__(self):
                self.event = threading.Event()

            def set(self):
                self.event.set()

            def clear(self):
                self.event.clear()

            def is_set(self):
                return self.event.is_set()

            def wait(self, timeout=None):
                if threading.get_ident() == caller:
                    caller_waiting.set()
                    # A safety bound exposes a missing completion signal without
                    # relying on a millisecond latency assertion.
                    signalled = self.event.wait(1)
                    awakened.append(signalled)
                    return signalled
                return self.event.wait(timeout)

        class Header(io.StringIO):
            def readline(self, *args):
                if not caller_waiting.wait(1):
                    raise TimeoutError("caller never waited for the handshake")
                return super().readline(*args)

        class Writer(io.StringIO):
            def write(self, content):
                if not caller_waiting.wait(1):
                    raise TimeoutError("caller never waited for the send")
                return super().write(content)

        process = OwnedProcess()
        process.stdout = Header("^ 10 1920 1080 255\n$ 123\n")
        process.stdin = Writer()
        with (
            patch("arknights_mower.utils.device.maatouch.session.Event", ObservedEvent),
            patch("arknights_mower.utils.device.maatouch.session.guard_adb"),
            patch(
                "arknights_mower.utils.device.maatouch.session.subprocess.Popen",
                return_value=process,
            ),
        ):
            session = Session(
                SimpleNamespace(adb_bin="verified-adb", device_id="USB-123"),
                defer_start=True,
            )
            self.addCleanup(session.close)
            session.start()
            self.assertFalse(session.input_started)
            caller_waiting.clear()
            session.send("d 0 400 300 100\nc\nu 0\nc\n")
        self.assertEqual(session.pid, "123")
        self.assertEqual(awakened, [True, True])
        self.assertTrue(session.input_started)
        self.assertEqual(process.stdin.getvalue(), "d 0 400 300 100\nc\nu 0\nc\n")

    def test_send_propagates_the_original_pipe_error_without_repeating_input(self):
        process = OwnedProcess()
        failure = BrokenPipeError("send result unknown")
        writes = []

        class Writer(io.StringIO):
            def write(self, content):
                writes.append(content)
                raise failure

        process.stdin = Writer()
        session = self.open_session(process)
        with self.assertRaises(BrokenPipeError) as raised:
            session.send("c\n")
        self.assertIs(raised.exception, failure)
        self.assertEqual(writes, ["c\n"])
        self.assertTrue(session.input_started)

    def test_interrupt_wakes_a_blocked_send_and_close_releases_its_resources(self):
        self.check_blocked_send_shutdown(close=False)

    def test_close_wakes_a_blocked_send_and_stops_the_process_before_pipe_closure(self):
        self.check_blocked_send_shutdown(close=True)

    def check_blocked_send_shutdown(self, *, close):
        process = OwnedProcess()
        entered = threading.Event()
        released = threading.Event()
        caller_waiting = threading.Event()
        shutdown_signalled = threading.Event()
        awakened = []
        shutdown_caller = threading.get_ident()
        caller = None
        writes = []

        class ObservedEvent:
            def __init__(self):
                self.event = threading.Event()
                self.waiting = False

            def set(self):
                if self.waiting and threading.get_ident() == shutdown_caller:
                    shutdown_signalled.set()
                self.event.set()

            def is_set(self):
                return self.event.is_set()

            def wait(self, timeout=None):
                if threading.current_thread() is caller:
                    self.waiting = True
                    caller_waiting.set()
                    # Observe the signal itself, with a safety bound instead of
                    # relying on the production budget polling interval.
                    signalled = self.event.wait(1)
                    awakened.append(signalled)
                    return signalled
                return self.event.wait(timeout)

        class Writer(io.StringIO):
            def write(self, content):
                writes.append(content)
                entered.set()
                if not released.wait(2):
                    raise TimeoutError("blocked writer was not released")
                return super().write(content)

        process.stdin = Writer()
        terminate = process.terminate

        def stop_process():
            self.assertFalse(process.stdin.closed)
            self.assertFalse(process.stdout.closed)
            # Completion after termination must not substitute for a shutdown
            # signal while the send caller and its writer are both blocked.
            self.assertTrue(shutdown_signalled.is_set())
            terminate()
            released.set()

        process.terminate = stop_process
        self.enterContext(
            patch("arknights_mower.utils.device.maatouch.session.Event", ObservedEvent)
        )
        session = self.open_session(process)
        results = []

        def send():
            try:
                session.send("c\n")
            except BaseException as exc:
                results.append(exc)

        caller = threading.Thread(target=send)
        caller.start()
        self.addCleanup(caller.join, 2)
        self.addCleanup(released.set)
        self.assertTrue(entered.wait(1))
        self.assertTrue(caller_waiting.wait(1))
        if close:
            session.close()
        else:
            session.interrupt()
        self.assertTrue(shutdown_signalled.is_set())
        caller.join(1)
        self.assertFalse(caller.is_alive())
        self.assertEqual(awakened, [True])
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], ConnectionError)
        self.assertTrue(session.input_started)
        self.assertEqual(writes, ["c\n"])
        session.close()
        self.assertEqual(process.events, ["terminate", "wait"])
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)

    def test_expired_recovery_budget_rejects_send_before_input_starts(self):
        process = OwnedProcess()
        session = self.open_session(process)
        with device_io_budget(lambda: 0):
            with self.assertRaises(TimeoutError):
                session.send("c\n")
        self.assertFalse(session.input_started)
        self.assertEqual(process.stdin.getvalue(), "")

    def test_send_completion_after_its_deadline_still_reports_timeout(self):
        process = OwnedProcess()
        session = self.open_session(process)
        clock = [0.0]
        writes = []

        class Writer(io.StringIO):
            def write(self, content):
                writes.append(content)
                clock[0] = 11.0
                return super().write(content)

        process.stdin = Writer()
        with patch(
            "arknights_mower.utils.device.maatouch.session.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            with self.assertRaises(TimeoutError):
                session.send("c\n")
        self.assertTrue(session.input_started)
        self.assertEqual(writes, ["c\n"])


if __name__ == "__main__":
    unittest.main()
