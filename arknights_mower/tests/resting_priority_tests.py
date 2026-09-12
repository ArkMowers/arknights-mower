"""统一休息层级、绝对心情排序及严格跨级接管矩阵。"""

import pickle
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_release_tests
from arknights_mower.utils import config
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import (
    RestingTier,
    resting_key,
    resting_tier,
)
from arknights_mower.utils.scheduler_task import try_reorder

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data


def set_tier(data, name, tier, mood=10):
    if name not in data.operators:
        data.add(Operator(name, ""))
    op = data.operators[name]
    op.mood = mood
    op.time_stamp = datetime.now()
    op.operator_type = "high" if tier <= RestingTier.STANDBY else "low"
    op.resting_priority = {
        RestingTier.LOW_MAIN: "low",
        RestingTier.STANDBY: "standby",
    }.get(tier, "high" if op.is_high() else "low")
    if tier == RestingTier.PRIORITY:
        data.config.ope_resting_priority.append(name)
    if tier == RestingTier.REPLACEMENT:
        data.plan["meeting"][0].replacement.append(name)
    if tier == RestingTier.STANDBY:
        op.room = "meeting"
        op.group = "候补组"
    return op


@pytest.mark.parametrize("incoming", list(RestingTier)[:6])
@pytest.mark.parametrize("occupant", list(RestingTier)[:6])
@pytest.mark.parametrize("mood", [22, 22.01])
def test_cross_tier_takeover_matrix(op_data, incoming, occupant, mood):
    data = op_data
    request = set_tier(data, "银灰", incoming, mood)
    current = set_tier(data, "空爆", occupant, 3)
    current.current_room, current.current_index = ROOM, 4
    data.dorm[0].time = datetime.now() + timedelta(hours=4)
    expected = incoming <= RestingTier.LOW_MAIN and incoming < occupant
    if incoming == RestingTier.STANDBY and occupant == RestingTier.REPLACEMENT:
        expected = True
    if (
        incoming in (RestingTier.STANDBY, RestingTier.REPLACEMENT)
        and occupant == RestingTier.IDLE
    ):
        expected = mood <= 22
    assert (
        data._find_dorm_slot(request.name, set(), group_resting=True) is not None
    ) == expected


def test_unknown_mood_cannot_evict_idle_occupant_as_replacement(op_data):
    op_data.dorm[0].time = datetime.now() + timedelta(hours=1)
    op_data.operators["空爆"].mood = 3
    op_data.operators["红"].time_stamp = None
    assert op_data.assign_dorm("红") is None


def test_unexecuted_bed_reservation_is_not_preempted(op_data):
    op_data.dorm[0].name = "红"
    op_data.dorm[0].time = None
    op_data.operators["红"].current_room = ""
    assert op_data.assign_dorm("银灰") is None


def test_blacklist_and_zero_mood_work_are_excluded_but_actual_zero_mood_is_not(op_data):
    op_data.config.free_blacklist = ["银灰"]
    op_data.config.ope_resting_priority = ["银灰"]
    assert resting_tier(op_data, "银灰") == RestingTier.EXCLUDED
    assert op_data.assign_dorm("银灰") is None
    op_data.operators["红"].workaholic = True
    assert op_data.assign_dorm("红") is None
    op_data.operators["红"].workaholic = False
    op_data.operators["红"].mood = 0
    assert op_data.assign_dorm("红") is not None


def test_same_tier_uses_absolute_mood_not_lower_limit_or_priority_list_order(op_data):
    set_tier(op_data, "银灰", RestingTier.PRIORITY, 15)
    set_tier(op_data, "红", RestingTier.PRIORITY, 10)
    op_data.operators["银灰"].lower_limit = 12
    assert sorted(["银灰", "红"], key=lambda n: resting_key(op_data, n)) == [
        "红",
        "银灰",
    ]
    op_data.operators["红"].time_stamp = None
    assert sorted(["红", "银灰"], key=lambda n: resting_key(op_data, n)) == [
        "银灰",
        "红",
    ]


def test_dorm_reorder_uses_same_mood_order_and_settles(op_data):
    set_tier(op_data, "陈", RestingTier.REPLACEMENT, 3)
    op_data.plan[ROOM][3] = Room("Free", "", [])
    op_data.dorm = [Dormitory((ROOM, 3), "红"), Dormitory((ROOM, 4), "陈")]
    for bed in op_data.dorm:
        op = op_data.operators[bed.name]
        op.current_room, op.current_index = bed.position
    plan = try_reorder(op_data, {})
    assert plan[ROOM][3:] == ["陈", "红"]
    for index, name in enumerate(plan[ROOM]):
        if name != "Current":
            op_data.operators[name].current_index = index
    for bed in op_data.dorm:
        bed.name = plan[ROOM][bed.position[1]]
    assert try_reorder(op_data, {}) == {}


def test_train_support_keeps_replacement_tier_during_recovery_and_restart(op_data):
    op = op_data.operators["空爆"]
    op_data.update_detail(op.name, 8, "train", 0, True)
    assert resting_tier(op_data, op.name) == RestingTier.REPLACEMENT
    op_data.update_detail(op.name, 8, ROOM, 4, True)
    assert resting_tier(op_data, op.name) == RestingTier.REPLACEMENT
    restored = pickle.loads(pickle.dumps(op))
    op_data.shadow_copy = {op.name: restored}
    op_data.add(Operator(op.name, ""))
    assert resting_tier(op_data, op.name) == RestingTier.REPLACEMENT
    op_data.update_detail(op.name, 24, ROOM, 4, True)
    assert resting_tier(op_data, op.name) == RestingTier.IDLE


def test_workshop_switch_can_lower_planned_replacement_but_explicit_priority_wins(
    op_data,
):
    config.conf.fodder_operators = ["红"]
    assert resting_tier(op_data, "红") == RestingTier.IDLE
    config.conf.workshop_low_priority_rest = False
    assert resting_tier(op_data, "红") == RestingTier.REPLACEMENT
    config.conf.workshop_low_priority_rest = True
    op_data.config.ope_resting_priority = ["红"]
    assert resting_tier(op_data, "红") == RestingTier.PRIORITY


def test_explicit_priority_replacement_is_protected_from_equal_or_lower_tiers(op_data):
    op_data.dorm[0].name = "红"
    op_data.dorm[0].time = datetime.now() + timedelta(hours=2)
    op_data.operators["红"].current_room, op_data.operators["红"].current_index = (
        ROOM,
        4,
    )
    op_data.config.ope_resting_priority = ["红"]
    assert op_data.assign_dorm("银灰") is None
    op_data.config.ope_resting_priority.append("银灰")
    assert op_data.assign_dorm("银灰") is None
