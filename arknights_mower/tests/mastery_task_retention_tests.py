"""训练读数失败保留原任务，有限本地复核不依赖普通巡检周期。"""

import pickle
from datetime import timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import mastery_legacy_swap_recovery_tests as legacy
from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.mastery_support_types import TrainingObservationError
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    scheduling,
)

scheduler = recovery.scheduler
handoff = legacy.handoff


@pytest.fixture
def training_dispatch(scheduler, monkeypatch):
    from arknights_mower.solvers import mastery
    from arknights_mower.utils import mastery_db, workshop_automation

    solver = scheduler.solver
    solver.back_to_infrastructure = Mock()
    state = {"id": 17, "status": "training", "swap_frozen": 0}
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda key: dict(state))
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: dict(state))
    monkeypatch.setattr(mastery_db, "get_all_routes", lambda: [])
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: [])
    monkeypatch.setattr(mastery_db, "get_route_settings", lambda: {})
    monkeypatch.setattr(mastery, "_get_plan_route", lambda plan, level: None)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", Mock())
    return solver, mastery, state


@pytest.mark.parametrize("task_type", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
def test_one_failed_observation_recovers_in_same_dispatch(
    scheduler, training_dispatch, monkeypatch, task_type
):
    solver, mastery, _ = training_dispatch
    task = SchedulerTask(scheduler.clock.now(), task_type=task_type)
    task.plan_key = "17"
    solver.tasks, solver.task = [task], task
    action = Mock(side_effect=[TrainingObservationError("读数未确认"), None])
    name = (
        "run_swap_support"
        if task_type == TaskTypes.SWAP_SUPPORT
        else "run_mastery_task"
    )
    monkeypatch.setattr(mastery, name, action)

    solver.infra_main()

    assert action.call_count == 2
    assert solver.tasks == []
    assert not hasattr(task, "execution_failure")
    assert not solver.error
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("task_type", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
@pytest.mark.parametrize("change", ["panel", "room", "plan"])
def test_exhausted_observation_retains_original_until_related_new_evidence(
    scheduler, training_dispatch, monkeypatch, task_type, change
):
    solver, mastery, state = training_dispatch
    now = scheduler.clock.now()
    task = SchedulerTask(now, task_type=task_type)
    task.plan_key = "17"
    later = SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.DEPOT)
    solver.tasks, solver.task = [task, later], task
    action = Mock(side_effect=TrainingObservationError("读数未确认"))
    name = (
        "run_swap_support"
        if task_type == TaskTypes.SWAP_SUPPORT
        else "run_mastery_task"
    )
    monkeypatch.setattr(mastery, name, action)

    solver.infra_main()

    assert action.call_count == 3
    assert solver.tasks[0] is task
    assert task.time == now
    assert task.plan_key == "17"
    assert task.execution_failure["rooms"] == ("train",)
    assert state["swap_frozen"] == 0
    assert find_next_task(solver.tasks) is later
    assert not solver.error
    restored = pickle.loads(pickle.dumps(task))
    assert restored.execution_failure == task.execution_failure
    assert restored.time == now

    for _ in range(3):
        scheduler.clock.current += timedelta(hours=1)
        solver._resume_failed_tasks()
        solver.task = task
        solver.infra_main()
        assert action.call_count == 3
        assert task.time == now
        assert find_next_task(solver.tasks) is later

    # Another facility's successful observation does not release training work.
    solver.op_data.room_observations = {"room_1_1": 1}
    solver._resume_failed_tasks()
    assert task.execution_failure
    if change == "panel":
        solver.last_mastery_observation = scheduler.clock.now()
    elif change == "room":
        solver.op_data.room_observations["train"] = 1
    else:
        state["support_plan"] = "changed arrangement"
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == now
    scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
    assert find_next_task(solver.tasks) is task
    action.side_effect = None
    solver.task = task
    solver.infra_main()
    assert action.call_count == 4
    assert all(queued is not task for queued in solver.tasks)
    scheduler.io.assert_not_called()


def test_mastery_cancellation_does_not_retry_or_consume_task(
    scheduler, training_dispatch, monkeypatch
):
    from arknights_mower.utils.csleep import MowerExit

    solver, mastery, _ = training_dispatch
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SWAP_SUPPORT)
    solver.tasks, solver.task = [task], task
    action = Mock(side_effect=MowerExit())
    monkeypatch.setattr(mastery, "run_swap_support", action)

    with pytest.raises(MowerExit):
        solver.infra_main()

    action.assert_called_once()
    solver.back_to_infrastructure.assert_not_called()
    assert solver.tasks[0] is task
    assert not hasattr(task, "execution_failure")


