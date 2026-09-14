"""排班改变后仅刷新运行时优先级，不改动用户设置。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.operators import Dormitory, Operators
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
        "dormitory_2_4,dormitory_1_2,dormitory_2_2,dormitory_1_4,"
        "dormitory_1_3,dormitory_2_3",
        "dormitory_2_4",
    ],
)
def test_stale_or_incomplete_order_keeps_original_validation(saved, old):
    config.conf.dorm_order = old
    op = operators()
    assert (
        op.init_and_validate()
        == "宿舍优先级和当前宿舍不匹配，请清除优先级自动排序或者自己更正"
    )
    assert config.conf.dorm_order == old
    saved.assert_not_called()


def test_empty_order_uses_runtime_default_without_rewriting_setting(saved):
    op = operators()
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == DEFAULT
    assert config.conf.dorm_order == ""
    saved.assert_not_called()


def test_valid_manual_order_is_used_without_rewriting_setting(saved):
    order = list(reversed(DEFAULT))
    config.conf.dorm_order = ",".join(order)
    op = operators()
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == order
    saved.assert_not_called()


def test_saved_state_restores_values_without_overriding_regenerated_order(saved):
    op = operators()
    assert op.init_and_validate() is None
    first_time = datetime(2026, 9, 14, 12)
    last_time = datetime(2026, 9, 14, 13)
    op.restore_dorm_state(
        [
            Dormitory(("dormitory_2", 4), "流明", last_time),
            Dormitory(("dormitory_3", 2), "失效床位", first_time),
            Dormitory(("dormitory_1", 3), "冰酿", first_time),
        ]
    )
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == DEFAULT
    assert (op.dorm[0].name, op.dorm[0].time) == ("冰酿", first_time)
    assert (op.dorm[-1].name, op.dorm[-1].time) == ("流明", last_time)
    assert all(dorm.position[0] != "dormitory_3" for dorm in op.dorm)
    assert config.conf.dorm_order == ""
    saved.assert_not_called()


def test_invalid_plan_still_rejected(saved):
    config.conf.dorm_order = "obsolete"
    op = operators()
    op.plan["dormitory_1"][0] = Room("Free", "", [])
    assert op.init_and_validate() == "宿舍必须安排2个宿管"
    saved.assert_not_called()


def test_plan_save_never_changes_dorm_order(saved, monkeypatch):
    import server

    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "save_plan", MagicMock())
    client = server.app.test_client()
    config.conf.dorm_order = ",".join(reversed(DEFAULT))
    payload = config.plan.model_dump(mode="json", exclude_none=True)
    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert "dorm_order_reset" not in response.json
    saved.assert_not_called()
    payload["conf"]["ling_xi"] = 2
    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert config.conf.dorm_order == ",".join(reversed(DEFAULT))
    saved.assert_not_called()


def test_failed_plan_save_restores_plan_and_keeps_dorm_order(monkeypatch, tmp_path):
    import server

    original_plan = config.PlanModel()
    original_order = ",".join(reversed(DEFAULT))
    monkeypatch.setattr(config, "plan", original_plan)
    monkeypatch.setattr(config, "conf", config.Conf(dorm_order=original_order))
    monkeypatch.setattr(config, "plan_path", tmp_path / "plan.json")
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    config.save_plan()
    config.save_conf()
    real_save = config.save_plan

    def fail_once():
        nonlocal first_attempt
        if first_attempt:
            first_attempt = False
            raise OSError("temporary write failure")
        real_save()

    first_attempt = True
    monkeypatch.setattr(config, "save_plan", fail_once)
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
    assert config.plan.conf.ling_xi == 2
    assert config.conf.dorm_order == original_order
