"""排班改变后重新生成优先级，历史失效床位不再阻断启动。"""

import json
from unittest.mock import MagicMock

import pytest
import yaml

from arknights_mower.utils import config
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room


@pytest.fixture
def saved(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    save = MagicMock()
    monkeypatch.setattr(config, "save_conf", save)
    return save


def operators():
    return Operators(
        {
            "default_plan": Plan(
                {
                    "dormitory_1": [
                        Room(n, "", [])
                        for n in ["冰酿", "闪灵", "至简", "Free", "Free"]
                    ],
                    "dormitory_2": [
                        Room(n, "", [])
                        for n in ["流明", "蜜莓", "Free", "Free", "Free"]
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )


DEFAULT = [
    "dormitory_1_3",
    "dormitory_2_2",
    "dormitory_1_4",
    "dormitory_2_3",
    "dormitory_2_4",
]


@pytest.mark.parametrize(
    "old",
    [
        "dormitory_2_4,dormitory_1_2,dormitory_2_2,dormitory_1_4,dormitory_1_3,dormitory_2_3",
        "dormitory_2_4",
        "",
    ],
)
def test_stale_or_empty_order_regenerates_entire_default_order(saved, old):
    config.conf.dorm_order = old
    op = operators()
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == DEFAULT
    assert config.conf.dorm_order == ",".join(DEFAULT)
    saved.assert_called_once()
    assert operators().init_and_validate() is None
    saved.assert_called_once()


def test_valid_manual_order_unchanged_until_plan_is_edited(saved):
    order = list(reversed(DEFAULT))
    config.conf.dorm_order = ",".join(order)
    op = operators()
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == order
    saved.assert_not_called()


def test_invalid_plan_still_rejected(saved):
    config.conf.dorm_order = "obsolete"
    op = operators()
    op.plan["dormitory_1"][0] = Room("Free", "", [])
    assert op.init_and_validate() == "宿舍必须安排2个宿管"
    saved.assert_not_called()


def test_plan_save_clears_old_order_only_when_content_changes(saved, monkeypatch):
    import server

    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "save_plan", MagicMock())
    client = server.app.test_client()
    config.conf.dorm_order = ",".join(reversed(DEFAULT))
    payload = config.plan.model_dump(mode="json", exclude_none=True)
    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert response.json["dorm_order_reset"] is False
    saved.assert_not_called()
    payload["conf"]["ling_xi"] = 2
    response = client.post("/plan", json=payload)
    assert response.json["dorm_order_reset"] is True
    assert config.conf.dorm_order == ""
    saved.assert_called_once()
    config.conf.dorm_order = ",".join(DEFAULT)
    response = client.post("/plan", json=payload)
    assert response.json["dorm_order_reset"] is False
    assert config.conf.dorm_order == ",".join(DEFAULT)
    saved.assert_called_once()


@pytest.mark.parametrize("failed_save", ["save_plan", "save_conf"])
def test_failed_plan_save_can_retry_dorm_order_reset(
    monkeypatch, tmp_path, failed_save
):
    import server

    original_plan = config.PlanModel()
    original_order = ",".join(reversed(DEFAULT))
    monkeypatch.setattr(config, "plan", original_plan)
    monkeypatch.setattr(config, "conf", config.Conf(dorm_order=original_order))
    monkeypatch.setattr(config, "plan_path", tmp_path / "plan.json")
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    config.save_plan()
    config.save_conf()
    real_save = getattr(config, failed_save)

    def fail_once():
        nonlocal first_attempt
        if first_attempt:
            first_attempt = False
            raise OSError("temporary write failure")
        real_save()

    first_attempt = True
    monkeypatch.setattr(config, failed_save, fail_once)
    monkeypatch.setitem(server.app.config, "PROPAGATE_EXCEPTIONS", False)
    client = server.app.test_client()
    payload = original_plan.model_dump(mode="json", exclude_none=True)
    payload["conf"]["ling_xi"] = 2

    response = client.post("/plan", json=payload)
    assert response.status_code == 500
    assert config.plan is original_plan
    assert config.conf.dorm_order == original_order

    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert response.json["dorm_order_reset"] is True
    assert config.plan.conf.ling_xi == 2
    assert config.conf.dorm_order == ""
    assert json.loads(config.plan_path.read_text())["conf"]["ling_xi"] == 2
    assert yaml.safe_load(config.conf_path.read_text())["dorm_order"] == ""

    config.conf.dorm_order = original_order
    config.save_conf()
    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert response.json["dorm_order_reset"] is False
    assert config.conf.dorm_order == original_order
    assert yaml.safe_load(config.conf_path.read_text())["dorm_order"] == original_order
