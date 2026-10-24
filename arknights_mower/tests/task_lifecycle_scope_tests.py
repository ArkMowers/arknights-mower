"""任务保留跨派发、重规划、预约及持久化的生产入口回归。"""

import copy
import pickle
from datetime import timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests.emergency_group_return_tests import (
    group_return as group_return,
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.mass_mood_recovery_tests import NOW, PRIMARY
from arknights_mower.tests.scheduler_recovery_preservation_tests import (
    scheduler as scheduler,
)
from arknights_mower.tests.scheduler_wakeup_tests import primary_with_vacancies
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture(params=[False, True], ids=["paused", "reopened"])
def reopened(request):
    return request.param


@pytest.fixture(params=[False, True], ids=["memory", "restored"])
def restored(request):
    return request.param


def retain(solver, task, reopened, restored):
    solver.tasks.append(task)
    solver._retain_failed_task(task, "换人结果未确认", task.plan or ["dormitory_1"])
    if reopened:
        for room in task.execution_failure["rooms"]:
            solver.op_data.room_observations[room] = (
                solver.op_data.room_observations.get(room, 0) + 1
            )
        solver._resume_failed_tasks()
        assert not getattr(task, "execution_failure", None)
    if restored:
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
        task = solver.tasks[-1]
    solver.task = None
    return task


def assert_preserved(solver, task, original):
    assert any(pending is task for pending in solver.tasks)
    assert (task.time, task.plan, task.meta_data) == original
    assert task.retains_execution


def snapshot(task):
    return copy.deepcopy((task.time, task.plan, task.meta_data))


def test_failed_fill_survives_primary_preflight(
    scheduler, monkeypatch, reopened, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    fill = SchedulerTask(
        scheduler.clock.now(),
        {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]},
        TaskTypes.FILL_DORM,
    )
    solver.tasks.append(fill)
    solver.task = fill
    solver.agent_arrange = Mock(side_effect=RuntimeError("识别失败"))
    monkeypatch.setattr(scheduler.module, "save_exception", Mock())
    solver.infra_main()
    assert fill.execution_failure
    if reopened:
        solver.op_data.room_observations["dormitory_1"] = 1
        solver._resume_failed_tasks()
    if restored:
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
        fill = next(t for t in solver.tasks if t.type == TaskTypes.FILL_DORM)
    original = snapshot(fill)
    for _ in range(3):
        solver._fill_empty_dorms()
        assert_preserved(solver, fill, original)
    assert solver.agent_arrange.call_count == 1


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.FIAMMETTA,
        TaskTypes.NOT_SPECIFIC,
        TaskTypes.SHIFT_OFF,
        TaskTypes.SHIFT_ON,
        TaskTypes.EXHAUST_OFF,
        TaskTypes.FILL_DORM,
        TaskTypes.RE_ORDER,
        TaskTypes.SELF_CORRECTION,
    ],
)
@pytest.mark.parametrize("target", ["陈", "Free"])
def test_paused_arrangement_allows_unrelated_primary_rest(
    scheduler, monkeypatch, kind, restored, target
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    solver.op_data.add(Operator("菲亚梅塔", ""))
    failed = retain(
        solver,
        SchedulerTask(
            scheduler.clock.now(),
            {"dormitory_1": ["Current", "Current", target, "Current", "Current"]},
            kind,
            meta_data="陈",
        ),
        False,
        restored,
    )
    original = snapshot(failed)
    solver._fill_empty_dorms()
    assert any(
        t.type == TaskTypes.SHIFT_OFF and t.plan.get("meeting") == ["红"]
        for t in solver.tasks
    )
    assert_preserved(solver, failed, original)
    assert all(
        t is failed or t.plan.get("dormitory_1", [])[2:3] in ([], ["Current"])
        for t in solver.tasks
    )


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.SHIFT_OFF,
        TaskTypes.SHIFT_ON,
        TaskTypes.SELF_CORRECTION,
        TaskTypes.RE_ORDER,
        TaskTypes.FILL_DORM,
        TaskTypes.NOT_SPECIFIC,
    ],
)
def test_backup_coalescing_preserves_retained_work_and_independent_changes(
    scheduler, monkeypatch, reopened, restored, kind
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(
            scheduler.clock.now(),
            {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]},
            kind,
        ),
        reopened,
        restored,
    )
    original = snapshot(task)
    transition = {
        "dormitory_1": ["Current", "Current", "Free", "Current", "Current"],
        "meeting": ["红"],
    }
    source = copy.deepcopy(transition)
    for _ in range(3):
        merged, consumed = solver._coalesce_backup_transition(transition)
        assert merged == {"meeting": ["红"]}
        assert not consumed
        assert transition == source
        assert_preserved(solver, task, original)


@pytest.mark.parametrize("ready", [None, -1, 60])
def test_charging_refresh_preserves_retained_task(
    scheduler, monkeypatch, reopened, restored, ready
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.FIAMMETTA),
        reopened,
        restored,
    )
    original = snapshot(task)
    ready_at = (
        None if ready is None else scheduler.clock.now() + timedelta(minutes=ready)
    )
    for _ in range(3):
        solver._refresh_fiammetta_task(ready_at)
        assert_preserved(solver, task, original)


