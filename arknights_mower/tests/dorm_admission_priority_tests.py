"""新入住者竞争单回位，但不会把原入住者踢出宿舍或触发日常反复搬床。"""

import copy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_release_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.operators import Dormitory
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    prioritize_new_dorm_recovery,
    rebalance_plan_swap_dorms,
    try_add_release_dorm,
    try_reorder,
)

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data


@pytest.fixture
def residents(op_data):
    data = op_data
    data.plan[ROOM][3] = Room("Free", "", [])
    incumbent = set_tier(data, "银灰", RestingTier.MAIN, 10)
    incumbent.current_room, incumbent.current_index = ROOM, 3
    incumbent.dorm_recovery_room = ROOM
    data.operators["空爆"].current_room = ""
    data.dorm = [Dormitory((ROOM, 3), "银灰"), Dormitory((ROOM, 4))]
    data.dorm[0].time = datetime.now() + timedelta(hours=2)
    return data


@pytest.mark.parametrize(
    "tier,mood,preempts",
    [
        (RestingTier.PRIORITY, 20, True),
        (RestingTier.MAIN, 1, True),
        (RestingTier.MAIN, 10, False),
        (RestingTier.MAIN, 20, False),
        (RestingTier.LOW_MAIN, 0, False),
    ],
)
def test_newcomer_competes_by_dorm_priority_without_evicting_resident(
    residents, tier, mood, preempts
):
    data = residents
    set_tier(data, "红", tier, mood)
    assert data.assign_dorm_group(["红"]) is not None
    before = copy.deepcopy([(bed.name, bed.time) for bed in data.dorm])
    plan = try_reorder(data, {})
    assert plan[ROOM][3:] == (["红", "银灰"] if preempts else ["Current", "红"])
    assert try_reorder(data, {}) == plan  # 未执行重算也保持确定性
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert data.operators["银灰"].dorm_recovery_room == ROOM
    projected = data.project_arrangements([plan])
    assert {bed.name for bed in projected.dorm} == {"银灰", "红"}
    assert try_reorder(projected, {}) == {}  # 已入住后心情排序不会触发第二次搬床


def test_mood_crossing_without_arrival_does_not_reorder(residents):
    data = residents
    other = set_tier(data, "红", RestingTier.MAIN, 1)
    other.current_room, other.current_index = ROOM, 4
    data.dorm[1].name = other.name
    assert try_reorder(data, {}) == {}


def test_priority_replacement_wins_single_recovery_without_evicting_standby(residents):
    data = residents
    set_tier(data, "银灰", RestingTier.STANDBY, 12)
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 20)
    assert data.assign_dorm_group(["红"]) is not None
    plan = try_reorder(data, {})
    assert plan[ROOM][3:] == ["红", "银灰"]
    projected = data.project_arrangements([plan])
    assert {bed.name for bed in projected.dorm} == {"红", "银灰"}
    assert try_reorder(projected, {}) == {}


def test_departing_single_target_does_not_force_other_sleepers_to_move(residents):
    data = residents
    other = set_tier(data, "红", RestingTier.REPLACEMENT, 1)
    other.current_room, other.current_index = ROOM, 4
    data.dorm[1].name = other.name
    work_plan = {"meeting": ["银灰"]}
    assert prioritize_new_dorm_recovery(data, work_plan) == work_plan
    assert try_reorder(data, work_plan) == {}


@pytest.mark.parametrize("marked_target", [False, True])
def test_backup_reordering_preserves_ordinary_beds_despite_priority_and_mood_changes(
    residents, marked_target
):
    data = residents
    if not marked_target:
        data.operators["银灰"].clear_dorm_recovery()
    other = set_tier(data, "红", RestingTier.REPLACEMENT, 1)
    other.current_room, other.current_index = ROOM, 4
    data.dorm[1].name = other.name
    second = "dormitory_2"
    data.plan[second] = [Room("Free", "", []), Room("Free", "", [])]
    data.dorm += [Dormitory((second, 0), "陈"), Dormitory((second, 1), "空爆")]
    for bed in data.dorm[2:]:
        op = set_tier(data, bed.name, RestingTier.REPLACEMENT, 20)
        op.current_room, op.current_index = bed.position
        bed.time = datetime.now() + timedelta(hours=4)
    before = {bed.position: (bed.name, bed.time) for bed in data.dorm}
    previous = copy.deepcopy(data.dorm)
    data.dorm = data.dorm[2:] + data.dorm[:2]
    data.operators["空爆"].mood = 0
    data.operators["红"].mood = 23
    assert rebalance_plan_swap_dorms(data, previous) == {}
    assert {bed.position: (bed.name, bed.time) for bed in data.dorm} == before


@pytest.mark.parametrize("reverse_rooms", [False, True])
def test_cross_room_newcomer_uses_configured_room_order(residents, reverse_rooms):
    data = residents
    second = "dormitory_2"
    data.plan[second] = [Room("Free", "", []), Room("Free", "", [])]
    other = set_tier(data, "陈", RestingTier.LOW_MAIN, 1)
    other.current_room, other.current_index = second, 0
    other.dorm_recovery_room = second
    data.dorm += [Dormitory((second, 0), "陈"), Dormitory((second, 1))]
    if reverse_rooms:
        data.dorm = data.dorm[2:] + data.dorm[:2]
    set_tier(data, "红", RestingTier.PRIORITY, 20)
    plan = {second: ["Current", "红"]}
    result = prioritize_new_dorm_recovery(data, plan)
    if reverse_rooms:
        assert result == {second: ["红", "陈"]}
    else:
        assert result == {
            ROOM: ["Current", "Current", "Current", "红", "Current"],
            second: ["银灰", "陈"],
        }
    assert plan == {second: ["Current", "红"]}
    projected = data.project_arrangements([result])
    assert {bed.name for bed in projected.dorm if bed.name} == {"银灰", "陈", "红"}


