"""单 Free 宿舍离宿触发一次跨宿舍单回分配。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import dorm_release_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.operators import Dormitory
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    prioritize_new_dorm_recovery,
    try_reorder,
)

ROOM = dorm_release_tests.ROOM
OTHER = "dormitory_2"
op_data = dorm_release_tests.op_data


@pytest.fixture
def residents(op_data):
    data = op_data
    data.plan[OTHER] = [
        Room(name, "", []) for name in ["安赛尔", "嘉维尔", "Free", "Free", "Free"]
    ]
    for name, tier, mood, position in (
        ("银灰", RestingTier.MAIN, 24, (ROOM, 4)),
        ("夕", RestingTier.REPLACEMENT, 2, (OTHER, 2)),
        ("苍苔", RestingTier.PRIORITY_REPLACEMENT, 20, (OTHER, 3)),
        ("空爆", RestingTier.IDLE, 5, (OTHER, 4)),
    ):
        op = set_tier(data, name, tier, mood)
        op.current_room, op.current_index = position
    data.dorm = [
        Dormitory((ROOM, 4), "银灰"),
        Dormitory((OTHER, 2), "夕"),
        Dormitory((OTHER, 3), "苍苔"),
        Dormitory((OTHER, 4), "空爆"),
    ]
    data.global_plan["default_plan"].plan = copy.deepcopy(data.plan)
    data.global_plan["default_plan"].config = data.config
    return data


def test_single_free_departure_promotes_existing_priority_replacement(residents):
    data = residents
    plan = {"meeting": ["银灰"]}
    before = copy.deepcopy(data.operators), copy.deepcopy(data.dorm)
    result = prioritize_new_dorm_recovery(data, plan)
    assert result == {
        "meeting": ["银灰"],
        ROOM: ["Current"] * 4 + ["苍苔"],
        OTHER: ["Current"] * 3 + ["Free", "Current"],
    }
    assert plan == {"meeting": ["银灰"]}
    assert [repr(op) for op in data.operators.values()] == [
        repr(op) for op in before[0].values()
    ]
    assert [(bed.name, bed.time) for bed in data.dorm] == [
        (bed.name, bed.time) for bed in before[1]
    ]
    projected = data.project_arrangements([result])
    assert prioritize_new_dorm_recovery(projected, {}) == {}
    assert try_reorder(projected, {}) == {}


def test_try_reorder_detects_departure_without_new_admission(residents):
    result = try_reorder(residents, {"meeting": ["银灰"]})
    assert result[ROOM][-1] == "苍苔"
    assert "银灰" not in {name for row in result.values() for name in row}


def test_single_free_departure_ranks_all_rooms_and_recovery_gaps(residents):
    data = residents
    third = "dormitory_3"
    data.plan[third] = [Room("Free", "", []), Room("Free", "", [])]
    first = set_tier(data, "陈", RestingTier.PRIORITY_REPLACEMENT, 10)
    first.current_room, first.current_index = third, 1
    data.dorm += [Dormitory((third, 0)), Dormitory((third, 1), "陈")]
    result = prioritize_new_dorm_recovery(data, {"meeting": ["银灰"]})
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(ROOM, 4).name == "陈"
    assert projected.get_current_operator(OTHER, 2).name == "苍苔"
    assert projected.get_current_operator(third, 0).name == "夕"
    assert {bed.name for bed in projected.dorm if bed.name} == {
        "陈",
        "苍苔",
        "夕",
        "空爆",
    }


def test_concurrent_ordinary_arrival_does_not_take_vacated_single_free(residents):
    data = residents
    set_tier(data, "红", RestingTier.REPLACEMENT, 1)
    result = prioritize_new_dorm_recovery(
        data, {"meeting": ["银灰"], ROOM: ["Current"] * 4 + ["红"]}
    )
    assert result[ROOM][-1] == "苍苔"
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(OTHER, 2).name == "红"
    assert projected.get_current_operator(OTHER, 3).name == "夕"


@pytest.mark.parametrize("lock", ["queued", "product", "protected", "returning"])
def test_departure_preserves_reserved_or_protected_donor(residents, lock):
    data = residents
    slots, names = set(), set()
    if lock == "queued":
        slots.add((OTHER, 3))
    elif lock == "product":
        data.reserved_product_beds[(OTHER, 3)] = "苍苔"
    elif lock == "protected":
        data.config.free_room_exclusions = ["苍苔"]
    else:
        names.add("苍苔")
    result = prioritize_new_dorm_recovery(
        data, {"meeting": ["银灰"]}, slots, reserved_names=names
    )
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(OTHER, 3).name == "苍苔"


def test_multi_free_departure_keeps_existing_residents(residents):
    data = residents
    data.plan[ROOM][3] = Room("Free", "", [])
    data.dorm.insert(1, Dormitory((ROOM, 3)))
    plan = {"meeting": ["银灰"]}
    assert prioritize_new_dorm_recovery(data, plan) == plan


@pytest.fixture
def solver(residents, monkeypatch):
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = residents
    instance.tasks = []
    instance.task = None
    instance._initial_mood_read_pending = MagicMock(return_value=False)
    instance._prepare_shift_backup = MagicMock()
    instance.resting = MagicMock(return_value={})
    instance.agent_get_mood = MagicMock(return_value={})
    monkeypatch.setattr(base, "try_add_release_dorm", lambda *args, **kwargs: None)
    return instance


def test_shift_convergence_keeps_cross_room_reallocation(solver):
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": ["银灰"]})
    before = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    solver._prepare_shift_cycle(task)
    assert task.plan[ROOM][-1] == "苍苔"
    assert [(bed.name, bed.time) for bed in solver.op_data.dorm] == before


@pytest.mark.parametrize("completed", [True, False])
def test_release_reallocation_requires_completed_room(solver, completed):
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 4 + ["Free"]},
        meta_data="银灰",
        strict_mood_limit=True,
    )
    solver.op_data.config.operator_mood_limits = {"银灰": {"upper": 24}}
    solver.task = task
    solver.agent_arrange = MagicMock(return_value=None if completed else False)
    solver.arrange_release_dorm()
    assert len(solver.tasks) == int(completed)
    if completed:
        assert solver.tasks[0].type == TaskTypes.RE_ORDER
        assert solver.tasks[0].plan[ROOM][-1] == "苍苔"


def test_cancelled_release_does_not_reallocate(solver):
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 4 + ["Free"]},
        meta_data="夕",
    )
    solver.task = task
    solver.agent_arrange = MagicMock()
    solver.arrange_release_dorm()
    assert solver.tasks == []


def test_partial_release_queues_only_confirmed_single_free_event(solver):
    third = "dormitory_3"
    data = solver.op_data
    data.plan[third] = [Room("Free", "", [])]
    op = set_tier(data, "红", RestingTier.REPLACEMENT, 24)
    op.current_room, op.current_index = third, 0
    data.dorm.append(Dormitory((third, 0), "红"))
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 4 + ["Free"], third: ["Free"]},
        meta_data="银灰,红",
    )
    task.release_targets = {"银灰": (ROOM, 4), "红": (third, 0)}
    solver.task = task

    def arrange(plan, get_time):
        del plan[ROOM]
        return False

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.arrange_release_dorm()
    assert task.plan == {third: ["Free"]}
    assert len(solver.tasks) == 1
    assert solver.tasks[0].plan[ROOM][-1] == "苍苔"
    assert third not in solver.tasks[0].plan


def test_existing_future_return_does_not_block_recovery_migration(solver):
    data = solver.op_data
    op = set_tier(data, "苍苔", RestingTier.MAIN, 10)
    op.room, op.index = "room_1_1", 0
    data.plan["meeting"][0].replacement.remove(op.name)
    data.plan[op.room] = [Room("苍苔", "", ["红"])]
    data.global_plan["default_plan"].plan = copy.deepcopy(data.plan)
    solver.tasks.append(
        SchedulerTask(
            time=datetime.now() + timedelta(hours=2),
            task_type=TaskTypes.SHIFT_ON,
            task_plan={op.room: [op.name]},
            meta_data="dorm2",
        )
    )
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": ["银灰"]})
    solver._prepare_shift_cycle(task)
    assert task.plan[ROOM][-1] == "苍苔"


def test_urgent_shift_boundary_retains_single_free_event(solver):
    solver.tasks.append(SchedulerTask(task_type=TaskTypes.RUN_ORDER))
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": ["银灰"]})
    solver._prepare_shift_cycle(task)
    assert task.plan[ROOM][-1] == "苍苔"
    solver.resting.assert_not_called()


def test_completed_resident_does_not_win_recovery_over_unfinished(residents):
    data = residents
    data.operators["苍苔"].mood = 24
    result = prioritize_new_dorm_recovery(data, {"meeting": ["银灰"]})
    assert result[ROOM][-1] == "夕"


def test_mood_changes_without_departure_keep_all_positions(residents):
    data = residents
    data.operators["苍苔"].mood = 1
    assert prioritize_new_dorm_recovery(data, {}) == {}
    assert try_reorder(data, {}) == {}
