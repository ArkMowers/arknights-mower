"""救急排班读写与导入仅更新自己的配置。"""

import io
import json
from unittest.mock import MagicMock

import pytest

import server
from arknights_mower.utils import config


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "save_conf", MagicMock())
    monkeypatch.setattr(config, "save_plan", MagicMock())
    monkeypatch.setattr(server.app, "token", "rescue-route", raising=False)
    return server.app.test_client()


@pytest.mark.parametrize("imported", [False, True])
def test_rescue_write_and_import_do_not_replace_normal_schedule(client, imported):
    payload = {
        "plan1": {"central": {"plans": [{"agent": "红"}]}},
        "backup_plans": [
            {"name": "设施变化", "plan": {}, "conf": {}, "task": {}, "trigger": {}}
        ],
    }
    normal = config.plan.model_dump()
    if imported:
        response = client.post(
            "/import?rescue=1",
            data={"img": (io.BytesIO(json.dumps(payload).encode()), "rescue.json")},
            headers={"token": "rescue-route"},
        )
    else:
        response = client.post(
            "/rescue-plan", json=payload, headers={"token": "rescue-route"}
        )
    assert response.status_code == 200
    saved = client.get("/rescue-plan", headers={"token": "rescue-route"}).get_json()
    assert saved["plan1"]["central"]["plans"][0]["agent"] == "红"
    assert saved["backup_plans"][0]["name"] == "设施变化"
    assert config.plan.model_dump() == normal
    config.save_plan.assert_not_called()
    config.save_conf.assert_called_once()


def test_save_failure_preserves_rescue_roster(client):
    original = config.conf.automatic_rescue_plan
    config.save_conf.side_effect = OSError("readonly")
    with pytest.raises(OSError):
        server._save_rescue_plan(
            config.PlanModel(plan1={"central": {"plans": [{"agent": "红"}]}})
        )
    assert config.conf.automatic_rescue_plan is original


@pytest.mark.parametrize("backup_source", ["normal", "rescue", None])
def test_validation_defers_conditional_plans_and_rejects_product_mismatch(
    client, monkeypatch, backup_source
):
    from types import SimpleNamespace

    from arknights_mower.utils.plan import Room

    normal = SimpleNamespace(
        plan={"room_1_1": [Room("红", "", [], "贸易站")]},
        products={"room_1_1": "lmd"},
        backup_plans=[object()] if backup_source == "normal" else [],
        init_and_validate=lambda: None,
    )
    monkeypatch.setattr(server, "build_global_plan", lambda: {})
    monkeypatch.setattr(server, "Operators", lambda plan: normal)
    config.conf.automatic_rescue_plan = config.PlanModel(
        plan1={
            "room_1_1": {
                "name": "贸易站",
                "product": "orundum",
                "plans": [{"agent": "砾"}],
            }
        },
        backup_plans=(
            [{"name": "条件", "plan": {}, "conf": {}, "task": {}, "trigger": {}}]
            if backup_source == "rescue"
            else []
        ),
    )
    before = config.conf.model_dump()
    response = client.post(
        "/rescue-plan/validate", headers={"token": "rescue-route"}
    ).get_json()
    if backup_source:
        assert response["success"]
        assert response["status"] == "incomplete"
        assert "初始化实测后" in response["message"]
    else:
        assert not response["success"]
        assert "room_1_1 产物不一致" in response["message"]
    assert config.conf.model_dump() == before
    config.save_conf.assert_not_called()
    config.save_plan.assert_not_called()
