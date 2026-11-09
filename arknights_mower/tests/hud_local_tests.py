import http.client
import select
import socket
import socketserver
import threading
import time
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import server
import webview_ui
from arknights_mower import __main__ as mower
from arknights_mower.utils import hud_local
from arknights_mower.utils.lifecycle import Phase, Shutdown
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.views import task as task_route


@pytest.fixture
def local_hud(monkeypatch):
    start = getattr(webview_ui, "start_hud_local_server", None)
    assert callable(start), "桌面实例应提供本地只读 HUD 服务"
    worker = SimpleNamespace(is_alive=lambda: True)
    task = SchedulerTask(
        time=datetime(2026, 11, 9, 12, 30),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_2_1": ["但书", "龙舌兰"]},
    )
    scheduler = SimpleNamespace(
        sleeping=True,
        tasks=[task],
        op_data=SimpleNamespace(
            operators={},
            plan={},
            plan_condition=[],
            backup_plans=[],
            facility_states={"room_2_1": {"facility": "trade"}},
        ),
    )
    monkeypatch.setattr(server.app, "token", "synthetic-secret", raising=False)
    monkeypatch.setattr(server, "mower_thread", worker)
    monkeypatch.setattr(task_route, "mower_thread", worker)
    monkeypatch.setattr(mower, "base_scheduler", scheduler)
    monkeypatch.setattr(
        mower,
        "device_control",
        SimpleNamespace(status=lambda: SimpleNamespace(status="ready")),
    )
    monkeypatch.setattr(mower, "get_manual_pause", lambda: None)
    service = start(server.app, "fixture-instance", 58000, "测试实例")
    try:
        yield service, scheduler
    finally:
        service.close()


def request(service, method="GET", path="/mowerhud", headers=None, timeout=3):
    client = http.client.HTTPConnection("127.0.0.1", service.port, timeout=timeout)
    try:
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        client.close()


def test_local_hud_reads_current_status_and_task_without_revealing_token(local_hud):
    import json

    service, scheduler = local_hud
    status, headers, body = request(service)
    data = json.loads(body)
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert data["protocol"] == "mowerhud/1"
    assert data["id"] == "fixture-instance"
    assert data["mower_port"] == 58000
    assert data["status"] == "sleeping"
    assert data["tasks"][0]["presentation"]["rooms"][0]["label"] == "贸易站 B201"
    assert data["tasks"][0]["plan"] == {"room_2_1": []}
    assert b"synthetic-secret" not in body
    assert scheduler.tasks[0].plan == {"room_2_1": ["但书", "龙舌兰"]}
    assert server.app.test_client().get("/status").status_code == 403
    assert server.app.test_client().get("/task").status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://elsewhere.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Referer": "https://elsewhere.example/"},
        {"Host": "elsewhere.example"},
        {"Forwarded": "for=192.0.2.4"},
        {"X-Forwarded-For": "192.0.2.4"},
        {"X-Forwarded-Host": "elsewhere.example"},
        {"X-Real-IP": "192.0.2.4"},
        {"Sec-Fetch-Mode": "cors"},
    ],
)
def test_local_hud_rejects_browser_and_forwarded_requests(local_hud, headers):
    status, response_headers, body = request(local_hud[0], headers=headers)
    assert status == 403
    assert b"fixture-instance" not in body
    assert "Access-Control-Allow-Origin" not in response_headers


def test_local_hud_rejects_write_methods(local_hud):
    assert request(local_hud[0], method="POST")[0] == 405


def test_local_hud_does_not_serve_unknown_paths(local_hud):
    assert request(local_hud[0], path="/status")[0] == 404


def test_local_hud_returns_at_most_two_queued_tasks(local_hud):
    import json

    service, scheduler = local_hud
    scheduler.tasks.extend([scheduler.tasks[0], scheduler.tasks[0]])
    assert len(json.loads(request(service)[2])["tasks"]) == 2


def test_local_hud_close_releases_its_listener(local_hud):
    service, _ = local_hud
    service.close()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", service.port), timeout=1)


def test_incomplete_headers_do_not_block_another_hud_request(local_hud):
    service, _ = local_hud
    with socket.create_connection(("127.0.0.1", service.port), timeout=1) as slow:
        slow.sendall(b"GET /mowerhud HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Slow: ")
        time.sleep(0.2)
        assert request(service, timeout=1)[0] == 200


def test_close_finishes_while_client_trickles_incomplete_headers(
    local_hud, monkeypatch
):
    service, _ = local_hud
    calls = Mock(wraps=server.app.test_client)
    monkeypatch.setattr(server.app, "test_client", calls)
    slow = socket.create_connection(("127.0.0.1", service.port), timeout=1)
    slow.sendall(b"GET /mowerhud HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Slow: ")
    stop_sending = threading.Event()
    closed = threading.Event()
    later_cleanup = threading.Event()
    errors = []
    shutdown = Shutdown()
    shutdown.own("local HUD server", service.close, Phase.SERVER)
    shutdown.own("later cleanup", later_cleanup.set, Phase.UI)

    def send_slowly():
        while not stop_sending.wait(0.1):
            try:
                slow.sendall(b"x")
            except OSError:
                return

    def close_service():
        try:
            shutdown.close()
        except Exception as exc:
            errors.append(exc)
        finally:
            closed.set()

    sender = threading.Thread(target=send_slowly, daemon=True)
    closer = threading.Thread(target=close_service, daemon=True)
    sender.start()
    disconnected_during_close = False
    try:
        time.sleep(0.2)
        closer.start()
        completed_during_trickle = closed.wait(1.5)
        if completed_during_trickle:
            try:
                disconnected_during_close = not slow.recv(1)
            except ConnectionError:
                disconnected_during_close = True
    finally:
        stop_sending.set()
        slow.close()
        sender.join(1)
        closer.join(4)
    assert completed_during_trickle
    assert disconnected_during_close
    assert not errors
    assert not shutdown.errors
    assert later_cleanup.is_set()
    calls.assert_not_called()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", service.port), timeout=1)


