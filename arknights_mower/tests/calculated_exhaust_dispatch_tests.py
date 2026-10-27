"""实时心情沿用工作倒计时预约用尽下班，到期执行现有换班安排。"""

import pickle
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.exhaust_replacement_tests import (
    run_retained,
)
from arknights_mower.tests.exhaust_replacement_tests import (
    solver as solver,
)
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def timed_solver(solver, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 27, 12)

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    solver.clock = Clock
    solver.enter_room = Mock()
    solver.back = Mock()
    solver.get_agent_from_room = Mock(
        return_value=[{"agent": "机械师", "time": Clock(2026, 10, 27, 14)}]
    )
    worker = solver.op_data.operators["机械师"]
    worker.mood, worker.time_stamp = 2, Clock.now()
    return solver


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("rest_in_full", [False, True])
def test_exhaustion_reads_working_countdown_with_original_preparation_margin(
    timed_solver, enabled, rest_in_full
):
    instance = timed_solver
    config.conf.test_mood_calculation = enabled
    instance.op_data.operators["机械师"].rest_in_full = rest_in_full
    instance.run_order_solver()
    (task,) = instance.tasks
    assert task.type == TaskTypes.EXHAUST_OFF
    assert task.time == instance.clock(2026, 10, 27, 13, 50 if rest_in_full else 30)
    instance.enter_room.assert_called_once_with("room_3_3")
    instance.get_agent_from_room.assert_called_once_with("room_3_3", [0])
    instance.run_order_solver()
    assert instance.tasks == [task]
    assert instance.get_agent_from_room.call_count == 1


def test_calculated_group_uses_earliest_observed_personal_deadline(timed_solver):
    instance = timed_solver
    config.conf.test_mood_calculation = True
    worker = instance.op_data.operators["机械师"]
    follower = instance.op_data.operators["能天使"]
    worker.group = follower.group = "用尽"
    follower.lower_limit, follower.mood = 8, 10
    follower.time_stamp = instance.clock.now()
    instance.op_data.groups[worker.group] = [worker.name, follower.name]
    instance.op_data.exhaust_agent.add(follower.name)
    instance.op_data.rest_in_full_group.add(worker.group)

    def observe(room, indexes):
        if room == "meeting":
            return [{"agent": follower.name, "time": instance.clock(2026, 10, 27, 17)}]
        return [{"agent": worker.name, "time": instance.clock(2026, 10, 27, 14)}]

    instance.get_agent_from_room.side_effect = observe
    instance.run_order_solver()
    (task,) = instance.tasks
    # 心情 10 到个人下限 8 占归零倒计时五分之一，13:00 前十分钟下班。
    assert task.time == instance.clock(2026, 10, 27, 12, 50)
    assert set(task.meta_data.split(",")) == {worker.name, follower.name}
    assert instance.get_agent_from_room.call_count == 2


@pytest.mark.parametrize("minutes", [0, 3, 10])
def test_calculated_near_or_reached_working_deadline_schedules_now(
    timed_solver, minutes
):
    instance = timed_solver
    config.conf.test_mood_calculation = True
    instance.get_agent_from_room.return_value[0]["time"] = (
        instance.clock.now() + timedelta(minutes=minutes)
    )
    instance.run_order_solver()
    assert instance.tasks[0].time == instance.clock.now()
    instance.get_agent_from_room.assert_called_once()


@pytest.mark.parametrize("observation", ["unknown", "wrong_occupant", "unconfirmed"])
def test_calculated_missing_working_observation_does_not_invent_deadline(
    timed_solver, observation
):
    instance = timed_solver
    config.conf.test_mood_calculation = True
    item = instance.get_agent_from_room.return_value[0]
    if observation == "unknown":
        item.pop("time")
    elif observation == "wrong_occupant":
        item["agent"] = "能天使"
    else:
        item["observed"] = False
    instance.run_order_solver()
    assert instance.tasks == []
    instance.get_agent_from_room.assert_called_once()
    instance.back.assert_called_once()


