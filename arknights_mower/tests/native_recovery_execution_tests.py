"""恢复实读失败保留原任务，真实恢复期限唤醒不制造轮询。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

from arknights_mower.tests import native_group_recovery_sync_tests
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

resting = native_group_recovery_sync_tests.resting
solver = native_group_recovery_sync_tests.solver


def returning_task():
    return SchedulerTask(
        task_plan={"meeting": ["伊内丝", "银灰"], "contact": ["讯使"]},
        task_type=TaskTypes.SHIFT_ON,
    )


def test_predicted_full_is_rechecked_and_keeps_original_request(resting, monkeypatch):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full = True
    op.mood = 24
    op.mood_is_prediction = True
    deadline = datetime.now() + timedelta(hours=2)
    data.get_dorm_by_name(op.name)[1].time = deadline
    task = returning_task()
    scheduler.tasks = [task]
    before, original_time = deepcopy(task.plan), task.time

    def read(rooms):
        op.mood, op.time_stamp, op.mood_is_prediction = 23, datetime.now(), False

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert scheduler._verify_required_recovery(task) is False
    assert task.plan == before and task.time == original_time
    assert task.execution_failure
    observers = [
        t for t in scheduler.tasks if getattr(t, "recovery_observation_rooms", None)
    ]
    assert len(observers) == 1 and observers[0].time == deadline
    scheduler._resume_failed_tasks()
    assert task.execution_failure
    assert len(scheduler.tasks) == 2
    op.mood, op.time_stamp = 24, datetime.now()
    scheduler._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert task.time == original_time


def test_all_required_members_are_checked_before_any_arrangement(resting, monkeypatch):
    scheduler, _ = resting
    data = scheduler.op_data
    for name in ["银灰", "讯使"]:
        data.operators[name].rest_in_full = True
    task = returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        for name, mood in [("银灰", 24), ("讯使", 23.9)]:
            op = data.operators[name]
            op.mood, op.time_stamp, op.mood_is_prediction = mood, datetime.now(), False

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    arrange = Mock(side_effect=AssertionError("must not move operators"))
    monkeypatch.setattr(scheduler, "agent_arrange", arrange)
    assert not scheduler._verify_required_recovery(task)
    arrange.assert_not_called()


def test_unknown_recovery_time_does_not_create_retry_timer(resting, monkeypatch):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full = True
    data.get_dorm_by_name(op.name)[1].time = None
    task = returning_task()
    scheduler.tasks = [task]
    monkeypatch.setattr(scheduler, "_read_recovery_rooms", lambda rooms: None)
    assert not scheduler._verify_required_recovery(task)
    assert scheduler.tasks == [task]


def test_fresh_full_read_allows_return_without_new_tasks(resting, monkeypatch):
    scheduler, _ = resting
    data = scheduler.op_data
    for name in ["银灰", "讯使"]:
        data.operators[name].rest_in_full = True
    task = returning_task()
    scheduler.tasks = [task]
    before = deepcopy(task.plan)
    read_rooms = []

    def read(rooms):
        read_rooms.extend(rooms)
        for name in ["银灰", "讯使"]:
            op = data.operators[name]
            op.mood, op.time_stamp, op.mood_is_prediction = 24, datetime.now(), False

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert scheduler._verify_required_recovery(task)
    assert read_rooms == ["dormitory_1"]
    assert task.plan == before and scheduler.tasks == [task]
    assert not getattr(task, "execution_failure", None)


def test_old_full_sample_does_not_replace_current_observation(resting, monkeypatch):
    scheduler, _ = resting
    op = scheduler.op_data.operators["讯使"]
    op.rest_in_full, op.mood, op.mood_is_prediction = True, 24, False
    op.time_stamp = datetime.now() - timedelta(hours=1)
    task = returning_task()
    scheduler.tasks = [task]
    monkeypatch.setattr(scheduler, "_read_recovery_rooms", lambda rooms: None)
    assert not scheduler._verify_required_recovery(task)
    assert task.execution_failure and scheduler.tasks == [task]


def test_infra_main_blocks_physical_arrangement_until_every_required_member_is_full(
    resting, monkeypatch
):
    scheduler, _ = resting
    data = scheduler.op_data
    for name in ["银灰", "讯使"]:
        data.operators[name].rest_in_full = True
    task = returning_task()
    scheduler.tasks, scheduler.task = [task], task
    scheduler.refresh_connecting = False
    before, original_time = deepcopy(task.plan), task.time
    monkeypatch.setattr(scheduler, "find", Mock(return_value=True))
    monkeypatch.setattr(scheduler, "skip", Mock())
    monkeypatch.setattr(scheduler, "_product_switching_enabled", lambda: True)
    for method in [
        "_prepare_group_shift",
        "_prepare_shift_cycle",
        "_defer_conflicting_product_shift_slots",
    ]:
        monkeypatch.setattr(scheduler, method, Mock())

    def read(rooms):
        assert rooms == {"dormitory_1"}
        for name, mood in [("银灰", 24), ("讯使", 23.9)]:
            op = data.operators[name]
            op.mood, op.time_stamp, op.mood_is_prediction = mood, datetime.now(), False

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    arrange = Mock(side_effect=AssertionError("未回满时不得进入实际换人"))
    monkeypatch.setattr(scheduler, "agent_arrange", arrange)
    assert scheduler.infra_main()
    arrange.assert_not_called()
    assert task in scheduler.tasks and task.execution_failure
    assert task.plan == before and task.time == original_time