def test_close_finishes_when_a_snapshot_request_is_still_running(
    local_hud, monkeypatch
):
    service, _ = local_hud
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    errors = []
    original_status = server.app.view_functions["get_status"]

    def blocked_status():
        entered.set()
        release.wait(5)
        return original_status()

    def read_snapshot():
        try:
            request(service)
        except OSError:
            pass

    def close_service():
        try:
            service.close()
        except Exception as exc:
            errors.append(exc)
        finally:
            closed.set()

    monkeypatch.setitem(server.app.view_functions, "get_status", blocked_status)
    reader = threading.Thread(target=read_snapshot, daemon=True)
    closer = threading.Thread(target=close_service, daemon=True)
    reader.start()
    try:
        assert entered.wait(2)
        closer.start()
        completed_while_blocked = closed.wait(1.5)
    finally:
        release.set()
        reader.join(3)
        if closer.ident is not None:
            closer.join(4)
    assert completed_while_blocked
    assert not errors


def test_close_applies_its_deadline_when_server_shutdown_stalls(local_hud, monkeypatch):
    service, _ = local_hud
    release = threading.Event()
    original_shutdown = socketserver.BaseServer.shutdown

    def delayed_shutdown(http_server):
        release.wait(5)
        original_shutdown(http_server)

    monkeypatch.setattr(hud_local, "_SHUTDOWN_TIMEOUT", 0.3)
    monkeypatch.setattr(socketserver.BaseServer, "shutdown", delayed_shutdown)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            service.close()
        assert time.monotonic() - started < 2
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", service.port), timeout=1)
    finally:
        monkeypatch.setattr(socketserver.BaseServer, "shutdown", original_shutdown)
        release.set()


def test_close_releases_listener_if_socket_shutdown_is_unsupported(
    local_hud, monkeypatch
):
    service, _ = local_hud

    def unsupported_shutdown(_socket, _how):
        raise OSError("shutdown unsupported")

    monkeypatch.setattr(socket.socket, "shutdown", unsupported_shutdown)
    service.close()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", service.port), timeout=1)


def test_concurrent_snapshot_requests_are_bounded(local_hud, monkeypatch):
    service, _ = local_hud
    entered = threading.Event()
    release = threading.Event()
    count_lock = threading.Lock()
    active = 0
    original_status = server.app.view_functions["get_status"]

    def blocked_status():
        nonlocal active
        with count_lock:
            active += 1
            if active == 4:
                entered.set()
        release.wait(5)
        return original_status()

    monkeypatch.setitem(server.app.view_functions, "get_status", blocked_status)
    headers = (
        f"GET /mowerhud HTTP/1.1\r\nHost: 127.0.0.1:{service.port}\r\n\r\n"
    ).encode("ascii")
    try:
        with ExitStack() as sockets:
            for _ in range(4):
                client = sockets.enter_context(
                    socket.create_connection(("127.0.0.1", service.port), timeout=1)
                )
                client.sendall(headers)
            assert entered.wait(2)
            extra = sockets.enter_context(
                socket.create_connection(("127.0.0.1", service.port), timeout=1)
            )
            try:
                extra.sendall(headers)
                assert not extra.recv(1)
            except ConnectionError:
                pass
            with count_lock:
                assert active == 4
    finally:
        release.set()


def test_client_disconnect_during_headers_does_not_read_snapshot(
    local_hud, monkeypatch
):
    service, _ = local_hud
    calls = Mock(wraps=server.app.test_client)
    monkeypatch.setattr(server.app, "test_client", calls)
    with socket.create_connection(("127.0.0.1", service.port), timeout=1) as slow:
        slow.sendall(
            f"GET /mowerhud HTTP/1.1\r\nHost: 127.0.0.1:{service.port}\r\n"
            "X-Incomplete: ".encode("ascii")
        )
        slow.shutdown(socket.SHUT_WR)
        assert not slow.recv(1024)
    calls.assert_not_called()


@pytest.mark.parametrize(
    ("partial_line", "fragment"),
    [(True, b"x"), (False, b"x"), (False, b"x\r\nX-Slow: ")],
    ids=["request-line", "header-line", "complete-header-lines"],
)
def test_trickling_request_headers_have_a_total_deadline(
    local_hud, monkeypatch, partial_line, fragment
):
    service, _ = local_hud
    calls = Mock(wraps=server.app.test_client)
    monkeypatch.setattr(server.app, "test_client", calls)
    with socket.create_connection(("127.0.0.1", service.port), timeout=1) as slow:
        initial = (
            b"GET /mow"
            if partial_line
            else (
                f"GET /mowerhud HTTP/1.1\r\nHost: 127.0.0.1:{service.port}\r\nX-Slow: "
            ).encode("ascii")
        )
        slow.sendall(initial)
        deadline = time.monotonic() + 4.5
        disconnected = False
        while time.monotonic() < deadline:
            time.sleep(0.1)
            try:
                slow.sendall(fragment)
                if select.select([slow], [], [], 0.05)[0]:
                    disconnected = not slow.recv(1)
                    break
            except OSError:
                disconnected = True
                break
    assert disconnected
    calls.assert_not_called()
    assert request(service, timeout=1)[0] == 200
