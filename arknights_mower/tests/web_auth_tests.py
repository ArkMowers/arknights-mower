"""Protected HTTP requests reject credentials before accessing instance state."""

from io import BytesIO
from unittest.mock import Mock

import pytest
from flask import Flask, Request

from arknights_mower.utils.web_auth import require_token


@pytest.fixture
def protected_server(monkeypatch):
    import server
    from arknights_mower.utils import (
        config_profiles,
        crash_recovery,
        manager_instances,
        resource_version,
    )
    from arknights_mower.utils.config import gui
    from arknights_mower.views import config_profiles as profile_routes

    monkeypatch.setattr(server.app, "token", "current-instance", raising=False)
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", True)
    forbidden = Mock(side_effect=AssertionError("Unauthorized request accessed state"))
    for owner, name in (
        (Request, "get_json"),
        (config_profiles, "check_generation"),
        (profile_routes, "_execute"),
        (manager_instances, "InstanceController"),
        (resource_version, "check_resource_update"),
        (crash_recovery, "status"),
        (server, "runtime_deployment"),
        (gui, "load_sidebar"),
        (gui, "save_sidebar"),
        (gui, "load_software_version_display"),
        (gui, "load_software_version_language"),
        (gui, "load_task_settings_layout"),
        (gui, "save_appearance"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    return server.app.test_client(), forbidden


@pytest.mark.parametrize("token", [None, "another-instance"])
@pytest.mark.parametrize(
    "method,path,representation",
    [
        ("GET", "/config-profiles", "json"),
        ("HEAD", "/config-profiles", "json"),
        ("GET", "/config-profiles/export", "json"),
        ("HEAD", "/config-profiles/export", "json"),
        ("POST", "/config-profiles", "json"),
        ("POST", "/config-profiles/example/activate", "json"),
        ("PATCH", "/config-profiles/example", "json"),
        ("POST", "/config-profiles/import", "json"),
        ("POST", "/config-profiles/import", "multipart"),
        ("GET", "/gui/sidebar", "json"),
        ("HEAD", "/gui/sidebar", "json"),
        ("PUT", "/gui/sidebar", "json"),
        ("GET", "/gui/appearance", "json"),
        ("HEAD", "/gui/appearance", "json"),
        ("PUT", "/gui/appearance", "json"),
        ("GET", "/instances", "json"),
        ("HEAD", "/instances", "json"),
        ("POST", "/instances/actions", "json"),
        ("GET", "/resource-version", "json"),
        ("HEAD", "/resource-version", "json"),
        ("GET", "/resource-version?local=1", "json"),
        ("HEAD", "/resource-version?local=1", "json"),
        ("GET", "/status", "json"),
        ("HEAD", "/status", "json"),
    ],
)
def test_missing_and_invalid_tokens_precede_parsing_and_instance_access(
    protected_server, token, method, path, representation
):
    client, forbidden = protected_server
    headers = {"X-Mower-Settings": "1", "X-Mower-Config-Generation": "0"}
    if token is not None:
        headers["token"] = token
    arguments = (
        {"data": {"backup": (BytesIO(b"not a backup"), "backup.zip")}}
        if representation == "multipart"
        else {"json": {"name": "unauthorized"}}
    )
    response = client.open(path, method=method, headers=headers, **arguments)
    assert response.status_code == 403
    forbidden.assert_not_called()


@pytest.mark.parametrize("local_only", [False, True])
def test_current_token_reaches_resource_version_reader(monkeypatch, local_only):
    import server
    from arknights_mower.utils import resource_version

    monkeypatch.setattr(server.app, "token", "current-instance", raising=False)
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", True)
    read = Mock(return_value={"current": "installed", "current_metadata": {}})
    monkeypatch.setattr(resource_version, "check_resource_update", read)
    response = server.app.test_client().get(
        "/resource-version" + ("?local=1" if local_only else ""),
        headers={"token": "current-instance"},
    )
    assert response.status_code == 200
    assert response.json["current"] == "installed"
    read.assert_called_once_with(local_only=local_only)


@pytest.mark.parametrize(
    "configured,supplied,expected",
    [
        (None, None, 200),
        (None, "arbitrary", 200),
        ("", None, 200),
        ("", "arbitrary", 403),
        ("current", None, 403),
        ("current", "another", 403),
        ("current", "current", 200),
    ],
)
def test_shared_guard_preserves_existing_token_configuration(
    configured, supplied, expected
):
    app = Flask(__name__)
    if configured is not None:
        app.token = configured
    reached = Mock(return_value={"ok": True})
    app.add_url_rule("/protected", "protected", require_token(reached))
    headers = {} if supplied is None else {"token": supplied}
    response = app.test_client().get("/protected", headers=headers)
    assert response.status_code == expected
    assert reached.call_count == (1 if expected == 200 else 0)


def test_supervisor_accepts_protected_status_without_reading_operational_state(
    monkeypatch,
):
    import urllib.request
    from urllib.error import HTTPError

    import server
    from arknights_mower.utils import crash_recovery, instance_supervisor

    monkeypatch.setattr(server.app, "token", "current-instance", raising=False)
    forbidden = Mock(side_effect=AssertionError("Probe read operational status"))
    monkeypatch.setattr(crash_recovery, "status", forbidden)
    client = server.app.test_client()
    content = BytesIO()

    def open_status(url, timeout):
        assert url == "http://127.0.0.1:58000/status"
        assert timeout == 3
        response = client.get("/status")
        assert response.status_code == 403
        raise HTTPError(
            url, response.status_code, "Forbidden", response.headers, content
        )

    opener = Mock()
    opener.open.side_effect = open_status
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: opener)
    assert instance_supervisor.http_probe(58000, 3)
    assert content.closed
    forbidden.assert_not_called()


@pytest.mark.parametrize("status", [404, 500, 503])
def test_supervisor_does_not_accept_unavailable_status(status, monkeypatch):
    import urllib.request
    from urllib.error import HTTPError

    from arknights_mower.utils import instance_supervisor

    content = BytesIO()
    opener = Mock()
    opener.open.side_effect = HTTPError(
        "http://localhost/status", status, "", {}, content
    )
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: opener)
    assert not instance_supervisor.http_probe(58000, 3)
    assert content.closed