@pytest.mark.parametrize("lock", ["queued", "product", "unexecuted"])
@pytest.mark.parametrize("vacant", [False, True])
def test_locked_room_is_not_used_for_single_recovery_swap(residents, lock, vacant):
    data = residents
    if vacant:
        data.dorm[0].reset()
        data.operators["银灰"].current_room = "meeting"
    set_tier(data, "红", RestingTier.PRIORITY, 1)
    plan = {ROOM: ["Current"] * 4 + ["红"]}
    reserved = set()
    if lock == "queued":
        reserved.add((ROOM, 3))
    elif lock == "product":
        data.reserved_product_beds[(ROOM, 3)] = "银灰"
    else:
        set_tier(data, "陈", RestingTier.MAIN, 1)
        data.dorm[0].name = "陈"
    assert prioritize_new_dorm_recovery(data, plan, reserved) == plan


def test_departing_worker_is_not_brought_back_by_recovery_swap(residents):
    data = residents
    set_tier(data, "红", RestingTier.PRIORITY, 1)
    data.dorm[1].name = "红"
    assert try_reorder(data, {"meeting": ["银灰"]}) == {
        ROOM: ["Current"] * 3 + ["红", "Free"]
    }


@pytest.mark.parametrize("vacant_first", [False, True])
def test_newcomer_recovery_chain_stops_at_empty_vip(residents, vacant_first):
    data = residents
    second, third = "dormitory_2", "dormitory_3"
    for room in (second, third):
        data.plan[room] = [Room("Free", "", []), Room("Free", "", [])]
        data.dorm += [Dormitory((room, 0)), Dormitory((room, 1))]
    if vacant_first:
        data.dorm[0].reset()
        data.operators["银灰"].current_room = "meeting"
    set_tier(data, "红", RestingTier.PRIORITY, 20)
    plan = {third: ["Current", "红"]}

    result = prioritize_new_dorm_recovery(data, plan)

    expected = {
        ROOM: ["Current"] * 3 + ["红", "Current"],
        third: ["Current", "Free"],
    }
    if not vacant_first:
        expected[second] = ["银灰", "Current"]
    assert result == expected
    assert plan == {third: ["Current", "红"]}
    projected = data.project_arrangements([result])
    assert [bed.name for bed in projected.dorm if bed.name] == (
        ["红"] if vacant_first else ["红", "银灰"]
    )
    assert try_reorder(projected, {}) == {}


@pytest.mark.parametrize("reverse_rooms", [False, True])
def test_multiple_arrivals_fill_empty_vips_in_priority_and_room_order(
    residents, reverse_rooms
):
    data = residents
    second, third = "dormitory_2", "dormitory_3"
    data.dorm[0].reset()
    data.operators["银灰"].current_room = "meeting"
    for room in (second, third):
        data.plan[room] = [Room("Free", "", []), Room("Free", "", [])]
        data.dorm += [Dormitory((room, 0)), Dormitory((room, 1))]
    if reverse_rooms:
        data.dorm = data.dorm[2:4] + data.dorm[:2] + data.dorm[4:]
    set_tier(data, "红", RestingTier.PRIORITY, 20)
    set_tier(data, "陈", RestingTier.MAIN, 1)

    result = prioritize_new_dorm_recovery(data, {third: ["陈", "红"]})

    assert result[ROOM][3] == ("陈" if reverse_rooms else "红")
    assert result[second][0] == ("红" if reverse_rooms else "陈")
    assert result[third] == ["Free", "Free"]
    projected = data.project_arrangements([result])
    assert sorted(bed.name for bed in projected.dorm if bed.name) == ["红", "陈"]


def test_inactive_slot_is_not_used_as_empty_vip(residents):
    data = residents
    data.dorm[0].reset()
    data.plan[ROOM][3] = Room("银灰", "", [])
    set_tier(data, "红", RestingTier.PRIORITY, 1)
    plan = {ROOM: ["Current"] * 4 + ["红"]}
    assert prioritize_new_dorm_recovery(data, plan) == plan


def test_idle_filling_uses_same_recovery_allocation(residents):
    data = residents
    set_tier(data, "红", RestingTier.PRIORITY, 20).operator_type = "low"
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert [task.plan for task in tasks] == [
        {ROOM: ["Current", "Current", "Current", "红", "银灰"]}
    ]
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1


def test_idle_filling_preserves_queued_bed(residents):
    data = residents
    set_tier(data, "红", RestingTier.PRIORITY, 20).operator_type = "low"
    tasks = [SchedulerTask(task_plan={ROOM: ["Current"] * 3 + ["银灰", "Current"]})]
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[1].plan == {ROOM: ["Current"] * 4 + ["红"]}


def test_legacy_arrangement_is_unchanged(residents):
    data = residents
    data.config.experimental_dorm_logic = False
    set_tier(data, "红", RestingTier.PRIORITY, 1)
    plan = {ROOM: ["Current"] * 4 + ["红"]}
    assert prioritize_new_dorm_recovery(data, plan) == plan
