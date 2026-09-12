import copy
import json
import sqlite3
import threading

import pytest
from flask import Flask

from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils.mastery_db import _PLAN_SCHEMA, _ROUTE_SCHEMA
from arknights_mower.utils.workshop_config import save_user_config
from arknights_mower.views.config_backup import config_backup_bp


@pytest.fixture
def storage(tmp_path, monkeypatch):
    def get_path(name, space=None):
        return (
            tmp_path
            / ("shared" if space == "" else "instance")
            / name.removeprefix("@app/")
        )

    monkeypatch.setattr(backup, "get_path", get_path)
    monkeypatch.setattr(
        backup.update_runtime, "state_dir", lambda: tmp_path / "updates"
    )
    for attr, name in (
        ("conf_path", "conf.yml"),
        ("plan_path", "plan.json"),
        ("weekly_plans_path", "weekly_plans.yml"),
        ("app_state_path", "state.json"),
        ("gui_path", "gui.yml"),
    ):
        monkeypatch.setattr(config, attr, get_path(f"@app/config/{name}"))
    monkeypatch.setattr(
        backup.network_settings,
        "settings_path",
        lambda: get_path("@app/config/network.json", space=""),
    )
    monkeypatch.setattr(backup.network_settings, "apply_http_proxy", lambda: None)
    monkeypatch.setattr(
        config,
        "conf",
        config.Conf(account="before", dorm_order="dormitory_3,dormitory_1"),
    )
    monkeypatch.setattr(config, "plan", config.PlanModel())
    config.save_conf()
    config.save_plan()
    path = get_path("@app/tmp/data.db")
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute(_PLAN_SCHEMA)
        conn.execute(_ROUTE_SCHEMA)
        conn.execute(
            "INSERT INTO mastery_plan(char_id, skill_index, target_level, support_plan) VALUES ('char_1', 0, 3, '{}')"
        )
        conn.execute(
            "INSERT INTO mastery_route(profession, supports) VALUES ('__settings__', '{\"central_bonus\":5}')"
        )
        conn.execute("CREATE TABLE reports(value TEXT)")
        conn.execute("INSERT INTO reports VALUES ('keep')")
        conn.execute("CREATE TABLE saved_state(state BLOB)")
        conn.execute("INSERT INTO saved_state VALUES ('stale')")
    return get_path


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_importing_changed_plan_resets_dorm_priority(storage):
    data = backup.export_configuration()
    data["data"]["plan"]["conf"]["ling_xi"] = 2
    assert config.plan.conf.ling_xi != 2
    backup.import_configuration(data)
    assert config.plan.conf.ling_xi == 2
    assert config.conf.dorm_order == ""
    assert json.loads(config.conf_path.read_text())["dorm_order"] == ""


def test_full_round_trip_includes_optional_files_secrets_and_mastery(storage):
    config.conf.ai_key = "test-secret"
    config.conf.maa_eat_stone = True  # Not included in the web form.
    paths = backup.configuration_paths()
    day = {"weekday": "周一", "stage": ["1-7"], "medicine": 2}
    values = {
        "weekly_plans": {
            "plans": {"日常": [day], "活动": [day]},
            "inventory_configs": {
                "活动": {"enabled": True, "limit_rules": [], "ratio_rules": []}
            },
            "activity_fallbacks": {"活动": "日常"},
            "activity_fallback_switch_times": {"活动": 1234567890},
        },
        "state": {"active_weekly_plan": "活动", "other_setting": True},
        "gui": {"ratio": {"width": 0.7, "height": 0.8}},
        "network": {"http_proxy": "", "github_proxy": "https://example.com"},
        "software_update": {
            "channel": "beta",
            "auto_check": True,
            "source_branch": "alpha",
        },
        "skland_device_id": {"dId": "test-device"},
        "sss": {"type": "SSS", "stages": []},
        "workshop_preset": {"settings": []},
    }
    for name, value in values.items():
        write_json(paths[name], value)
    original = backup.export_configuration()
    assert original["data"]["conf"]["ai_key"] == "test-secret"
    assert original["data"]["conf"]["maa_eat_stone"] is True
    assert len(original["data"]["mastery"]["mastery_route"]) == 1
    config.conf = config.Conf(account="changed")
    config.save_conf()
    for name in values:
        paths[name].unlink()
    recovery = backup.import_configuration(original)
    expected = copy.deepcopy(original["data"])
    expected["network"] = None  # The destination has no proxy configuration.
    expected["gui"] = None  # Native window geometry is not imported.
    assert backup.export_configuration()["data"] == expected
    assert (
        json.loads(open(recovery, encoding="utf-8").read())["data"]["conf"]["account"]
        == "changed"
    )
    with sqlite3.connect(storage("@app/tmp/data.db")) as conn:
        assert conn.execute("SELECT value FROM reports").fetchone()[0] == "keep"
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone()[0] == 0


