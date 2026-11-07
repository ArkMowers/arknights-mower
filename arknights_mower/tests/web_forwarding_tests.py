"""Forwarded requests retain explicit credentials before reaching operations."""

import json
from contextlib import nullcontext
from io import BytesIO
from unittest.mock import Mock

import pytest
from flask import Request

TOKEN = "forwarded-instance"
FORWARDED = {
    "Host": "127.0.0.1:58000",
    "Origin": "https://mower.example:8443",
    "X-Forwarded-Host": "untrusted.example",
    "X-Forwarded-Proto": "http",
}
OPERATIONS = [
    ("POST", "/software-update/check", "X-Mower-Update", {"channel": "beta"}),
    (
        "POST",
        "/network/settings",
        "X-Mower-Settings",
        {"http_proxy": "", "github_proxy": ""},
    ),
    ("POST", "/network/test", "X-Mower-Settings", {}),
    ("POST", "/process-control/action", "X-Mower-Control", {"action": "resume"}),
    ("POST", "/config-backup/import", "X-Mower-Settings", {}),
    ("POST", "/config-profiles", "X-Mower-Settings", {"name": "next"}),
    ("PATCH", "/config-profiles/example", "X-Mower-Settings", {"name": "next"}),
    ("POST", "/db-admin/compact", "X-Mower-Settings", {}),
    ("PUT", "/db-admin/backup-limit", "X-Mower-Settings", {"backup_limit_mib": 10}),
    ("DELETE", "/diagnostics/errors/123", "X-Mower-Diagnostics", {}),
    ("POST", "/diagnostics/errors/123/analyze", "X-Mower-Diagnostics", {}),
]


@pytest.fixture
def forwarding_server(monkeypatch, tmp_path):
    import server
    from arknights_mower.agent import schedule_error
    from arknights_mower.utils import (
        config_profiles,
        network_settings,
        process_control,
        software_update,
    )
    from arknights_mower.utils.config import gui
    from arknights_mower.views import db_admin

    monkeypatch.setattr(server.app, "token", TOKEN, raising=False)
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", True)
    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", True)
    monkeypatch.setitem(server.app.config, "CONFIG_BACKUP_BUSY", lambda: False)
    monkeypatch.setitem(server.app.config, "CONFIG_PROFILES_BUSY", lambda: False)
    monkeypatch.setitem(server.app.config, "CONFIG_PROFILES_LOCKS", nullcontext)
    monkeypatch.setitem(server.app.config, "CONFIGURATION_ACTIVATED", lambda: None)
    monkeypatch.delenv("MOWER_MANAGED", raising=False)
    monkeypatch.setattr(config_profiles, "check_generation", lambda *a, **kw: None)
    operation = Mock(return_value={"ok": True, "generation": "0"})
    for owner, name in (
        (software_update, "check"),
        (software_update, "inspect_upload"),
        (network_settings, "save_settings"),
        (process_control, "request_action"),
        (config_profiles, "import_backup"),
        (config_profiles, "create_profile"),
        (config_profiles, "import_profile"),
        (config_profiles, "rename_profile"),
        (db_admin, "_compact_database"),
        (gui, "update_gui_data"),
        (schedule_error, "analyze_schedule_error"),
        (server.shutil, "rmtree"),
    ):
        monkeypatch.setattr(owner, name, operation)
    monkeypatch.setattr(db_admin, "_maintenance_status", lambda: {"busy": False})
    monkeypatch.setattr(
        network_settings,
        "get_effective_settings",
        lambda: {"http_proxy": "", "github_proxy": "", "github_token": ""},
    )
    from arknights_mower.views import network

    monkeypatch.setattr(network, "_probe_connection", operation)
    from arknights_mower.utils import log

    monkeypatch.setattr(log, "get_screenshot_store", lambda: None)
    monkeypatch.setattr(server, "diagnostic_error_logs", lambda _: {"logs": []})
    monkeypatch.setattr(
        server, "get_path", lambda name: tmp_path / name.removeprefix("@app/")
    )
    folder = tmp_path / "screenshot/errors/123"
    folder.mkdir(parents=True)
    (folder / "event.json").write_text("{}", encoding="utf-8")
    return server, operation


@pytest.mark.parametrize("method,path,header,body", OPERATIONS)
@pytest.mark.parametrize(
    "origin",
    [
        "https://mower.example:8443",
        "http://mower.example:18000",
        "https://[2001:db8::1]:8443",
    ],
)
def test_valid_token_reaches_forwarded_operation(
    forwarding_server, method, path, header, body, origin
):
    server, operation = forwarding_server
    response = server.app.test_client().open(
        path,
        method=method,
        headers={
            **FORWARDED,
            "Origin": origin,
            "token": TOKEN,
            header: "1",
            "X-Mower-Config-Generation": "0",
        },
        json=body,
    )
    assert response.status_code in {200, 204}, response.get_data(as_text=True)
    operation.assert_called_once()


@pytest.mark.parametrize("method,path,header,body", OPERATIONS)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_forwarded_headers_never_replace_token(
    forwarding_server, monkeypatch, method, path, header, body, token
):
    server, operation = forwarding_server
    forbidden = Mock(side_effect=AssertionError("Unauthorized request parsed input"))
    monkeypatch.setattr(Request, "get_json", forbidden)
    headers = {**FORWARDED, header: "1"}
    if token is not None:
        headers["token"] = token
    response = server.app.test_client().open(
        path, method=method, headers=headers, json=body
    )
    assert response.status_code == 403
    forbidden.assert_not_called()
    operation.assert_not_called()


