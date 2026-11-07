"""救急续行保留依赖，释放完成后继续，不按固定间隔重做。"""

import copy
import pickle
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.emergency import RESUME_META
from arknights_mower.tests import mass_mood_recovery_tests
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.emergency_observation_budget_tests import (
    observation_solver as observation_solver,
)
from arknights_mower.tests.emergency_observation_budget_tests import set_release_window
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)

legacy_solver = mass_mood_recovery_tests.solver


def test_observation_retains_original_deadline_and_waits_for_release(
    observation_solver,
):
    case, solver = observation_solver, observation_solver.solver
    release = set_release_window(case, 120)
    original_next_read = case.state["next_read"]

    solver._emergency_tick()

    assert case.state["next_read"] == original_next_read
    assert release in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
    continuation = next(task for task in solver.tasks if task.meta_data == RESUME_META)
    assert continuation.execution_failure["dependency"]
    original_time = continuation.time
    unread = copy.deepcopy(case.state["pending_read_rooms"])
    for _ in range(4):
        case.clock["now"] += timedelta(minutes=2)
        solver._emergency_tick()
        assert continuation.time == original_time
        assert case.state["pending_read_rooms"] == unread
        assert continuation not in task_view(
            solver.tasks, TaskScope.DISPATCH, solver.op_data
        )
    assert case.reads == case.rooms[:1]
    solver._emergency_update_targets.assert_not_called()


def test_continuation_survives_save_and_resumes_on_completed_prerequisite(
    observation_solver,
):
    case, solver = observation_solver, observation_solver.solver
    release = set_release_window(case, 120)
    solver._emergency_tick()
    original_reads = list(case.reads)
    state, tasks = pickle.loads(pickle.dumps((case.state, solver.tasks)))
    solver.emergency_state, solver.tasks = state, tasks
    solver._emergency_tick()
    assert case.reads == original_reads
    restored_release = next(task for task in tasks if task.strict_mood_limit)
    solver.tasks.remove(restored_release)
    solver._emergency_replan_releases = MagicMock()
    solver._emergency_operation_fits = MagicMock(return_value=True)

    solver._emergency_tick(completed_task=restored_release)

    assert case.reads == case.rooms
    assert "pending_read_rooms" not in state
    assert release.time == restored_release.time


def test_pending_staffing_does_not_push_read_deadline(observation_solver):
    case, solver = observation_solver, observation_solver.solver
    case.state["phase"] = "recovering"
    case.state["staffing_complete"] = True
    original = case.state["next_read"]
    task = SchedulerTask(case.clock["now"], {"room_1_1": ["伊内丝"]})
    task.emergency_staffing = True
    solver.tasks = [task]

    for _ in range(3):
        solver._emergency_tick()

    assert case.state["next_read"] == original
    assert task in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
    assert case.reads == []


def test_normal_wakeup_observes_only_the_existing_failure_once(observation_solver):
    case, solver = observation_solver, observation_solver.solver
    solver._emergency_defer_read()
    checkpoint = solver._emergency_continuation_checkpoint()
    continuation = next(task for task in solver.tasks if task.meta_data == RESUME_META)
    original_time = continuation.time
    unrelated = SchedulerTask(case.clock["now"], task_type=TaskTypes.CLUE)
    solver.tasks.append(unrelated)
    for _ in range(3):
        solver._resume_failed_tasks()
        solver._emergency_tick(completed_task=unrelated)
    assert case.reads == []
    assert unrelated in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)

    solver._request_emergency_continuation_observation(checkpoint)
    solver._emergency_tick()

    assert case.reads == case.rooms
    assert continuation.time == original_time
    current = solver._emergency_continuation_checkpoint()
    assert current is not None and current is not checkpoint
    solver._request_emergency_continuation_observation(checkpoint)
    solver._emergency_tick()
    assert case.reads == case.rooms


def test_related_completion_does_not_release_other_failed_tasks(observation_solver):
    case, solver = observation_solver, observation_solver.solver
    release = set_release_window(case, 120)
    unrelated = SchedulerTask(case.clock["now"], task_type=TaskTypes.CLUE)
    solver.tasks.append(unrelated)
    solver._retain_failed_task(unrelated, "其他任务仍未取得新观测", [])
    failure = copy.deepcopy(unrelated.execution_failure)
    solver._emergency_tick()
    solver.tasks.remove(release)
    solver._emergency_replan_releases = MagicMock()
    solver._emergency_operation_fits = MagicMock(return_value=True)

    solver._emergency_tick(completed_task=release)

    assert case.reads == case.rooms
    assert unrelated.execution_failure == failure


