"""恢复实读失败保留原任务，真实恢复期限唤醒不制造轮询。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import native_group_recovery_sync_tests
from arknights_mower.utils import operation_timing
from arknights_mower.utils.group_recovery import group_recovery_deadline
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
    assert not getattr(task, "execution_failure", None)
    assert scheduler.waiting_group_shifts == [task]
    observers = [
        t for t in scheduler.tasks if getattr(t, "recovery_observation_rooms", None)
    ]
    assert len(observers) == 1 and observers[0].time == deadline
    scheduler._resume_waiting_group_shifts()
    assert scheduler.waiting_group_shifts == [task]
    assert len(scheduler.tasks) == 1
    op.mood, op.time_stamp = 24, datetime.now()
    scheduler._resume_waiting_group_shifts()
    assert task in scheduler.tasks and not scheduler.waiting_group_shifts
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

    reader = Mock(side_effect=read)
    monkeypatch.setattr(scheduler, "_read_recovery_rooms", reader)
    arrange = Mock(side_effect=AssertionError("未回满时不得进入实际换人"))
    monkeypatch.setattr(scheduler, "agent_arrange", arrange)
    assert scheduler.infra_main()
    arrange.assert_not_called()
    assert task in scheduler.waiting_group_shifts and task not in scheduler.tasks
    assert not getattr(task, "execution_failure", None)
    assert task.plan == before and task.time == original_time

    scheduler.planned = scheduler.todo_task = scheduler.collect_notification = True
    monkeypatch.setattr(scheduler, "handle_error", Mock(return_value=True))
    for _ in range(3):
        assert scheduler.infra_main()
    assert reader.call_count == 1
    arrange.assert_not_called()
    assert scheduler.task is None
    assert scheduler.waiting_group_shifts == [task]


@pytest.mark.parametrize("group_wait", [False, True])
def test_fresh_near_full_members_allow_return_with_unchanged_mood(
    resting, monkeypatch, group_wait
):
    scheduler, _ = resting
    data = scheduler.op_data
    required = ["银灰", "讯使"]
    if group_wait:
        data.group_recovery_full_members["联动"] = required
        required.append("伊内丝")
    else:
        for name in required:
            data.operators[name].rest_in_full = True
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    task = returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        for name in required:
            op = data.operators[name]
            op.mood, op.time_stamp, op.mood_is_prediction = 23.88, datetime.now(), False
            data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(seconds=85)

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert scheduler._verify_required_recovery(task)
    assert all(data.operators[name].mood == 23.88 for name in required)
    assert scheduler.tasks == [task]


@pytest.mark.parametrize("remaining", [None, -1, 120])
def test_near_full_mood_alone_does_not_allow_return(resting, monkeypatch, remaining):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full = True
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    task = returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        op.mood, op.time_stamp, op.mood_is_prediction = 23.99, datetime.now(), False
        data.get_dorm_by_name(op.name)[1].time = (
            None if remaining is None else datetime.now() + timedelta(seconds=remaining)
        )

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    if remaining is not None and remaining > 0:
        assert task in scheduler.waiting_group_shifts
        assert not getattr(task, "execution_failure", None)
    else:
        assert task.execution_failure
    assert op.mood == 23.99


@pytest.mark.parametrize("sample_room", ["dormitory_1", "dormitory_2"])
def test_near_full_window_uses_only_this_rooms_operation_history(
    resting, monkeypatch, sample_room
):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full = True
    monkeypatch.setattr(
        operation_timing, "_dorm_durations", {(sample_room, False): [120]}
    )
    task = returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        op.mood, op.time_stamp, op.mood_is_prediction = 23.8, datetime.now(), False
        data.get_dorm_by_name(op.name)[1].time = datetime.now() + timedelta(seconds=150)

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert scheduler._verify_required_recovery(task) is (sample_room == "dormitory_1")
    assert op.mood == 23.8


@pytest.mark.parametrize("prediction", [False, True])
def test_near_full_stale_or_predicted_read_cannot_allow_return(
    resting, monkeypatch, prediction
):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full = True
    task = returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        op.mood, op.mood_is_prediction = 23.99, prediction
        op.time_stamp = datetime.now() - timedelta(seconds=0 if prediction else 60)
        data.get_dorm_by_name(op.name)[1].time = datetime.now() + timedelta(seconds=30)

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    assert scheduler.tasks == [task]


@pytest.mark.parametrize("personal_full", [False, True])
def test_personal_cap_release_preserves_early_operation_window(
    resting, monkeypatch, personal_full
):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full, op.upper_limit, op.mood = personal_full, 12, 11.879
    data.config.operator_mood_limits[op.name] = {"lower": 0, "upper": 12}
    data.group_recovery_full_members["联动"] = ["伊内丝", "银灰", "讯使"]
    bed = data.get_dorm_by_name(op.name)[1]
    bed.time = datetime.now() + timedelta(seconds=140)
    row = ["Current"] * 5
    row[op.current_index] = "Free"
    task = SchedulerTask(
        task_plan={op.current_room: row},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data=op.name,
        strict_mood_limit=True,
        mood_limit=12,
    )
    scheduler.tasks, scheduler.task = [task], task
    monkeypatch.setattr(
        scheduler, "_read_recovery_rooms", Mock(side_effect=AssertionError)
    )
    arrange = Mock(return_value=True)
    monkeypatch.setattr(scheduler, "agent_arrange", arrange)
    assert scheduler.arrange_release_dorm() == (True, True)
    arrange.assert_called_once()
    assert task.plan == {} and not getattr(task, "execution_failure", None)
    assert op.mood == 11.879


def test_early_cap_release_still_rejects_changed_personal_limit(resting):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.upper_limit = 20
    data.config.operator_mood_limits[op.name] = {"lower": 0, "upper": 20}
    row = ["Current"] * 5
    row[op.current_index] = "Free"
    task = SchedulerTask(
        task_plan={op.current_room: row},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data=op.name,
        strict_mood_limit=True,
        mood_limit=12,
    )
    assert scheduler._verify_required_recovery(task)
    assert not scheduler.prepare_release_dorm(task)
    assert task.plan == {}


def test_confirmed_early_cap_departure_completes_only_its_recovery(
    resting, monkeypatch
):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full, op.upper_limit, op.mood = True, 12, 11.879
    op.mood_is_prediction, op.time_stamp, op.depletion_rate = False, datetime.now(), -3
    observed_at = op.time_stamp
    data.config.operator_mood_limits[op.name] = {"lower": 0, "upper": 12}
    data.group_recovery_full_members["联动"] = ["伊内丝", "银灰", "讯使"]
    room, index = op.current_room, op.current_index
    row = [data.get_current_operator(room, i) for i in range(5)]
    row = [member.name if member else "" for member in row]
    row[index] = ""
    scheduler.task = SchedulerTask(
        task_plan={room: row},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data=op.name,
        strict_mood_limit=True,
        mood_limit=12,
    )
    scheduler._reconcile_room_observation(room, [{"agent": name} for name in row])
    assert op.current_room == "" and op.rest_mood_release_limit == 12
    assert (op.mood, op.time_stamp, op.depletion_rate) == (11.879, observed_at, 0)
    assert data.rest_mood_complete(op.name)
    assert op.name not in scheduler.get_free_list([])
    task = returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        assert rooms == {room}
        for name in ["伊内丝", "银灰"]:
            member = data.operators[name]
            member.mood, member.time_stamp = 24, datetime.now()
            member.mood_is_prediction = False

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert scheduler._verify_required_recovery(task)
    now = datetime.now()
    assert group_recovery_deadline(data, "联动", now=now)[1] == now
    assert op.mood == 11.879
    op.upper_limit = 20
    assert group_recovery_deadline(data, "联动", now=now)[1] is None


@pytest.mark.parametrize("observation", ["near-full", "unfinished", "unread"])
def test_new_required_members_receive_one_supplemental_room_read(
    resting, monkeypatch, observation
):
    scheduler, _ = resting
    data = scheduler.op_data
    data.operators["伊内丝"].rest_in_full = True
    newcomer = data.operators["银灰"]
    data.plan["dormitory_2"] = deepcopy(data.plan["dormitory_1"])
    bed = data.get_dorm_by_name(newcomer.name)[1]
    newcomer.current_room = "dormitory_2"
    bed.position = (newcomer.current_room, newcomer.current_index)
    newcomer.mood, newcomer.time_stamp = 23.9, datetime.now() - timedelta(hours=1)
    bed.time = datetime.now() + timedelta(seconds=60)
    task = returning_task()
    scheduler.tasks = [task]
    original_time = task.time
    reads = []

    def read(rooms):
        reads.append(set(rooms))
        if rooms == {"dormitory_1"}:
            for name in ["伊内丝", "讯使"]:
                op = data.operators[name]
                op.mood, op.time_stamp, op.mood_is_prediction = (
                    24,
                    datetime.now(),
                    False,
                )
            data.group_recovery_full_members["联动"] = ["伊内丝", "银灰", "讯使"]
        else:
            assert rooms == {"dormitory_2"}
            if observation != "unread":
                newcomer.time_stamp = datetime.now()
                bed.time = datetime.now() + timedelta(
                    seconds=60 if observation == "near-full" else 3600
                )

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert scheduler._verify_required_recovery(task) is (observation == "near-full")
    assert reads == [{"dormitory_1"}, {"dormitory_2"}]
    assert newcomer.mood == 23.9 and task.time == original_time
    if observation == "unread":
        assert task.execution_failure and scheduler.tasks == [task]
    elif observation == "unfinished":
        assert not getattr(task, "execution_failure", None)
        assert scheduler.waiting_group_shifts == [task]
        assert len(scheduler.tasks) == 1
        assert scheduler.tasks[0].recovery_observation_rooms == {"dormitory_2"}
        assert scheduler.tasks[0].time == bed.time
