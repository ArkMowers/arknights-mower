"""Profile generation admission through the real server request hooks."""

import json
import sys
from threading import Event, Lock, RLock, Thread
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


@pytest.mark.parametrize("operation", ["list", "create"])
@pytest.mark.parametrize("completion", ["success", "error", "timeout", "running"])
def test_profile_admission_collects_maa_check_without_browser_polling(
    storage, monkeypatch, operation, completion
):
    import arknights_mower.__main__ as main
    import server
    from arknights_mower.utils import config_profiles as profiles

    monkeypatch.setattr(server.app, "token", "profile-test-token", raising=False)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setitem(server.app.config, "CONFIG_BACKUP_BUSY", lambda: False)
    monkeypatch.setitem(server.app.config, "CONFIGURATION_ACTIVATED", lambda: None)
    monkeypatch.setattr(
        main,
        "device_control",
        SimpleNamespace(active=False, configuration_lock=RLock()),
    )
    process = Mock(returncode=0 if completion == "success" else 1)
    process.poll.return_value = (
        None if completion in {"timeout", "running"} else process.returncode
    )
    process.communicate.return_value = (
        json.dumps({"status": completion, "message": "completed check"}),
        "",
    )
    started_at = server.time.monotonic() - (
        server.MAA_CHECK_TIMEOUT + 1 if completion == "timeout" else 1
    )
    monkeypatch.setattr(
        server,
        "maa_check_job",
        {
            "process": process,
            "status": "running",
            "message": "checking",
            "started_at": started_at,
        },
    )
    initial = profiles.list_profiles()
    headers = {
        "token": "profile-test-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": initial["generation"],
    }
    client = server.app.test_client()
    running = completion == "running"

    if operation == "list":
        response = client.get("/config-profiles", headers=headers)
        assert response.status_code == 200
        assert response.json["busy"] is running
    else:
        response = client.post(
            "/config-profiles",
            headers=headers,
            json={"name": "after MAA check", "inherit": []},
        )
        assert response.status_code == (409 if running else 200)
        assert (profiles.current_generation() == initial["generation"]) is running

    assert server.maa_check_job["status"] == completion
    if running:
        assert server.maa_check_job["process"] is process
        process.communicate.assert_not_called()
    else:
        assert server.maa_check_job["process"] is None
        process.communicate.assert_called_once_with(
            **({"timeout": 1} if completion == "timeout" else {})
        )
    if completion == "timeout":
        process.kill.assert_called_once_with()
    else:
        process.kill.assert_not_called()


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


@pytest.mark.parametrize("token", [None, "wrong", "inventory-token"])
@pytest.mark.parametrize("generation", [None, "0", "active-generation"])
def test_depot_read_authenticates_and_checks_generation_before_inventory_writes(
    storage, monkeypatch, token, generation
):
    import server
    from arknights_mower.solvers import record
    from arknights_mower.utils import config_backup as backup
    from arknights_mower.utils import config_profiles, depot

    monkeypatch.setattr(server.app, "token", "inventory-token", raising=False)
    monkeypatch.setattr(
        config_profiles, "current_generation", lambda: "active-generation"
    )
    monkeypatch.setattr(record, "get_path", storage)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(depot, "get_path", storage)
    storage("@app/tmp/cultivate.json").write_text(
        json.dumps(
            {
                "code": 0,
                "data": {"items": [{"id": "30062", "count": 9}]},
                "_mower_inventory_observed_at": 1759400000,
            }
        ),
        encoding="utf-8",
    )
    before = backup.read_archive(backup.export_archive(), include_tmp=True)
    parsed = []
    read = depot.读取仓库

    def parse():
        parsed.append(True)
        return read()

    monkeypatch.setattr(depot, "读取仓库", parse)
    headers = {}
    if token is not None:
        headers["token"] = token
    if generation is not None:
        headers["X-Mower-Config-Generation"] = generation
    response = server.app.test_client().get("/depot/readdepot", headers=headers)
    if token != "inventory-token":
        assert response.status_code == 403
    elif generation != "active-generation":
        assert response.status_code == 409
        assert response.json["code"] == "configuration_changed"
    else:
        assert response.status_code == 200
        assert parsed == [True]
        assert record.get_inventory_counts()["装置"] == 9
        return
    assert parsed == []
    assert backup.read_archive(backup.export_archive(), include_tmp=True) == before


