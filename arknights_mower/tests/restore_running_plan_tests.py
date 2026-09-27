from types import SimpleNamespace

import pytest

import arknights_mower.__main__ as mower_main
import server
from arknights_mower.utils import config
from arknights_mower.utils.operators import build_global_plan


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "plan_path", tmp_path / "plan.json")
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


def test_restore_running_plan_uses_startup_snapshot(client, monkeypatch):
    startup = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "阿米娅"}]}},
        backup_plans=[
            {"name": "运行副表", "plan": {}, "conf": {}, "task": {}, "trigger": {}}
        ],
    )
    edited = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "杜宾"}]}},
        advanced_settings={"drone_count_limit": 140},
    )
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
    assert config.plan.advanced_settings == {"drone_count_limit": 140}
    assert config.plan_path.is_file()


def test_restore_running_plan_rejects_stopped_or_unready_runtime(client, monkeypatch):
    edited = config.PlanModel(plan1={"central": {"plans": [{"agent": "杜宾"}]}})
    monkeypatch.setattr(config, "plan", edited)

    assert restore(client).status_code == 409
    monkeypatch.setattr(server, "mower_thread", SimpleNamespace(is_alive=lambda: True))
    assert restore(client).status_code == 409
    assert config.plan is edited
    assert not config.plan_path.exists()