def test_restart_without_new_training_observation_keeps_failure_paused(
    scheduler, training_dispatch, monkeypatch
):
    solver, mastery, _ = training_dispatch
    now = scheduler.clock.now()
    solver.last_mastery_observation = now
    task = SchedulerTask(now, task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "17"
    solver.tasks, solver.task = [task], task
    action = Mock(side_effect=TrainingObservationError("槽位未确认"))
    monkeypatch.setattr(mastery, "run_swap_support", action)
    solver.infra_main()
    restored = pickle.loads(pickle.dumps(task))
    solver.tasks = [restored]
    del solver.last_mastery_observation

    solver._resume_failed_tasks()

    assert restored.execution_failure
    assert restored.time == now
    solver.last_mastery_observation = now + timedelta(seconds=1)
    solver._resume_failed_tasks()
    assert not hasattr(restored, "execution_failure")
    assert find_next_task(solver.tasks) is restored


def test_retaining_failure_does_not_resolve_unreadable_saved_routes(
    scheduler, training_dispatch, monkeypatch
):
    from arknights_mower.utils.mastery_support import SupportPlanError

    solver, mastery, state = training_dispatch
    state["support_plan"] = "{"
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "17"
    solver.tasks, solver.task = [task], task
    action = Mock(side_effect=TrainingObservationError("协助方案尚未确认"))
    resolver = Mock(side_effect=SupportPlanError("方案暂时不可读"))
    monkeypatch.setattr(mastery, "run_swap_support", action)
    monkeypatch.setattr(mastery, "_get_plan_route", resolver)

    solver.infra_main()
    solver._resume_failed_tasks()

    assert action.call_count == 3
    assert solver.tasks[0] is task
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None
    resolver.assert_not_called()


def test_failed_route_resource_does_not_prevent_task_retention(
    scheduler, training_dispatch, monkeypatch
):
    from arknights_mower.utils import mastery_recommendation

    solver, mastery, _ = training_dispatch
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "17"
    solver.tasks, solver.task = [task], task
    monkeypatch.setattr(
        mastery_recommendation,
        "get_skill_data",
        Mock(side_effect=ValueError("资源暂不可读")),
    )
    monkeypatch.setattr(
        mastery,
        "run_swap_support",
        Mock(side_effect=TrainingObservationError("路线未确认")),
    )

    solver.infra_main()
    solver._resume_failed_tasks()

    assert task.execution_failure
    assert find_next_task(solver.tasks) is None


def test_form_specific_route_update_reopens_training_task(
    scheduler, training_dispatch, monkeypatch
):
    from arknights_mower.utils import mastery_db, mastery_recommendation

    solver, mastery, state = training_dispatch
    state.update(char_id="char_1001_amiya2", char_name="阿米娅")
    routes = {"近卫": {"supports": "saved guard route"}, "术师": {"supports": "other"}}
    monkeypatch.setattr(
        mastery_recommendation,
        "get_skill_data",
        lambda: {"characters": {"char_1001_amiya2": {"profession": "WARRIOR"}}},
    )
    monkeypatch.setattr(mastery_db, "get_route", lambda profession: routes[profession])
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "17"
    solver.tasks, solver.task = [task], task
    monkeypatch.setattr(
        mastery,
        "run_swap_support",
        Mock(side_effect=TrainingObservationError("驻员未确认")),
    )
    solver.infra_main()

    routes["术师"]["supports"] = "unrelated change"
    solver._resume_failed_tasks()
    assert task.execution_failure
    routes["近卫"]["supports"] = "changed selected form route"
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == scheduler.clock.now()


@pytest.mark.parametrize("persistent", [False, True])
def test_real_swap_dispatch_recovers_reading_without_losing_handoff(
    scheduler, handoff, monkeypatch, persistent
):
    from arknights_mower.solvers import mastery
    from arknights_mower.utils import mastery_db

    solver = scheduler.solver
    task = handoff.solver.task
    task.time = scheduler.clock.now()
    original_time = task.time
    for name in ("enter_room", "train_scene", "choose_train", "back", "sleep"):
        setattr(solver, name, getattr(handoff.solver, name))
    solver.back_to_infrastructure = Mock()
    solver.tasks, solver.task = [task], task
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda key: handoff.plan)
    mastery.read_main_panel.side_effect = (
        [None, None, None] if persistent else [None, handoff.panel]
    )

    solver.infra_main()

    if persistent:
        assert solver.tasks[0] is task
        assert task.time == original_time
        assert task.execution_failure
        assert handoff.plan["swap_frozen"] == 0
        solver.choose_train.assert_not_called()
        solver._resume_failed_tasks()
        assert task.execution_failure
        mastery.read_main_panel.side_effect = None
        solver.last_mastery_observation = scheduler.clock.now()
        solver._resume_failed_tasks()
        solver.task = task
        solver.infra_main()
    assert all(queued is not task for queued in solver.tasks)
    solver.choose_train.assert_called_once_with(["逻各斯", "Current"])
    assert handoff.plan["swap_frozen"] == 1
    collect = [
        queued for queued in solver.tasks if queued.type == TaskTypes.SKILL_UPGRADE
    ]
    assert len(collect) == 1
    assert collect[0].time == handoff.end
    scheduler.io.assert_not_called()


