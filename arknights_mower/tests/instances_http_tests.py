"""Offline HTTP instance management retains shared manager admission rules."""

import json
import os
import subprocess
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from flask import Flask

from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.views import instances as routes


@pytest.fixture
def managed_http(tmp_path, monkeypatch):
    storage = tmp_path / "instances.json"
    current_directory = tmp_path / "current"
    live = []
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: list(live))
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    monkeypatch.setattr(runtime, "process_alive", lambda pid: pid == 12345)
    spawn = Mock(return_value=Mock(pid=12345))
    send = Mock()
    monkeypatch.setattr(controls.subprocess, "Popen", spawn)
    monkeypatch.setattr(runtime, "send_instance_command", send)
    monkeypatch.setattr(
        routes, "InstanceController", partial(controls.InstanceController, storage)
    )
    monkeypatch.setattr(routes, "get_path", lambda value: current_directory)
    controller = controls.InstanceController(storage)
    controller.add("current", str(current_directory))
    app = Flask(__name__)
    app.token = "instance-test-token"
    app.register_blueprint(routes.instances_bp)
    client = app.test_client()
    headers = {"token": app.token, "X-Mower-Settings": "1"}

    def action(name, *args, **kwargs):
        return client.post(
            "/instances/actions",
            json={"action": name, "args": list(args)},
            headers=kwargs.pop("headers", headers),
            **kwargs,
        )

    return SimpleNamespace(
        app=app,
        client=client,
        action=action,
        headers=headers,
        controller=controller,
        storage=storage,
        root=tmp_path,
        current=current_directory,
        live=live,
        spawn=spawn,
        send=send,
    )


def snapshot(api):
    return json.loads(api.storage.read_text("utf-8"))


def registration(instance, identifier="current", **changes):
    return dict(
        id=identifier,
        pid=12345,
        kind="instance",
        space=instance["path"],
        managed=True,
        ready=True,
        **changes,
    )


def test_reads_reload_the_shared_list_and_preserve_manager_status(managed_http):
    api = managed_http
    response = api.client.get("/instances", headers=api.headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json[0]["name"] == "current"
    assert response.json[0]["can_start"] is True
    assert response.json[0]["editable"] is True
    api.controller.add("second", str(api.root / "second"))
    api.live.append(registration(snapshot(api)[0]))
    response = api.client.get("/instances", headers=api.headers)
    assert [item["name"] for item in response.json] == ["current", "second"]
    assert response.json[0]["state"] == "running"
    assert response.json[0]["editable"] is False
    assert response.json[0]["can_stop"] is True
    assert not (api.current / "config/conf.yml").exists()


@pytest.mark.parametrize("token", [None, "wrong"])
def test_both_routes_reject_invalid_credentials_before_access(managed_http, token):
    api = managed_http
    headers = {"token": token} if token is not None else {}
    before = api.storage.read_bytes()
    for response in (
        api.client.get("/instances", headers=headers),
        api.action("add", "new", "", snapshot(api), headers=headers),
    ):
        assert response.status_code == 403
        assert response.json["message"]
    assert api.storage.read_bytes() == before
    api.spawn.assert_not_called()
    api.send.assert_not_called()


@pytest.mark.parametrize(
    "origin",
    [
        "http://other.example",
        "https://localhost",
        "http://localhost:5173",
        "http://localhost/path",
        "http://user@localhost",
        "null",
    ],
)
def test_mutations_reject_untrusted_origins(managed_http, origin):
    api = managed_http
    before = api.storage.read_bytes()
    response = api.action(
        "add", "new", "", snapshot(api), headers={**api.headers, "Origin": origin}
    )
    assert response.status_code == 403
    assert response.json["message"]
    assert api.storage.read_bytes() == before


def test_mutations_require_the_explicit_settings_header(managed_http):
    api = managed_http
    response = api.action(
        "add", "new", "", snapshot(api), headers={"token": api.app.token}
    )
    assert response.status_code == 403
    assert len(snapshot(api)) == 1


def test_same_origin_add_and_server_path_edit_persist_without_native_dialogs(
    managed_http,
):
    api = managed_http
    response = api.action(
        "add",
        "another",
        "",
        snapshot(api),
        headers={**api.headers, "Origin": "http://localhost"},
    )
    assert response.json == {"ok": True}
    second = snapshot(api)[1]
    directory = str(api.root / "服务器目录 空格")
    response = api.action("set_path", 1, directory, second)
    assert response.status_code == 200
    assert response.json == {"ok": True}
    assert snapshot(api)[1] == {"name": "another", "path": directory}
    assert not Path(directory).exists()
    response = api.action("rename", 1, "renamed", snapshot(api)[1])
    assert response.json == {"ok": True}
    response = api.action("remove", 1, snapshot(api)[1])
    assert response.json == {"ok": True}
    assert len(snapshot(api)) == 1


@pytest.mark.parametrize("path", [None, 1, "", " ", "relative/path", "../other"])
def test_manual_path_input_requires_a_nonempty_absolute_server_path(managed_http, path):
    api = managed_http
    before = api.storage.read_bytes()
    response = api.action("set_path", 0, path, snapshot(api)[0])
    assert response.status_code == 400
    assert response.json["message"]
    assert api.storage.read_bytes() == before


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"action": "add", "args": []},
        {"action": "add", "args": ["name", ""]},
        {"action": "add", "args": ["name", "", None]},
        {"action": "start_all", "args": []},
        {"action": "stop_all", "args": [None]},
        {"action": "remove", "args": [0, None]},
        {"action": "remove", "args": [-1, {"name": "current", "path": ""}]},
        {"action": "remove", "args": [True, {"name": "current", "path": ""}]},
        {"action": "remove", "args": [0, {"name": "current", "path": "", "extra": 1}]},
        {"action": "_save", "args": [[]]},
        {"action": "select_path", "args": [0]},
        {"action": "mark_ready", "args": []},
        {"action": ["add"], "args": []},
        {"action": "add", "args": {}, "extra": True},
    ],
)
def test_only_explicit_operations_with_valid_identity_arguments_are_accepted(
    managed_http, body
):
    api = managed_http
    before = api.storage.read_bytes()
    response = api.client.post("/instances/actions", json=body, headers=api.headers)
    assert response.status_code == 400
    assert response.json["message"]
    assert api.storage.read_bytes() == before
    api.spawn.assert_not_called()
    api.send.assert_not_called()


