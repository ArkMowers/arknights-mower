"""Shared swaps release their own sources; real conflicts wait for group returns."""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import (
    GroupShiftBlocked,
    ProductSwitchDeferred,
)
from arknights_mower.tests.multi_group_shift_tests import SHARED, A, B
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.mark.parametrize("dorm_first", [False, True])
@pytest.mark.parametrize("available", [False, True])
@pytest.mark.parametrize("full_cycle", [False, True])
def test_shared_primary_can_move_to_fixed_dorm_in_same_arrangement(
    solver, dorm_first, available, full_cycle
):
    slots = solver.global_plan["default_plan"].plan
    slots["dormitory_1"][0] = Room(
        "塑心",
        "甲",
        [SHARED],
        group_bindings=[{"group": "乙", "replacement": ["夜刀"]}],
    )
    assert solver.initialize_operators() is None
    data = solver.op_data
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    data.operators[A].mood = 5
    if dorm_first:
        data.operators = dict(reversed(list(data.operators.items())))
    if not available:
        data.operators["红"]._current_room = "factory"
        data.operators["红"].current_index = 0
    before = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["陈", "Current"],
            "dormitory_1": ["Current", "Current", A, "Current", "Current"],
        },
    )
    original = deepcopy(task.plan)
    solver.task, solver.tasks = task, [task]
    if available:
        if full_cycle:
            solver._prepare_group_shift(task)
            solver._prepare_shift_cycle(task)
        solver._prepare_group_shift(task, remember_targets=True)
        assert task.plan["contact"] == ["红"]
        assert task.plan["dormitory_1"][0] == SHARED
        assert task.group_shift_expected["contact", 0] == "红"
        assert task.group_shift_expected["dormitory_1", 0] == SHARED
        projected = data.project_arrangements([task.plan])
        assert projected.get_current_operator("contact", 0).name == "红"
        assert projected.get_current_operator("dormitory_1", 0).name == SHARED
        assert not projected.is_auto_free_dorm_slot("dormitory_1", 0)
    else:
        with pytest.raises(ProductSwitchDeferred):
            solver._prepare_group_shift(task)
        assert task.plan == original
    assert before == {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    assert not data.group_is_resting("甲")


@pytest.fixture
def conflicting_groups(solver):
    slots = solver.global_plan["default_plan"].plan
    slots["factory"] = [Room("梅尔", "丙", ["砾"])]
    slots["contact"][0].group_bindings = [
        {"group": "乙", "replacement": ["红"]},
        {"group": "丙", "replacement": ["黑角"]},
    ]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
    solver.op_data.commit_group_shifts({"甲": True, "乙": True, "丙": False})
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={"factory": ["砾"]})
    solver.task, solver.tasks = task, [task]
    return solver


@pytest.mark.parametrize("reverse", [False, True])
def test_conflict_is_suspended_until_both_groups_confirm_return(
    conflicting_groups, reverse
):
    s = conflicting_groups
    blocked = s.task
    first = SchedulerTask(
        time=datetime.now() - timedelta(hours=2),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"]},
    )
    last = SchedulerTask(
        time=datetime.now() - timedelta(hours=1),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["Current", B]},
    )
    s.tasks += [last, first] if reverse else [first, last]
    before = deepcopy(blocked.plan), blocked.time
    with pytest.raises(GroupShiftBlocked) as error:
        s._prepare_group_shift(blocked)
    assert error.value.groups == {"甲", "乙"}
    s._suspend_group_shift(blocked, error.value.groups)
    assert blocked not in s.tasks
    assert s.waiting_group_shifts == [blocked]
    assert first in s.tasks and last in s.tasks
    s._resume_waiting_group_shifts()
    assert (blocked.plan, blocked.time) == before
    # Passing both forecast times does not release the suspended task.
    first.group_shift_transitions = {"甲": False}
    first.group_shift_expected = {("meeting", 0): A}
    assert s._complete_group_shift(first)
    assert s.waiting_group_shifts == [blocked]
    last.group_shift_transitions = {"乙": False}
    last.group_shift_expected = {("meeting", 1): B}
    s.op_data.operators[B]._current_room = ""
    assert not s._complete_group_shift(last)
    assert blocked not in s.tasks
    s.op_data.operators[B]._current_room = "meeting"
    assert s._complete_group_shift(last)
    assert not s.waiting_group_shifts
    assert blocked in s.tasks
    assert blocked.plan["contact"] == ["黑角"]
    assert not hasattr(blocked, "group_shift_waiting")
    s._resume_waiting_group_shifts()
    assert sum(t is blocked for t in s.tasks) == 1
    assert s.op_data.group_shift_state == {"甲": False, "乙": False, "丙": False}


