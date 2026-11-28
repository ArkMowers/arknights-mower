"""主副表按实际 Free 槽位提供恢复容量，不限制其数量和排列。"""

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402


def make_plan(*, base=None, changes=None):
    default = base or ["闪灵", "波登可", "Free", "Free", "Free"]
    modified = changes or {4: "星源"}
    config = PlanConfig("", "", "")
    base_plan = Plan({"dormitory_1": [Room(name, "", []) for name in default]}, config)
    overlay = [Room(modified.get(i, "Current"), "", []) for i in range(5)]
    backup = Plan({"dormitory_1": overlay}, config, name="dynamic Free slot")
    return Operators({"default_plan": base_plan, "backup_plans": [backup]})


def test_unified_backup_may_replace_trailing_free_without_moving_earlier_slots():
    data = make_plan()
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) is None
    assert [d.position for d in data.dorm] == [("dormitory_1", 2), ("dormitory_1", 3)]


def test_default_plan_allows_free_before_a_named_resident():
    data = make_plan(base=["闪灵", "波登可", "Free", "Free", "星源"])
    assert data.init_and_validate() is None
    assert [bed.position for bed in data.dorm] == [
        ("dormitory_1", 2),
        ("dormitory_1", 3),
    ]


def test_interleaved_free_positions_survive_backup_switches():
    data = make_plan(base=["Free", "闪灵", "Free", "流明", "Free"], changes={4: "星源"})
    assert data.init_and_validate() is None
    assert [bed.position for bed in data.dorm] == [
        ("dormitory_1", index) for index in (0, 2, 4)
    ]
    assert data.swap_plan([True], refresh=True) is None
    assert [bed.position for bed in data.dorm] == [
        ("dormitory_1", index) for index in (0, 2)
    ]
    assert data.swap_plan([False], refresh=True) is None
    assert [slot.agent for slot in data.plan["dormitory_1"]] == [
        "Free",
        "闪灵",
        "Free",
        "流明",
        "Free",
    ]
    assert [bed.position for bed in data.dorm] == [
        ("dormitory_1", index) for index in (0, 2, 4)
    ]


def test_complete_group_uses_only_interleaved_free_positions():
    workers = ["芬", "香草", "翎羽"]
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [
                        Room(name, "g", [cover])
                        for name, cover in zip(workers, ["红", "黑角", "米格鲁"])
                    ],
                    "dormitory_1": [
                        Room(name, "", [])
                        for name in ["Free", "杜林", "Free", "琴柳", "Free"]
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    for name in workers:
        data.operators[name].mood = 5
    beds = data.assign_dorm_group(workers, active_groups={"g"})
    assert beds is not None
    assert {bed.position for bed in beds} == {
        ("dormitory_1", index) for index in (0, 2, 4)
    }
    assert {bed.name for bed in beds} == set(workers)
    assert [slot.agent for slot in data.plan["dormitory_1"]][1::2] == ["杜林", "琴柳"]
    assert not data.is_dynamic_dorm_position("dormitory_1", 1)
    assert not data.is_dynamic_dorm_position("dormitory_1", 3)


def test_backup_can_replace_every_free_and_restore_the_original_beds():
    data = make_plan(changes={2: "星源", 3: "流明", 4: "炎客"})
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) is None
    assert data.dorm == []
    assert data.swap_plan([False], refresh=True) is None
    assert [d.position for d in data.dorm] == [
        ("dormitory_1", index) for index in (2, 3, 4)
    ]


def test_group_managed_capacity_does_not_require_an_ordinary_free():
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("芬", "g", ["香草"])],
                    "dormitory_1": [
                        Room("杜林", "g", ["Free"]),
                        *[
                            Room(name, "", [])
                            for name in ("闪灵", "波登可", "流明", "炎客")
                        ],
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    assert [bed.position for bed in data.dorm] == [("dormitory_1", 0)]
    assert data.is_effective_free_slot(data.dorm[0], active_groups={"g"})
    data.global_plan["default_plan"].plan["dormitory_1"][0] = Room("杜林", "", [])
    assert "宿舍" in Operators(data.global_plan).init_and_validate()
