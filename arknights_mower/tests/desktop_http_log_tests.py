"""桌面 HTTP 日志不记录请求中的会话凭据。"""

import logging
import socket
from http.client import HTTPConnection
from urllib.parse import quote

import pytest
from flask import Flask, request
from werkzeug import serving

import webview_ui
from arknights_mower.utils import lifecycle, log


@pytest.mark.parametrize(
    ("status", "malformed", "expected_access_log"),
    [
        (200, False, []),
        (204, False, []),
        (302, False, []),
        (304, False, []),
        (401, False, ["HTTP 请求完成，状态码 401"]),
        (500, False, ["HTTP 请求完成，状态码 500"]),
        (400, True, ["HTTP 请求完成，状态码 400"]),
    ],
)
def test_desktop_http_keeps_request_credentials_out_of_logs(
    monkeypatch, caplog, capsys, status, malformed, expected_access_log
):
    token = "synthetic-session-secret-84"
    encoded = quote("synthetic/encoded+secret", safe="")
    target = f"/?token={token}&token={encoded}"
    app = Flask(__name__)
    received = []

    @app.get("/")
    def index():
        received.append(request.args.getlist("token"))
        return "ready", status

    shutdown = lifecycle.Shutdown()
    monkeypatch.setattr(lifecycle, "shutdown", shutdown)
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    monkeypatch.setattr(log.logger, "disabled", False)
    monkeypatch.setattr(log.logger, "level", logging.DEBUG)
    caplog.set_level(logging.DEBUG)
    servers = []
    make_server = serving.make_server

    def create_server(*args, **kwargs):
        server = make_server(*args, **kwargs)
        servers.append(server)
        return server

    monkeypatch.setattr(serving, "make_server", create_server)
    webview_ui.start_http_server(app, "127.0.0.1", 0)
    try:
        port = servers[0].server_port
        if malformed:
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                client.sendall(f"GET {target} HTTP/1.1 extra\r\n\r\n".encode())
                response = b""
                while chunk := client.recv(4096):
                    response += chunk
                assert b"400" in response
            assert received == []
        else:
            client = HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                client.request("GET", target)
                response = client.getresponse()
                assert response.status == status
                assert response.read() == (b"" if status in (204, 304) else b"ready")
            finally:
                client.close()
            assert received == [[token, "synthetic/encoded+secret"]]
    finally:
        shutdown.close("test")

    assert shutdown.errors == []
    output = caplog.text + capsys.readouterr().err
    for secret in (token, encoded, "synthetic/encoded+secret"):
        assert secret not in output
    request_records = [
        record
        for record in caplog.records
        if record.name == log.logger.name and record.funcName == "log_request"
    ]
    assert [record.getMessage() for record in request_records] == expected_access_log
    assert all(record.levelno == logging.DEBUG for record in request_records)
    if malformed:
        assert "HTTP 请求处理事件：error" in output
