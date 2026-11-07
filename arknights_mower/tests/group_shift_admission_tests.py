"""换班准入同时保留恢复入住、共享成员跟随和未完成安排。"""

import pickle
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import multi_group_shift_tests as shared
from arknights_mower.tests import shift_backup_convergence_tests as cycle
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    estimate_task_duration,
)

cycle_solver = cycle.solver
shared_solver = shared.solver


@pytest.mark.parametrize("explicit_cover", [False, True])
@pytest.mark.parametrize("urgent", [False, True])
def test_existing_cover_still_requires_primary_recovery(
    cycle_solver, explicit_cover, urgent
):
    s = cycle_solver
    s.op_data.backup_plans, s.op_data.plan_condition = [], []
    owner = s.op_data.operators["野鬃"]
    owner._current_room, owner.current_index = "", -1
    cover = s.op_data.operators["酒神"]
    cover._current_room, cover.current_index = owner.room, owner.index
    plan = {
        "central": ["陈"],
        "dormitory_1": ["Current", "Current", "薇薇安娜", "Current", "Current"],
    }
    if explicit_cover:
        plan[owner.room] = ["酒神", "Current"]
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=plan)
    s.task, s.tasks = task, [task]
    if urgent:
        s.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    s._prepare_group_shift(task)
    s._prepare_shift_cycle(task)
    s._prepare_group_shift(task, remember_targets=True)
    expected = dict(task.group_shift_expected)
    assert any(
        name == owner.name and room.startswith("dorm")
        for (room, _), name in expected.items()
    )
    confirmed = dict(s.op_data.group_shift_state)
    s.op_data = s.op_data.project_arrangements([task.plan])
    s.op_data.group_shift_state = confirmed
    assert s._complete_group_shift(task)
    assert s.op_data.operators[owner.name].is_resting()
    assert s.op_data.group_is_resting("红松")


@pytest.mark.parametrize("restart", [False, True])
def test_retained_return_does_not_reintroduce_completed_rooms(cycle_solver, restart):
    s = cycle_solver
    s.op_data.backup_plans, s.op_data.plan_condition = [], []
    down = cycle.downshift(s)
    s.op_data = s.op_data.project_arrangements([down.plan])
    s.op_data = s.op_data.project_arrangements([{"central": ["薇薇安娜"]}])
    s.op_data.commit_group_shifts({"红松": True})
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"room_1_2": ["野鬃", "灰毫"]}
    )
    task.group_shift_transitions = {"红松": False}
    task.group_shift_expected = {
        ("central", 0): "薇薇安娜",
        ("room_1_2", 0): "野鬃",
        ("room_1_2", 1): "灰毫",
    }
    s.task, s.tasks = task, [task]
    s._retain_failed_task(task, "remaining room failed", ["room_1_2"])
    if restart:
        task = pickle.loads(pickle.dumps(task))
        s.task, s.tasks = task, [task]
    s.op_data.room_observations["room_1_2"] = 1
    s._resume_failed_tasks()
    before = (
        deepcopy(task.plan),
        task.time,
        estimate_task_duration(task, op_data=s.op_data),
    )
    s._prepare_group_shift(task)
    s._prepare_shift_cycle(task)
    s._prepare_group_shift(task, remember_targets=True)
    assert (
        task.plan,
        task.time,
        estimate_task_duration(task, op_data=s.op_data),
    ) == before
    assert task.group_shift_expected[("central", 0)] == "薇薇安娜"
    assert s.op_data.group_is_resting("红松")