@pytest.mark.parametrize("method,path,header,body", OPERATIONS)
def test_forwarded_operation_still_requires_operation_header(
    forwarding_server, method, path, header, body
):
    server, operation = forwarding_server
    response = server.app.test_client().open(
        path, method=method, headers={**FORWARDED, "token": TOKEN}, json=body
    )
    assert response.status_code == 403
    operation.assert_not_called()


@pytest.mark.parametrize(
    "origin",
    [
        "https://mower.example:8443",
        "http://mower.example:18000",
        "https://[2001:db8::1]:8443",
        "null",
        None,
    ],
)
@pytest.mark.parametrize("token", [None, "wrong", TOKEN])
def test_forwarded_ai_chat_authenticates_before_model_call(
    forwarding_server, monkeypatch, origin, token
):
    server, _ = forwarding_server
    from arknights_mower.agent import agent
    from arknights_mower.tests.ai_security_tests import FakeSocket

    ask = Mock(return_value=iter(["forwarded reply"]))
    monkeypatch.setattr(agent, "ask_llm", ask)
    monkeypatch.setattr(server, "configuration_chat_request", lambda _: nullcontext())
    socket = FakeSocket(
        json.dumps({"token": token}),
        json.dumps({"message": "hello", "generation": "0"}),
    )
    headers = {
        key: value
        for key, value in {**FORWARDED, "Origin": origin}.items()
        if value is not None
    }
    with server.app.test_request_context("/ws/chat", headers=headers):
        server.app.view_functions["ws_chat"].__wrapped__(socket)
    if token == TOKEN:
        assert socket.sent == [{"reply": "forwarded reply"}, {"done": True}]
        ask.assert_called_once()
    else:
        assert socket.closed
        assert socket.close_reason == 4401
        ask.assert_not_called()


@pytest.mark.parametrize("configured", [None, ""])
@pytest.mark.parametrize(
    "origin,expected", [("http://localhost", 200), ("https://mower.example:8443", 403)]
)
def test_tokenless_operations_keep_direct_origin_boundary(
    monkeypatch, configured, origin, expected
):
    from flask import Flask

    from arknights_mower.utils import software_update
    from arknights_mower.views.software_update import software_update_bp

    app = Flask(__name__)
    if configured is not None:
        app.token = configured
    app.register_blueprint(software_update_bp)
    check = Mock(return_value={"ok": True})
    monkeypatch.setattr(software_update, "check", check)
    response = app.test_client().post(
        "/software-update/check",
        headers={
            "Origin": origin,
            "X-Mower-Update": "1",
            "X-Forwarded-Host": "mower.example:8443",
            "X-Forwarded-Proto": "https",
        },
        json={"channel": "beta"},
    )
    assert response.status_code == expected
    assert check.call_count == (1 if expected == 200 else 0)


@pytest.mark.parametrize(
    "path,field,header",
    [
        ("/software-update/manual/inspect", "file", "X-Mower-Update"),
        ("/config-backup/import", "backup", "X-Mower-Settings"),
        ("/config-profiles/import", "backup", "X-Mower-Settings"),
    ],
)
@pytest.mark.parametrize("token", [None, "wrong", TOKEN])
def test_forwarded_uploads_keep_credentials_before_inspection(
    forwarding_server, monkeypatch, path, field, header, token
):
    server, operation = forwarding_server
    headers = {**FORWARDED, header: "1", "X-Mower-Config-Generation": "0"}
    if token is not None:
        headers["token"] = token
    parse_upload = Mock(side_effect=AssertionError("Unauthorized upload was parsed"))
    if token != TOKEN:
        monkeypatch.setattr(Request, "_load_form_data", parse_upload)
    response = server.app.test_client().post(
        path,
        headers=headers,
        data={field: (BytesIO(b"offline upload fixture"), "fixture.zip")},
    )
    assert response.status_code == (200 if token == TOKEN else 403)
    assert operation.call_count == (1 if token == TOKEN else 0)
    parse_upload.assert_not_called()


def test_forwarded_update_still_requires_manager_permission(
    forwarding_server, monkeypatch
):
    server, operation = forwarding_server
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", False)
    response = server.app.test_client().post(
        "/software-update/check",
        headers={**FORWARDED, "token": TOKEN, "X-Mower-Update": "1"},
        json={"channel": "beta"},
    )
    assert response.status_code == 403
    assert response.json["error"] == "updates_disabled"
    operation.assert_not_called()


def test_forwarded_chat_still_requires_assistant_permission(
    forwarding_server, monkeypatch
):
    server, _ = forwarding_server
    from arknights_mower.agent import agent
    from arknights_mower.tests.ai_security_tests import FakeSocket

    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", False)
    ask = Mock()
    monkeypatch.setattr(agent, "ask_llm", ask)
    socket = FakeSocket(json.dumps({"token": TOKEN}), json.dumps({"message": "hello"}))
    with server.app.test_request_context("/ws/chat", headers=FORWARDED):
        server.app.view_functions["ws_chat"].__wrapped__(socket)
    assert socket.closed
    assert socket.close_reason == 4403
    assert socket.sent[0]["code"] == "ai_assistant_disabled"
    ask.assert_not_called()
