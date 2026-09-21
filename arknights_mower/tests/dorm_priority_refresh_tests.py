"""宿舍床位顺序随主副排班独立保存并在切换时刷新。"""

import copy
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.config.plan import migrate_legacy_dorm_order
from arknights_mower.utils.operators import Dormitory, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import rebalance_plan_swap_dorms


@pytest.fixture
def saved(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(experimental_dorm_logic=True))
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
                PlanConfig(
                    "",
                    "",
                    "",
                    dorm_order=dorm_order,
                    experimental_dorm_logic=True,
                ),
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig(
                        "",
                        "",
                        "",
                        dorm_order=order,
                        experimental_dorm_logic=True,
                    ),
                )
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
ROOM_DEFAULT = ["dormitory_1", "dormitory_2", "dormitory_3", "dormitory_4"]


def bed_order(room_order):
    return [bed for room in room_order for bed in DEFAULT if bed.startswith(room + "_")]


def test_experimental_dorm_logic_defaults_off():
    assert config.Conf().experimental_dorm_logic is False


def test_stable_logic_uses_global_order_and_ignores_backup_order(saved):
    global_order = list(reversed(DEFAULT))
    backup_order = DEFAULT[1:] + DEFAULT[:1]
    config.conf.experimental_dorm_logic = False
    config.conf.dorm_order = ",".join(global_order)
    op = operators(",".join(DEFAULT), [",".join(backup_order)])
    op.global_plan["default_plan"].config.experimental_dorm_logic = False
    op.global_plan["backup_plans"][0].config.experimental_dorm_logic = False
    op.config.experimental_dorm_logic = False

    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == global_order
    assert op.swap_plan([True], refresh=True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == global_order


@pytest.mark.parametrize(
    "old",
    [
        "dormitory_2_4,dormitory_1_2,dormitory_2_2,dormitory_1_4,"
        "dormitory_1_3,dormitory_2_3",
        "dormitory_2_4",
    ],
)
def test_old_or_incomplete_bed_order_is_folded_to_rooms(saved, old):
    op = operators(old)
    assert op.init_and_validate() is None
    expected_rooms = ["dormitory_2", "dormitory_1", "dormitory_3", "dormitory_4"]
    assert op.config.dorm_order == expected_rooms
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        expected_rooms
    )
    saved.assert_not_called()


def test_empty_order_uses_default_room_order(saved):
    op = operators()
    assert op.init_and_validate() is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        ROOM_DEFAULT
    )
    assert op.config.dorm_order == ROOM_DEFAULT
    saved.assert_not_called()


def test_old_manual_bed_order_preserves_first_room_occurrence(saved):
    order = list(reversed(DEFAULT))
    op = operators(",".join(order))
    assert op.init_and_validate() is None
    rooms = ["dormitory_2", "dormitory_1", "dormitory_3", "dormitory_4"]
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(rooms)
    saved.assert_not_called()


def test_backup_plan_applies_its_own_dorm_order(saved):
    op = operators(",".join(DEFAULT))
    op.global_plan["backup_plans"] = [
        Plan(
            {},
            PlanConfig(
                "",
                "",
                "",
                dorm_order=",".join(reversed(DEFAULT)),
                experimental_dorm_logic=True,
            ),
        )
    ]
    op.backup_plans = op.global_plan["backup_plans"]

    assert op.swap_plan([True], refresh=True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        ["dormitory_2", "dormitory_1"]
    )
    assert op.swap_plan([False], refresh=True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        ROOM_DEFAULT
    )


