"""救急主表完整下发与部分失败后的续排。"""

import pickle
from datetime import timedelta

import pytest

from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def staffing(recovery_fixture, monkeypatch):  # noqa: F811
    episode, solver = recovery_fixture, recovery_fixture.solver
    data = solver.op_data
    original = {data.operators[name].room: [name] for name in PRIMARY}
    original.update(
        {
            "dormitory_1": ["塑心", "冰酿", "", "", ""],
            "dormitory_2": ["闪灵", "白面鸮", "", "", ""],
        }
    )
    solver.op_data = data.project_arrangements([original])
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        op.mood = 8
        solver.op_data.plan[op.room][0].facility = "制造站"
    episode.state["phase"] = "staffing"
    episode.state["staffing_complete"] = False
    episode.state["rescue_plan"] = {
        data.operators[name].room: [COVERS[index]] for index, name in enumerate(PRIMARY)
    }
    return episode


def staffing_task(solver):
    return next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )


def test_all_workrooms_precede_dorm_tasks(staffing):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    assert task.plan == staffing.state["rescue_plan"]
    assert all(not room.startswith("dorm") for room in task.plan)
    assert set(task.emergency_staffing_members) == set(PRIMARY)
    assert staffing.saves[0]["state"]["staffing_plan"] == task.plan
    solver.backup_plan_solver.assert_not_called()


def test_restart_only_requeues_outstanding_rooms(staffing):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    first = staffing_task(solver)
    room = next(iter(first.plan))
    solver.op_data = solver.op_data.project_arrangements([{room: first.plan[room]}])
    solver.emergency_state = pickle.loads(pickle.dumps(staffing.state))
    solver.tasks.clear()
    assert solver._emergency_schedule_staffing()
    assert room not in staffing_task(solver).plan
    assert len(staffing_task(solver).plan) == 3


def test_finished_manual_workers_keep_working_after_mood_drops(staffing):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    solver.op_data = solver.op_data.project_arrangements([staffing_task(solver).plan])
    solver.tasks.clear()
    assert solver._emergency_reconcile_staffing()
    for name in COVERS:
        solver.op_data.operators[name].mood = 0
    assert solver._emergency_schedule_staffing()
    assert not solver.tasks


@pytest.mark.parametrize("mood", [None, 0, 8])
def test_low_or_unknown_worker_does_not_produce_partial_roster(staffing, mood):
    solver = staffing.solver
    op = solver.op_data.operators[COVERS[-1]]
    op.mood = mood if mood is not None else 24
    op.time_stamp = NOW if mood is not None else None
    solver.op_data.dorm_mood_estimates.clear()
    assert not solver._emergency_schedule_staffing()
    assert not solver.tasks
    assert not staffing.state.get("staffing_plan")


def test_near_strict_release_defers_whole_work_roster(staffing):
    solver = staffing.solver
    task = SchedulerTask(
        time=NOW + timedelta(seconds=50),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
    )
    task.strict_mood_limit = True
    solver.tasks.append(task)
    assert not solver._emergency_schedule_staffing()
    assert solver.tasks == [task]


def test_specialized_compensation_precedes_rescue_staffing(staffing):
    solver = staffing.solver
    room = next(iter(staffing.state["rescue_plan"]))
    task = SchedulerTask(task_plan={room: [COVERS[0]]})
    task.emergency_original_roster = {room: [PRIMARY[0]]}
    solver.tasks.append(task)
    assert not solver._emergency_schedule_staffing()
    assert solver.tasks == [task]
