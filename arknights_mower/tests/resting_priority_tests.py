"""统一休息层级、距上限差值排序及严格跨级接管矩阵。"""

import pickle
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_release_tests
from arknights_mower.utils import config
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import (
    RestingTier,
    has_resting_mood,
    resting_key,
    resting_mood,
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
    op.operator_type = (
        "high"
        if tier <= RestingTier.STANDBY and tier != RestingTier.PRIORITY_REPLACEMENT
        else "low"
    )
    op.resting_priority = {
        RestingTier.LOW_MAIN: "low",
        RestingTier.STANDBY: "standby",
    }.get(tier, "high" if op.is_high() else "low")
    if tier == RestingTier.PRIORITY:
        data.config.ope_resting_priority.append(name)
    if tier in (RestingTier.PRIORITY_REPLACEMENT, RestingTier.REPLACEMENT):
        data.plan["meeting"][0].replacement.append(name)
    if tier == RestingTier.PRIORITY_REPLACEMENT:
        data.config.resting_priority_replacement.append(name)
    if tier == RestingTier.STANDBY:
        op.room = "meeting"
        op.group = "候补组"
    return op


@pytest.mark.parametrize("incoming", list(RestingTier)[:-1])
@pytest.mark.parametrize("occupant", list(RestingTier)[:-1])
@pytest.mark.parametrize("mood", [22, 22.01, None])
def test_cross_tier_takeover_matrix(op_data, incoming, occupant, mood):
    data = op_data
    request = set_tier(data, "银灰", incoming, 24 if mood is None else mood)
    if mood is None:
        request.time_stamp = None
    current = set_tier(data, "空爆", occupant, 12)
    current.current_room, current.current_index = ROOM, 4
    data.dorm[0].time = datetime.now() + timedelta(hours=4)
    expected = False
    if occupant > RestingTier.LOW_MAIN and incoming < occupant:
        expected = incoming <= RestingTier.PRIORITY_REPLACEMENT
        if incoming == RestingTier.STANDBY and occupant == RestingTier.REPLACEMENT:
            expected = True
        if (
            incoming in (RestingTier.STANDBY, RestingTier.REPLACEMENT)
            and occupant == RestingTier.IDLE
        ):
            expected = mood is not None and mood <= 22
    assert (
        data._find_dorm_slot(request.name, set(), group_resting=True) is not None
    ) == expected


@pytest.mark.parametrize("tier", [RestingTier.STANDBY, RestingTier.REPLACEMENT])
@pytest.mark.parametrize("mood", [-1, 25])
def test_invalid_cached_mood_defaults_full_and_preserves_idle(op_data, tier, mood):
    op_data.dorm[0].time = datetime.now() + timedelta(hours=1)
    op_data.operators["空爆"].mood = 3
    set_tier(op_data, "红", tier, mood)
    assert op_data.assign_dorm("红") is None


def test_free_selection_keeps_idle_bed_with_unknown_replacement(op_data):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    op_data.operators["空爆"].mood = 3
    op_data.operators["红"].mood = 24
    op_data.operators["红"].time_stamp = None
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = op_data
    solver.task = None
    solver.tasks = []
    plan = ["Current"] * 4 + ["Free"]

    solver.preserve_resting_crafters(plan, ROOM)

    assert plan[-1] == "空爆"


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


def test_equal_upper_limit_ignores_lower_limit_and_priority_list_order(op_data):
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


@pytest.mark.parametrize(
    "first,second",
    [
        ((10, 0, 12), (12, 0, 24)),  # 剩 2 与 12 点，不能按原始心情。
        ((5, 0, 10), (12, 0, 20)),  # 剩 5 与 8 点，不能按 50% 与 60%。
        ((5, 0, 12), (13, 12, 24)),  # 剩 7 与 11 点，不比较距下限余量。
    ],
)
def test_same_tier_prefers_larger_recovery_gap(op_data, first, second):
    for name, (mood, lower, upper) in zip(("银灰", "红"), (first, second)):
        op = set_tier(op_data, name, RestingTier.PRIORITY, mood)
        op.lower_limit, op.upper_limit = lower, upper
    assert sorted(["银灰", "红"], key=lambda n: resting_key(op_data, n)) == [
        "红",
        "银灰",
    ]


def test_group_bed_assignment_uses_recovery_gap(op_data):
    short = set_tier(op_data, "银灰", RestingTier.MAIN, 10)
    short.upper_limit = 12
    set_tier(op_data, "红", RestingTier.MAIN, 12)
    op_data.plan[ROOM][3] = Room("Free", "", [])
    op_data.dorm = [Dormitory((ROOM, 3)), Dormitory((ROOM, 4))]
    beds = op_data.assign_dorm_group(["银灰", "红"])
    assert [(bed.name, bed.position) for bed in beds] == [
        ("红", (ROOM, 3)),
        ("银灰", (ROOM, 4)),
    ]


def test_unknown_mood_remains_full_and_priority_still_precedes_gap(op_data):
    first = set_tier(op_data, "银灰", RestingTier.PRIORITY, 1)
    first.upper_limit = 12
    first.time_stamp = None
    set_tier(op_data, "红", RestingTier.PRIORITY, 23)
    assert resting_key(op_data, "红") < resting_key(op_data, "银灰")
    op_data.config.ope_resting_priority.remove("红")
    assert resting_key(op_data, "银灰") < resting_key(op_data, "红")


def test_legacy_resting_key_retains_raw_mood_order(op_data):
    op_data.config.experimental_dorm_logic = False
    first = set_tier(op_data, "银灰", RestingTier.PRIORITY, 10)
    first.upper_limit = 12
    set_tier(op_data, "红", RestingTier.PRIORITY, 12)
    assert resting_key(op_data, "银灰") < resting_key(op_data, "红")


def test_dorm_reorder_keeps_existing_beds_and_only_places_new_resters(op_data):
    set_tier(op_data, "陈", RestingTier.REPLACEMENT, 3)
    op_data.plan[ROOM][3] = Room("Free", "", [])
    op_data.dorm = [Dormitory((ROOM, 3), "红"), Dormitory((ROOM, 4), "陈")]
    for bed in op_data.dorm:
        op = op_data.operators[bed.name]
        op.current_room, op.current_index = bed.position
    assert try_reorder(op_data, {}) == {}

    set_tier(op_data, "空爆", RestingTier.IDLE, 1)
    op_data.plan[ROOM][2] = Room("Free", "", [])
    op_data.dorm.insert(0, Dormitory((ROOM, 2), "空爆"))
    plan = try_reorder(op_data, {})
    assert plan == {ROOM: ["Current", "Current", "空爆", "Current", "Current"]}


def test_dorm_reorder_keeps_active_recovery_target_in_its_room(op_data):
    second_room = "dormitory_2"
    op_data.plan[second_room] = [
        Room(name, "", []) for name in ["杜林", "闪灵", "爱丽丝", "Free"]
    ]
    protected_bed = op_data.dorm[0]
    other_bed = Dormitory((second_room, 3), "陈")
    op_data.dorm.append(other_bed)

    protected = set_tier(op_data, "红", RestingTier.REPLACEMENT, 20)
    other = set_tier(op_data, "陈", RestingTier.REPLACEMENT, 1)
    protected.current_room, protected.current_index = protected_bed.position
    protected.dorm_recovery_room = protected.current_room
    protected.dorm_recovery_index = protected.current_index
    protected_bed.name = protected.name
    other.current_room, other.current_index = other_bed.position

    assert try_reorder(op_data, {}) == {}
    assert protected.dorm_recovery_room == protected.current_room


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


def test_workshop_selection_does_not_override_schedule_identity(op_data):
    config.conf.fodder_operators = ["红"]
    assert resting_tier(op_data, "红") == RestingTier.REPLACEMENT
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


@pytest.mark.parametrize("tier", list(RestingTier)[:-1])
def test_priority_replacement_list_only_promotes_replacement_identity(op_data, tier):
    set_tier(op_data, "陈", tier)
    op_data.config.resting_priority_replacement = ["陈"]
    expected = (
        RestingTier.PRIORITY_REPLACEMENT if tier == RestingTier.REPLACEMENT else tier
    )
    assert resting_tier(op_data, "陈") == expected


def test_priority_replacement_disabled_in_legacy_and_never_overrides_exclusions(
    op_data,
):
    set_tier(op_data, "红", RestingTier.PRIORITY_REPLACEMENT)
    op_data.config.experimental_dorm_logic = False
    assert resting_tier(op_data, "红") == RestingTier.REPLACEMENT
    op_data.config.experimental_dorm_logic = True
    op_data.operators["红"].workaholic = True
    assert resting_tier(op_data, "红") == RestingTier.EXCLUDED
    op_data.operators["红"].workaholic = False
    op_data.config.free_blacklist.append("红")
    assert resting_tier(op_data, "红") == RestingTier.EXCLUDED


def test_fiammetta_targets_are_not_promoted_to_priority_replacements(op_data):
    op_data.add(Operator("陈", ""))
    op_data.config.resting_priority_replacement = ["陈"]
    op_data.plan["dormitory_2"] = [Room("菲亚梅塔", "", ["陈"])]
    assert resting_tier(op_data, "陈") == RestingTier.IDLE


@pytest.mark.parametrize(
    "mood,has_timestamp", [(24, False), (3, False), (-1, True), (25, True)]
)
def test_unknown_mood_defaults_to_twenty_four_without_fabricating_reading(
    mood, has_timestamp
):
    op = Operator(
        "红", "", mood=mood, time_stamp=datetime.now() if has_timestamp else None
    )
    original = (op.mood, op.time_stamp)
    assert resting_mood(op) == 24
    assert not has_resting_mood(op)
    assert (op.mood, op.time_stamp) == original
    op.mood, op.time_stamp = 8, datetime.now()
    assert resting_mood(op) == 8
    assert has_resting_mood(op)