def test_request_limit_is_checked_before_loading_instances(managed_http, monkeypatch):
    api = managed_http
    construct = Mock(side_effect=AssertionError("Oversized request read instances"))
    monkeypatch.setattr(routes, "InstanceController", construct)
    response = api.client.post(
        "/instances/actions",
        data=b"x" * (1024 * 1024 + 1),
        content_type="application/json",
        headers=api.headers,
    )
    assert response.status_code == 413
    assert response.json["message"]
    construct.assert_not_called()


@pytest.mark.parametrize(
    "action", ["remove", "rename", "set_path", "update_settings", "start", "stop"]
)
def test_stale_single_row_targets_never_write_launch_or_stop(managed_http, action):
    api = managed_http
    target = snapshot(api)[0]
    arguments = {
        "remove": [0, target],
        "rename": [0, "renamed", target],
        "set_path": [0, str(api.root / "other"), target],
        "update_settings": [0, {"token": "new", "port": None}, target],
        "start": [0, target],
        "stop": [0, target],
    }
    controls.InstanceController(api.storage).rename(0, "changed elsewhere")
    before = api.storage.read_bytes()
    response = api.action(action, *arguments[action])
    assert response.status_code == 409
    assert response.json["ok"] is False
    assert api.storage.read_bytes() == before
    assert not (api.current / "config/conf.yml").exists()
    api.spawn.assert_not_called()
    api.send.assert_not_called()


@pytest.mark.parametrize(
    "action", ["add", "start_all", "stop_all", "update_all_settings"]
)
def test_stale_list_targets_never_modify_another_snapshot(managed_http, action):
    api = managed_http
    targets = snapshot(api)
    arguments = {
        "add": ["new", "", targets],
        "start_all": [targets],
        "stop_all": [targets],
        "update_all_settings": [[{"idx": 0, "settings": {"port": 58001}}], targets],
    }
    controls.InstanceController(api.storage).add("external", "")
    before = api.storage.read_bytes()
    response = api.action(action, *arguments[action])
    assert response.status_code == 409
    assert api.storage.read_bytes() == before
    assert not (api.current / "config/conf.yml").exists()
    api.spawn.assert_not_called()
    api.send.assert_not_called()


