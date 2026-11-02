"""初始化让路的训练任务可实际派发，完成后继续剩余实读。"""

import pickle
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, emergency, mastery
from arknights_mower.tests.calculated_mood_startup_return_tests import (
    NOW,
)
from arknights_mower.tests.calculated_mood_startup_return_tests import (
    solver as solver,
)
from arknights_mower.tests.calculated_mood_startup_return_tests import (
    startup as startup,
)
from arknights_mower.utils import config, scheduler_task, workshop_automation
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def priority_startup(startup, monkeypatch):
    running, _, _, reads = startup
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    actions = MagicMock()
    monkeypatch.setattr(mastery, "run_mastery_task", actions)
    monkeypatch.setattr(mastery, "run_swap_support", actions)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", MagicMock())
    running.tasks = []
    running.task = None
    running._initial_mood_refresh_rooms = {"dormitory_1"}
    running.planned = running.todo_task = running.collect_notification = True
    running.handle_error = MagicMock(return_value=True)
    return running, reads, actions


@pytest.mark.parametrize("kind", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
@pytest.mark.parametrize("restored", ["fresh", "held", "serialized"])
def test_yielded_training_dispatches_and_completion_resumes_initialization(
    priority_startup, kind, restored
):
    running, reads, actions = priority_startup
    task = SchedulerTask(NOW - timedelta(seconds=1), task_type=kind)
    original_time = task.time
    running.tasks = [task]
    if restored != "fresh":
        task.startup_observation_pending = True
        running._emergency_defer_read()
        if restored == "serialized":
            running.tasks, running._emergency_continuation_wait = pickle.loads(
                pickle.dumps(
                    (running.tasks, running._emergency_continuation_checkpoint())
                )
            )
            task = next(t for t in running.tasks if t.type == kind)
        # run() 在选择任务前使用同一恢复入口。
        running._resume_failed_tasks()
    running.task = running.find_next_task()
    assert running.task is task
    running.infra_main()
    actions.assert_called_once_with(running)
    assert task.time == original_time
    assert all(t is not task for t in running.tasks)
    assert running._emergency_startup_pending
    assert not reads

    for _ in range(3):
        running.task = running.find_next_task()
        running.infra_main()
    assert not running._emergency_startup_pending
    assert "dormitory_1" in reads
    actions.assert_called_once_with(running)
    assert not any(t.type == kind for t in running.tasks)


@pytest.mark.parametrize("kind", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
@pytest.mark.parametrize("blocked", ["failed", "maintenance", "disabled"])
def test_non_dispatchable_training_does_not_suspend_initialization(
    priority_startup, monkeypatch, kind, blocked
):
    running, reads, actions = priority_startup
    task = SchedulerTask(NOW - timedelta(seconds=1), task_type=kind)
    running.tasks = [task]
    if blocked == "failed":
        task.startup_observation_pending = True
        running._retain_failed_task(task, "等待训练室新观测", ["train"])
        original_failure = task.execution_failure
    elif blocked == "maintenance":
        task.maintenance_preparation_pending = True
    else:
        monkeypatch.setattr(config.conf, "enable_mastery", False)
    assert running._yield_initial_mood_to_priority_task() is False
    running.infra_main()
    assert not running._emergency_startup_pending
    assert "dormitory_1" in reads
    actions.assert_not_called()
    if blocked == "failed":
        assert task.execution_failure is original_failure
        assert task not in task_view(running.tasks, TaskScope.DISPATCH, running.op_data)
        original_time = task.time
        for _ in range(3):
            running._resume_failed_tasks()
            running.task = None
            running.infra_main()
            assert task.execution_failure is original_failure
        clue = SchedulerTask(NOW, task_type=TaskTypes.CLUE)
        running.tasks.append(clue)
        running.task = clue
        running._run_clue_flow = MagicMock(return_value=True)
        running.infra_main()
        running._run_clue_flow.assert_called_once()
        actions.assert_not_called()
        assert task.time == original_time
        operator = running.op_data.operators["伊内丝"]
        operator._current_room, operator.current_index = "train", 0
        operator.time_stamp = NOW + timedelta(seconds=1)
        running._resume_failed_tasks()
        assert not getattr(task, "execution_failure", None)
        scheduler_task.scheduling(running.tasks, op_data=running.op_data)
        running.task = running.find_next_task()
        assert running.task is task
        running.infra_main()
        actions.assert_called_once_with(running)
        assert task.time == original_time


def test_unchanged_startup_wait_resumes_after_training_deadline_and_completion(
    priority_startup, monkeypatch
):
    running, reads, actions = priority_startup

    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for module in (base_schedule, emergency, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    priority = SchedulerTask(
        NOW + timedelta(seconds=30), task_type=TaskTypes.SWAP_SUPPORT
    )
    original_time = priority.time
    running.tasks = [priority]
    running.infra_main()
    assert running._emergency_startup_pending and not reads
    checkpoint = running._emergency_continuation_checkpoint()
    for _ in range(3):
        running.task = None
        running.infra_main()
        assert running._emergency_continuation_checkpoint() is checkpoint
    Clock.current = original_time
    running.task = running.find_next_task()
    assert running.task is priority
    running.infra_main()
    actions.assert_called_once_with(running)
    running.task = None
    running.infra_main()
    assert not running._emergency_startup_pending
    assert "dormitory_1" in reads
    assert priority.time == original_time

    clue = SchedulerTask(original_time, task_type=TaskTypes.CLUE)
    running.tasks.append(clue)
    running.task = clue
    running._run_clue_flow = MagicMock(return_value=True)
    running.infra_main()
    running._run_clue_flow.assert_called_once()
    assert clue not in running.tasks


@pytest.mark.parametrize("kind", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
def test_due_training_can_dispatch_while_initial_charge_remains_pending(
    priority_startup, kind
):
    running, _, actions = priority_startup
    priority = SchedulerTask(NOW - timedelta(seconds=1), task_type=kind)
    charge = SchedulerTask(NOW + timedelta(minutes=2), task_type=TaskTypes.FIAMMETTA)
    charge.initial_fia = True
    running._initial_fia_checked = True
    running.tasks = [priority, charge]
    running.task = priority
    running.infra_main()
    actions.assert_called_once_with(running)
    assert priority not in running.tasks
    assert charge in running.tasks


@pytest.mark.parametrize("kind", [TaskTypes.SWAP_SUPPORT, TaskTypes.SKILL_UPGRADE])
def test_current_training_outside_queue_remains_a_continuation_dependency(
    priority_startup, kind
):
    running, _, _ = priority_startup
    current = SchedulerTask(NOW, task_type=kind)
    running.task = current
    running._emergency_defer_read()
    checkpoint = running._emergency_continuation_checkpoint()
    assert checkpoint["dependencies"] == [(kind, "", NOW, {})]
    assert running._emergency_continuation_waiting()
    running.task = None
    assert not running._emergency_continuation_waiting()