def test_real_skill_panel_exception_enters_bounded_retention(
    scheduler, handoff, monkeypatch
):
    from arknights_mower.solvers import mastery_reader
    from arknights_mower.utils import mastery_db
    from arknights_mower.utils.recognize import RecognizeError

    solver = scheduler.solver
    task = handoff.solver.task
    task.type = TaskTypes.SKILL_UPGRADE
    task.time = scheduler.clock.now()
    solver.tasks, solver.task = [task], task
    solver.back_to_infrastructure = Mock()
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda key: handoff.plan)
    read = Mock(side_effect=RecognizeError("截图读取失败"))
    monkeypatch.setattr(mastery_reader, "read_room_state", read)

    solver.infra_main()

    assert read.call_count == 3
    assert solver.tasks[0] is task
    assert task.execution_failure
    assert task.time == scheduler.clock.now()
    assert handoff.plan["status"] == "training"
    assert not solver.error
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("advanced", [False, True])
def test_restored_legacy_intent_waits_for_observed_swap_threshold(handoff, advanced):
    from datetime import datetime

    from arknights_mower.solvers import mastery

    solver, task = handoff.solver, handoff.solver.task
    task.mastery_swap_verify_only = True
    task.advance_support_swap = advanced
    deadline = datetime.now() + timedelta(hours=8)
    handoff.panel.countdown = deadline
    mastery._read_train_countdown3.return_value = ("active", deadline)

    mastery.run_swap_support(solver)

    if advanced:
        solver.choose_train.assert_called_once_with(["逻各斯", "Current"])
    else:
        solver.choose_train.assert_not_called()
        successors = [
            queued
            for queued in solver.tasks
            if queued is not task and queued.type == TaskTypes.SWAP_SUPPORT
        ]
        assert len(successors) == 1
        expected = deadline - timedelta(minutes=232.5)
        assert abs((successors[0].time - expected).total_seconds()) < 1
        assert all(queued.type != TaskTypes.SKILL_UPGRADE for queued in solver.tasks)