def test_absent_optional_configuration_clears_destination(storage):
    original = backup.export_configuration()
    path = backup.configuration_paths()["sss"]
    write_json(path, {"type": "SSS", "stages": []})
    backup.import_configuration(original)
    assert not path.exists()


def test_import_into_instance_without_database(storage):
    original = backup.export_configuration()
    storage("@app/tmp/data.db").unlink()
    storage("@app/tmp").rmdir()
    backup.import_configuration(original)
    assert backup.export_configuration()["data"] == original["data"]


@pytest.mark.parametrize("has_weekly_file", [False, True])
def test_import_reinitializes_weekly_plans_without_restart(
    storage, monkeypatch, has_weekly_file
):
    from arknights_mower.utils.config import app_state, weekly_plan_loader

    monkeypatch.setattr(app_state, "STATE_FILE", config.app_state_path)
    monkeypatch.setattr(
        weekly_plan_loader.WeeklyPlanManager,
        "WEEKLY_PLANS_FILE",
        config.weekly_plans_path,
    )
    monkeypatch.setattr(weekly_plan_loader, "_weekly_plan_manager", None)
    old_manager = weekly_plan_loader.get_weekly_plan_manager()
    incoming = backup.export_configuration()
    daily = {"weekday": "周一", "stage": ["1-7"], "medicine": 2}
    incoming["data"]["conf"]["maa_weekly_plan"] = [daily]
    incoming["data"]["weekly_plans"] = (
        {"plans": {"default": [daily]}} if has_weekly_file else None
    )
    backup.import_configuration(incoming)
    manager = weekly_plan_loader.get_weekly_plan_manager()
    assert manager is not old_manager
    assert manager.get_active_plan_key() == "默认"
    assert manager.get_plan("默认")[0]["stage"] == ["1-7"]
    assert config.conf.maa_weekly_plan[0].stage == ["1-7"]
    assert manager.set_inventory_config("默认", manager.get_inventory_config("默认"))


