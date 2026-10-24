"""Profile generation admission through the real server request hooks."""

from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.config_profiles_tests import storage as storage


@pytest.fixture
def guarded_server(monkeypatch):
    import server
    from arknights_mower.utils import config_profiles

    monkeypatch.setattr(server.app, "token", "profile-test-token", raising=False)
    monkeypatch.setattr(
        config_profiles, "current_generation", lambda: "active-generation"
    )
    return server, config_profiles, server.app.test_client()


@pytest.mark.parametrize(
    "method,path",
    [
        ("patch", "/conf"),
        ("post", "/plan"),
        ("post", "/rescue-plan"),
        ("post", "/weekly-plans"),
        ("post", "/device/preflight"),
        ("post", "/config-profiles"),
        ("get", "/start/0"),
        ("post", "/scheduled-start"),
        ("get", "/stop"),
        ("get", "/stop-maa"),
        ("get", "/check-maa"),
        ("get", "/report/restore-trading-history"),
        ("get", "/test-email"),
        ("get", "/test-custom-screenshot"),
        ("get", "/check-skland"),
        ("get", "/check-skland-sign"),
        ("get", "/cultivate-fetch"),
    ],
)
@pytest.mark.parametrize("generation", [None, "previous-generation"])
def test_stale_request_is_rejected_before_route_side_effects(
    guarded_server, monkeypatch, method, path, generation
):
    server, profiles, client = guarded_server
    checks = []
    lock = RLock()

    class RequestLock:
        def acquire(self):
            lock.acquire()
            checks.append("acquired")

        def release(self):
            checks.append("released")
            lock.release()

    monkeypatch.setattr(server, "backup_lock", RequestLock())
    original = profiles.check_generation

    def check(value, **kwargs):
        assert checks[-1] == "acquired"
        checks.append("checked")
        return original(value, **kwargs)

    monkeypatch.setattr(profiles, "check_generation", check)
    headers = {"token": "profile-test-token"}
    if generation is not None:
        headers["X-Mower-Config-Generation"] = generation
    response = getattr(client, method)(path, headers=headers)

    assert response.status_code == 409
    assert response.json["error"] == "configuration_changed"
    assert checks == ["acquired", "checked", "released"]


def test_current_generation_reaches_read_only_validation(guarded_server):
    _, _, client = guarded_server
    response = client.post(
        "/device/preflight",
        headers={
            "token": "profile-test-token",
            "X-Mower-Config-Generation": "active-generation",
        },
        json={"unknown": True},
    )
    assert response.status_code == 400
    assert response.json["error"] == "invalid_configuration"


@pytest.mark.parametrize("generation", [None, "previous-generation"])
def test_gui_sidebar_save_preserves_auth_and_backup_lock_without_profile_generation(
    guarded_server, monkeypatch, tmp_path, generation
):
    server, profiles, client = guarded_server
    from arknights_mower.utils.config import gui

    monkeypatch.setattr(gui, "gui_path", tmp_path / "gui.yml")
    checks = []

    class RequestLock:
        def acquire(self):
            checks.append("acquired")

        def release(self):
            checks.append("released")

    def forbidden(*args, **kwargs):
        raise AssertionError("Instance GUI preferences do not read profile generation")

    monkeypatch.setattr(server, "backup_lock", RequestLock())
    monkeypatch.setattr(profiles, "check_generation", forbidden)
    layout = {
        "version": 3,
        "groups": [],
        "knownKeys": ["log"],
        "placements": [
            {
                "id": "log",
                "key": "log",
                "group": "ungrouped",
                "visible": True,
                "pinned": False,
            }
        ],
    }
    headers = {"token": "profile-test-token"}
    if generation is not None:
        headers["X-Mower-Config-Generation"] = generation
    response = client.put("/gui/sidebar", headers=headers, json={"sidebar": layout})
    assert response.status_code == 200
    assert response.json == {"sidebar": layout}
    assert checks == ["acquired", "released"]
    assert client.get("/gui/sidebar", headers=headers).json == {"sidebar": layout}
    before = gui.gui_path.read_bytes()
    assert client.put("/gui/sidebar", json={"sidebar": layout}).status_code == 403
    assert gui.gui_path.read_bytes() == before
    assert checks == ["acquired", "released", "acquired", "released"]


def test_legacy_request_remains_valid_before_first_activation(
    guarded_server, monkeypatch
):
    _, profiles, client = guarded_server
    monkeypatch.setattr(profiles, "current_generation", lambda: "0")
    response = client.post(
        "/device/preflight",
        headers={"token": "profile-test-token"},
        json={"unknown": True},
    )
    assert response.status_code == 400


def test_invalid_token_is_rejected_before_generation_lookup(
    guarded_server, monkeypatch
):
    _, profiles, client = guarded_server

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Unauthenticated requests must not inspect saved configurations"
        )

    monkeypatch.setattr(profiles, "check_generation", forbidden)
    assert client.patch("/conf", headers={"token": "wrong"}, json={}).status_code == 403


def test_damaged_registry_refuses_writes(guarded_server, monkeypatch):
    _, profiles, client = guarded_server
    from arknights_mower.utils.config_backup import LocalConfigError

    def unreadable(*args, **kwargs):
        raise LocalConfigError("invalid registry")

    monkeypatch.setattr(profiles, "check_generation", unreadable)
    response = client.post(
        "/rescue-plan", headers={"token": "profile-test-token"}, json={}
    )
    assert response.status_code == 503
    assert response.json["error"] == "configuration_unavailable"


