"""Regression: experimental backup plans may replace individual trailing Free slots.

The normal/default dorm plan must still keep its Free slots contiguous and
all merged plans must retain at least one Free per dorm.
"""

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402


def make_plan(*, experimental=True, base=None, changes=None):
    default = base or ["闪灵", "波登可", "Free", "Free", "Free"]
    modified = changes or {4: "星源"}
    config = PlanConfig("", "", "", experimental_dorm_logic=experimental)
    base_plan = Plan({"dormitory_1": [Room(name, "", []) for name in default]}, config)
    overlay = [Room(modified.get(i, "Current"), "", []) for i in range(5)]
    backup = Plan({"dormitory_1": overlay}, config, name="dynamic Free slot")
    return Operators({"default_plan": base_plan, "backup_plans": [backup]})


def test_experimental_backup_may_replace_trailing_free_without_moving_earlier_slots():
    data = make_plan()
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) is None
    assert [d.position for d in data.dorm] == [("dormitory_1", 2), ("dormitory_1", 3)]


def test_default_plan_still_requires_contiguous_free():
    data = make_plan(base=["闪灵", "波登可", "Free", "Free", "星源"])
    assert data.init_and_validate() == "Free必须连续且安排在宿管后"


def test_backup_still_requires_at_least_one_free():
    data = make_plan(changes={2: "星源", 3: "流明", 4: "炎客"})
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) == "宿舍必须安排至少一个Free"


def test_stable_mode_switch_uses_unchanged_legacy_rules():
    data = make_plan(experimental=False)
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) is None