@pytest.mark.parametrize("seconds, allow_wakeup", [(2, True), (0, True), (2, False)])
def test_real_idle_wait_supplies_only_normal_positive_wait_observation(
    observation_solver, monkeypatch, seconds, allow_wakeup
):
    case, solver = observation_solver, observation_solver.solver
    solver._emergency_defer_read()
    solver.recog = SimpleNamespace(reset_after_external_control=MagicMock())
    monkeypatch.setattr(base_schedule, "refresh_resource_at_boundary", lambda: None)

    def advance(seconds):
        case.clock["now"] += timedelta(seconds=seconds)

    monkeypatch.setattr(base_schedule, "csleep", advance)
    solver._idle_sleep(seconds, allow_wakeup=allow_wakeup)
    solver._emergency_tick()

    assert case.reads == (case.rooms if seconds > 0 and allow_wakeup else [])
    solver._emergency_tick()
    assert case.reads == (case.rooms if seconds > 0 and allow_wakeup else [])


@pytest.mark.parametrize("new_failure", [False, True])
def test_reset_failure_preserves_the_original_wakeup_permission(
    observation_solver, monkeypatch, new_failure
):
    case, solver = observation_solver, observation_solver.solver
    solver._emergency_defer_read()
    solver.recog = SimpleNamespace(
        reset_after_external_control=MagicMock(
            side_effect=ConnectionError("画面未复位")
        )
    )
    monkeypatch.setattr(base_schedule, "refresh_resource_at_boundary", lambda: None)
    monkeypatch.setattr(
        base_schedule,
        "csleep",
        lambda seconds: case.clock.update(
            now=case.clock["now"] + timedelta(seconds=seconds)
        ),
    )
    with pytest.raises(ConnectionError, match="画面未复位"):
        solver._idle_sleep(2)
    solver._emergency_tick()
    assert not case.reads
    if new_failure:
        solver._emergency_defer_read()
    solver.recog.reset_after_external_control.side_effect = None
    solver._complete_idle_observation()
    solver._emergency_tick()
    assert case.reads == ([] if new_failure else case.rooms)


def test_initialization_dependency_allows_independent_real_dispatch(
    observation_solver,
):
    case, solver = observation_solver, observation_solver.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver._read_agent_mood = MagicMock(return_value=False)
    solver._emergency_startup()
    solver._read_agent_mood.reset_mock()
    independent = SchedulerTask(case.clock["now"], task_type=TaskTypes.CLUE)
    solver.tasks.insert(0, independent)
    solver.task = independent
    solver.find = MagicMock(return_value=(1, 1))
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.handle_error = MagicMock(return_value=True)
    solver._run_clue_flow = MagicMock()
    solver.skip = MagicMock()

    solver.infra_main()

    solver._read_agent_mood.assert_not_called()
    solver._run_clue_flow.assert_called_once()
    assert independent not in solver.tasks
    assert solver._emergency_startup_pending


def test_cancelled_idle_wait_does_not_supply_emergency_observation(
    observation_solver, monkeypatch
):
    case, solver = observation_solver, observation_solver.solver
    solver._emergency_defer_read()
    checkpoint = solver._emergency_continuation_checkpoint()
    solver.recog = SimpleNamespace(reset_after_external_control=MagicMock())
    monkeypatch.setattr(base_schedule, "refresh_resource_at_boundary", lambda: None)

    def stop_wait(seconds):
        raise MowerExit

    monkeypatch.setattr(base_schedule, "csleep", stop_wait)
    with pytest.raises(MowerExit):
        solver._idle_sleep(2)
    assert not solver.sleeping
    assert "_idle_emergency_checkpoint" not in solver.__dict__
    assert solver._emergency_continuation_checkpoint() is checkpoint
    solver.recog.reset_after_external_control.assert_not_called()
    solver._complete_idle_observation()
    solver._emergency_tick()
    assert case.reads == []


def test_lost_mood_timestamp_does_not_reopen_continuation(observation_solver):
    case, solver = observation_solver, observation_solver.solver
    solver._emergency_defer_read()
    for op in solver.op_data.operators.values():
        op.time_stamp = None
        op.mood_is_prediction = True
    for _ in range(3):
        solver._emergency_tick()
    assert case.reads == []
