"""计算心情的用尽预约只在个人下限实读，失败保留原任务。"""

import pickle
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils import calculated_mood
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)


@pytest.fixture
def calculated_solver(solver, monkeypatch):
    monkeypatch.setattr(
        Operators, "mood_calculation_enabled", property(lambda self: True)
    )
    solver.test_moods = {"机械师": 12}
    solver.test_deadlines = {"机械师": datetime.now() + timedelta(hours=4)}
    solver.op_data.operators["机械师"].time_stamp -= timedelta(minutes=1)
    monkeypatch.setattr(
        solver.op_data,
        "calculated_mood",
        lambda name, now=None: solver.test_moods.get(name),
    )
    solver.deadline_targets = []

    def deadline(name, target, now=None):
        solver.deadline_targets.append((name, target))
        return solver.test_deadlines.get(name)

    monkeypatch.setattr(solver.op_data, "calculated_mood_deadline", deadline)
    solver.back = Mock()
    solver.get_agent_from_room = Mock()
    return solver


@pytest.mark.parametrize("lower", [0, 8])
def test_run_order_solver_schedules_personal_floor_without_early_room_read(
    calculated_solver, lower
):
    instance = calculated_solver
    instance.op_data.operators["机械师"].lower_limit = lower
    instance.run_order_solver()
    (task,) = instance.tasks
    assert task.type == TaskTypes.EXHAUST_OFF
    assert task.time == instance.test_deadlines["机械师"]
    assert ("机械师", lower) in instance.deadline_targets
    instance.run_order_solver()
    assert instance.tasks == [task]
    instance.enter_room.assert_not_called()
    instance.get_agent_from_room.assert_not_called()


def test_due_task_above_floor_uses_new_real_deadline_without_observation(
    calculated_solver,
):
    instance = calculated_solver
    original = instance.task
    assert instance.overtake_room() is False
    assert instance.tasks == [original]
    assert original.time == instance.test_deadlines["机械师"]
    instance.enter_room.assert_not_called()


@pytest.mark.parametrize("lower", [0, 8])
def test_due_floor_reads_once_and_reuses_calibrated_deadline(calculated_solver, lower):
    instance = calculated_solver
    op = instance.op_data.operators["机械师"]
    op.lower_limit = lower
    instance.test_moods[op.name] = lower
    instance.enter_room = Mock()
    expected = datetime.now() + timedelta(minutes=37)

    def observe(*args, **kwargs):
        instance.test_moods[op.name] = lower + 1
        instance.test_deadlines[op.name] = expected
        op.mood = lower + 1
        op.time_stamp = datetime.now()
        return [{"agent": op.name, "mood": lower + 1}]

    instance.get_agent_from_room.side_effect = observe
    original = instance.task
    assert instance.overtake_room() is False
    assert instance.tasks == [original]
    assert original.time == expected
    instance.get_agent_from_room.assert_called_once_with(
        "room_3_3", force_mood=True, strict_observation=True
    )
    assert instance.overtake_room() is False
    assert instance.get_agent_from_room.call_count == 1


def test_observed_personal_floor_continues_existing_group_planning(calculated_solver):
    instance = calculated_solver
    instance.test_moods["机械师"] = 8
    instance.op_data.operators["机械师"].lower_limit = 8
    instance.enter_room = Mock()
    instance.get_agent_from_room.return_value = [{"agent": "机械师", "mood": 8}]
    original = instance.get_resting_plan
    instance.get_resting_plan = Mock(wraps=original)
    instance.overtake_room()
    assert instance.get_resting_plan.call_count >= 1
    instance.get_agent_from_room.assert_called_once()


