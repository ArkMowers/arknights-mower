"""Missing backup task groups remain editable and fail execution validation."""

import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

import server
from arknights_mower.utils import config, schedule_roster
from arknights_mower.utils.config.plan import PlanModel


def schedule():
    return {
        "plan1": {"central": {"plans": [{"agent": "能天使", "group": "现有绑组"}]}},
        "conf": {"workaholic": "能天使"},
        "backup_plans": [
            {
                "name": "待修正副表",
                "trigger": {"left": "False"},
                "group_tasks": [{"group": "已删除的绑组", "action": "off"}],
            }
        ],
    }


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "conf", config.Conf())
    baseline = schedule()
    baseline["backup_plans"] = []
    monkeypatch.setattr(config, "plan", PlanModel(**baseline))
    monkeypatch.setattr(config, "rescue_plan", PlanModel())
    monkeypatch.setattr(config, "save_plan", Mock())
    monkeypatch.setattr(config, "save_rescue_plan", Mock())
    monkeypatch.setattr(config, "save_conf", Mock())
    monkeypatch.setattr(
        schedule_roster, "get_path", lambda _: tmp_path / "cultivate.json"
    )
    monkeypatch.setattr(server.app, "token", "plan-recovery", raising=False)
    return server.app.test_client()


def test_unknown_task_group_survives_document_round_trip():
    model = PlanModel(**schedule())
    restored = PlanModel.model_validate_json(model.model_dump_json())
    assert restored.backup_plans[0].group_tasks[0].group == "已删除的绑组"


@pytest.mark.parametrize("source", ["main", "binding", "backup"])
def test_schedule_validation_accepts_groups_declared_in_any_operator_binding(source):
    from arknights_mower.utils.operators import Operators, build_global_plan

    payload = schedule()
    group = "任务绑组"
    payload["backup_plans"][0]["group_tasks"][0]["group"] = group
    slot = payload["plan1"]["central"]["plans"][0]
    if source == "main":
        slot["group"] = group
    elif source == "binding":
        slot["group_bindings"] = [{"group": group, "replacement": []}]
    else:
        payload["backup_plans"].append(
            {
                "name": "声明绑组的副表",
                "trigger": {"left": "False"},
                "plan": {"central": {"plans": [{"agent": "能天使", "group": group}]}},
            }
        )
    data = Operators(build_global_plan(plan_model=PlanModel(**payload)))
    assert data.init_and_validate() is None


@pytest.mark.parametrize("rescue", [False, True])
@pytest.mark.parametrize("repair", ["remove", "retarget"])
def test_save_validate_correct_and_revalidate(client, rescue, repair):
    endpoint = "/rescue-plan" if rescue else "/plan"
    validation = "/rescue-plan/validate" if rescue else "/validate-plan"
    headers = {"token": "plan-recovery"}
    payload = schedule()
    response = client.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 200
    saved = client.get(endpoint, headers=headers).json
    assert saved["backup_plans"][0]["group_tasks"][0]["group"] == "已删除的绑组"

    result = client.post(validation, json={}, headers=headers)
    assert result.status_code == 200
    assert result.json["success"] is False
    assert "待修正副表" in result.json["message"]
    assert "绑组任务组名不存在：已删除的绑组" in result.json["message"]

    if repair == "remove":
        payload["backup_plans"][0]["group_tasks"] = []
    else:
        payload["backup_plans"][0]["group_tasks"][0]["group"] = "现有绑组"
    assert client.post(endpoint, json=payload, headers=headers).status_code == 200
    assert client.post(validation, json={}, headers=headers).json["success"] is True


def test_snapshot_validation_reports_unknown_group_without_saving(client):
    before = config.plan.model_dump()
    response = client.post(
        "/validate-plan",
        json={"plan": schedule(), "operatorMode": "maximum"},
        headers={"token": "plan-recovery"},
    )
    assert response.status_code == 200
    assert response.json["status"] == "failed"
    assert "待修正副表" in response.json["message"]
    assert "绑组任务组名不存在：已删除的绑组" in response.json["message"]
    assert config.plan.model_dump() == before
    config.save_plan.assert_not_called()


@pytest.mark.parametrize("rescue", [False, True])
@pytest.mark.parametrize("kind", ["json", "image"])
def test_import_can_replace_a_schedule_with_an_unknown_task_group(
    client, monkeypatch, rescue, kind
):
    headers = {"token": "plan-recovery"}
    endpoint = "/rescue-plan" if rescue else "/plan"
    if kind == "json":
        upload = (io.BytesIO(json.dumps(schedule()).encode()), "plan.json")
    else:
        from arknights_mower import utils

        codec = SimpleNamespace(decode=Mock(return_value=schedule()))
        monkeypatch.setitem(sys.modules, "arknights_mower.utils.qrcode", codec)
        monkeypatch.setattr(utils, "qrcode", codec, raising=False)
        image = io.BytesIO()
        Image.new("RGB", (16, 16), "white").save(image, "PNG")
        image.seek(0)
        upload = (image, "plan.png")
    imported = client.post(
        "/import?rescue=1" if rescue else "/import",
        data={"img": upload},
        headers=headers,
    )
    assert imported.status_code == 200
    assert imported.text == "排班已加载"
    saved = client.get(endpoint, headers=headers).json
    assert saved["backup_plans"][0]["group_tasks"][0]["group"] == "已删除的绑组"

    replacement = schedule()
    replacement["backup_plans"] = []
    result = client.post(
        "/import?rescue=1" if rescue else "/import",
        data={
            "img": (io.BytesIO(json.dumps(replacement).encode()), "replacement.json")
        },
        headers=headers,
    )
    assert result.text == "排班已加载"
    assert client.get(endpoint, headers=headers).json["backup_plans"] == []


@pytest.mark.parametrize(
    "rescue,snapshot", [(False, False), (True, False), (False, True)]
)
def test_image_export_preserves_unknown_group_task(
    client, monkeypatch, rescue, snapshot
):
    from arknights_mower import utils

    headers = {"token": "plan-recovery"}
    endpoint = "/rescue-plan" if rescue else "/plan"
    if not snapshot:
        assert (
            client.post(endpoint, json=schedule(), headers=headers).status_code == 200
        )
    export = Mock(side_effect=lambda plan, image, theme: image)
    codec = SimpleNamespace(export=export)
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.qrcode", codec)
    monkeypatch.setattr(utils, "qrcode", codec, raising=False)
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, "PNG")
    image.seek(0)
    data = {"img": (image, "plan.png"), "theme": "light"}
    if snapshot:
        data["plan"] = json.dumps(schedule())
    response = client.post(
        "/dialog/save/img?rescue=1" if rescue else "/dialog/save/img",
        data=data,
        headers=headers,
    )
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert export.call_args.args[0]["backup_plans"][0]["group_tasks"][0]["group"] == (
        "已删除的绑组"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "/plan",
        "/rescue-plan",
        "/import",
        "/import?rescue=1",
        "/dialog/save/img",
        "/dialog/save/img?rescue=1",
    ],
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_recovery_routes_require_token_before_parsing(
    client, monkeypatch, endpoint, token
):
    from flask import Request

    forbidden = Mock(side_effect=AssertionError("unauthorized request parsed input"))
    monkeypatch.setattr(Request, "get_json", forbidden)
    monkeypatch.setattr(Request, "files", property(lambda _: forbidden()))
    response = client.post(endpoint, headers={"token": token} if token else {})
    assert response.status_code == 403
    forbidden.assert_not_called()
    config.save_plan.assert_not_called()
    config.save_rescue_plan.assert_not_called()
