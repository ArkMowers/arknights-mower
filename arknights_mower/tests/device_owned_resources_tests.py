"""Owned helpers release once and interrupt I/O without touching foreign handles."""

import os
import socket
import unittest
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.tests.device_maatouch_tests import OwnedProcess
from arknights_mower.tests.device_scrcpy_tests import Transport
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.maatouch.session import Session as MaaTouchSession
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.lifecycle import Phase, Shutdown


class DeviceOwnershipTests(unittest.TestCase):
    def setUp(self):
        with (
            patch.object(Device, "start"),
            patch("arknights_mower.utils.device.device.atexit.register"),
        ):
            self.device = Device(device_id="USB-A")

    def resources(self, failing=False):
        events = []

        def resource(name):
            def close():
                events.append(name)
                if failing and name == "capture":
                    raise OSError("capture close failed")

            def interrupt():
                events.append("interrupt " + name)

            return SimpleNamespace(
                close=close, interrupt=interrupt, interrupt_io=interrupt
            )

        self.device._mumu_capture = resource("capture")
        self.device._droidcast = resource("droidcast")
        self.device.control = resource("touch")
        self.device.client = resource("adb")
        return events

    def test_partial_initialization_and_repeated_close_are_safe(self):
        self.device.close()
        self.device.close()
        self.device.interrupt_io()
        self.device.close()

    def test_failed_cleanup_is_retried_without_repeating_completed_items(
        self,
    ):
        events = self.resources(failing=True)
        for _ in range(2):
            with self.assertRaisesRegex(OSError, "capture close failed"):
                self.device.close()
        self.assertEqual(events, ["capture", "droidcast", "touch", "adb", "capture"])

    def test_unowned_cleanup_failure_is_not_cleared_by_resource_release(self):
        events = self.resources(failing=True)
        failure = OSError("unregistered helper did not exit")
        self.device._close_error = failure
        for _ in range(2):
            with self.assertRaisesRegex(OSError, "unregistered helper did not exit"):
                self.device.close()
        self.assertEqual(events, ["capture", "droidcast", "touch", "adb", "capture"])

    def test_interruption_releases_once_and_rejects_all_helper_rebuilds(self):
        events = self.resources()
        self.device.interrupt_io()
        self.device.interrupt_io()
        self.assertEqual(
            events,
            [
                "interrupt touch",
                "interrupt capture",
                "interrupt droidcast",
                "interrupt adb",
            ],
        )
        self.device.close()
        self.assertEqual(events[-4:], ["capture", "droidcast", "touch", "adb"])
        for operation in (
            self.device.start,
            self.device.start_droidcast,
            self.device.rebuild_screenshot,
            self.device.capture_frame,
            lambda: self.device.rebind_target("USB-B", "adb"),
        ):
            with self.subTest(operation=operation), self.assertRaises(MowerExit):
                operation()

    def test_owner_mismatch_preserves_every_handle_and_original_owner_can_close(self):
        events = self.resources()
        self.device.owner_pid = os.getpid() + 1
        self.device.interrupt_io()
        self.device.close()
        self.assertEqual(events, [])
        self.assertFalse(self.device._interrupted.is_set())
        self.device.owner_pid = os.getpid()
        self.device.close()
        self.assertEqual(events, ["capture", "droidcast", "touch", "adb"])

    def test_application_restores_after_worker_wait_before_real_device_helper_cleanup(
        self,
    ):
        events = self.resources()
        configuration = Conf(device={"last_serial": "USB-A"})
        helper = SimpleNamespace(
            interrupt=lambda: events.append("interrupt touch"),
            stop=lambda: events.append("touch"),
        )
        with (
            patch("arknights_mower.utils.device.device.config.conf", configuration),
            patch("arknights_mower.utils.device.device.Scrcpy", return_value=helper),
        ):
            self.device.control = Device.Control(self.device, self.device.client)
        app = DeviceControl(
            lambda: configuration,
            SimpleNamespace(open=lambda *args, **kwargs: self.device),
            preparation=SimpleNamespace(
                begin=lambda *args: None,
                close=lambda: events.append("restore"),
            ),
        )
        self.assertTrue(app.start().ok)
        shutdown = Shutdown()
        shutdown.own("gate", app.begin_shutdown, Phase.GATE)
        shutdown.own("interrupt", app.interrupt_io, Phase.INTERRUPT)
        shutdown.own("worker", lambda: events.append("worker joined"), Phase.WORKER)
        shutdown.own("device", lambda: app.close().unwrap(), Phase.DEVICE)
        shutdown.close()
        shutdown.close()
        self.assertEqual(shutdown.errors, [])
        self.assertEqual(
            events,
            [
                "interrupt touch",
                "interrupt capture",
                "interrupt droidcast",
                "interrupt adb",
                "worker joined",
                "restore",
                "capture",
                "droidcast",
                "touch",
                "adb",
            ],
        )


