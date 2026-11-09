import http.client
import socket
from datetime import datetime
from types import SimpleNamespace

import pytest

import server
import webview_ui
from arknights_mower import __main__ as mower
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


def request(service, method="GET", path="/mowerhud", headers=None):
    client = http.client.HTTPConnection("127.0.0.1", service.port, timeout=3)
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