@pytest.mark.parametrize("has_local_network", [False, True])
@pytest.mark.parametrize("has_backup_network", [False, True])
def test_import_preserves_access_and_network_settings(
    storage, monkeypatch, has_local_network, has_backup_network
):
    config.conf.webview.port = 18080
    config.conf.webview.token = "local-token"
    config.save_conf()
    network_path = backup.configuration_paths()["network"]
    local_network = {"http_proxy": "http://127.0.0.1:7890", "github_proxy": ""}
    if has_local_network:
        write_json(network_path, local_network)
    previous_bytes = network_path.read_bytes() if has_local_network else None
    incoming = backup.export_configuration()
    incoming["data"]["conf"]["webview"].update(
        port=19090, token="backup-token", scale=1.25, tray=False
    )
    incoming["data"]["conf"]["account"] = "restored"
    incoming["data"]["plan"]["conf"]["ling_xi"] = 2
    incoming["data"]["network"] = (
        {"http_proxy": "http://127.0.0.1:8888", "github_proxy": "https://example.com"}
        if has_backup_network
        else None
    )
    original_input = copy.deepcopy(incoming)
    proxy_changes = []
    import_thread = threading.get_ident()

    def record_proxy_change():
        # Server imports start an independent periodic proxy sync thread.
        # Assert that this import itself does not reapply proxy settings.
        if threading.get_ident() == import_thread:
            proxy_changes.append(True)

    monkeypatch.setattr(
        backup.network_settings, "apply_http_proxy", record_proxy_change
    )
    recovery = backup.import_configuration(incoming)
    assert incoming == original_input
    assert config.conf.webview.port == 18080
    assert config.conf.webview.token == "local-token"
    assert config.conf.webview.scale == 1.25
    assert config.conf.webview.tray is True
    assert config.conf.account == "restored"
    assert config.plan.conf.ling_xi == 2
    assert not proxy_changes
    if has_local_network:
        assert network_path.read_bytes() == previous_bytes
    else:
        assert not network_path.exists()
    config.load_conf()  # The same access settings must also survive a restart.
    assert config.conf.webview.port == 18080
    assert config.conf.webview.token == "local-token"
    with open(recovery, encoding="utf-8") as stream:
        before = json.load(stream)["data"]
    assert before["conf"]["webview"]["token"] == "local-token"
    assert before["network"] == (local_network if has_local_network else None)


@pytest.mark.parametrize("has_local_gui", [False, True])
@pytest.mark.parametrize("has_backup_gui", [False, True])
@pytest.mark.parametrize("local_tray", [False, True])
def test_import_preserves_restart_only_settings(
    storage, has_local_gui, has_backup_gui, local_tray
):
    config.conf.webview.tray = local_tray
    config.save_conf()
    if has_local_gui:
        write_json(config.gui_path, {"ratio": {"width": 0.6, "height": 0.7}})
    previous = config.gui_path.read_bytes() if has_local_gui else None
    incoming = backup.export_configuration()
    incoming["data"]["conf"]["webview"].update(tray=not local_tray, scale=1.5)
    incoming["data"]["conf"].update(theme="dark", start_automatically=True)
    incoming["data"]["gui"] = (
        {"ratio": {"width": 0.9, "height": 1}} if has_backup_gui else None
    )
    backup.import_configuration(incoming)
    assert config.conf.webview.tray is local_tray
    config.load_conf()
    assert config.conf.webview.tray is local_tray
    # These are applied by the frontend on page load, without a process restart.
    assert config.conf.webview.scale == 1.5
    assert config.conf.theme == "dark"
    assert config.conf.start_automatically is True
    assert (
        config.gui_path.read_bytes() if config.gui_path.exists() else None
    ) == previous


def test_import_ignores_values_of_preserved_network_fields(storage):
    incoming = backup.export_configuration()
    incoming["data"]["conf"]["webview"].update(port="unused", token=None, tray="unused")
    incoming["data"]["network"] = {"http_proxy": "unused"}
    before = config.conf.webview.model_dump()
    backup.import_configuration(incoming)
    assert config.conf.webview.model_dump() == before


def test_browser_preferences_are_preserved_in_recovery_backup(storage):
    incoming = backup.export_configuration()
    incoming["browser_settings"] = {"sc_preview": "true"}
    incoming["current_browser_settings"] = {"sc_preview": "false"}
    recovery = backup.import_configuration(incoming)
    with open(recovery, encoding="utf-8") as stream:
        assert json.load(stream)["browser_settings"] == {"sc_preview": "false"}


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(version=2),
        lambda value: value["data"].pop("plan"),
        lambda value: value["data"].update(conf={"screenshot_interval": "invalid"}),
        lambda value: value["data"].update(weekly_plans={"plans": {"bad": [7]}}),
        lambda value: value["data"].update(network=[]),
        lambda value: value["data"]["mastery"]["mastery_plan"][0].update(
            unknown="invalid"
        ),
    ],
)
def test_invalid_backup_changes_nothing(storage, change):
    original = backup.export_configuration()
    invalid = copy.deepcopy(original)
    change(invalid)
    with pytest.raises((ValueError, TypeError)):
        backup.import_configuration(invalid)
    assert backup.export_configuration()["data"] == original["data"]
    assert not storage("@app/config-backups").exists()