def test_profile_admission_covers_device_and_background_work(
    guarded_server, monkeypatch
):
    server, _, _ = guarded_server
    import arknights_mower.__main__ as main

    control = SimpleNamespace(active=False)
    monkeypatch.setattr(main, "device_control", control)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setitem(server.app.config, "CONFIG_BACKUP_BUSY", lambda: False)
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setattr(server, "maa_check_job", {"status": "idle"})
    assert server.configuration_profiles_busy() is False

    control.active = True
    assert server.configuration_profiles_busy() is True
    control.active = False
    monkeypatch.setattr(
        server, "_performance_test_status", lambda: {"status": "running"}
    )
    assert server.configuration_profiles_busy() is True
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    server.maa_check_job["status"] = "running"
    assert server.configuration_profiles_busy() is True
    server.maa_check_job["status"] = "idle"
    server.shutdown.closing = True
    assert server.configuration_profiles_busy() is True


def test_real_server_switches_selected_groups_and_rejects_old_page_saves(
    storage, monkeypatch
):
    import arknights_mower.__main__ as main
    import server
    from arknights_mower.utils import config
    from arknights_mower.utils.config import weekly_plan_loader

    control = SimpleNamespace(active=False, configuration_lock=RLock())
    monkeypatch.setattr(main, "device_control", control)
    monkeypatch.setattr(server.app, "token", "profile-test-token", raising=False)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setattr(server, "maa_check_job", {"status": "idle"})
    monkeypatch.setitem(server.app.config, "CONFIG_BACKUP_BUSY", lambda: False)
    monkeypatch.setattr(weekly_plan_loader, "_weekly_plan_manager", None)
    client = server.app.test_client()
    headers = {"token": "profile-test-token", "X-Mower-Settings": "1"}
    initial = client.get("/config-profiles", headers=headers).json
    assert initial["generation"] == "0"
    headers["X-Mower-Config-Generation"] = "0"

    created = client.post(
        "/config-profiles",
        headers=headers,
        json={"name": "HTTP configuration", "inherit": ["device", "appearance"]},
    )
    assert created.status_code == 200
    assert created.json["active_id"] != initial["active_id"]
    assert config.conf.account == ""
    assert (
        client.patch("/conf", headers=headers, json={"theme": "dark"}).status_code
        == 409
    )
    assert config.conf.theme == "light"

    headers["X-Mower-Config-Generation"] = created.json["generation"]
    assert (
        client.patch("/conf", headers=headers, json={"theme": "dark"}).status_code
        == 200
    )
    assert config.conf.theme == "dark"
    restored = client.post(
        f"/config-profiles/{initial['active_id']}/activate",
        headers=headers,
        json={"keep": ["appearance"]},
    )
    assert restored.status_code == 200
    assert config.conf.account == "original"
    assert config.conf.theme == "dark"
    assert restored.json["active_id"] == initial["active_id"]

    headers["X-Mower-Config-Generation"] = restored.json["generation"]
    control.active = True
    refused = client.post(
        "/config-profiles", headers=headers, json={"name": "blocked", "inherit": []}
    )
    assert refused.status_code == 409
    assert len(client.get("/config-profiles", headers=headers).json["profiles"]) == 2


@pytest.mark.parametrize(
    "configuration_change",
    ["unchanged", "renamed", "activated", "failed_activation", "damaged_registry"],
)
def test_scheduled_start_remains_bound_to_its_configuration(
    storage, monkeypatch, configuration_change
):
    import server
    from arknights_mower.utils import config_profiles as profiles

    timers = []

    class Timer:
        def __init__(self, delay, callback):
            self.callback = callback
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            pass

    monkeypatch.setattr(server, "Timer", Timer)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "scheduled_start_timer", None)
    monkeypatch.setattr(server, "scheduled_start_at", None)
    monkeypatch.setattr(server.app, "token", "profile-test-token", raising=False)
    start = Mock(return_value=True)
    monkeypatch.setattr(server, "_start_mower", start)
    initial = profiles.list_profiles()
    response = server.app.test_client().put(
        "/scheduled-start",
        headers={
            "token": "profile-test-token",
            "X-Mower-Config-Generation": initial["generation"],
        },
        json={"delay_seconds": 600},
    )
    assert response.status_code == 200

    if configuration_change == "renamed":
        profiles.rename_profile(
            initial["active_id"], "renamed", expected_generation="0"
        )
    elif configuration_change == "activated":
        profiles.create_profile("second", [], expected_generation="0")
    elif configuration_change == "failed_activation":

        def fail(data):
            raise OSError("metadata failed")

        monkeypatch.setattr(profiles, "_write_registry", fail)
        with pytest.raises(OSError, match="metadata failed"):
            profiles.create_profile("failed", [], expected_generation="0")
    elif configuration_change == "damaged_registry":
        storage("@app/config-profiles/index.json").write_text("{}", encoding="utf-8")

    timers[0].callback()

    if configuration_change in {"activated", "damaged_registry"}:
        start.assert_not_called()
    else:
        start.assert_called_once_with("2")
    assert server.scheduled_start_timer is None
    assert server.scheduled_start_at is None