def test_backup_order_only_change_generates_physical_reorder(saved):
    op = operators("", ["dormitory_2,dormitory_1,dormitory_3,dormitory_4"])
    assert op.init_and_validate() is None
    first, second = op.dorm[:2]
    first.name = "至简"
    second.name = "蜜莓"
    for bed in (first, second):
        agent = op.operators[bed.name]
        agent.current_room, agent.current_index = bed.position
        agent.mood = 12
        agent.time_stamp = datetime(2026, 9, 22, 10)
    previous = copy.deepcopy(op.dorm)

    assert op.swap_plan([True], refresh=True) is None
    plan = rebalance_plan_swap_dorms(op, previous)

    assert plan["dormitory_2"][2:4] == ["至简", "蜜莓"]
    assert [bed.name for bed in op.dorm[:2]] == ["至简", "蜜莓"]


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
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        ROOM_DEFAULT
    )
    assert (op.dorm[0].name, op.dorm[0].time) == ("冰酿", first_time)
    assert (op.dorm[-1].name, op.dorm[-1].time) == ("流明", last_time)
    assert all(dorm.position[0] != "dormitory_3" for dorm in op.dorm)
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
    main_rooms = ["dormitory_2", "dormitory_1", "dormitory_3", "dormitory_4"]
    backup_rooms = ["dormitory_2", "dormitory_1", "dormitory_3", "dormitory_4"]
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        main_rooms
    )

    assert op.swap_plan([True], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        backup_rooms
    )

    assert op.swap_plan([False], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        main_rooms
    )


def test_empty_backup_order_explicitly_restores_default(saved):
    op = operators(",".join(reversed(DEFAULT)), [""])
    assert op.init_and_validate() is None
    assert op.swap_plan([True], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        ROOM_DEFAULT
    )


def test_last_active_backup_order_wins(saved):
    first = DEFAULT[1:] + DEFAULT[:1]
    second = DEFAULT[2:] + DEFAULT[:2]
    op = operators("", [",".join(first), ",".join(second)])
    assert op.init_and_validate() is None
    assert op.swap_plan([True, True], True) is None
    assert [f"{d.position[0]}_{d.position[1]}" for d in op.dorm] == bed_order(
        ["dormitory_1", "dormitory_2", "dormitory_3", "dormitory_4"]
    )


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
    migrated = "dormitory_2,dormitory_1,dormitory_3,dormitory_4"
    assert plan.conf.dorm_order == migrated
    assert plan.backup_plans[0].conf.dorm_order == migrated
    assert plan.backup_plans[1].conf.dorm_order == ",".join(ROOM_DEFAULT)


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
    monkeypatch.setattr(config, "conf", config.Conf(experimental_dorm_logic=True))
    monkeypatch.setattr(config, "_legacy_dorm_order", legacy)

    config.load_plan()

    assert config._legacy_dorm_order == legacy
    migrated = "dormitory_2,dormitory_1,dormitory_3,dormitory_4"
    assert config.plan.conf.dorm_order == migrated
    assert config.plan.backup_plans[0].conf.dorm_order == migrated
    saved_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert saved_plan["conf"]["dorm_order"] == migrated
    assert saved_plan["backup_plans"][0]["conf"]["dorm_order"] == migrated


def test_plan_save_persists_plan_dorm_order(saved, monkeypatch):
    import server

    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "save_plan", MagicMock())
    client = server.app.test_client()
    payload = config.plan.model_dump(mode="json", exclude_none=True)
    payload["conf"]["dorm_order"] = ",".join(reversed(DEFAULT))
    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert config.plan.conf.dorm_order == ",".join(reversed(DEFAULT))
    saved.assert_not_called()
    payload["conf"]["ling_xi"] = 2
    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert config.plan.conf.dorm_order == ",".join(reversed(DEFAULT))
    saved.assert_not_called()


def test_failed_plan_save_restores_plan_dorm_order(monkeypatch, tmp_path):
    import server

    original_plan = config.PlanModel()
    monkeypatch.setattr(config, "plan", original_plan)
    monkeypatch.setattr(config, "conf", config.Conf())
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
    payload["conf"]["dorm_order"] = ",".join(reversed(DEFAULT))

    response = client.post("/plan", json=payload)
    assert response.status_code == 500
    assert config.plan is original_plan
    assert config.plan.conf.dorm_order == ""

    response = client.post("/plan", json=payload)
    assert response.status_code == 200
    assert config.plan.conf.ling_xi == 2
    assert config.plan.conf.dorm_order == ",".join(reversed(DEFAULT))
