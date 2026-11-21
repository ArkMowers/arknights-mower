"""Instance session credentials never grant global manager access over HTTP."""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from flask import Flask, Request

from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import path
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.views.instances import instances_bp


def snapshot(root):
    return {
        str(item.relative_to(root)): item.read_bytes()
        for item in root.rglob("*")
        if item.is_file()
    }


@pytest.fixture
def loaded_server():
    import server

    return server


@pytest.fixture
def isolated_instances(loaded_server, tmp_path, monkeypatch):
    monkeypatch.setattr(path, "_data_dir", tmp_path)
    monkeypatch.setattr(path, "global_space", str(tmp_path / "current"))
    targets = []
    for name, token in (("current", "current-session"), ("other", "other-private")):
        directory = tmp_path / name
        destination = directory / "config/conf.yml"
        destination.parent.mkdir(parents=True)
        destination.write_text(
            yaml.safe_dump(
                {
                    "webview": {"token": token, "port": 0},
                    "ai_assistant_enabled": False,
                    "updates_enabled": False,
                }
            ),
            encoding="utf-8",
        )
        targets.append({"name": name, "path": str(directory)})
    controller = controls.InstanceController()
    for target in targets:
        controller.add(target["name"], target["path"])
    runtime.write_json(
        runtime.state_dir() / "instances/other.json",
        {
            "id": "other",
            "pid": os.getpid(),
            "kind": "instance",
            "space": targets[1]["path"],
            "data_dir": str(tmp_path),
            "managed": True,
            "ready": True,
        },
    )
    app = Flask(__name__)
    app.token = "current-session"
    app.register_blueprint(instances_bp)
    forbidden = Mock(
        side_effect=AssertionError("HTTP request reached global manager state")
    )
    for owner, name in (
        (controls, "InstanceController"),
        (controls, "read_instance_config"),
        (controls.subprocess, "Popen"),
        (runtime, "instances"),
        (runtime, "send_instance_command"),
        (Request, "get_json"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr(Request, "stream", property(forbidden))
    monkeypatch.setattr(Request, "files", property(forbidden))
    return SimpleNamespace(
        root=tmp_path,
        targets=targets,
        client=app.test_client(),
        headers={"token": app.token, "X-Mower-Settings": "1"},
        forbidden=forbidden,
        server=loaded_server,
    )


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("token", [None, "wrong", "other-private", "current-session"])
def test_instance_credentials_cannot_read_global_rows_or_other_tokens(
    isolated_instances, method, token
):
    api = isolated_instances
    before = snapshot(api.root)
    response = api.client.open(
        "/instances", method=method, headers={} if token is None else {"token": token}
    )
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"
    assert b"other-private" not in response.data
    if method == "GET" and token == "current-session":
        assert response.json["code"] == "instance_management_unavailable"
    api.forbidden.assert_not_called()
    assert snapshot(api.root) == before


@pytest.mark.parametrize(
    "action",
    [
        "add",
        "remove",
        "rename",
        "set_path",
        "update_settings",
        "update_all_settings",
        "start",
        "stop",
        "start_all",
        "stop_all",
    ],
)
@pytest.mark.parametrize("token", [None, "wrong", "other-private", "current-session"])
def test_every_global_operation_rejects_instance_credentials_before_side_effects(
    isolated_instances, action, token
):
    api = isolated_instances
    other = api.targets[1]
    settings = {
        "token": "replacement",
        "port": None,
        "ai_assistant_enabled": True,
        "updates_enabled": True,
    }
    arguments = {
        "add": ["new", str(api.root / "new"), api.targets],
        "remove": [1, other],
        "rename": [1, "renamed", other],
        "set_path": [1, str(api.root / "replacement"), other],
        "update_settings": [1, settings, other],
        "update_all_settings": [[{"idx": 1, "settings": settings}], api.targets],
        "start": [1, other],
        "stop": [1, other],
        "start_all": [api.targets],
        "stop_all": [api.targets],
    }
    headers = {"X-Mower-Settings": "1"}
    if token is not None:
        headers["token"] = token
    before = snapshot(api.root)
    response = api.client.post(
        "/instances/actions",
        headers=headers,
        json={"action": action, "args": arguments[action]},
    )
    assert response.status_code == 403
    if token == "current-session":
        assert response.json["code"] == "instance_management_unavailable"
    api.forbidden.assert_not_called()
    assert snapshot(api.root) == before


@pytest.mark.parametrize(
    "method,path", [("GET", "/instances"), ("POST", "/instances/actions")]
)
@pytest.mark.parametrize("token", [None, "current-session"])
@pytest.mark.parametrize(
    "origin", ["http://localhost", "http://localhost:5188", "http://external.example"]
)
def test_preflight_does_not_authorize_browser_instance_management(
    isolated_instances, method, path, token, origin
):
    api = isolated_instances
    headers = {"Origin": origin, "Access-Control-Request-Method": method}
    if token is not None:
        headers["token"] = token
    before = snapshot(api.root)
    response = api.client.options(path, headers=headers)
    assert response.status_code == 403
    api.forbidden.assert_not_called()
    assert snapshot(api.root) == before


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
)
@pytest.mark.parametrize(
    "route", ["/instances", "/instances/actions", "/instances/unknown"]
)
@pytest.mark.parametrize("token", [None, "wrong", "other-private", "current-session"])
def test_real_server_rejects_group_before_configuration_or_manager_access(
    isolated_instances, monkeypatch, method, route, token
):
    from arknights_mower.utils import config_profiles

    api = isolated_instances
    server = api.server
    monkeypatch.setattr(server.app, "token", "current-session", raising=False)
    monkeypatch.setattr(config_profiles, "check_generation", api.forbidden)
    monkeypatch.setattr(
        server,
        "backup_lock",
        SimpleNamespace(acquire=api.forbidden, release=api.forbidden),
    )
    headers = {"X-Mower-Settings": "1", "X-Mower-Config-Generation": "old-generation"}
    if token is not None:
        headers["token"] = token
    before = snapshot(api.root)
    response = server.app.test_client().open(
        route,
        method=method,
        headers=headers,
        data=json.dumps({"action": "stop_all", "args": [api.targets]}),
        content_type="application/json",
    )
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"
    if method != "HEAD" and token == "current-session":
        assert response.json["code"] == "instance_management_unavailable"
    api.forbidden.assert_not_called()
    assert snapshot(api.root) == before


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_page_navigation_cannot_bypass_instance_management_refusal(
    isolated_instances, method, monkeypatch
):
    api = isolated_instances
    monkeypatch.setattr(api.server.app, "token", "current-session", raising=False)
    response = api.server.app.test_client().open(
        "/instances",
        method=method,
        headers={**api.headers, "Accept": "text/html", "Sec-Fetch-Dest": "document"},
    )
    assert response.status_code == 403
    api.forbidden.assert_not_called()