def test_unknown_model_retains_failure_and_unrelated_work(calculated_solver):
    instance = calculated_solver
    instance.test_moods.clear()
    instance.test_deadlines.clear()
    original, original_time = instance.task, instance.task.time
    assert instance.overtake_room() is False
    failure = original.execution_failure
    independent = SchedulerTask(meta_data="独立工作")
    instance.tasks.append(independent)
    for _ in range(3):
        instance.run_order_solver()
        instance._resume_failed_tasks()
        assert original.execution_failure is failure
        assert original.time == original_time
        assert find_next_task(instance.tasks) is independent
        assert sum(task is original for task in instance.tasks) == 1
    instance.enter_room.assert_not_called()


def test_failed_unstarted_task_rechecks_floor_after_new_observation(calculated_solver):
    instance = calculated_solver
    instance.test_moods.clear()
    instance.test_deadlines.clear()
    assert instance.overtake_room() is False
    original, original_time = instance.task, instance.task.time
    instance.op_data.room_observations["room_3_3"] = datetime.now()
    instance.op_data.operators["机械师"].mood = 10
    instance.test_moods["机械师"] = 10
    expected = datetime.now() + timedelta(hours=3)
    instance.test_deadlines["机械师"] = expected
    instance._resume_failed_tasks()
    assert not getattr(original, "execution_failure", None)
    assert original.retains_execution
    assert instance.overtake_room() is None
    assert original.time == original_time
    successor = next(task for task in instance.tasks if task is not original)
    assert successor.time == expected
    assert not successor.retains_execution
    instance.enter_room.assert_not_called()


def test_floor_observation_propagates_device_recovery(calculated_solver):
    instance = calculated_solver
    instance.test_moods["机械师"] = 0
    instance.enter_room = Mock(side_effect=SharedADBError("共享设备恢复"))
    with pytest.raises(SharedADBError):
        instance.overtake_room()


@pytest.mark.parametrize("known", [False, True])
def test_fiammetta_reservation_uses_model_without_room_read(calculated_solver, known):
    instance = calculated_solver
    instance.check_fia = Mock(return_value=(["机械师"], "dormitory_1"))
    instance.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔", "dormitory_1", current_room="dormitory_1", current_index=0
    )
    expected = datetime.now() + timedelta(hours=1)
    if known:
        instance.test_deadlines["菲亚梅塔"] = expected
    for _ in range(2):
        instance.run_order_solver()
    tasks = [task for task in instance.tasks if task.type == TaskTypes.FIAMMETTA]
    assert len(tasks) == int(known)
    if known:
        assert tasks[0].time == expected
    instance.enter_room.assert_not_called()
    instance.get_agent_from_room.assert_not_called()


def test_changed_model_input_advances_future_exhaustion_without_clock_polling(
    calculated_solver,
):
    instance = calculated_solver
    instance.run_order_solver()
    (task,) = instance.tasks
    initial = task.time
    calls = len(instance.deadline_targets)
    expected = datetime.now() + timedelta(minutes=31)
    instance.test_deadlines["机械师"] = expected
    instance._refresh_calculated_exhaustion_tasks()
    assert task.time == initial
    assert len(instance.deadline_targets) == calls
    instance.op_data.mood_model.revision += 1
    instance._refresh_calculated_exhaustion_tasks()
    assert task.time == expected
    instance.enter_room.assert_not_called()


def test_retained_failure_deadline_is_unchanged_by_model_updates(calculated_solver):
    instance = calculated_solver
    instance.test_deadlines.clear()
    instance.run_order_solver()
    (task,) = instance.tasks
    original = task.time
    failure = task.execution_failure
    instance.test_deadlines["机械师"] = original + timedelta(hours=2)
    instance.op_data.mood_model.revision += 1
    instance._refresh_calculated_exhaustion_tasks()
    assert task.time == original
    assert task.execution_failure is failure


