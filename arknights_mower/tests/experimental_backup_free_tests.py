"""主副表允许宿舍没有 Free，主表已有 Free 仍须连续。"""

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


def test_default_plan_still_requires_contiguous_free():
    data = make_plan(base=["闪灵", "波登可", "Free", "Free", "星源"])
    assert data.init_and_validate() == "Free必须连续且安排在宿管后"


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
