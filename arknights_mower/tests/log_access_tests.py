"""Local log reads stay available without a configured Web UI token."""

import json
import unittest
from threading import Thread
from unittest.mock import Mock, patch

import pytest
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
                    # 订阅快照含 records 字段；这里只验证日志文本到达客户端。
                    self.assertEqual(
                        json.loads(connection.receive(timeout=2))["data"],
                        "forwarded-log-fixture",
                    )
                    stream.publish("next-forwarded-log")
                    self.assertEqual(
                        json.loads(connection.receive(timeout=2))["data"],
                        "next-forwarded-log",
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
                    # 订阅快照含 records 字段；这里只验证日志文本到达客户端。
                    self.assertEqual(payload["data"], "local-log-fixture")
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

    def test_range_export_preserves_local_and_configured_token_boundaries(self):
        url = "/diagnostics/export?at=1792468800000&start=1792465200000&end=1792469100000&screenshots=0"
        with patch.object(
            server, "_send_diagnostic_bundle", return_value="bundle"
        ) as send:
            client = server.app.test_client()
            local_headers = {
                "Host": "127.0.0.1:58000",
                "Origin": "http://127.0.0.1:58000",
                "Sec-Fetch-Site": "same-origin",
            }
            for method in ("GET", "HEAD"):
                for headers, remote, expected in (
                    (local_headers, "127.0.0.1", 200),
                    (
                        {**local_headers, "Origin": "https://attacker.example"},
                        "127.0.0.1",
                        403,
                    ),
                    ({**local_headers, "Host": "attacker.example"}, "127.0.0.1", 403),
                    (
                        {**local_headers, "Sec-Fetch-Site": "cross-site"},
                        "127.0.0.1",
                        403,
                    ),
                    (local_headers, "192.0.2.1", 403),
                ):
                    with self.subTest(method=method, headers=headers, remote=remote):
                        send.reset_mock()
                        response = client.open(
                            url,
                            method=method,
                            headers=headers,
                            environ_base={"REMOTE_ADDR": remote},
                        )
                        self.assertEqual(response.status_code, expected)
                        self.assertEqual(send.call_count, int(expected == 200))
            server.app.config["WEBVIEW_LOCAL_ONLY_NO_TOKEN"] = False
            for token, expected in (
                (None, 403),
                ("invalid", 403),
                ("runtime-secret", 200),
            ):
                with self.subTest(token=token):
                    send.reset_mock()
                    headers = {**local_headers, **({"token": token} if token else {})}
                    response = client.get(url, headers=headers)
                    self.assertEqual(response.status_code, expected)
                    self.assertEqual(send.call_count, int(expected == 200))


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("screenshots", ["0", "1"])
def test_export_modes_preserve_log_read_boundary(
    tmp_path, monkeypatch, archived, screenshots
):
    from datetime import datetime

    center = datetime.now()
    timestamp = int(center.timestamp() * 10**9)
    archive = tmp_path / "screenshot" / "errors" / str(timestamp)
    archive.mkdir(parents=True)
    (archive / "event.json").write_text("{}", encoding="utf-8")
    path = (
        f"/diagnostics/errors/{timestamp}/export?screenshots={screenshots}"
        if archived
        else f"/diagnostics/export?at={int(center.timestamp() * 1000)}&screenshots={screenshots}"
    )
    monkeypatch.setattr(server.app, "token", "runtime-secret", raising=False)
    monkeypatch.setitem(server.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", True)
    client = server.app.test_client()
    local_headers = {
        "Host": "127.0.0.1:58000",
        "Origin": "http://127.0.0.1:58000",
        "Sec-Fetch-Site": "same-origin",
    }
    with (
        patch.object(
            server, "get_path", side_effect=AssertionError("未授权时不可读取文件")
        ),
        patch.object(
            server, "export_bundle", side_effect=AssertionError("未授权时不可打包")
        ),
    ):
        for headers, remote in (
            ({**local_headers, "Origin": "https://other.example"}, "127.0.0.1"),
            ({**local_headers, "Host": "other.example"}, "127.0.0.1"),
            ({**local_headers, "Sec-Fetch-Site": "cross-site"}, "127.0.0.1"),
            (local_headers, "192.0.2.1"),
        ):
            response = client.get(
                path, headers=headers, environ_base={"REMOTE_ADDR": remote}
            )
            assert response.status_code == 403
        monkeypatch.setitem(server.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", False)
        for token in (None, "wrong"):
            headers = {**local_headers, **({"token": token} if token else {})}
            assert client.get(path, headers=headers).status_code == 403
    with (
        patch.object(server, "get_path", side_effect=lambda name: tmp_path / name[5:]),
        patch.object(
            server, "_send_diagnostic_bundle", return_value={"export": True}
        ) as send,
    ):
        assert client.get(
            path, headers={**local_headers, "token": "runtime-secret"}
        ).json == {"export": True}
        monkeypatch.setitem(server.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", True)
        assert client.get(path, headers=local_headers).json == {"export": True}
        assert send.call_count == 2


@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("screenshots", ["", "false", "2"])
def test_invalid_screenshot_option_rejected_before_packing(
    monkeypatch, screenshots, archived
):
    import time

    monkeypatch.setattr(server.app, "token", "runtime-secret", raising=False)
    with (
        patch.object(
            server, "get_path", side_effect=AssertionError("无效选项不可读取文件")
        ),
        patch.object(
            server, "export_bundle", side_effect=AssertionError("无效选项不可打包")
        ),
    ):
        path = (
            f"/diagnostics/errors/123/export?screenshots={screenshots}"
            if archived
            else f"/diagnostics/export?at={int(time.time() * 1000)}&screenshots={screenshots}"
        )
        response = server.app.test_client().get(
            path,
            headers={"token": "runtime-secret"},
        )
        assert response.status_code == 400


@pytest.fixture
def media_access(tmp_path, monkeypatch):
    from arknights_mower.utils import log

    archive = tmp_path / "errors" / "123"
    archive.mkdir(parents=True)
    (tmp_path / "fixture.jpg").write_bytes(b"synthetic screenshot")
    (archive / "event.json").write_text("{}", encoding="utf-8")
    (archive / "logs.json").write_text(
        '[{"message":"synthetic log"}]', encoding="utf-8"
    )
    paths = Mock(return_value=tmp_path)
    store = Mock()
    store.last_saved.return_value = "fixture.jpg"
    monkeypatch.setattr(server, "get_path", paths)
    monkeypatch.setattr(log, "get_screenshot_store", Mock(return_value=store))
    monkeypatch.setattr(server.app, "token", "media-fixture-token", raising=False)
    monkeypatch.setitem(server.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", False)
    return server.app.test_client(), paths, store


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("remote", ["127.0.0.1", "192.0.2.1"])
@pytest.mark.parametrize("accept", ["application/json", "text/html"])
@pytest.mark.parametrize("token", [None, "wrong", "media-fixture-token"])
@pytest.mark.parametrize(
    "path,body",
    [
        ("/latest-screenshot", b"fixture.jpg"),
        ("/screenshots/fixture.jpg", b"synthetic screenshot"),
        ("/screenshots/errors/123/logs.json", b'[{"message":"synthetic log"}]'),
        ("/diagnostics/errors/123/logs", b"synthetic log"),
    ],
)
def test_media_reads_require_configured_token_before_access(
    media_access, method, remote, accept, token, path, body
):
    client, paths, store = media_access
    headers = {"Accept": accept}
    if token is not None:
        headers["token"] = token
    with client.open(
        path,
        method=method,
        headers={"Host": "127.0.0.1", **headers},
        environ_base={"REMOTE_ADDR": remote},
    ) as response:
        if token == "media-fixture-token":
            assert response.status_code == 200
            assert body in response.data if method == "GET" else response.data == b""
        else:
            assert response.status_code == 403
            paths.assert_not_called()
            store.last_saved.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_diagnostic_logs_keep_complete_local_log_boundary(
    media_access, monkeypatch, method
):
    client, paths, _ = media_access
    monkeypatch.setitem(server.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", True)
    local = {
        "Host": "127.0.0.1:58000",
        "Origin": "http://127.0.0.1:58000",
        "Referer": "http://127.0.0.1:58000/log/schedule",
        "Sec-Fetch-Site": "same-origin",
    }
    for overrides, remote, expected in (
        ({}, "127.0.0.1", 200),
        ({"Origin": "https://other.example"}, "127.0.0.1", 403),
        ({"Host": "other.example"}, "127.0.0.1", 403),
        ({"Referer": "https://other.example/page"}, "127.0.0.1", 403),
        ({"Sec-Fetch-Site": "cross-site"}, "127.0.0.1", 403),
        ({}, "192.0.2.1", 403),
    ):
        paths.reset_mock()
        with client.open(
            "/diagnostics/errors/123/logs",
            method=method,
            headers={**local, **overrides},
            environ_base={"REMOTE_ADDR": remote},
        ) as response:
            assert response.status_code == expected
            if expected == 403:
                paths.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("token", [None, "wrong", "media-fixture-token"])
@pytest.mark.parametrize(
    "path",
    [
        "/latest-screenshot",
        "/screenshots/fixture.jpg",
        "/screenshots/errors/123/logs.json",
    ],
)
def test_screenshot_files_and_path_have_no_local_log_exception(
    media_access, monkeypatch, method, token, path
):
    client, paths, store = media_access
    monkeypatch.setitem(server.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", True)
    with client.open(
        path,
        method=method,
        headers={
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            **({"token": token} if token is not None else {}),
        },
    ) as response:
        assert response.status_code == (200 if token == "media-fixture-token" else 403)
        if token != "media-fixture-token":
            paths.assert_not_called()
            store.last_saved.assert_not_called()


def test_media_file_conditional_and_range_requests_keep_token_boundary(media_access):
    client, paths, _ = media_access
    path = "/screenshots/fixture.jpg"
    authorized = {"token": "media-fixture-token"}
    with client.get(path, headers=authorized) as response:
        etag = response.headers["ETag"]
    for extra, expected in (
        ({"If-None-Match": etag}, 304),
        ({"Range": "bytes=0-3"}, 206),
    ):
        for token in (None, "wrong", "media-fixture-token"):
            paths.reset_mock()
            headers = {**extra, **({"token": token} if token is not None else {})}
            with client.get(path, headers=headers) as response:
                assert response.status_code == (
                    expected if token == "media-fixture-token" else 403
                )
                if token != "media-fixture-token":
                    paths.assert_not_called()


@pytest.mark.parametrize(
    "path",
    ["/latest-screenshot", "/screenshots/fixture.jpg", "/diagnostics/errors/123/logs"],
)
def test_media_options_does_not_read_files_or_runtime_state(media_access, path):
    client, paths, store = media_access
    with client.options(path) as response:
        assert response.status_code == 200
        assert response.data == b""
        paths.assert_not_called()
        store.last_saved.assert_not_called()