def test_suspension_without_return_deadline_has_no_timer(conflicting_groups):
    s = conflicting_groups
    blocked = s.task
    original_time = blocked.time
    with pytest.raises(GroupShiftBlocked) as error:
        s._prepare_group_shift(blocked)
    s._suspend_group_shift(blocked, error.value.groups)
    s._resume_waiting_group_shifts()
    s._resume_waiting_group_shifts()
    assert not s.tasks
    assert s.waiting_group_shifts == [blocked]
    assert blocked.time == original_time


def test_return_alone_does_not_release_an_unavailable_cover(conflicting_groups):
    s = conflicting_groups
    blocked = s.task
    s._suspend_group_shift(blocked, {"甲", "乙"})
    s.op_data.commit_group_shifts({"甲": False, "乙": False})
    s.op_data.operators["黑角"]._current_room = "room_1_1"
    s.op_data.operators["黑角"].current_index = 0
    s._resume_waiting_group_shifts()
    assert s.waiting_group_shifts == [blocked]
    assert not s.tasks
    s.op_data.operators["黑角"]._current_room = ""
    s._resume_waiting_group_shifts()
    assert not s.waiting_group_shifts
    assert s.tasks == [blocked]


def test_waiting_shift_survives_snapshot_and_queue_rebuild(
    conflicting_groups, monkeypatch
):
    import pickle

    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state
    from arknights_mower.utils.scheduler_task import dorm_task_reservations

    s = conflicting_groups
    blocked = s.task
    s._suspend_group_shift(blocked, {"甲", "乙"})
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(s, attr, None)
    monkeypatch.setattr(main, "base_scheduler", s)
    snapshot = pickle.loads(pickle.dumps(current_state()))
    assert snapshot["tasks"] == []
    restored = snapshot["waiting_group_shifts"][0]
    assert restored.plan == blocked.plan
    assert restored.group_shift_waiting == {"甲", "乙"}
    s.waiting_group_shifts = snapshot["waiting_group_shifts"]
    s.tasks = snapshot["tasks"]
    assert dorm_task_reservations(s.op_data, s.tasks) == (set(), set())
    s.plan_metadata()
    assert s.waiting_group_shifts == [restored]
    assert restored not in s.tasks
    s.op_data.commit_group_shifts({"甲": False, "乙": False})
    s._resume_waiting_group_shifts()
    assert restored in s.tasks


def test_dispatch_parks_conflict_without_timed_retry(conflicting_groups, monkeypatch):
    from arknights_mower.solvers import base_schedule

    s = conflicting_groups
    blocked, original_time = s.task, s.task.time
    s.find = MagicMock(return_value=(1, 1))
    s.refresh_connecting = False
    s.agent_arrange = MagicMock()
    s.skip = MagicMock()
    monkeypatch.setattr(
        base_schedule, "protect_priority_tasks", lambda tasks, **kwargs: None
    )
    s.infra_main()
    s.agent_arrange.assert_not_called()
    assert blocked not in s.tasks
    assert s.waiting_group_shifts == [blocked]
    assert blocked.time == original_time


@pytest.mark.parametrize("guard", ["_initial_mood_read_pending", "_emergency_frozen"])
def test_resume_requires_current_normal_observation(
    conflicting_groups, guard, monkeypatch
):
    s = conflicting_groups
    task = s.task
    s._suspend_group_shift(task, {"甲", "乙"})
    s.op_data.commit_group_shifts({"甲": False, "乙": False})
    monkeypatch.setattr(s, guard, lambda: True)
    s._resume_waiting_group_shifts()
    assert s.waiting_group_shifts == [task]
    assert task not in s.tasks


def test_shared_follower_retains_cover_for_other_resting_group(solver):
    data = solver.op_data
    data.operators[B]._current_room = "dormitory_1"
    data.operators[B].current_index = 2
    data.operators[SHARED]._current_room = ""
    data.operators[SHARED].current_index = -1
    data.operators["黑角"]._current_room = "contact"
    data.operators["黑角"].current_index = 0
    data.commit_group_shifts({"甲": True, "乙": True})
    plan = solver._observed_group_return_plan()
    assert plan == {"meeting": [A, "Current"]}
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=plan)
    solver.tasks, solver.task = [task], task
    solver._prepare_group_shift(task)
    assert task.group_shift_transitions == {"甲": False}
    assert SHARED not in task.plan.get("contact", [])
    assert data.group_shift_state == {"甲": True, "乙": True}
    assert data.get_current_operator("contact", 0).name == "黑角"