def test_staffing_callback_preserves_retained_return(
    scheduler, monkeypatch, reopened, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(scheduler.clock.now(), {"meeting": ["银灰"]}, TaskTypes.SHIFT_ON),
        reopened,
        restored,
    )
    original = snapshot(task)
    solver._cancel_pending_shift_on("银灰")
    assert_preserved(solver, task, original)


@pytest.mark.parametrize("minutes", [1, 30])
def test_order_time_refresh_preserves_retained_task(
    scheduler, monkeypatch, reopened, restored, minutes
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(
            scheduler.clock.now() + timedelta(minutes=minutes),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="meeting",
        ),
        reopened,
        restored,
    )
    original = snapshot(task)
    solver.refresh_run_order_time("meeting")
    assert_preserved(solver, task, original)
    assert len(solver.tasks) == 2


def test_reopened_execution_does_not_rebuild_its_remaining_plan(
    scheduler, monkeypatch, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(scheduler.clock.now(), {"meeting": ["红"]}, TaskTypes.SHIFT_OFF),
        True,
        restored,
    )
    original = snapshot(task)
    solver._prepare_shift_cycle(task)
    assert_preserved(solver, task, original)
    assert len(solver.tasks) == 2


def test_reopened_charging_still_precedes_primary_rest(
    scheduler, monkeypatch, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.FIAMMETTA),
        True,
        restored,
    )
    original = snapshot(task)
    solver._plan_primary_recovery()
    assert len(solver.tasks) == 2
    assert_preserved(solver, task, original)


@pytest.mark.parametrize("reopened", [False, True])
def test_rescue_observation_deferral_preserves_retained_release(
    scheduler, monkeypatch, reopened, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(
            scheduler.clock.now(),
            {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
            TaskTypes.RELEASE_DORM,
            meta_data="陈",
        ),
        reopened,
        restored,
    )
    task.emergency_recovery_release = True
    original = snapshot(task)
    solver.emergency_state = {"phase": "recovering"}
    solver._emergency_save = Mock()
    solver._emergency_defer_read()
    assert_preserved(solver, task, original)
    assert sum(pending.meta_data == "自动救急继续安排" for pending in solver.tasks) == 1


def test_rescue_unrelated_planning_retains_failed_release(
    scheduler, monkeypatch, reopened, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(
            scheduler.clock.now(),
            {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
            TaskTypes.RELEASE_DORM,
            meta_data="陈",
        ),
        reopened,
        restored,
    )
    task.emergency_recovery_release = True
    original = snapshot(task)
    solver.emergency_state = {
        "phase": "recovering",
        "targets": {},
        "next_read": scheduler.clock.now() + timedelta(hours=2),
    }
    for name in (
        "_emergency_save",
        "_emergency_sync_reservations",
        "_emergency_update_targets",
        "_emergency_release_ready",
        "_open_emergency_beds",
    ):
        setattr(solver, name, Mock())
    solver._emergency_reconcile_staffing = Mock(return_value=True)
    solver._emergency_schedule_staffing = Mock(return_value=True)
    solver._emergency_ready = Mock(return_value=False)
    solver._emergency_observe_recovery = Mock(return_value=True)
    monkeypatch.setattr(scheduler.module, "try_workshop_tasks", Mock())
    from arknights_mower.solvers import emergency

    monkeypatch.setattr(emergency, "datetime", scheduler.clock)
    monkeypatch.setattr(emergency, "try_workshop_tasks", Mock())
    solver._emergency_tick()
    assert_preserved(solver, task, original)
    if not reopened:
        solver._emergency_observe_recovery.assert_not_called()


def test_rescue_departures_respect_retained_resources_and_release_independent_primary(
    group_return, reopened, restored
):
    solver = group_return.solver
    first = solver.op_data.operators[PRIMARY[0]]
    row = ["Current"] * len(solver.op_data.plan[first.current_room])
    row[first.current_index] = first.name
    task = retain(
        solver,
        SchedulerTask(NOW, {first.current_room: row}, TaskTypes.FILL_DORM),
        reopened,
        restored,
    )
    task.emergency_dorm = True
    original = snapshot(task)
    independent = solver.op_data.operators[PRIMARY[2]]
    independent.mood = solver.emergency_state["targets"][independent.name]
    assert solver._emergency_release_ready()
    assert_preserved(solver, task, original)
    assert solver.op_data.operators[first.name].is_resting()
    assert not solver.op_data.operators[independent.name].current_room


def test_paused_partial_group_does_not_block_independent_arrangement(
    scheduler, monkeypatch, restored
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    task = retain(
        solver,
        SchedulerTask(
            scheduler.clock.now(),
            {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]},
            TaskTypes.SHIFT_OFF,
        ),
        False,
        restored,
    )
    task.group_shift_expected = {("dormitory_1", 2): "陈"}
    original = snapshot(task)
    independent = SchedulerTask(
        scheduler.clock.now(), {"meeting": ["红"]}, TaskTypes.SHIFT_OFF
    )
    solver.tasks.append(independent)
    solver._prepare_group_shift(independent)
    assert independent.plan == {"meeting": ["红"]}
    assert_preserved(solver, task, original)