def test_write_failure_rolls_back_files_runtime_and_database(storage, monkeypatch):
    original = backup.export_configuration()
    incoming = copy.deepcopy(original)
    incoming["data"]["conf"]["account"] = "after"
    incoming["data"]["mastery"]["mastery_plan"] = []
    atomic_write = config.atomic_write

    def fail_plan(path, writer):
        if path == config.plan_path:
            raise OSError("test disk failure")
        atomic_write(path, writer)

    monkeypatch.setattr(config, "atomic_write", fail_plan)
    with pytest.raises(OSError):
        backup.import_configuration(incoming)
    assert backup.export_configuration()["data"] == original["data"]
    assert len(list(storage("@app/config-backups").glob("*.json"))) == 1
    with sqlite3.connect(storage("@app/tmp/data.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone()[0] == 1


def test_form_save_keeps_fields_not_exposed_in_ui(storage):
    config.conf.maa_eat_stone = True
    config.conf.webview.port = 18080
    save_user_config({"theme": "dark", "webview": {"scale": 1.25}})
    assert config.conf.maa_eat_stone is True
    assert config.conf.webview.port == 18080
    assert config.conf.webview.scale == 1.25


@pytest.fixture
def client(storage):
    app = Flask(__name__)
    app.register_blueprint(config_backup_bp)
    app.token = "old-token"
    app.config["CONFIG_BACKUP_BUSY"] = lambda: False
    return app.test_client()


def test_routes_auth_busy_validation_and_existing_token_stays_valid(client):
    headers = {"token": "old-token", "X-Mower-Settings": "1"}
    assert client.get("/config-backup/export").status_code == 403
    exported = client.get("/config-backup/export", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["Cache-Control"] == "no-store"
    assert "attachment" in exported.headers["Content-Disposition"]
    data = exported.get_json()
    assert (
        client.post(
            "/config-backup/import", json=data, headers={"token": "old-token"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/config-backup/import",
            json=data,
            headers={**headers, "Origin": "https://other.example"},
        ).status_code
        == 403
    )
    assert (
        client.post("/config-backup/import", data="broken", headers=headers).status_code
        == 400
    )
    client.application.config["CONFIG_BACKUP_BUSY"] = lambda: True
    assert (
        client.post("/config-backup/import", json=data, headers=headers).status_code
        == 409
    )
    client.application.config["CONFIG_BACKUP_BUSY"] = lambda: False
    data["data"]["conf"]["webview"]["token"] = "new-token"
    imported = client.post("/config-backup/import", json=data, headers=headers)
    assert imported.status_code == 200
    assert imported.get_json()["token"] == "old-token"
    assert client.application.token == "old-token"
    assert client.get("/config-backup/export", headers=headers).status_code == 200
    assert (
        client.get("/config-backup/export", headers={"token": "new-token"}).status_code
        == 403
    )


def test_import_does_not_enable_authentication_on_open_instance(client):
    del client.application.token
    incoming = backup.export_configuration()
    incoming["data"]["conf"]["webview"]["token"] = "backup-token"
    response = client.post(
        "/config-backup/import", json=incoming, headers={"X-Mower-Settings": "1"}
    )
    assert response.status_code == 200
    assert not hasattr(client.application, "token")
    assert config.conf.webview.token == ""
    assert client.get("/config-backup/export").status_code == 200


def test_oversized_import_is_rejected(client, monkeypatch):
    monkeypatch.setattr("arknights_mower.views.config_backup.MAX_BACKUP_BYTES", 32)
    response = client.post(
        "/config-backup/import",
        data="x" * 33,
        headers={"token": "old-token", "X-Mower-Settings": "1"},
    )
    assert response.status_code == 413
