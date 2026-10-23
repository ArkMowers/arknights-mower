"""换班演算仅使用当前演算排班仍然有效的用尽预约。"""

from copy import deepcopy
from datetime import timedelta

import pytest

from arknights_mower.tests import backup_rest_schedule_tests as backup
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = backup.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


def prepare_return(solver, *, reenter=False):
    if reenter:
        solver.global_plan["default_plan"].plan["meeting"] = [
            Room("能天使", "红松", ["斥罪"])
        ]
        solver.global_plan["backup_plans"][0].trigger = LogicExpression(
            LogicExpression("op_data.operators['黑键'].is_resting()", "==", "True"),
            "or",
            LogicExpression("op_data.operators['能天使'].is_resting()", "==", "True"),
        )
        solver.op_data = Operators(solver.global_plan)
        assert solver.op_data.init_and_validate() is None
        for op in solver.op_data.operators.values():
            op._current_room, op.current_index = (
                (op.room, op.index) if op.is_high() else ("", -1)
            )
            op.mood, op.time_stamp = 24, backup.base.datetime.now()
        solver.op_data = solver.op_data.project_arrangements(
            [{"contact": ["红"], "dormitory_1": ["Current", "Current", "黑键"]}]
        )
        solver.op_data.operators["能天使"].mood = 0
    assert solver.op_data.swap_plan([True], refresh=True) is None
    data = solver.op_data
    data.operators["黑键"].mood = 24
    data.operators["黑键"].time_stamp = backup.base.datetime.now()
    data.operators["歌蕾蒂娅"].mood = 0.5
    data.operators["歌蕾蒂娅"].time_stamp = backup.base.datetime.now()
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"contact": ["黑键"]},
    )
    solver.tasks, solver.task = [task], task
    return task


@pytest.mark.parametrize("minutes", [-1, 30])
@pytest.mark.parametrize("meta_data", ["歌蕾蒂娅", "黑键,歌蕾蒂娅"])
def test_main_plan_projection_ignores_old_backup_exhaust_deadline(
    solver, monkeypatch, minutes, meta_data
):
    task = prepare_return(solver)
    old = SchedulerTask(
        time=backup.base.datetime.now() + timedelta(minutes=minutes),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data=meta_data,
    )
    unaffected = SchedulerTask(
        time=backup.base.datetime.now() + timedelta(hours=2),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="黑键",
    )
    solver.tasks.extend([old, unaffected])
    original = deepcopy(old.__dict__)
    before = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    observations = []
    fill_observations = []
    resting = backup.base.BaseSchedulerSolver.resting
    fill = backup.base.try_add_release_dorm

    def observe(trial, **kwargs):
        if trial.op_data.plan_condition == [False]:
            observations.append(
                [t.meta_data for t in trial.tasks if t.type == TaskTypes.EXHAUST_OFF]
            )
        return resting(trial, **kwargs)

    def observe_fill(plan, time, data, tasks, **kwargs):
        if data.plan_condition == [False]:
            fill_observations.append(
                [t.meta_data for t in tasks if t.type == TaskTypes.EXHAUST_OFF]
            )
        return fill(plan, time, data, tasks, **kwargs)

    monkeypatch.setattr(backup.base.BaseSchedulerSolver, "resting", observe)
    monkeypatch.setattr(backup.base, "try_add_release_dorm", observe_fill)
    for _ in range(2):
        solver._prepare_shift_cycle(task)

    assert observations
    assert all(meta_data not in names for names in observations)
    assert all("黑键" in names for names in observations)
    assert fill_observations
    assert all(meta_data not in names for names in fill_observations)
    assert all("黑键" in names for names in fill_observations)
    projected = solver.op_data.project_arrangements([task.plan])
    assert projected.operators["歌蕾蒂娅"].is_resting()
    assert solver.op_data.plan_condition == [True]
    assert any(pending is old for pending in solver.tasks)
    assert any(pending is unaffected for pending in solver.tasks)
    assert old.__dict__ == original
    assert before == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }

    solver._activate_shift_backup(task)
    assert not any(pending is old for pending in solver.tasks)
    assert any(pending is unaffected for pending in solver.tasks)


def test_old_deadline_stays_out_after_another_group_reenters_backup(
    solver, monkeypatch
):
    task = prepare_return(solver, reenter=True)
    old = SchedulerTask(
        time=backup.base.datetime.now() + timedelta(minutes=30),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="歌蕾蒂娅",
    )
    solver.tasks.append(old)
    observations = []
    resting = backup.base.BaseSchedulerSolver.resting

    def observe(trial, **kwargs):
        observations.append(
            (
                trial.op_data.plan_condition,
                [t.meta_data for t in trial.tasks if t.type == TaskTypes.EXHAUST_OFF],
            )
        )
        return resting(trial, **kwargs)

    monkeypatch.setattr(backup.base.BaseSchedulerSolver, "resting", observe)
    solver._prepare_shift_cycle(task)

    assert observations[0][0] == [False]
    assert observations[-1][0] == [True]
    assert all("歌蕾蒂娅" not in names for _, names in observations)
    projected = solver.op_data.project_arrangements([task.plan])
    assert projected.operators["能天使"].is_resting()
    assert projected.operators["歌蕾蒂娅"].is_working()
    assert any(pending is old for pending in solver.tasks)


@pytest.mark.parametrize("kind", ["concrete", "paused", "reopened"])
def test_projection_preserves_concrete_and_retained_exhaust_work(
    solver, monkeypatch, kind
):
    task = prepare_return(solver)
    old = SchedulerTask(
        time=backup.base.datetime.now() + timedelta(minutes=30),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="歌蕾蒂娅",
    )
    if kind == "concrete":
        old.plan = {"central": ["陈"]}
    elif kind == "paused":
        old.execution_failure = {"reason": "未完成换班"}
    else:
        old.execution_retained = True
    solver.tasks.append(old)
    original = deepcopy(old.__dict__)
    observations = []
    resting = backup.base.BaseSchedulerSolver.resting

    def observe(trial, **kwargs):
        observations.extend(
            deepcopy(pending.__dict__)
            for pending in trial.tasks
            if pending.type == TaskTypes.EXHAUST_OFF
        )
        return resting(trial, **kwargs)

    monkeypatch.setattr(backup.base.BaseSchedulerSolver, "resting", observe)
    solver._prepare_shift_cycle(task)

    assert observations and all(state == original for state in observations)
    assert any(pending is old for pending in solver.tasks)
    assert old.__dict__ == original


def test_failed_projection_preserves_original_exhaust_queue(solver, monkeypatch):
    task = prepare_return(solver)
    old = SchedulerTask(
        time=backup.base.datetime.now() + timedelta(minutes=30),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="歌蕾蒂娅",
    )
    solver.tasks.append(old)
    original = deepcopy(old.__dict__)

    def fail(trial, **kwargs):
        assert trial.op_data.plan_condition == [False]
        assert not any(t.type == TaskTypes.EXHAUST_OFF for t in trial.tasks)
        raise ValueError("中止演算")

    monkeypatch.setattr(backup.base.BaseSchedulerSolver, "resting", fail)
    with pytest.raises(ValueError, match="中止演算"):
        solver._prepare_shift_cycle(task)

    assert len(solver.tasks) == 2
    assert solver.tasks[0] is task
    assert solver.tasks[1] is old
    assert old.__dict__ == original
    assert solver.op_data.plan_condition == [True]