class HelperOwnershipTests(unittest.TestCase):
    def scrcpy(self):
        transport = Transport()
        with (
            patch("pathlib.Path.read_bytes", return_value=b"bundled jar"),
            patch("arknights_mower.utils.device.scrcpy.core.budget_sleep"),
        ):
            helper = Scrcpy(transport)
        self.addCleanup(helper.stop)
        return helper, transport

    def test_scrcpy_owner_mismatch_never_closes_sockets(self):
        helper, transport = self.scrcpy()
        helper.owner_pid = os.getpid() + 1
        helper.interrupt()
        self.assertTrue(all(wire.closed == 0 for wire in transport.wires))
        helper.stop()
        self.assertTrue(all(wire.closed == 0 for wire in transport.wires))
        helper.owner_pid = os.getpid()
        helper.interrupt()
        helper.stop()
        self.assertTrue(all(wire.closed == 1 for wire in transport.wires))
        with self.assertRaises(ConnectionError):
            helper.start()

    def test_scrcpy_interruption_does_not_wait_for_blocked_control_send_lock(self):
        helper, transport = self.scrcpy()
        entered, released = Event(), Event()
        wire = transport.wires[-1]

        def send(data):
            entered.set()
            released.wait(2)
            raise ConnectionError("interrupted")

        wire.sendall = send
        wire.shutdown = lambda how: released.set()
        errors = []

        def tap():
            try:
                helper.tap(20, 30)
            except Exception as exc:
                errors.append(exc)

        worker = Thread(target=tap)
        worker.start()
        self.addCleanup(released.set)
        self.addCleanup(worker.join, 2)
        self.assertTrue(entered.wait(1))
        helper.interrupt()
        worker.join(0.5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertTrue(all(stream.closed == 1 for stream in transport.wires))
        helper.stop()
        self.assertTrue(all(stream.closed == 1 for stream in transport.wires))

    def test_maatouch_owner_mismatch_does_not_touch_process_or_pipes(self):
        session = MaaTouchSession(MagicMock(), defer_start=True)
        process = OwnedProcess()
        session.process = process
        session.owner_pid = os.getpid() + 1
        session.close()
        self.assertIsNone(process.poll())
        self.assertFalse(process.stdin.closed)
        session.owner_pid = os.getpid()
        session.close()
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)


class SocketOwnershipTests(unittest.TestCase):
    def owned_socket(self):
        local, peer = socket.socketpair()
        self.addCleanup(peer.close)
        with patch("socket.create_connection", return_value=local):
            # AF_UNIX socketpairs do not support TCP_NODELAY; keep the real
            # recv/shutdown/close operations behind the same public wrapper.
            transport = MagicMock(wraps=local)
            transport.setsockopt = lambda *args: None
            with patch("socket.create_connection", return_value=transport):
                owned = Socket(("127.0.0.1", 5037), 5)
        self.addCleanup(owned.close)
        return owned, transport

    def test_close_interrupts_an_owned_blocked_receive_and_is_idempotent(self):
        owned, transport = self.owned_socket()
        entered = Event()
        outcomes = []

        def receive():
            entered.set()
            try:
                outcomes.append(owned.recv(1))
            except Exception as exc:
                outcomes.append(exc)

        worker = Thread(target=receive)
        worker.start()
        self.addCleanup(worker.join, 1)
        self.assertTrue(entered.wait(1))
        owned.interrupt()
        owned.interrupt()
        worker.join(0.5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcomes), 1)
        transport.close.assert_called_once_with()
        owned.close()
        owned.close()
        transport.close.assert_called_once_with()

    def test_owner_mismatch_does_not_shutdown_or_close_socket(self):
        owned, transport = self.owned_socket()
        owned.owner_pid = os.getpid() + 1
        owned.close()
        transport.shutdown.assert_not_called()
        transport.close.assert_not_called()
        owned.owner_pid = os.getpid()
        owned.close()
        transport.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
