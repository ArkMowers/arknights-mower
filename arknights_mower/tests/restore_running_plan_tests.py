import json
from types import SimpleNamespace

import pytest
from yaml import safe_load

import arknights_mower.__main__ as mower_main
import server
from arknights_mower.utils import config
from arknights_mower.utils.config.plan_advanced import (
    ADVANCED_SETTING_KEYS,
    export_advanced_settings,
)
from arknights_mower.utils.operators import build_global_plan


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "plan_path", tmp_path / "plan.json")
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "conf", config.Conf(account="current account"))
    monkeypatch.setattr(server.app, "token", "restore-test", raising=False)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(mower_main, "base_scheduler", None)
    return server.app.test_client()


def restore(client):
    return client.post("/plan/restore-running", headers={"token": "restore-test"})


def test_runtime_plan_keeps_independent_startup_snapshot(monkeypatch):
    configured = config.PlanModel(plan1={"central": {"plans": [{"agent": "阿米娅"}]}})
    monkeypatch.setattr(config, "plan", configured)

    runtime, snapshot = build_global_plan(include_source=True)
    configured.plan1.central.plans[0].agent = "杜宾"

    assert runtime["default_plan"].plan["central"][0].agent == "阿米娅"
    assert snapshot["plan1"]["central"]["plans"][0]["agent"] == "阿米娅"


def test_startup_snapshot_captures_actual_advanced_settings(monkeypatch):
    configured = config.PlanModel(advanced_settings={"drone_count_limit": 20})
    startup_conf = config.Conf(drone_count_limit=150, drone_interval=2)
    monkeypatch.setattr(config, "plan", configured)
    monkeypatch.setattr(config, "conf", startup_conf)

    _, snapshot = build_global_plan(include_source=True)
    startup_conf.drone_count_limit = 20
    startup_conf.product_switching.waiting_seconds = 5

    assert set(snapshot["advanced_settings"]) == set(ADVANCED_SETTING_KEYS)
    assert snapshot["advanced_settings"]["drone_count_limit"] == 150
    assert snapshot["advanced_settings"]["drone_interval"] == 2
    assert snapshot["advanced_settings"]["product_switching"]["waiting_seconds"] == 2
    assert configured.advanced_settings == {"drone_count_limit": 20}


def test_restore_running_plan_uses_startup_snapshot(client, monkeypatch):
    startup = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "阿米娅"}]}},
        backup_plans=[
            {"name": "运行副表", "plan": {}, "conf": {}, "task": {}, "trigger": {}}
        ],
        advanced_settings=export_advanced_settings(
            config.Conf(drone_count_limit=150, drone_interval=2, free_room=True)
        ),
    )
    edited = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "杜宾"}]}},
        advanced_settings={"drone_count_limit": 20},
    )
    config.conf.drone_count_limit = 20
    config.conf.drone_interval = 3
    config.conf.drone_room = "room_3_3"
    monkeypatch.setattr(config, "plan", edited)
    monkeypatch.setattr(server, "mower_thread", SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setattr(
        mower_main,
        "base_scheduler",
        SimpleNamespace(source_plan=startup.model_dump(exclude_none=True)),
    )

    response = restore(client)

    assert response.status_code == 200
    assert config.plan.plan1.central.plans[0].agent == "阿米娅"
    assert config.plan.backup_plans[0].name == "运行副表"
    assert config.plan.advanced_settings == startup.advanced_settings
    assert config.conf.drone_count_limit == 150
    assert config.conf.drone_interval == 2
    assert config.conf.free_room is True
    assert config.conf.account == "current account"
    assert config.conf.drone_room == "room_3_3"
    assert safe_load(config.conf_path.read_text())["drone_count_limit"] == 150
    assert (
        json.loads(config.plan_path.read_text())["advanced_settings"]
        == startup.advanced_settings
    )
    assert mower_main.base_scheduler.source_plan == startup.model_dump(
        exclude_none=True
    )
    assert config.plan_path.is_file()


def test_restore_running_plan_rejects_stopped_or_unready_runtime(client, monkeypatch):
    edited = config.PlanModel(plan1={"central": {"plans": [{"agent": "杜宾"}]}})
    monkeypatch.setattr(config, "plan", edited)

    assert restore(client).status_code == 409
    monkeypatch.setattr(server, "mower_thread", SimpleNamespace(is_alive=lambda: True))
    assert restore(client).status_code == 409
    assert config.plan is edited
    assert not config.plan_path.exists()


@pytest.mark.parametrize("advanced", [None, {"unknown_setting": True}])
def test_restore_rejects_unavailable_or_invalid_settings_before_writing(
    client, monkeypatch, advanced
):
    startup = config.PlanModel(advanced_settings=advanced)
    current_plan = config.plan
    current_conf = config.conf
    monkeypatch.setattr(server, "mower_thread", SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setattr(
        mower_main,
        "base_scheduler",
        SimpleNamespace(source_plan=startup.model_dump(exclude_none=True)),
    )

    response = restore(client)

    assert response.status_code == (409 if advanced is None else 400)
    assert config.plan is current_plan
    assert config.conf is current_conf
    assert not config.plan_path.exists()
    assert not config.conf_path.exists()


@pytest.mark.parametrize("target", ["plan", "conf"])
@pytest.mark.parametrize("after_write", [False, True])
@pytest.mark.parametrize("existing_files", [False, True])
def test_restore_compensates_either_file_write_failure(
    client, monkeypatch, target, after_write, existing_files
):
    startup = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "阿米娅"}]}},
        advanced_settings={"drone_count_limit": 150},
    )
    current_plan = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "杜宾"}]}},
        advanced_settings={"drone_count_limit": 20},
    )
    monkeypatch.setattr(config, "plan", current_plan)
    config.conf.drone_count_limit = 20
    current_conf = config.conf
    if existing_files:
        config.save_plan()
        config.save_conf()
        config.conf_path.write_bytes(
            b"# keep this comment\n" + config.conf_path.read_bytes()
        )
    originals = {
        path: path.read_bytes() if path.exists() else None
        for path in (config.plan_path, config.conf_path)
    }
    monkeypatch.setattr(server, "mower_thread", SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setattr(
        mower_main,
        "base_scheduler",
        SimpleNamespace(source_plan=startup.model_dump(exclude_none=True)),
    )
    original_save = getattr(config, f"save_{target}")

    def fail_save():
        if after_write:
            original_save()
        raise OSError("write failed")

    monkeypatch.setattr(config, f"save_{target}", fail_save)

    response = restore(client)

    assert response.status_code == 500
    assert config.plan is current_plan
    assert config.conf is current_conf
    for path, original in originals.items():
        assert (path.read_bytes() if path.exists() else None) == original