@pytest.mark.parametrize("failure", [ConnectionRefusedError(), TimeoutError()])
def test_supervisor_rejects_failed_connections(failure, monkeypatch):
    import urllib.request

    from arknights_mower.utils import instance_supervisor

    opener = Mock()
    opener.open.side_effect = failure
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: opener)
    assert not instance_supervisor.http_probe(58000, 3)


@pytest.fixture
def preflight_server(monkeypatch):
    import server
    from arknights_mower.utils import config_profiles
    from arknights_mower.utils.config import gui
    from arknights_mower.views import config_profiles as profile_routes

    monkeypatch.setattr(server.app, "token", "current-instance", raising=False)
    monkeypatch.setenv("MOWER_DEV_PORT", "5188")
    generation = Mock()
    monkeypatch.setattr(config_profiles, "check_generation", generation)
    access = Mock(return_value={"ok": True})
    for owner, name in (
        (profile_routes, "_execute"),
        (gui, "load_sidebar"),
        (gui, "save_sidebar"),
        (gui, "load_software_version_display"),
        (gui, "load_software_version_language"),
        (gui, "load_task_settings_layout"),
        (gui, "save_appearance"),
    ):
        monkeypatch.setattr(owner, name, access)
    return server.app.test_client(), access, generation


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/config-profiles"),
        ("GET", "/config-profiles/export"),
        ("POST", "/config-profiles"),
        ("POST", "/config-profiles/example/activate"),
        ("PATCH", "/config-profiles/example"),
        ("POST", "/config-profiles/import"),
        ("GET", "/gui/sidebar"),
        ("PUT", "/gui/sidebar"),
        ("GET", "/gui/appearance"),
        ("PUT", "/gui/appearance"),
    ],
)
def test_development_preflight_admits_only_the_following_authenticated_request(
    preflight_server, method, path
):
    client, access, generation = preflight_server
    headers = {"Origin": "http://localhost:5188", "Host": "127.0.0.1:58000"}
    response = client.options(
        path,
        headers={
            **headers,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "token,content-type,x-mower-settings",
        },
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == headers["Origin"]
    assert method in response.headers["Access-Control-Allow-Methods"]
    assert "token" in response.headers["Access-Control-Allow-Headers"].lower()
    access.assert_not_called()
    generation.assert_not_called()
    for credentials in ({}, {"token": "wrong-instance"}):
        response = client.open(
            path, method=method, headers={**headers, **credentials}, json={}
        )
        assert response.status_code == 403
        access.assert_not_called()
        generation.assert_not_called()
    response = client.open(
        path,
        method=method,
        headers={
            **headers,
            "token": "current-instance",
            "X-Mower-Settings": "1",
            "X-Mower-Config-Generation": "0",
        },
        json={"sidebar": {}},
    )
    assert response.status_code == 200
    assert access.called


@pytest.mark.parametrize(
    "path,method",
    [
        ("/config-profiles", "POST"),
        ("/gui/sidebar", "PUT"),
        ("/gui/appearance", "PUT"),
        ("/instances/actions", "POST"),
    ],
)
@pytest.mark.parametrize(
    "origin,remote,host,requested",
    [
        (None, "127.0.0.1", "127.0.0.1:58000", None),
        ("http://external.example:5188", "127.0.0.1", "127.0.0.1:58000", None),
        ("http://localhost:5173", "127.0.0.1", "127.0.0.1:58000", None),
        ("http://localhost:5188", "192.0.2.2", "127.0.0.1:58000", None),
        ("http://localhost:5188", "127.0.0.1", "mower.example", None),
        ("http://localhost:5188", "127.0.0.1", "127.0.0.1:58000", "DELETE"),
        ("http://localhost:5188", "127.0.0.1", "127.0.0.1:58000", "OPTIONS"),
    ],
)
def test_preflight_rejects_untrusted_origins_and_unregistered_methods(
    preflight_server, path, method, origin, remote, host, requested
):
    client, access, generation = preflight_server
    headers = {"Host": host, "Access-Control-Request-Method": requested or method}
    if origin is not None:
        headers["Origin"] = origin
    response = client.options(
        path, headers=headers, environ_overrides={"REMOTE_ADDR": remote}
    )
    assert response.status_code == 403
    access.assert_not_called()
    generation.assert_not_called()


@pytest.mark.parametrize("path", ["/config-profiles", "/gui/sidebar", "/instances"])
@pytest.mark.parametrize("boundary", ["empty_token", "missing_origin_checker"])
def test_development_preflight_requires_an_authenticated_local_session(
    preflight_server, monkeypatch, path, boundary
):
    client, access, generation = preflight_server
    if boundary == "empty_token":
        monkeypatch.setattr(client.application, "token", "")
    else:
        monkeypatch.delitem(client.application.config, "WEB_UI_ORIGIN_ALLOWED")
    response = client.options(
        path,
        headers={
            "Origin": "http://localhost:5188",
            "Host": "127.0.0.1:58000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 403
    access.assert_not_called()
    generation.assert_not_called()
