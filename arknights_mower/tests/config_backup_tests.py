import copy
import json
import sqlite3

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
    assert backup.export_configuration()["data"] == original["data"]
    assert (
        json.loads(open(recovery, encoding="utf-8").read())["data"]["conf"]["account"]
        == "changed"
    )
    with sqlite3.connect(storage("@app/tmp/data.db")) as conn:
        assert conn.execute("SELECT value FROM reports").fetchone()[0] == "keep"
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone()[0] == 0


def test_absent_optional_configuration_clears_destination(storage):
    original = backup.export_configuration()
    write_json(config.gui_path, {"ratio": {"width": 1, "height": 1}})
    backup.import_configuration(original)
    assert not config.gui_path.exists()


def test_import_into_instance_without_database(storage):
    original = backup.export_configuration()
    storage("@app/tmp/data.db").unlink()
    storage("@app/tmp").rmdir()
    backup.import_configuration(original)
    assert backup.export_configuration()["data"] == original["data"]


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
        lambda value: value["data"].update(network={"http_proxy": "invalid"}),
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


def test_routes_auth_busy_validation_and_token_refresh(client):
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
    assert imported.get_json()["token"] == "new-token"
    assert client.get("/config-backup/export", headers=headers).status_code == 403
    assert (
        client.get("/config-backup/export", headers={"token": "new-token"}).status_code
        == 200
    )


def test_oversized_import_is_rejected(client, monkeypatch):
    monkeypatch.setattr("arknights_mower.views.config_backup.MAX_BACKUP_BYTES", 32)
    response = client.post(
        "/config-backup/import",
        data="x" * 33,
        headers={"token": "old-token", "X-Mower-Settings": "1"},
    )
    assert response.status_code == 413
