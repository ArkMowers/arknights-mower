"""ADB acknowledgement uncertainty reaches the existing input failure boundary."""

import socket
import unittest
from threading import Event
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.adb_client.core import Client
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.touch_backend import TouchFailure


class FakeADBServer:
    def __init__(self, command, *, phase="ack", failures=1):
        self.command = command
        self.phase = phase
        self.failures = failures
        self.sent = []
        self.sockets = []

    def connect(self, address, timeout):
        server = self

        class Stream:
            closed = False

            def send(self, data):
                self.command = data[4:].decode()
                server.sent.append(self.command)
                self.fail("send")
                return self

            def check_okay(self):
                self.fail("ack")
                return self

            def fail(self, phase):
                if (
                    self.command == server.command
                    and phase == server.phase
                    and server.failures
                ):
                    server.failures -= 1
                    raise socket.timeout("input may have reached Android")

            def recv_response(self):
                return b"USB-A\tdevice\n" if self.command == "host:devices" else b"0029"

            def recv_all(self):
                return b""

            def close(self):
                self.closed = True

        stream = Stream()
        self.sockets.append(stream)
        return stream


class ADBInputDeliveryTests(unittest.TestCase):
    def test_uncertain_input_is_not_replayed_by_the_protocol_or_next_operation(self):
        operations = (
            (lambda device: device.send_keyevent(4), "input keyevent 4"),
            (lambda device: device.send_text("abc"), 'input text "abc"'),
            (lambda device: device.launch(), "input tap 20 30"),
        )
        for operation, command in operations:
            for phase in ("send", "ack"):
                with self.subTest(command=command, phase=phase):
                    conf = Conf(
                        device={
                            "last_serial": "USB-A",
                            "screenshot_backend": "adb_gzip",
                        },
                        tap_to_launch_game={"mode": "tap", "x": 20, "y": 30},
                    )
                    server = FakeADBServer(f"exec:{command}", phase=phase)
                    with (
                        patch.object(config, "conf", conf),
                        patch.object(config, "stop_mower", Event()),
                        patch(
                            "arknights_mower.utils.device.adb_client.session.Socket",
                            side_effect=server.connect,
                        ),
                    ):
                        client = Client(
                            device_id="USB-A", adb_bin="adb", strict_target=True
                        )
                        self.addCleanup(client.close)
                        # Startup helpers are outside this input contract. The
                        # input path below uses the real Device, Client and Session.
                        device = object.__new__(Device)
                        device.client = client
                        device.control = MagicMock()
                        device._profile = conf.device
                        with self.assertRaises(TouchFailure) as raised:
                            operation(device)
                        failure = raised.exception
                        self.assertEqual(failure.code, "touch_result_unknown")
                        self.assertEqual(failure.transport, "adb")
                        self.assertTrue(failure.delivery_unknown)
                        with self.assertRaises(TouchFailure) as repeated:
                            operation(device)
                        self.assertIs(repeated.exception, failure)
                        self.assertEqual(server.sent.count(f"exec:{command}"), 1)
                        self.assertTrue(all(stream.closed for stream in server.sockets))

    def test_unknown_and_mutating_services_do_not_retry_after_ack_timeout(self):
        for command in (
            "shell:input keyevent 4",
            "host:connect:127.0.0.1:5555",
            "host:disconnect:127.0.0.1:5555",
            "sync:",
            "localabstract:scrcpy",
        ):
            with self.subTest(command=command):
                server = FakeADBServer(command)
                with patch(
                    "arknights_mower.utils.device.adb_client.session.Socket",
                    side_effect=server.connect,
                ):
                    with Session() as session, self.assertRaises(socket.timeout):
                        session.request(command)
                    self.assertEqual(server.sent, [command])
                    self.assertEqual(len(server.sockets), 1)
                    self.assertTrue(server.sockets[0].closed)

    def test_helper_stream_timeout_closes_the_owned_connection_without_replay(self):
        server = FakeADBServer("localabstract:scrcpy")
        with patch(
            "arknights_mower.utils.device.adb_client.session.Socket",
            side_effect=server.connect,
        ):
            client = Client(device_id="USB-A", adb_bin="adb", strict_target=True)
            self.addCleanup(client.close)
            with self.assertRaises(socket.timeout):
                client.stream("localabstract:scrcpy")
        self.assertEqual(server.sent.count("localabstract:scrcpy"), 1)
        self.assertTrue(all(stream.closed for stream in server.sockets))

    def test_read_only_queries_and_transport_selection_keep_one_bounded_retry(self):
        for command in (
            "host:version",
            "host:devices",
            "host:transport:USB-A",
            "host:transport-any",
        ):
            for failures in (1, 2):
                with self.subTest(command=command, failures=failures):
                    server = FakeADBServer(command, failures=failures)
                    with patch(
                        "arknights_mower.utils.device.adb_client.session.Socket",
                        side_effect=server.connect,
                    ):
                        with Session() as session:
                            if failures == 1:
                                self.assertIs(session.request(command), session)
                            else:
                                with self.assertRaises(socket.timeout):
                                    session.request(command)
                        self.assertEqual(server.sent, [command, command])
                        self.assertEqual(len(server.sockets), 2)
                        self.assertTrue(all(stream.closed for stream in server.sockets))
