"""候补和多绑组成员的个人恢复事件不产生绑组上下班。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import group_resting_capacity_tests, mass_mood_recovery_tests
from arknights_mower.utils.operators import Dormitory
from arknights_mower.utils.resting_correction import correct_group_dorms
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import (
    TaskTypes,
    plan_metadata,
    rebalance_closing_dorm_slots,
    rebalance_plan_swap_dorms,
)

solver = mass_mood_recovery_tests.solver
standby_solver = group_resting_capacity_tests.solver


def prepare_follower(solver, role, mood):
    data = solver.op_data
    anchor, follower = mass_mood_recovery_tests.PRIMARY[:2]
    data.groups["轮休"] = [anchor, follower]
    for name in (anchor, follower):
        data.operators[name].group = "轮休"
    op = data.operators[follower]
    if role == "shared":
        op.group_bindings = [
            {"group": "轮休", "replacement": op.replacement.copy()},
            {"group": "其他", "replacement": op.replacement.copy()},
        ]
    else:
        data.config.resting_standby = [follower]
        op.resting_priority = "standby"
    op.mood, op.time_stamp = (
        (24, None) if mood is None else (mood, mass_mood_recovery_tests.NOW)
    )
    data.group_shift_state = {"轮休": True, "其他": False}
    return data, data.operators[anchor], op


@pytest.mark.parametrize("role", ["standby", "shared"])
@pytest.mark.parametrize("returning", [False, True])
def test_follower_workplace_arrangement_does_not_change_group_state(
    solver, role, returning
):
    data, _, follower = prepare_follower(solver, role, 0)
    plan = {follower.room: [follower.name if returning else follower.replacement[0]]}
    assert data.arrangement_group_transitions(plan) == {}


@pytest.mark.parametrize("role", ["standby", "shared"])
def test_legacy_state_and_group_mood_ignore_follower(solver, role):
    data, anchor, follower = prepare_follower(solver, role, 0)
    anchor.mood = 10
    follower._current_room, follower.current_index = data.dorm[0].position
    data.group_shift_state = {}
    assert not data.group_is_resting("轮休")
    assert data.group_min_mood("轮休") == data.group_max_mood("轮休") == 10


@pytest.mark.parametrize("role", ["standby", "shared"])
@pytest.mark.parametrize("mood", [0, 12, 24, None])
def test_follower_bed_cannot_supply_group_return_deadline(solver, role, mood):
    data, anchor, follower = prepare_follower(solver, role, mood)
    anchor._current_room, anchor.current_index = "", -1
    anchor.mood = 10
    bed = data.dorm[0]
    follower._current_room, follower.current_index = bed.position
    bed.name, bed.time = (
        follower.name,
        mass_mood_recovery_tests.NOW + timedelta(hours=1),
    )
    tasks = plan_metadata(data, [])
    assert not any(task.type == TaskTypes.SHIFT_ON for task in tasks)
    assert data.group_is_resting("轮休")


def test_standby_mood_cannot_initiate_group_departure(standby_solver):
    instance = standby_solver
    data = instance.op_data
    for op in instance.total_agent:
        op.mood, op.time_stamp = 24, datetime.now()
    candidate = data.operators[group_resting_capacity_tests.DEEP[1]]
    candidate.mood = 0

    assert instance.resting() == {}
    assert resting_tier(data, candidate.name) == RestingTier.STANDBY


@pytest.mark.parametrize("anchor_room", ["dormitory_1", ""])
@pytest.mark.parametrize("candidate_room", ["meeting", "contact"])
def test_standby_position_does_not_recall_resting_anchor(
    standby_solver, anchor_room, candidate_room
):
    instance = standby_solver
    data = instance.op_data
    anchor = data.operators[group_resting_capacity_tests.DEEP[0]]
    candidate = data.operators[group_resting_capacity_tests.DEEP[1]]
    bed = data.dorm[0]
    anchor._current_room, anchor.current_index = (
        bed.position if anchor_room else ("", -1)
    )
    cover = data.operators[anchor.replacement[0]]
    cover._current_room, cover.current_index = anchor.room, anchor.index
    if anchor_room:
        bed.name, bed.time = anchor.name, datetime.now() + timedelta(hours=3)
    else:
        anchor.mood = 24
    candidate._current_room = candidate_room
    data.group_shift_state = {"深海": True}
    plan = instance.agent_get_mood(read_rooms=False, return_plan=True)
    assert not any(anchor.name in row for row in plan.values())
    assert data.group_is_resting("深海")


def test_shared_active_binding_does_not_restart_normal_return_window(solver):
    data, anchor, follower = prepare_follower(solver, "shared", 12)
    for bed, op in zip(data.dorm, (anchor, follower)):
        op._current_room, op.current_index = bed.position
        op.mood = 10
        bed.name, bed.time = op.name, mass_mood_recovery_tests.NOW + timedelta(hours=3)
    tasks = plan_metadata(data, [])
    first = next(task for task in tasks if task.type == TaskTypes.SHIFT_ON)
    window = first.return_windows[anchor.name]
    data.select_group_binding(follower.name, "其他")
    tasks = plan_metadata(data, tasks)
    second = next(task for task in tasks if task.type == TaskTypes.SHIFT_ON)
    assert second.return_windows[anchor.name] == window


def test_individual_standby_return_does_not_block_normal_group_departure(
    standby_solver,
):
    instance = standby_solver
    candidate = group_resting_capacity_tests.DEEP[1]
    plan = instance.resting(returning={candidate})
    assert plan["central"] == [group_resting_capacity_tests.COVERS[0]]


def test_low_mood_standby_keeps_priority_after_group_departure(standby_solver):
    instance = standby_solver
    data = instance.op_data
    candidate = data.operators[group_resting_capacity_tests.DEEP[1]]
    data.update_detail(candidate.name, 0, candidate.room, candidate.index)
    assert resting_tier(data, candidate.name) == RestingTier.STANDBY
    plan = {}
    assert instance.get_resting_plan(data.groups["深海"], [], plan, 0)
    assert resting_tier(data, candidate.name) == RestingTier.STANDBY
    assert candidate.name in {bed.name for bed in data.all_dorms()}
    assert (
        data.arrangement_group_transitions(
            {candidate.room: [candidate.name, "Current"]}
        )
        == {}
    )


def test_low_mood_standby_does_not_require_bed_before_group_departure(standby_solver):
    instance = standby_solver
    group_resting_capacity_tests.occupy_beds(instance, "high")
    data = instance.op_data
    candidate = data.operators[group_resting_capacity_tests.DEEP[1]]
    candidate.mood, candidate.time_stamp = 0, datetime.now()
    before = [(bed.name, bed.time) for bed in data.dorm]
    plan = {}
    assert instance.get_resting_plan(data.groups["深海"], [], plan, 0)
    assert candidate.name not in {bed.name for bed in data.dorm}
    assert [(bed.name, bed.time) for bed in data.dorm][1:] == before[1:]
    assert data.dorm[0].name == group_resting_capacity_tests.DEEP[0]


@pytest.mark.parametrize("role", ["standby", "shared"])
@pytest.mark.parametrize("event", ["closing", "backup"])
def test_dropped_follower_during_capacity_rebalance_does_not_recall_group(
    solver, role, event
):
    data, anchor, follower = prepare_follower(solver, role, 12)
    anchor._current_room, anchor.current_index = "", -1
    owner = data.operators["冰酿"]
    owner.group, owner.replacement = "关闭", ["Free"]
    slot = data.plan["dormitory_1"][0]
    slot.group, slot.replacement = "关闭", ["Free"]
    owner._current_room, owner.current_index = "", -1
    bed = Dormitory(("dormitory_1", 0), follower.name)
    follower._current_room, follower.current_index = bed.position
    data.dorm = [bed]
    if event == "closing":
        plan = {"dormitory_1": [owner.name, "Current", "Current", "Current", "Current"]}
        recalled = rebalance_closing_dorm_slots(data, plan, {owner.name})
        assert anchor.name not in recalled and follower.name not in recalled
    else:
        data.dorm = []
        plan = rebalance_plan_swap_dorms(data, previous_dorms=[bed])
    assert not any(room in plan for room in (anchor.room, follower.room))
    assert data.group_is_resting("轮休")


@pytest.mark.parametrize("role", ["standby", "shared"])
def test_individual_follower_correction_keeps_group_dorm_post_off_shift(solver, role):
    data, _, follower = prepare_follower(solver, role, 12)
    owner = data.operators["冰酿"]
    owner.group, owner.replacement = "轮休", ["Free"]
    data.groups["轮休"].append(owner.name)
    data.plan["dormitory_1"][0].group = "轮休"
    data.plan["dormitory_1"][0].replacement = ["Free"]
    owner._current_room, owner.current_index = "", -1
    plan = {follower.room: [follower.name]}
    correct_group_dorms(data, plan, lambda _: False)
    assert plan.get("dormitory_1", ["Current"])[0] != owner.name


@pytest.mark.parametrize("role", ["standby"])
def test_native_recovery_does_not_start_group_for_low_mood_standby(solver, role):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    data, _, follower = prepare_follower(solver, role, 0)
    data.group_shift_state["轮休"] = False
    result = native_opportunity(
        solver, [follower.name], mass_mood_recovery_tests.NOW, current_only=True
    )
    assert result.complete and result.opportunity is None
    assert not data.group_is_resting("轮休")


def test_normal_fixed_primary_still_drives_confirmed_group_transitions(solver):
    data, anchor, _ = prepare_follower(solver, "standby", 0)
    assert data.arrangement_group_transitions({anchor.room: [anchor.name]}) == {
        "轮休": False
    }
    assert data.arrangement_group_transitions(
        {anchor.room: [anchor.replacement[0]]}
    ) == {"轮休": True}