@pytest.mark.parametrize("first", ["甲", "乙"])
def test_shared_member_departs_in_same_task_and_returns_after_last_group(
    shared_solver, first
):
    s = shared_solver
    s.check_fia = MagicMock(return_value=(None, None))
    shared_op = s.op_data.operators[shared.SHARED]
    shared_op.group_bindings[1]["replacement"] = ["红"]
    for op in s.op_data.operators.values():
        if not op.is_high():
            op._current_room, op.current_index = "", -1
    second = "乙" if first == "甲" else "甲"
    names = {"甲": (shared.A, "陈", 0), "乙": (shared.B, "初雪", 1)}

    def prepare(group, resting):
        name, cover, index = names[group]
        row = ["Current", "Current"]
        row[index] = cover if resting else name
        task = SchedulerTask(
            task_type=TaskTypes.SHIFT_OFF if resting else TaskTypes.SHIFT_ON,
            task_plan={"meeting": row},
        )
        s.task, s.tasks = task, [task]
        before = task.time
        s._prepare_group_shift(task, remember_targets=True)
        assert task.time == before
        return task

    def complete(task):
        state = dict(s.op_data.group_shift_state)
        s.op_data = s.op_data.project_arrangements([task.plan])
        s.op_data.group_shift_state = state
        assert s._complete_group_shift(task)

    first_off = prepare(first, True)
    assert first_off.plan["contact"] == ["红"]
    assert any(
        shared.SHARED in row
        for room, row in first_off.plan.items()
        if room.startswith("dorm")
    )
    complete(first_off)
    assert s.op_data.operators[shared.SHARED].is_resting()
    complete(prepare(second, True))
    first_return = prepare(first, False)
    assert not any(
        shared.SHARED in row
        for room, row in first_return.plan.items()
        if not room.startswith("dorm")
    )
    complete(first_return)
    assert s.op_data.operators[shared.SHARED].is_resting()
    last_return = prepare(second, False)
    assert last_return.plan["contact"] == [shared.SHARED]
    complete(last_return)
    assert s.op_data.operators[shared.SHARED].current_room == "contact"
    assert not any(s.op_data.group_is_resting(group) for group in (first, second))


@pytest.mark.parametrize("restart", [False, True])
def test_retained_shared_return_still_requires_every_binding_working(
    shared_solver, restart
):
    s = shared_solver
    s.op_data.commit_group_shifts({"甲": True, "乙": True})
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [shared.A, "Current"], "contact": [shared.SHARED]},
    )
    task.group_shift_transitions = {"甲": False}
    s.task, s.tasks = task, [task]
    s._retain_failed_task(task, "return interrupted", list(task.plan))
    if restart:
        task = pickle.loads(pickle.dumps(task))
        s.task, s.tasks = task, [task]
    before = deepcopy(task.plan), task.time
    with pytest.raises(base.GroupShiftBlocked) as blocked:
        s._prepare_group_shift(task)
    assert "乙" in blocked.value.groups
    assert (task.plan, task.time) == before
    s.op_data.commit_group_shifts({"乙": False})
    s._prepare_group_shift(task)
    assert (task.plan, task.time) == before


@pytest.mark.parametrize("restart", [False, True])
def test_retained_dorm_fill_uses_remaining_plan_after_readmission(
    cycle_solver, monkeypatch, restart
):
    from arknights_mower.utils.scheduler_task import try_add_release_dorm

    s = cycle_solver
    try_add_release_dorm({}, None, s.op_data, s.tasks)
    task = next(t for t in s.tasks if hasattr(t, "dorm_fill_plan"))
    s.task = task
    s._retain_failed_task(task, "interrupted before selection", list(task.plan))
    if restart:
        task = pickle.loads(pickle.dumps(task))
        s.task, s.tasks = task, [task]
    s.op_data.room_observations[next(iter(task.plan))] = 1
    s._resume_failed_tasks()
    before = deepcopy(task.plan), task.time
    s._track_idle_dorm_shift = MagicMock()
    s._finish_idle_dorm_shift = MagicMock()
    s.preserve_resting_crafters = MagicMock()

    class SelectedRoom(Exception):
        pass

    s.agent_arrange_room = MagicMock(side_effect=SelectedRoom)
    monkeypatch.setattr(
        base,
        "try_add_release_dorm",
        MagicMock(side_effect=AssertionError("retained work must not replan")),
    )
    with pytest.raises(SelectedRoom):
        s.agent_arrange(task.plan)
    assert (task.plan, task.time) == before
