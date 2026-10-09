"""Regression coverage for AI WebSocket and source-snippet boundaries."""

import json
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from simple_websocket import Client, ConnectionClosed
from werkzeug.serving import make_server

import server
from arknights_mower.agent.tools import get_source_snippet as snippet_module


class FakeSocket:
    def __init__(self, *frames):
        self.frames = iter(frames)
        self.sent = []
        self.closed = False

    def receive(self, timeout=None):
        return next(self.frames, None)

    def send(self, value):
        self.sent.append(json.loads(value))

    def close(self, reason=None, message=None):
        self.closed = True
        self.close_reason = reason


class WebSocketSecurityTests(unittest.TestCase):
    def setUp(self):
        self.old_token = getattr(server.app, "token", None)
        server.app.token = "test-secret"

    def tearDown(self):
        if self.old_token is None and hasattr(server.app, "token"):
            del server.app.token
        elif self.old_token is not None:
            server.app.token = self.old_token

    def _authorize(self, frames, origin="http://localhost"):
        headers = {"Host": "localhost"}
        if origin is not None:
            headers["Origin"] = origin
        ws = FakeSocket(*frames)
        with server.app.test_request_context("/ws/chat", headers=headers):
            allowed = server._authorize_websocket(ws)
        return allowed, ws

    def test_missing_invalid_and_cross_origin_credentials_are_rejected(self):
        for frames, origin in (
            ([json.dumps({"message": "hello"})], "http://localhost"),
            ([json.dumps({"token": "wrong"})], "http://localhost"),
            ([json.dumps({"token": "test-secret"})], "https://attacker.example"),
            ([json.dumps({"token": "test-secret"})], None),
        ):
            with self.subTest(frames=frames, origin=origin):
                allowed, ws = self._authorize(frames, origin)
                self.assertFalse(allowed)
                self.assertTrue(ws.closed)
                self.assertEqual(ws.close_reason, 4401)

    def test_configured_dev_port_is_explicit_and_loopback_only(self):
        with patch.dict("os.environ", {"MOWER_DEV_PORT": "5174"}):
            for origin, expected in (
                ("http://127.0.0.1:5174", True),
                ("http://127.0.0.1:5173", False),
                ("http://attacker.example:5174", False),
            ):
                allowed, _ = self._authorize(
                    [json.dumps({"token": "test-secret"})], origin
                )
                self.assertEqual(allowed, expected)

    def test_empty_configured_token_does_not_allow_chat(self):
        server.app.token = ""
        if hasattr(server.app, "token"):
            del server.app.token
        allowed, ws = self._authorize([json.dumps({"token": ""})])
        self.assertFalse(allowed)
        self.assertTrue(ws.closed)

    def test_authenticated_chat_preserves_streamed_reply(self):
        service = make_server("127.0.0.1", 0, server.app, threaded=True)
        thread = Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(service.shutdown)
        url = f"ws://127.0.0.1:{service.server_port}/ws/chat"
        # simple_websocket.Client omits the nondefault port from its Host header.
        origin = "http://127.0.0.1"
        with patch(
            "arknights_mower.agent.agent.ask_llm", return_value=iter(["reply"])
        ) as ask:
            unauthorized = Client.connect(url, headers={"Origin": origin})
            try:
                unauthorized.send(json.dumps({"message": "hello"}))
            except ConnectionClosed:
                pass
            else:
                with self.assertRaises(ConnectionClosed):
                    unauthorized.receive(timeout=2)
            ask.assert_not_called()

            authorized = Client.connect(url, headers={"Origin": origin})
            authorized.send(json.dumps({"token": "test-secret"}))
            authorized.send(json.dumps({"message": "hello"}))
            self.assertEqual(
                json.loads(authorized.receive(timeout=2)), {"reply": "reply"}
            )
            self.assertEqual(json.loads(authorized.receive(timeout=2)), {"done": True})
            ask.assert_called_once()
            authorized.close()

    def test_chat_completion_follows_all_chunks_and_handles_empty_or_failed_streams(
        self,
    ):
        def failed_stream():
            yield "部分回复"
            raise ValueError("模型错误")

        for stream, expected in (
            (
                iter(["正在查询", "结果"]),
                [{"reply": "正在查询"}, {"reply": "结果"}, {"done": True}],
            ),
            (iter([]), [{"done": True}]),
            (failed_stream(), [{"reply": "部分回复"}, {"error": "模型错误"}]),
        ):
            with self.subTest(expected=expected):
                ws = FakeSocket(
                    json.dumps({"token": "test-secret"}),
                    json.dumps({"message": "查询"}),
                )
                with (
                    server.app.test_request_context(
                        "/ws/chat",
                        headers={"Host": "localhost", "Origin": "http://localhost"},
                    ),
                    patch("arknights_mower.agent.agent.ask_llm", return_value=stream),
                ):
                    server.app.view_functions["ws_chat"].__wrapped__(ws)
                self.assertEqual(ws.sent, expected)


class SourceSnippetSecurityTests(unittest.TestCase):
    def test_source_allowlist_blocks_secrets_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            package = root / "arknights_mower"
            package.mkdir()
            source = package / "sample.py"
            source.write_text("safe source\n", encoding="utf-8")
            secret = root / "config" / "conf.yml"
            secret.parent.mkdir()
            secret.write_text("dummy-secret\n", encoding="utf-8")
            private_source = secret.parent / "private.py"
            private_source.write_text("dummy-secret\n", encoding="utf-8")
            link = package / "linked.py"
            link.symlink_to(private_source)
            with (
                patch.object(snippet_module, "_PROJECT_ROOT", root),
                patch.object(snippet_module, "_PACKAGE_ROOT", package),
            ):
                allowed = json.loads(
                    snippet_module.get_source_snippet("arknights_mower/sample.py", 1)
                )
                self.assertEqual(allowed["source_code"], "safe source\n")
                for target in (
                    str(secret),
                    "config/conf.yml",
                    "arknights_mower/../config/private.py",
                    "arknights_mower/linked.py",
                ):
                    with self.subTest(target=target):
                        blocked = json.loads(
                            snippet_module.get_source_snippet(target, 1, 50)
                        )
                        self.assertNotIn("dummy-secret", blocked["source_code"])
                        self.assertIn("读取失败", blocked["source_code"])
                oversized = json.loads(
                    snippet_module.get_source_snippet(str(source), 1, 100000)
                )
                self.assertIn("读取失败", oversized["source_code"])


if __name__ == "__main__":
    unittest.main()
