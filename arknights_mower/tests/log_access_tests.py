"""Local log reads stay available without a configured Web UI token."""

import json
import unittest
from threading import Thread
from unittest.mock import patch

from simple_websocket import Client
from werkzeug.serving import make_server

import server
from arknights_mower.utils.log_stream import LogStream


class FakeSocket:
    def __init__(self, token_frame=None):
        self.closed = False
        self.received = False
        self.token_frame = token_frame

    def receive(self, timeout=None):
        self.received = True
        return self.token_frame

    def close(self, reason=None, message=None):
        self.closed = True
        self.close_reason = reason


class LocalLogAccessTests(unittest.TestCase):
    def setUp(self):
        self.old_token = getattr(server.app, "token", None)
        self.old_local_mode = server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"]
        server.app.token = "runtime-secret"
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = True

    def tearDown(self):
        if self.old_token is None:
            del server.app.token
        else:
            server.app.token = self.old_token
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = self.old_local_mode

    def context(
        self,
        *,
        origin="http://127.0.0.1:58000",
        host="127.0.0.1:58000",
        remote="127.0.0.1",
        fetch_site="same-origin",
    ):
        headers = {"Host": host, "Sec-Fetch-Site": fetch_site}
        if origin is not None:
            headers["Origin"] = origin
        return server.app.test_request_context(
            "/log", headers=headers, environ_base={"REMOTE_ADDR": remote}
        )

    def test_local_log_socket_without_token_does_not_open_ai_socket(self):
        with self.context():
            log_socket = FakeSocket()
            self.assertTrue(
                server._authorize_websocket(log_socket, allow_local_log=True)
            )
            self.assertFalse(log_socket.received)
            ai_socket = FakeSocket()
            self.assertFalse(server._authorize_websocket(ai_socket))
            self.assertTrue(ai_socket.closed)

    def test_local_log_socket_rejects_cross_origin_and_nonlocal_requests(self):
        cases = (
            {"origin": "https://attacker.example"},
            {"origin": None},
            {"host": "attacker.example"},
            {"remote": "192.0.2.1"},
            {"fetch_site": "cross-site"},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.context(**kwargs):
                socket = FakeSocket()
                self.assertFalse(
                    server._authorize_websocket(socket, allow_local_log=True)
                )
                self.assertTrue(socket.closed)

    def test_configured_token_disables_local_exemption(self):
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = False
        with self.context():
            socket = FakeSocket()
            self.assertFalse(server._authorize_websocket(socket, allow_local_log=True))
            self.assertTrue(socket.closed)

    def test_forwarded_log_socket_accepts_valid_token_independently_of_origin(self):
        for local_mode in (True, False):
            server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = local_mode
            for origin in (
                "https://mower.example:8443",
                "http://mower.example:18000",
                "https://[2001:db8::1]:8443",
                "https://other.example:9443",
                "null",
                None,
            ):
                with (
                    self.subTest(local_mode=local_mode, origin=origin),
                    self.context(origin=origin, host="127.0.0.1:58000"),
                ):
                    socket = FakeSocket(json.dumps({"token": "runtime-secret"}))
                    self.assertTrue(
                        server._authorize_websocket(socket, allow_local_log=True)
                    )
                    self.assertTrue(socket.received)
                    self.assertFalse(socket.closed)

    def test_forwarded_log_socket_rejects_missing_or_invalid_credentials(self):
        for origin in ("https://mower.example:8443", "null", None):
            for token_frame in (
                None,
                json.dumps({"token": "wrong"}),
                json.dumps({}),
                json.dumps({"token": 123}),
                json.dumps(["runtime-secret"]),
                "invalid-json",
            ):
                with (
                    self.subTest(origin=origin, token_frame=token_frame),
                    self.context(origin=origin, host="127.0.0.1:58000"),
                ):
                    socket = FakeSocket(token_frame)
                    self.assertFalse(
                        server._authorize_websocket(socket, allow_local_log=True)
                    )
                    self.assertTrue(socket.closed)
                    self.assertEqual(socket.close_reason, 4401)

    def test_log_forwarding_does_not_relax_other_origin_checks(self):
        with self.context(origin="https://mower.example:8443", host="127.0.0.1:58000"):
            socket = FakeSocket(json.dumps({"token": "runtime-secret"}))
            self.assertFalse(server._authorize_websocket(socket))
            self.assertTrue(socket.closed)
            self.assertFalse(
                server._diagnostic_delete_origin_allowed("https://mower.example:8443")
            )

    def test_forwarded_headers_do_not_grant_tokenless_log_access(self):
        with server.app.test_request_context(
            "/log",
            headers={
                "Host": "127.0.0.1:58000",
                "Origin": "https://mower.example:8443",
                "X-Forwarded-Host": "mower.example:8443",
                "X-Forwarded-Proto": "https",
            },
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            socket = FakeSocket()
            self.assertFalse(server._authorize_websocket(socket, allow_local_log=True))
            self.assertTrue(socket.closed)
            self.assertEqual(socket.close_reason, 4401)

    def test_forwarded_log_route_streams_after_token_authentication(self):
        server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = False
        stream = LogStream()
        stream.publish("forwarded-log-fixture")
        with patch.object(server.log_stream, "serve", stream.serve):
            service = make_server("127.0.0.1", 0, server.app, threaded=True)
            thread = Thread(target=service.serve_forever, daemon=True)
            thread.start()
            try:
                connection = Client.connect(
                    f"ws://127.0.0.1:{service.server_port}/log",
                    headers={"Origin": "https://mower.example:8443"},
                    receive_bytes=1,
                )
                try:
                    connection.send(json.dumps({"token": "runtime-secret"}))
                    self.assertEqual(
                        json.loads(connection.receive(timeout=2)),
                        {"type": "log", "data": "forwarded-log-fixture"},
                    )
                    stream.publish("next-forwarded-log")
                    self.assertEqual(
                        json.loads(connection.receive(timeout=2)),
                        {"type": "log", "data": "next-forwarded-log"},
                    )
                finally:
                    connection.close()
            finally:
                service.shutdown()
                service.server_close()
                thread.join(3)
                self.assertFalse(thread.is_alive())

    def test_local_log_socket_streams_without_token_frame(self):
        stream = LogStream()
        stream.publish("local-log-fixture")
        # 仅绑定请求的日志流，后台日志消费者继续使用原流。
        with patch.object(server.log_stream, "serve", stream.serve):
            service = make_server("127.0.0.1", 0, server.app, threaded=True)
            thread = Thread(target=service.serve_forever, daemon=True)
            thread.start()
            try:
                connection = Client.connect(
                    f"ws://127.0.0.1:{service.server_port}/log",
                    headers={"Origin": "http://127.0.0.1"},
                    # 按字节接收，避免客户端把同批首帧留在握手解析器中。
                    receive_bytes=1,
                )
                try:
                    payload = json.loads(connection.receive(timeout=2))
                    self.assertEqual(
                        payload, {"type": "log", "data": "local-log-fixture"}
                    )
                finally:
                    connection.close()
            finally:
                service.shutdown()
                service.server_close()
                thread.join(3)
                self.assertFalse(thread.is_alive())

    def test_log_read_routes_allow_local_window_and_reject_cross_site(self):
        with patch.object(server, "error_events", return_value=[]):
            client = server.app.test_client()
            for origin, remote, fetch_site, expected_status in (
                ("http://127.0.0.1:58000", "127.0.0.1", "same-origin", 200),
                (None, "127.0.0.1", "same-origin", 200),
                ("https://attacker.example", "127.0.0.1", "cross-site", 403),
                ("http://127.0.0.1:58000", "192.0.2.1", "same-origin", 403),
            ):
                with self.subTest(origin=origin, remote=remote):
                    headers = {
                        "Host": "127.0.0.1:58000",
                        "Sec-Fetch-Site": fetch_site,
                    }
                    if origin is not None:
                        headers["Origin"] = origin
                    response = client.get(
                        "/diagnostics/errors",
                        headers=headers,
                        environ_base={"REMOTE_ADDR": remote},
                    )
                    self.assertEqual(response.status_code, expected_status)
                    if expected_status == 200:
                        self.assertEqual(json.loads(response.data), {"events": []})

            self.assertEqual(client.get("/conf").status_code, 403)
            self.assertEqual(client.delete("/diagnostics/errors/123").status_code, 403)

            server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = False
            response = client.get(
                "/diagnostics/errors", headers={"Host": "127.0.0.1:58000"}
            )
            self.assertEqual(response.status_code, 403)
            response = client.get(
                "/diagnostics/errors",
                headers={"Host": "127.0.0.1:58000", "token": "runtime-secret"},
            )
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