@pytest.fixture
def profile_run_intent(storage, monkeypatch):
    import arknights_mower.__main__ as main
    import server
    from arknights_mower.utils import config, config_profiles, crash_recovery
    from arknights_mower.utils import instance_supervisor as supervisor
    from arknights_mower.utils import update_runtime as runtime

    monkeypatch.setattr(server.app, "token", "intent-test-token", raising=False)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(server, "chat_active_requests", 0)
    monkeypatch.setattr(server, "active_job", lambda: None)
    monkeypatch.setattr(server, "_job_running", lambda job: False)
    monkeypatch.setattr(server, "_recycling_reports_running", lambda: False)
    monkeypatch.setattr(server.resource_update, "running", lambda: False)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setattr(server, "maa_check_job", {"status": "idle"})
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(
        main,
        "device_control",
        SimpleNamespace(active=False, configuration_lock=RLock()),
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    directory = storage("@app/supervisor")
    directory.mkdir()
    report, notice = directory / "child.json", directory / "recovery.json"
    monkeypatch.setenv("MOWER_SUPERVISOR_DIRECTORY", str(directory))
    monkeypatch.setenv("MOWER_SUPERVISOR_CHILD_REPORT", str(report))
    monkeypatch.setenv("MOWER_SUPERVISOR_GENERATION", "intent-test-launch")
    monkeypatch.delenv("MOWER_SUPERVISOR_INTENT", raising=False)
    monkeypatch.setenv("MOWER_RECOVERY_RUN", "1")
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    supervisor.task_intent(True)
    config_profiles.list_profiles()
    return SimpleNamespace(
        server=server,
        client=server.app.test_client(),
        config=config,
        profiles=config_profiles,
        recovery=crash_recovery,
        runtime=runtime,
        supervisor=supervisor,
        report=report,
        notice=notice,
        activation_target=None,
    )


def _replace_configuration(api, operation):
    from io import BytesIO

    current = api.profiles.list_profiles()
    if operation == "activate" and api.activation_target is None:
        original = current["active_id"]
        api.activation_target = api.profiles.create_profile(
            "target", [], expected_generation=current["generation"]
        )["active_id"]
        current = api.profiles.activate_profile(
            original, [], expected_generation=api.profiles.current_generation()
        )
    headers = {
        "token": "intent-test-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": current["generation"],
    }
    if operation == "create":
        return api.client.post(
            "/config-profiles", headers=headers, json={"name": "created", "inherit": []}
        )
    if operation == "activate":
        return api.client.post(
            f"/config-profiles/{api.activation_target}/activate",
            headers=headers,
            json={"keep": []},
        )
    raw = api.profiles.export_current_archive()
    if operation == "import":
        return api.client.post(
            "/config-profiles/import",
            headers=headers,
            data={"backup": (BytesIO(raw), "backup.zip"), "name": "imported"},
        )
    return api.client.post("/config-backup/import", headers=headers, data=raw)


@pytest.mark.parametrize("operation", ["create", "activate", "import", "backup"])
def test_successful_configuration_replacement_clears_old_run_intent_and_allows_manual_start(
    profile_run_intent, monkeypatch, operation
):
    api = profile_run_intent
    response = _replace_configuration(api, operation)
    assert response.status_code == 200
    assert api.runtime.read_json(api.report)["desired_running"] is False
    assert api.recovery.cancelled()
    assert api.config.stop_mower.is_set()

    api.supervisor.child_ready(
        SimpleNamespace(record={"port": 58000}, request=api.report.parent / "shutdown"),
        desired_running=True,
    )
    assert api.runtime.read_json(api.report)["desired_running"] is False
    assert api.recovery.cancelled()

    worker = Mock()
    monkeypatch.setattr(api.server, "Thread", Mock(return_value=worker))
    started = api.client.get(
        "/start/2",
        headers={
            "token": "intent-test-token",
            "X-Mower-Config-Generation": api.profiles.current_generation(),
        },
    )
    assert started.data == b"true"
    worker.start.assert_called_once()
    assert api.runtime.read_json(api.report)["desired_running"] is True
    assert not api.recovery.cancelled()
    assert not api.config.stop_mower.is_set()


@pytest.mark.parametrize("operation", ["create", "activate", "import", "backup"])
def test_failed_configuration_replacement_keeps_old_run_intent(
    profile_run_intent, monkeypatch, operation
):
    api = profile_run_intent
    if operation == "activate":
        original = api.profiles.list_profiles()["active_id"]
        api.activation_target = api.profiles.create_profile(
            "target", [], expected_generation=api.profiles.current_generation()
        )["active_id"]
        api.profiles.activate_profile(
            original, [], expected_generation=api.profiles.current_generation()
        )
    original_generation = api.profiles.current_generation()

    def fail(_data):
        raise OSError("metadata unavailable")

    monkeypatch.setattr(api.profiles, "_write_registry", fail)
    response = _replace_configuration(api, operation)
    assert response.status_code == 500
    assert api.profiles.current_generation() == original_generation
    assert api.runtime.read_json(api.report)["desired_running"] is True
    assert not api.recovery.cancelled()
    assert not api.config.stop_mower.is_set()


@pytest.mark.parametrize("operation", ["create", "backup"])
def test_waiting_automatic_recovery_requires_stop_before_replacing_configuration(
    profile_run_intent, operation
):
    api = profile_run_intent
    api.runtime.write_json(
        api.notice,
        {"active": True, "phase": "waiting", "resume_requested": True},
    )
    generation = api.profiles.current_generation()
    assert api.server.configuration_profiles_busy()
    response = _replace_configuration(api, operation)
    assert response.status_code == 409
    assert api.profiles.current_generation() == generation
    assert api.recovery.status()["automatic"]
    assert api.runtime.read_json(api.report)["desired_running"] is True

    stopped = api.client.get(
        "/stop",
        headers={"token": "intent-test-token", "X-Mower-Config-Generation": generation},
    )
    assert stopped.data == b"true"
    assert not api.recovery.status()["automatic"]
    assert _replace_configuration(api, operation).status_code == 200


def test_renaming_configuration_preserves_pending_run_intent(profile_run_intent):
    api = profile_run_intent
    current = api.profiles.list_profiles()
    response = api.client.patch(
        f"/config-profiles/{current['active_id']}",
        headers={
            "token": "intent-test-token",
            "X-Mower-Settings": "1",
            "X-Mower-Config-Generation": current["generation"],
        },
        json={"name": "renamed"},
    )
    assert response.status_code == 200
    assert api.runtime.read_json(api.report)["desired_running"] is True
    assert not api.recovery.cancelled()
    assert not api.config.stop_mower.is_set()


@pytest.fixture
def screenshot_requests(profile_run_intent, monkeypatch):
    api = profile_run_intent
    monkeypatch.setattr(api.server, "configuration_test_active_requests", 0)
    monkeypatch.setattr(api.config.conf.custom_screenshot, "command", "saved capture")
    monkeypatch.setitem(
        sys.modules,
        "numpy",
        SimpleNamespace(frombuffer=lambda data, dtype: data, uint8=object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            IMREAD_COLOR=1,
            IMWRITE_JPEG_QUALITY=1,
            imdecode=lambda data, mode: data,
            imencode=lambda extension, data, options: (True, b"encoded image"),
        ),
    )
    api.headers = {
        "token": "intent-test-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": api.profiles.current_generation(),
    }
    return api


def _request_worker(api, path, outcome, key, **kwargs):
    def request():
        with api.server.app.test_client() as client:
            outcome[key] = client.open(path, headers=api.headers, **kwargs)

    worker = Thread(target=request)
    worker.start()
    return worker


@pytest.mark.parametrize("operation", ["profile", "backup"])
def test_custom_screenshot_releases_configuration_lock_before_external_work(
    screenshot_requests, monkeypatch, operation
):
    api = screenshot_requests
    entered, release = Event(), Event()
    outcome = {}

    def capture(command, **kwargs):
        assert command == "saved capture"
        entered.set()
        assert release.wait(5)
        return b"captured image"

    monkeypatch.setattr(api.server.subprocess, "check_output", capture)
    screenshot = _request_worker(
        api, "/test-custom-screenshot", outcome, "screenshot", method="GET"
    )
    workers = [screenshot]
    try:
        assert entered.wait(2)
        stopped = _request_worker(api, "/stop", outcome, "stop", method="GET")
        workers.append(stopped)
        stopped.join(0.5)
        stopped_during_capture = not stopped.is_alive()
        path = "/config-profiles" if operation == "profile" else "/config-backup/import"
        replacement = _request_worker(
            api,
            path,
            outcome,
            "replacement",
            method="POST",
            **(
                {"json": {"name": "blocked", "inherit": []}}
                if operation == "profile"
                else {"data": b"not parsed while capturing"}
            ),
        )
        workers.append(replacement)
        replacement.join(0.5)
        refused_during_capture = not replacement.is_alive()
        busy_during_capture = api.server.configuration_profiles_busy()
    finally:
        release.set()
        for worker in workers:
            worker.join(3)
            assert not worker.is_alive()
    assert stopped_during_capture
    assert outcome["stop"].data == b"true"
    assert refused_during_capture
    assert outcome["replacement"].status_code == 409
    assert busy_during_capture
    assert outcome["screenshot"].status_code == 200
    assert api.server.configuration_test_active_requests == 0
    assert not api.server.configuration_profiles_busy()
    assert _replace_configuration(api, "create").status_code == 200


def test_parallel_custom_screenshots_remain_busy_until_the_last_request_finishes(
    screenshot_requests, monkeypatch
):
    api = screenshot_requests
    entered, release = [Event(), Event()], [Event(), Event()]
    assignment = Lock()
    commands = []
    outcome = {}

    def capture(command, **kwargs):
        with assignment:
            index = len(commands)
            commands.append(command)
        entered[index].set()
        assert release[index].wait(5)
        return b"captured image"

    monkeypatch.setattr(api.server.subprocess, "check_output", capture)
    first = _request_worker(
        api, "/test-custom-screenshot", outcome, "first", method="GET"
    )
    workers = [first]
    try:
        assert entered[0].wait(2)
        second = _request_worker(
            api, "/test-custom-screenshot", outcome, "second", method="GET"
        )
        workers.append(second)
        assert entered[1].wait(2)
        assert api.server.configuration_test_active_requests == 2
        release[0].set()
        first.join(2)
        assert not first.is_alive()
        assert api.server.configuration_test_active_requests == 1
        assert api.server.configuration_profiles_busy()
        response = api.client.post(
            "/config-profiles",
            headers=api.headers,
            json={"name": "blocked", "inherit": []},
        )
        assert response.status_code == 409
    finally:
        for signal in release:
            signal.set()
        for worker in workers:
            worker.join(3)
            assert not worker.is_alive()
    assert commands == ["saved capture", "saved capture"]
    assert outcome["first"].status_code == 200
    assert outcome["second"].status_code == 200
    assert api.server.configuration_test_active_requests == 0
    assert not api.server.configuration_profiles_busy()


@pytest.mark.parametrize("failure", ["command", "encoding"])
def test_custom_screenshot_failure_releases_profile_admission(
    screenshot_requests, monkeypatch, failure
):
    api = screenshot_requests
    monkeypatch.setattr(
        api.server.subprocess, "check_output", Mock(return_value=b"captured image")
    )

    def fail(*args, **kwargs):
        assert api.server.configuration_profiles_busy()
        raise OSError("capture failed")

    if failure == "command":
        monkeypatch.setattr(api.server.subprocess, "check_output", fail)
    else:
        monkeypatch.setattr(sys.modules["cv2"], "imencode", fail)
    response = api.client.get("/test-custom-screenshot", headers=api.headers)
    assert response.status_code == 500
    assert api.server.configuration_test_active_requests == 0
    assert not api.server.configuration_profiles_busy()
    assert _replace_configuration(api, "create").status_code == 200