@pytest.mark.parametrize("live_destination", [False, True])
def test_path_changes_recheck_both_source_and_destination_processes(
    managed_http, live_destination
):
    api = managed_http
    target = snapshot(api)[0]
    destination = str(api.root / "occupied")
    api.live.append(registration({"path": destination} if live_destination else target))
    before = api.storage.read_bytes()
    response = api.action("set_path", 0, destination, target)
    assert response.status_code == 400
    assert "进程运行期间" in response.json["message"]
    assert api.storage.read_bytes() == before


def test_config_writes_preserve_unselected_fields_and_skip_live_processes(managed_http):
    api = managed_http
    config_file = api.current / "config/conf.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("account: keep\nwebview:\n  tray: true\n", encoding="utf-8")
    target = snapshot(api)[0]
    response = api.action(
        "update_settings", 0, {"token": "shared", "port": None}, target
    )
    assert response.json == {"ok": True}
    saved = yaml.safe_load(config_file.read_text("utf-8"))
    assert saved["account"] == "keep"
    assert saved["webview"] == {"tray": True, "token": "shared", "port": 0}
    before = config_file.read_bytes()
    api.live.append(registration(target))
    response = api.action(
        "update_settings", 0, {"token": "replace", "port": None}, target
    )
    assert response.status_code == 400
    response = api.action(
        "update_all_settings",
        [{"idx": 0, "settings": {"updates_enabled": False}}],
        snapshot(api),
    )
    assert response.json["results"][0]["status"] == "skipped"
    assert config_file.read_bytes() == before


def test_update_admission_and_launch_reservations_remain_shared(
    managed_http, monkeypatch
):
    api = managed_http
    target = snapshot(api)[0]
    monkeypatch.setattr(runtime, "active_job", lambda: True)
    response = api.action("start", 0, target)
    assert response.status_code == 409
    assert "更新" in response.json["message"]
    api.spawn.assert_not_called()
    assert api.action("rename", 0, "changed", target).status_code == 400
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    assert api.action("start", 0, target).json == {"ok": True}
    response = api.action("start", 0, target)
    assert response.status_code == 409
    assert "重复启动" in response.json["message"]
    api.spawn.assert_called_once()
    assert target["path"] in api.spawn.call_args.args[0]


def test_bulk_start_and_stop_use_the_same_controller_and_stop_self_last(managed_http):
    api = managed_http
    api.controller.add("second", str(api.root / "second"))
    api.controller.add("unset", "")
    assert api.action("start_all", snapshot(api)).json == {"ok": True, "message": ""}
    assert api.spawn.call_count == 2
    for file in (api.root / "runtime/manager-controls").glob("*.json"):
        file.unlink()
    targets = snapshot(api)
    api.live.extend([registration(targets[0]), registration(targets[1], "second")])
    foreign = registration({"path": str(api.root / "foreign")}, "foreign")
    api.live.append(foreign)
    response = api.action("stop_all", targets)
    assert response.json == {"ok": True, "message": ""}
    assert [call.args[0]["id"] for call in api.send.call_args_list] == [
        "second",
        "current",
    ]
    assert all(call.args[1] == "exit" for call in api.send.call_args_list)


def test_shared_lock_contention_returns_a_retryable_error_without_writing(managed_http):
    api = managed_http
    before = api.storage.read_bytes()
    with runtime.submission_lock(api.root / "runtime/manager-controls"):
        response = api.action("remove", 0, snapshot(api)[0])
    assert response.status_code == 409
    assert response.json["message"]
    assert api.storage.read_bytes() == before
    assert api.action("rename", 0, "after release", snapshot(api)[0]).status_code == 200


@pytest.mark.parametrize(
    "failure", [OSError("unreadable"), runtime.InstanceScanError("scan failed")]
)
def test_incomplete_state_is_not_treated_as_an_empty_list(
    managed_http, monkeypatch, failure
):
    api = managed_http
    monkeypatch.setattr(runtime, "instances", Mock(side_effect=failure))
    response = api.client.get("/instances", headers=api.headers)
    assert response.status_code == 503
    assert response.json["ok"] is False
    assert response.json["message"]
    api.spawn.assert_not_called()