def test_restart_dispatch_consumes_old_failure_and_keeps_real_successor(
    calculated_solver, monkeypatch
):
    instance = calculated_solver
    instance.test_moods.clear()
    instance.test_deadlines.clear()
    assert instance.overtake_room() is False
    original = pickle.loads(pickle.dumps(instance.task))
    original_time = original.time
    independent = SchedulerTask(meta_data="独立工作")
    instance.tasks, instance.task = [original, independent], original
    instance.op_data.room_observations["room_3_3"] = datetime.now()
    instance.op_data.operators["机械师"].mood = 10
    instance.test_moods["机械师"] = 10
    expected = datetime.now() + timedelta(hours=3)
    instance.test_deadlines["机械师"] = expected
    monkeypatch.setattr(calculated_mood, "sync_model", lambda owner: owner.mood_model)
    instance.find = Mock(return_value=True)
    instance._refresh_deferred_product_reservations = Mock()
    instance.planned = instance.todo_task = instance.collect_notification = False
    instance.restart_after_mood_read = False
    instance.infra_main()
    assert original not in instance.tasks
    assert original.time == original_time
    successor = next(
        task for task in instance.tasks if task.type == TaskTypes.EXHAUST_OFF
    )
    assert successor.time == expected
    assert independent in instance.tasks
    assert find_next_task(instance.tasks) is independent
    instance.enter_room.assert_not_called()


def test_recent_actual_floor_read_is_reused(calculated_solver):
    instance = calculated_solver
    op = instance.op_data.operators["机械师"]
    instance.test_moods[op.name] = op.mood = 0
    op.time_stamp = datetime.now()
    instance._plan_exhaust_support = Mock(return_value=None)
    instance.overtake_room()
    instance.enter_room.assert_not_called()


@pytest.mark.parametrize("other_room", ["train", "dormitory_1", ""])
def test_mixed_group_keeps_working_trigger_floor_check(calculated_solver, other_room):
    instance = calculated_solver
    worker = instance.op_data.operators["机械师"]
    follower = instance.op_data.operators["能天使"]
    worker.group = follower.group = "用尽"
    instance.op_data.groups[worker.group] = [worker.name, follower.name]
    follower._current_room = other_room
    follower.current_index = 0 if other_room else -1
    instance.test_moods[follower.name] = 0
    assert instance.overtake_room() is False
    assert instance.task.time == instance.test_deadlines[worker.name]
    instance.enter_room.assert_not_called()


def test_two_due_group_members_share_one_room_observation(calculated_solver):
    instance = calculated_solver
    worker = instance.op_data.operators["机械师"]
    follower = instance.op_data.operators["能天使"]
    worker.group = follower.group = "用尽"
    instance.op_data.groups[worker.group] = [worker.name, follower.name]
    instance.op_data.exhaust_agent.add(follower.name)
    follower._current_room, follower.current_index = worker.current_room, 1
    follower.time_stamp -= timedelta(minutes=1)
    instance.test_moods.update({worker.name: 0, follower.name: 0})
    instance.enter_room = Mock()
    instance.get_agent_from_room.return_value = [
        {"agent": worker.name, "mood": 0},
        {"agent": follower.name, "mood": 0},
    ]
    instance.get_resting_plan = Mock()
    instance._plan_exhaust_support = Mock(return_value=None)
    instance.overtake_room()
    instance.get_agent_from_room.assert_called_once_with(
        worker.current_room, force_mood=True, strict_observation=True
    )
    instance.get_resting_plan.assert_called_once()


def test_disabled_fiammetta_reservation_keeps_room_timer_read(solver):
    solver.op_data.exhaust_agent = []
    solver.check_fia = Mock(return_value=(["机械师"], "dormitory_1"))
    solver.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔", "dormitory_1", current_room="dormitory_1", current_index=0
    )
    expected = datetime.now() + timedelta(hours=1)
    solver.enter_room = Mock()
    solver.back = Mock()
    solver.get_agent_from_room = Mock(
        return_value=[{"agent": "菲亚梅塔", "time": expected}]
    )
    solver.run_order_solver()
    assert solver.tasks[0].time == expected
    solver.enter_room.assert_called_once_with("dormitory_1")
    solver.get_agent_from_room.assert_called_once_with("dormitory_1", [0])


