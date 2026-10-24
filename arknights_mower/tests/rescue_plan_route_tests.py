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
    monkeypatch.setattr(config, "rescue_plan", config.PlanModel())
    monkeypatch.setattr(config, "save_rescue_plan", MagicMock())
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
    config.save_conf.assert_not_called()
    config.save_rescue_plan.assert_called_once()


def test_save_failure_preserves_rescue_roster(client):
    original = config.rescue_plan
    config.save_rescue_plan.side_effect = OSError("readonly")
    with pytest.raises(OSError):
        server._save_rescue_plan(
            config.PlanModel(plan1={"central": {"plans": [{"agent": "红"}]}})
        )
    assert config.rescue_plan is original


@pytest.mark.parametrize(
    "url,method",
    [
        ("/rescue-plan", "GET"),
        ("/rescue-plan", "POST"),
        ("/rescue-plan/validate", "POST"),
        ("/import?rescue=1", "POST"),
        ("/dialog/save/img?rescue=1", "POST"),
    ],
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_rescue_routes_reject_missing_or_invalid_token_before_work(
    client, monkeypatch, url, method, token
):
    def forbidden(*args, **kwargs):
        pytest.fail("未授权请求读取或写入救急排班")

    monkeypatch.setattr(config, "save_rescue_plan", forbidden)
    monkeypatch.setattr(server, "build_global_plan", forbidden)
    response = client.open(
        url, method=method, headers={"token": token} if token else {}
    )
    assert response.status_code == 403


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
    config.rescue_plan = config.PlanModel(
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


@pytest.mark.parametrize(
    "invalid, expected",
    [
        ("missing_left", "缺少必填"),
        ("empty_left", "无效"),
        ("duplicate", "重复"),
        ("replacement", "替换干员"),
        ("backup_name", "无效"),
        ("backup_duplicate", "重复"),
        ("backup_empty_left", "无效"),
    ],
)
@pytest.mark.parametrize("conditional", [False, True])
def test_rescue_validation_checks_own_roster_before_conditional_deferral(
    client, monkeypatch, invalid, expected, conditional
):
    from types import SimpleNamespace

    from arknights_mower.utils.plan import Room

    normal = SimpleNamespace(
        plan={
            "room_1_1": [Room("芬", "", [], "制造站")],
            "central": [Room("红", "", [])],
            "recycle": [Room("砾", "", []), Room("斑点", "", [])],
        },
        products={},
        backup_plans=[object()] if conditional else [],
        init_and_validate=lambda: None,
    )
    monkeypatch.setattr(server, "build_global_plan", lambda: {})
    monkeypatch.setattr(server, "Operators", lambda plan: normal)
    payload = {
        "plan1": {
            "room_1_1": {"name": "制造站", "plans": [{"agent": "香草"}]},
            "central": {"plans": [{"agent": "杜林"}]},
            "recycle": {"plans": [{"agent": "黑角"}, {"agent": "夜刀"}]},
        }
    }
    if invalid == "missing_left":
        del payload["plan1"]["room_1_1"]
    elif invalid == "empty_left":
        payload["plan1"]["room_1_1"]["plans"][0]["agent"] = ""
    elif invalid == "duplicate":
        payload["plan1"]["central"]["plans"][0]["agent"] = "香草"
    elif invalid == "replacement":
        payload["plan1"]["central"]["plans"][0]["replacement"] = ["不存在"]
    elif invalid == "backup_empty_left":
        payload["backup_plans"] = [
            {
                "name": "条件",
                "plan": {"room_1_1": {"name": "制造站", "plans": [{"agent": ""}]}},
            }
        ]
    else:
        rows = (
            [{"agent": "不存在"}]
            if invalid == "backup_name"
            else [{"agent": "初雪"}, {"agent": "初雪"}]
        )
        payload["backup_plans"] = [
            {"name": "条件", "trigger": {}, "plan": {"recycle": {"plans": rows}}}
        ]
    config.rescue_plan = config.PlanModel(**payload)
    response = client.post(
        "/rescue-plan/validate", headers={"token": "rescue-route"}
    ).get_json()
    assert response["success"] is False
    assert expected in response["message"]
    config.save_conf.assert_not_called()


@pytest.mark.parametrize("room", ["meeting", "contact", "recycle", "factory", "train"])
@pytest.mark.parametrize("blank", [False, True])
@pytest.mark.parametrize("conditional", [False, True])
def test_rescue_validation_preserves_working_and_specialized_room_rules(
    client, monkeypatch, room, blank, conditional
):
    from types import SimpleNamespace

    from arknights_mower.utils.plan import Room

    normal = SimpleNamespace(
        plan={
            "room_1_1": [Room("芬", "", [], "制造站")],
            "central": [Room("红", "", [])],
            room: [Room("砾", "", [])],
        },
        products={},
        backup_plans=[object()] if conditional else [],
        init_and_validate=lambda: None,
    )
    monkeypatch.setattr(server, "build_global_plan", lambda: {})
    monkeypatch.setattr(server, "Operators", lambda plan: normal)
    payload = {
        "room_1_1": {"name": "制造站", "plans": [{"agent": "香草"}]},
        "central": {"plans": [{"agent": "杜林"}]},
    }
    if blank:
        payload[room] = {"plans": [{"agent": ""}]}
    config.rescue_plan = config.PlanModel(plan1=payload)
    response = client.post(
        "/rescue-plan/validate", headers={"token": "rescue-route"}
    ).get_json()
    if room in {"factory", "train"}:
        assert response["success"] is True
        assert (response.get("status") == "incomplete") is conditional
    else:
        assert response["success"] is False
        assert room in response["message"]
    config.save_conf.assert_not_called()
    config.save_plan.assert_not_called()