@pytest.mark.parametrize("due", [False, True])
def test_restored_calculated_appointment_preserves_time_without_model_refresh(
    timed_solver, due
):
    instance = timed_solver
    config.conf.test_mood_calculation = True
    task = SchedulerTask(
        time=datetime(2026, 10, 27, 11 if due else 16),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="机械师",
    )
    task.calculated_exhaust_signature = (0, (), (("机械师", 0),))
    restored = pickle.loads(pickle.dumps(task))
    instance.tasks = [restored]
    instance.op_data.mood_model.revision += 1
    instance.run_order_solver()
    assert instance.tasks == [restored]
    assert restored.time == task.time
    assert not getattr(restored, "execution_failure", None)
    instance.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "evidence", ["positive_mood", "unknown", "long_zero_countdown"]
)
def test_due_calculated_appointment_plans_shift_without_another_mood_gate(
    timed_solver, monkeypatch, evidence
):
    instance = timed_solver
    config.conf.test_mood_calculation = True
    task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="机械师")
    instance.tasks, instance.task = [task], task
    worker = instance.op_data.operators["机械师"]
    worker.mood = 1
    monkeypatch.setattr(
        instance.op_data,
        "calculated_mood",
        lambda *args, **kwargs: None if evidence == "unknown" else worker.mood,
    )
    if evidence == "long_zero_countdown":
        worker.mood = 0
        worker.time_stamp = instance.clock.now()
        worker.exhaust_time = instance.clock.now() + timedelta(minutes=42)
    cover = instance.op_data.operators["槐琥"]
    cover.current_room, cover.current_index = "", -1
    instance.get_resting_plan = Mock(wraps=instance.get_resting_plan)
    instance.overtake_room()
    instance.get_resting_plan.assert_called_once()
    shift = next(task for task in instance.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert shift.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in shift.plan["dormitory_1"]
    instance.enter_room.assert_not_called()
    instance.get_agent_from_room.assert_not_called()


def test_restored_exhaustion_failure_requires_a_new_relevant_observation(solver):
    config.conf.test_mood_calculation = True
    original = run_retained(solver)
    restored = pickle.loads(pickle.dumps(original))
    assert "calculated_exhaustion" in restored.execution_failure["snapshot"]
    solver.tasks, solver.task = [restored], restored
    failure = restored.execution_failure
    for _ in range(3):
        solver._resume_failed_tasks()
        assert restored.execution_failure is failure
        assert restored.time == original.time
    solver.op_data.room_observations["room_3_3"] = datetime.now()
    solver._resume_failed_tasks()
    assert not getattr(restored, "execution_failure", None)
    assert restored.time == original.time


@pytest.mark.parametrize("known", [False, True])
def test_fiammetta_reservation_keeps_calculated_full_mood_deadline(
    timed_solver, monkeypatch, known
):
    instance = timed_solver
    config.conf.test_mood_calculation = True
    instance.op_data.exhaust_agent.clear()
    instance.check_fia = Mock(return_value=(["机械师"], "dormitory_1"))
    instance.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔", "dormitory_1", current_room="dormitory_1", current_index=0
    )
    expected = instance.clock(2026, 10, 27, 13)
    monkeypatch.setattr(
        instance.op_data,
        "calculated_mood_deadline",
        lambda *args: expected if known else None,
    )
    for _ in range(2):
        instance.run_order_solver()
    tasks = [task for task in instance.tasks if task.type == TaskTypes.FIAMMETTA]
    assert len(tasks) == int(known)
    if known:
        assert tasks[0].time == expected
    instance.enter_room.assert_not_called()
    instance.get_agent_from_room.assert_not_called()


def test_disabled_fiammetta_reservation_keeps_room_timer_read(timed_solver):
    instance = timed_solver
    instance.op_data.exhaust_agent.clear()
    instance.check_fia = Mock(return_value=(["机械师"], "dormitory_1"))
    instance.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔", "dormitory_1", current_room="dormitory_1", current_index=0
    )
    expected = instance.clock(2026, 10, 27, 13)
    instance.get_agent_from_room.return_value = [
        {"agent": "菲亚梅塔", "time": expected}
    ]
    instance.run_order_solver()
    assert instance.tasks[0].time == expected
    instance.enter_room.assert_called_once_with("dormitory_1")
    instance.get_agent_from_room.assert_called_once_with("dormitory_1", [0])