@pytest.mark.parametrize(
    "origin,remote,host,token,allowed",
    [
        ("http://localhost:5188", "127.0.0.1", "127.0.0.1:58000", True, True),
        ("http://localhost:5173", "127.0.0.1", "127.0.0.1:58000", True, False),
        ("http://localhost:5188", "192.0.2.2", "127.0.0.1:58000", True, False),
        ("http://localhost:5188", "127.0.0.1", "mower.example", True, False),
        ("http://remote.example:5188", "127.0.0.1", "127.0.0.1:58000", True, False),
        ("http://localhost:5188", "127.0.0.1", "127.0.0.1:58000", False, False),
    ],
)
def test_real_server_keeps_authenticated_loopback_development_and_profile_independence(
    managed_http, monkeypatch, origin, remote, host, token, allowed
):
    import server
    from arknights_mower.utils import config_profiles

    api = managed_http
    monkeypatch.setattr(
        server.app, "token", api.app.token if token else "", raising=False
    )
    monkeypatch.setenv("MOWER_DEV_PORT", "5188")
    forbidden = Mock(
        side_effect=AssertionError("Instance management read profile generation")
    )
    monkeypatch.setattr(config_profiles, "check_generation", forbidden)
    client = server.app.test_client()
    response = client.post(
        "/instances/actions",
        json={"action": "add", "args": ["HTTP instance", "", snapshot(api)]},
        headers={
            "token": api.app.token if token else "",
            "X-Mower-Settings": "1",
            "X-Mower-Config-Generation": "stale generation",
            "Origin": origin,
            "Host": host,
        },
        environ_overrides={"REMOTE_ADDR": remote},
    )
    assert response.status_code == (200 if allowed else 403)
    assert len(snapshot(api)) == (2 if allowed else 1)
    forbidden.assert_not_called()
    response = client.get("/instances/unknown", headers={"Accept": "text/html"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "method,path", [("GET", "/instances"), ("POST", "/instances/actions")]
)
@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("http://localhost:5188", True),
        ("http://localhost:5173", False),
        ("http://external.example:5188", False),
    ],
)
def test_real_server_cors_preflight_allows_only_trusted_origins_without_credentials(
    managed_http, monkeypatch, method, path, origin, allowed
):
    import server

    api = managed_http
    monkeypatch.setattr(server.app, "token", api.app.token, raising=False)
    monkeypatch.setenv("MOWER_DEV_PORT", "5188")
    controller = Mock(wraps=routes.InstanceController)
    monkeypatch.setattr(routes, "InstanceController", controller)
    client = server.app.test_client()
    headers = {"Origin": origin, "Host": "127.0.0.1:58000"}
    response = client.options(
        path,
        headers={
            **headers,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "token,content-type,x-mower-settings",
        },
    )
    assert response.status_code == (200 if allowed else 403)
    controller.assert_not_called()
    if not allowed:
        return
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert method in response.headers["Access-Control-Allow-Methods"]
    allowed_headers = response.headers["Access-Control-Allow-Headers"].lower()
    assert "token" in allowed_headers
    assert "x-mower-settings" in allowed_headers
    body = {"action": "add", "args": ["after preflight", "", snapshot(api)]}
    arguments = {"json": body} if method == "POST" else {}
    response = client.open(path, method=method, headers=headers, **arguments)
    assert response.status_code == 403
    controller.assert_not_called()
    response = client.open(
        path,
        method=method,
        headers={**headers, **api.headers},
        **arguments,
    )
    assert response.status_code == 200
    controller.assert_called_once()
    assert len(snapshot(api)) == (2 if method == "POST" else 1)


def test_blueprint_can_import_without_the_desktop_gui(tmp_path):
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'manager' or name == 'webview' or name.startswith('webview.'):
        raise AssertionError('HTTP instance management imported desktop GUI: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from arknights_mower.views.instances import instances_bp
assert instances_bp.url_prefix == '/instances'
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "MOWER_DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
