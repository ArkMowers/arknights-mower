import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Barrier, Event, Thread
from unittest.mock import Mock

from flask import Flask
from flask_sock import Sock
from simple_websocket import Client, ConnectionClosed
from werkzeug.serving import make_server

from arknights_mower.utils.log_stream import LogStream


class FakeSocket:
    def __init__(self):
        self.sent = Queue()
        self.disconnected = Event()

    def receive(self, timeout=0):
        if self.disconnected.is_set():
            raise ConnectionClosed()

    def send(self, payload):
        self.sent.put(json.loads(payload))

    def close(self):
        self.disconnected.set()


class LogStreamTests(unittest.TestCase):
    def setUp(self):
        self.stream = LogStream()

    def serve(self, ws):
        thread = Thread(target=self.stream.serve, args=(ws,), daemon=True)
        thread.start()

        def cleanup():
            ws.close()
            thread.join(3)
            self.assertFalse(thread.is_alive())

        self.addCleanup(cleanup)
        return thread

    def test_disconnected_client_does_not_stop_logs_for_other_clients(self):
        healthy = FakeSocket()
        self.serve(healthy)
        healthy.sent.get(timeout=2)
        for error in (BrokenPipeError(), ConnectionResetError(), ConnectionClosed()):
            with self.subTest(error=type(error).__name__):
                broken = Mock()
                broken.send.side_effect = error
                self.stream.serve(broken)
                broken.close.assert_called_once()
                self.stream.publish("after disconnect")
                self.assertEqual(
                    healthy.sent.get(timeout=2),
                    {"type": "log", "data": "after disconnect"},
                )
        self.assertEqual(len(self.stream._subscriptions), 1)

    def test_disconnect_during_live_send_cleans_up(self):
        ws = FakeSocket()
        ws.send = Mock(side_effect=[None, BrokenPipeError()])
        original_receive = ws.receive

        def receive(timeout=0):
            original_receive(timeout)
            if ws.send.call_count == 1:
                self.stream.publish("live message")

        ws.receive = receive
        self.stream.serve(ws)
        self.assertEqual(ws.send.call_count, 2)
        self.assertFalse(self.stream._subscriptions)
        self.assertTrue(ws.disconnected.is_set())

    def test_idle_disconnect_is_cleaned_without_another_log(self):
        ws = FakeSocket()
        thread = self.serve(ws)
        ws.sent.get(timeout=2)
        ws.close()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertFalse(self.stream._subscriptions)

    def test_receive_or_close_failure_does_not_leak_subscription(self):
        ws = Mock()
        ws.receive.side_effect = ConnectionResetError()
        ws.close.side_effect = BrokenPipeError()
        self.stream.serve(ws)
        self.assertFalse(self.stream._subscriptions)
        ws.send.assert_not_called()

    def test_unexpected_failure_still_cleans_up(self):
        ws = Mock()
        ws.send.side_effect = ValueError("unexpected")
        with self.assertRaises(ValueError):
            self.stream.serve(ws)
        self.assertFalse(self.stream._subscriptions)
        ws.close.assert_called_once()

    def test_slow_client_does_not_block_publishing_or_healthy_client(self):
        entered = Event()
        release = Event()
        slow = FakeSocket()

        def blocked_send(payload):
            entered.set()
            release.wait(5)

        slow.send = blocked_send
        thread = self.serve(slow)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(2))
        healthy = self.stream.subscribe()
        healthy.messages.get_nowait()
        for index in range(150):
            self.stream.publish(str(index))
            self.assertEqual(
                json.loads(healthy.messages.get(timeout=2))["data"], str(index)
            )
        self.assertEqual(self.stream._subscriptions, {healthy})
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_reconnect_gets_latest_bounded_history_after_queue_overflow(self):
        slow = self.stream.subscribe()
        for index in range(250):
            self.stream.publish(str(index))
        self.assertTrue(slow.closed.is_set())
        self.assertLessEqual(slow.messages.qsize(), 100)
        reconnected = self.stream.subscribe()
        self.assertEqual(
            json.loads(reconnected.messages.get_nowait())["data"].splitlines(),
            [str(index) for index in range(150, 250)],
        )

    def test_subscribe_and_publish_have_no_gap_or_duplicate(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            for _ in range(30):
                stream = LogStream()
                stream.publish("before")
                barrier = Barrier(2)

                def subscribe():
                    barrier.wait()
                    return stream.subscribe()

                def publish():
                    barrier.wait()
                    stream.publish("during")

                subscriber = pool.submit(subscribe)
                publisher = pool.submit(publish)
                subscription = subscriber.result(timeout=2)
                publisher.result(timeout=2)
                stream.publish("after")
                lines = []
                while True:
                    try:
                        lines.extend(
                            json.loads(subscription.messages.get_nowait())[
                                "data"
                            ].splitlines()
                        )
                    except Empty:
                        break
                self.assertEqual(lines, ["before", "during", "after"])

    def test_resource_notifications_share_ordered_queue_without_entering_history(self):
        subscription = self.stream.subscribe()
        subscription.messages.get_nowait()
        self.stream.publish("before")
        self.stream.broadcast({"type": "resource_updated"})
        self.stream.publish("after")
        messages = [json.loads(subscription.messages.get_nowait()) for _ in range(3)]
        self.assertEqual(
            messages,
            [
                {"type": "log", "data": "before"},
                {"type": "resource_updated"},
                {"type": "log", "data": "after"},
            ],
        )
        snapshot = self.stream.subscribe().messages.get_nowait()
        self.assertEqual(json.loads(snapshot)["data"], "before\nafter")

    def test_clear_resets_history_and_preserves_live_subscriptions(self):
        self.stream.publish("old")
        subscription = self.stream.subscribe()
        subscription.messages.get_nowait()
        self.stream.clear()
        self.stream.publish("new")
        self.assertEqual(json.loads(subscription.messages.get_nowait())["data"], "new")
        snapshot = self.stream.subscribe().messages.get_nowait()
        self.assertEqual(json.loads(snapshot)["data"], "new")


class LogStreamIntegrationTests(unittest.TestCase):
    def test_real_websockets_keep_receiving_when_another_page_reconnects(self):
        stream = LogStream()
        app = Flask(__name__)
        app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 0.1}
        sock = Sock(app)
        sock.route("/log")(stream.serve)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.shutdown)
        url = f"ws://127.0.0.1:{server.server_port}/log"
        healthy = Client.connect(url)
        self.addCleanup(healthy.close)
        self.assertEqual(json.loads(healthy.receive(timeout=2))["data"], "")
        for index in range(5):
            other = Client.connect(url)
            try:
                snapshot = json.loads(other.receive(timeout=2))
                self.assertEqual(snapshot["type"], "log")
                if index:
                    self.assertTrue(snapshot["data"].endswith(str(index - 1)))
            finally:
                other.close()
            stream.publish(str(index))
            self.assertEqual(json.loads(healthy.receive(timeout=2))["data"], str(index))


if __name__ == "__main__":
    unittest.main()