@pytest.mark.parametrize(
    "changed_input",
    ["stages", "rooms", "observation", "known", "limits", "global_sample"],
)
def test_unknown_deadline_dispatch_resumes_only_after_changed_model_input(
    calculated_solver, monkeypatch, changed_input
):
    instance = calculated_solver
    instance.test_deadlines.clear()
    instance.run_order_solver()
    (original,) = instance.tasks
    original_time = original.time
    failure = original.execution_failure
    model = instance.op_data.mood_model
    monkeypatch.setattr(calculated_mood, "sync_model", lambda owner: owner.mood_model)
    monkeypatch.setattr(base_schedule, "sync_replacement_checks", lambda owner: None)
    instance.find = Mock(return_value=True)
    instance._refresh_deferred_product_reservations = Mock()
    instance.planned = instance.todo_task = instance.collect_notification = True
    instance.restart_after_mood_read = False
    for index in range(3):
        model.revision += 1
        model.at = datetime.now() + timedelta(hours=index + 1)
        independent = SchedulerTask(meta_data="独立工作")
        instance.tasks.append(independent)
        instance.task = independent
        instance.infra_main()
        assert independent not in instance.tasks
        assert original.execution_failure is failure
        assert original.time == original_time
        assert instance.tasks == [original]

    expected = datetime.now() + timedelta(hours=2)
    instance.test_deadlines["机械师"] = expected
    if changed_input == "stages":
        model.stages["机械师"] = (2, 90)
    elif changed_input == "rooms":
        model.rooms["central"] = {"roster": ["阿米娅"], "level": 5}
    elif changed_input == "observation":
        instance.op_data.operators["能天使"].mood = 7
    elif changed_input == "limits":
        instance.op_data.operators["机械师"].lower_limit = 8
    elif changed_input == "global_sample":
        instance.op_data.operators["能天使"].time_stamp = datetime.now()
    else:
        model.moods["机械师"] = 12
    instance.task = original
    instance.infra_main()
    assert not getattr(original, "execution_failure", None)
    assert original.time == original_time
    assert original not in instance.tasks
    (successor,) = instance.tasks
    assert successor.type == TaskTypes.EXHAUST_OFF
    assert successor.time == expected
    instance.enter_room.assert_not_called()


def test_failed_floor_read_resumes_after_external_same_value_observation(
    calculated_solver, monkeypatch
):
    instance = calculated_solver
    op = instance.op_data.operators["机械师"]
    instance.test_moods[op.name] = op.mood = 0
    instance.enter_room = Mock(side_effect=RuntimeError("本次进房失败"))
    assert instance.overtake_room() is False
    original, original_time = instance.task, instance.task.time
    instance.enter_room.reset_mock(side_effect=True)
    op.time_stamp = datetime.now()
    instance.op_data.room_observations[op.current_room] = op.time_stamp
    monkeypatch.setattr(calculated_mood, "sync_model", lambda owner: owner.mood_model)
    monkeypatch.setattr(base_schedule, "sync_replacement_checks", lambda owner: None)
    instance.find = Mock(return_value=True)
    instance._refresh_deferred_product_reservations = Mock()
    instance.planned = instance.todo_task = instance.collect_notification = True
    instance.restart_after_mood_read = False
    instance.get_resting_plan = Mock(
        side_effect=lambda names, used, plan, count: plan.update(
            {"room_3_3": ["槐琥"], "dormitory_1": ["机械师"]}
        )
    )
    monkeypatch.setattr(base_schedule, "try_reorder", lambda *args, **kwargs: None)
    instance.infra_main()
    assert not getattr(original, "execution_failure", None)
    assert original.time == original_time
    assert all(task is not original for task in instance.tasks)
    assert any(task.type == TaskTypes.SHIFT_OFF for task in instance.tasks)
    instance.get_resting_plan.assert_called_once()
    instance.enter_room.assert_not_called()
