"""宿舍床位顺序随主副排班独立保存并在切换时刷新。"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.config.plan import migrate_legacy_dorm_order
from arknights_mower.utils.operators import Dormitory, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room


@pytest.fixture
def saved(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    save = MagicMock()
    monkeypatch.setattr(config, "save_conf", save)
    return save


def operators(dorm_order="", backup_orders=()):
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
                PlanConfig("", "", "", dorm_order=dorm_order),
            ),
            "backup_plans": [
                Plan({}, PlanConfig("", "", "", dorm_order=order))
                for order in backup_orders
            ],
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
    op = operators(old)
    assert (
        op.init_and_validate()
        == "宿舍优先级和当前宿舍不匹配，请清除优先级自动排序或者自己更正"
    )
    saved.assert_not_called()


def test_empty_order_uses_runtime_default_without_rewriting_setting(saved):
    config.conf.dorm_order = ",".join(reversed(DEFAULT))
    op = operators()
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == DEFAULT
    # The deprecated global setting is no longer a runtime source.
    assert config.conf.dorm_order == ",".join(reversed(DEFAULT))
    saved.assert_not_called()


def test_valid_manual_order_is_used_without_rewriting_setting(saved):
    order = list(reversed(DEFAULT))
    op = operators(",".join(order))
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
    op = operators("obsolete")
    op.plan["dormitory_1"][0] = Room("Free", "", [])
    assert op.init_and_validate() == "宿舍必须安排2个宿管"
    saved.assert_not_called()


def test_backup_order_overrides_main_and_switching_back_restores_main(saved):
    main = list(reversed(DEFAULT))
    backup = DEFAULT[1:] + DEFAULT[:1]
    op = operators(",".join(main), [",".join(backup)])
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == main

    assert op.swap_plan([True], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == backup

    assert op.swap_plan([False], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == main


def test_empty_backup_order_explicitly_restores_default(saved):
    op = operators(",".join(reversed(DEFAULT)), [""])
    assert op.init_and_validate() is None
    assert op.swap_plan([True], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == DEFAULT


def test_last_active_backup_order_wins(saved):
    first = DEFAULT[1:] + DEFAULT[:1]
    second = DEFAULT[2:] + DEFAULT[:2]
    op = operators("", [",".join(first), ",".join(second)])
    assert op.init_and_validate() is None
    assert op.swap_plan([True, True], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == second


def test_legacy_global_order_is_copied_to_every_missing_plan_config():
    legacy = ",".join(reversed(DEFAULT))
    data = {
        "plan1": {},
        "conf": {},
        "backup_plans": [
            {"plan": {}, "conf": {}},
            {"plan": {}, "conf": {"dorm_order": ""}},
        ],
    }
    plan = config.PlanModel(**data)

    assert migrate_legacy_dorm_order(plan, data, legacy)
    assert plan.conf.dorm_order == legacy
    assert plan.backup_plans[0].conf.dorm_order == legacy
    # An explicitly empty per-plan value means default order and is preserved.
    assert plan.backup_plans[1].conf.dorm_order == ""


def test_loading_legacy_files_moves_global_order_into_plan(monkeypatch, tmp_path):
    legacy = ",".join(reversed(DEFAULT))
    plan_path = tmp_path / "plan.json"
    conf_path = tmp_path / "conf.yml"
    plan_path.write_text(
        json.dumps(
            {
                "plan1": {},
                "conf": {},
                "backup_plans": [{"plan": {}, "conf": {}}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "plan_path", plan_path)
    monkeypatch.setattr(config, "conf_path", conf_path)
    monkeypatch.setattr(config, "conf", config.Conf(dorm_order=legacy))

    config.load_plan()

    assert config.conf.dorm_order == ""
    assert config.plan.conf.dorm_order == legacy
    assert config.plan.backup_plans[0].conf.dorm_order == legacy
    saved_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert saved_plan["conf"]["dorm_order"] == legacy
    assert saved_plan["backup_plans"][0]["conf"]["dorm_order"] == legacy


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
