"""恢复实读失败保留原任务，真实恢复期限唤醒不制造轮询。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import jsonpickle
import pytest

from arknights_mower.tests import native_group_recovery_sync_tests
from arknights_mower.utils import operation_timing
from arknights_mower.utils.group_recovery import group_recovery_deadline
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
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


def test_recovery_observation_keeps_targets_when_reusing_same_deadline(resting):
    scheduler, _ = resting
    now = datetime.now()
    deadline = now + timedelta(hours=1)
    scheduler.tasks = []
    for name in ("伊内丝", "银灰"):
        op = scheduler.op_data.operators[name]
        op.mood, op.time_stamp, op.mood_is_prediction = 10, now, False
        scheduler.op_data.get_dorm_by_name(name)[1].time = deadline
        scheduler._schedule_recovery_observations({name}, now)
    assert len(scheduler.tasks) == 1
    task = scheduler.tasks[0]
    assert task.time == deadline
    assert task.type == TaskTypes.REFRESH_TIME and task.plan == {}
    assert task.recovery_observation_rooms == {"dormitory_1"}
    assert task.recovery_observation_targets == {
        "伊内丝": "dormitory_1",
        "银灰": "dormitory_1",
    }
    assert task.display_name == "复查宿舍心情：宿舍1（伊内丝、银灰）"


@pytest.mark.parametrize("seconds", [-3, 3])
def test_recovery_observation_replaces_superseded_deadlines(resting, seconds):
    scheduler, now = resting
    data = scheduler.op_data
    name = "伊内丝"
    op = data.operators[name]
    op.rest_in_full, op.mood_is_prediction = True, False
    scheduler.tasks = []
    bed = data.get_dorm_by_name(name)[1]
    original_deadline = now + timedelta(hours=2)

    for revision in range(5):
        op.time_stamp = now + timedelta(seconds=revision)
        bed.time = original_deadline + timedelta(seconds=seconds * revision)
        scheduler._schedule_recovery_observations({name}, now)
        assert len(scheduler.tasks) == 1
        observation = scheduler.tasks[0]
        assert observation.time == bed.time
        assert observation.recovery_observation_targets == {name: "dormitory_1"}
        assert observation.recovery_observation_rooms == {"dormitory_1"}


def test_selected_future_recovery_observation_replaces_old_deadline(resting):
    scheduler, now = resting
    data = scheduler.op_data
    name = "伊内丝"
    op = data.operators[name]
    op.rest_in_full, op.mood_is_prediction = True, False
    scheduler.tasks = []
    scheduler._schedule_recovery_observations({name}, now)
    selected = scheduler.task = scheduler.tasks[0]
    bed = data.get_dorm_by_name(name)[1]
    op.time_stamp = now + timedelta(seconds=1)
    bed.time = selected.time + timedelta(seconds=3)

    scheduler._schedule_recovery_observations({name}, now + timedelta(seconds=1))

    assert len(scheduler.tasks) == 1
    observation = scheduler.tasks[0]
    assert observation.time == bed.time
    assert observation.recovery_observation_targets == {name: "dormitory_1"}
    assert observation.recovery_observation_rooms == {"dormitory_1"}


def test_recovery_observation_move_keeps_other_targets_and_deadlines(resting):
    scheduler, now = resting
    data = scheduler.op_data
    for room in ("dormitory_2", "dormitory_3"):
        data.plan[room] = deepcopy(data.plan["dormitory_1"])
    shared_deadline = now + timedelta(hours=2)
    for name, room, deadline in (
        ("伊内丝", "dormitory_1", shared_deadline),
        ("银灰", "dormitory_2", shared_deadline),
        ("讯使", "dormitory_1", shared_deadline + timedelta(hours=1)),
    ):
        op = data.operators[name]
        bed = data.get_dorm_by_name(name)[1]
        op.current_room = room
        bed.position = (room, op.current_index)
        op.rest_in_full, op.mood_is_prediction = True, False
        op.time_stamp, bed.time = now, deadline
    scheduler.tasks = []
    scheduler._schedule_recovery_observations({"伊内丝", "银灰", "讯使"}, now)
    shared = next(
        t for t in scheduler.tasks if "银灰" in t.recovery_observation_targets
    )
    other = next(t for t in scheduler.tasks if "讯使" in t.recovery_observation_targets)

    moved = data.operators["伊内丝"]
    bed = data.get_dorm_by_name(moved.name)[1]
    moved.current_room = "dormitory_3"
    bed.position = (moved.current_room, moved.current_index)
    moved.time_stamp = now + timedelta(seconds=1)
    bed.time = shared_deadline + timedelta(minutes=5)
    scheduler._schedule_recovery_observations({moved.name}, now)

    assert len(scheduler.tasks) == 3
    assert any(t is shared for t in scheduler.tasks) and shared.time == shared_deadline
    assert shared.recovery_observation_targets == {"银灰": "dormitory_2"}
    assert shared.recovery_observation_rooms == {"dormitory_2"}
    assert any(t is other for t in scheduler.tasks)
    assert other.time == shared_deadline + timedelta(hours=1)
    assert other.recovery_observation_targets == {"讯使": "dormitory_1"}
    assert other.recovery_observation_rooms == {"dormitory_1"}
    current = next(
        t for t in scheduler.tasks if moved.name in t.recovery_observation_targets
    )
    assert current.time == bed.time
    assert current.recovery_observation_targets == {moved.name: "dormitory_3"}
    assert current.recovery_observation_rooms == {"dormitory_3"}


def test_recovery_observation_reuses_unchanged_task_and_cleans_restored_duplicates(
    resting,
):
    scheduler, now = resting
    name = "伊内丝"
    scheduler.op_data.operators[name].rest_in_full = True
    scheduler.tasks = []
    scheduler._schedule_recovery_observations({name}, now)
    original = scheduler.tasks[0]
    scheduler._schedule_recovery_observations({name}, now)
    assert len(scheduler.tasks) == 1 and scheduler.tasks[0] is original

    scheduler.tasks = jsonpickle.decode(
        jsonpickle.encode([original, deepcopy(original)])
    )
    restored = scheduler.tasks[0]
    scheduler._schedule_recovery_observations({name}, now)
    assert len(scheduler.tasks) == 1 and scheduler.tasks[0] is restored
    assert restored.time == original.time
    assert restored.recovery_observation_targets == {name: "dormitory_1"}
    assert restored.recovery_observation_rooms == {"dormitory_1"}


def test_recovery_observation_preserves_other_refresh_and_retained_tasks(resting):
    scheduler, now = resting
    name = "伊内丝"
    scheduler.op_data.operators[name].rest_in_full = True
    scheduler.tasks = []
    scheduler._schedule_recovery_observations({name}, now)
    retained = scheduler.tasks[0]
    retained.execution_retained = True
    old_deadline = retained.time
    deadline = old_deadline + timedelta(seconds=3)
    scheduler.op_data.get_dorm_by_name(name)[1].time = deadline
    order = SchedulerTask(
        time=deadline, task_type=TaskTypes.REFRESH_TIME, meta_data="room_1_1"
    )
    legacy = SchedulerTask(time=deadline, task_type=TaskTypes.REFRESH_TIME)
    legacy.recovery_observation_rooms = {"dormitory_1"}
    scheduler.tasks.extend([order, legacy])

    scheduler._schedule_recovery_observations({name}, now)

    assert len(scheduler.tasks) == 4
    assert any(t is order for t in scheduler.tasks) and order.time == deadline
    assert order.meta_data == "room_1_1"
    assert not hasattr(order, "recovery_observation_targets")
    assert any(t is legacy for t in scheduler.tasks) and legacy.time == deadline
    assert legacy.recovery_observation_rooms == {"dormitory_1"}
    assert not hasattr(legacy, "recovery_observation_targets")
    assert any(t is retained for t in scheduler.tasks) and retained.time == old_deadline
    assert retained.recovery_observation_targets == {name: "dormitory_1"}
    current = next(
        t
        for t in scheduler.tasks
        if all(t is not old for old in (order, legacy, retained))
    )
    assert current.time == deadline
    assert current.recovery_observation_targets == {name: "dormitory_1"}


@pytest.mark.parametrize("invalid", ["unknown_deadline", "stale_sample", "predicted"])
def test_recovery_observation_without_valid_new_sample_keeps_old_task(resting, invalid):
    scheduler, now = resting
    data = scheduler.op_data
    name = "伊内丝"
    op = data.operators[name]
    op.rest_in_full = True
    scheduler.tasks = []
    scheduler._schedule_recovery_observations({name}, now)
    observation = scheduler.tasks[0]
    deadline = observation.time
    if invalid == "unknown_deadline":
        data.get_dorm_by_name(name)[1].time = None
    elif invalid == "stale_sample":
        op.time_stamp = now - timedelta(seconds=1)
    else:
        op.mood_is_prediction = True

    scheduler._schedule_recovery_observations({name}, now, sampled_after=now)

    assert len(scheduler.tasks) == 1 and scheduler.tasks[0] is observation
    assert observation.time == deadline
    assert observation.recovery_observation_targets == {name: "dormitory_1"}
    assert observation.recovery_observation_rooms == {"dormitory_1"}


def test_executing_recovery_observation_keeps_its_replacement_after_completion(
    resting, monkeypatch
):
    scheduler, _ = resting
    data = scheduler.op_data
    name = "伊内丝"
    op = data.operators[name]
    op.rest_in_full = True
    task = returning_task()
    scheduler.tasks = [task]
    original_time, original_plan = task.time, deepcopy(task.plan)
    monkeypatch.setattr(scheduler, "find", Mock(return_value=True))
    monkeypatch.setattr(scheduler, "skip", Mock())
    monkeypatch.setattr(scheduler, "_product_switching_enabled", lambda: True)
    observed = []

    def read(rooms):
        assert rooms == {"dormitory_1"}
        observed.append(datetime.now())
        op.mood, op.time_stamp, op.mood_is_prediction = 10, observed[-1], False
        data.get_dorm_by_name(name)[1].time = observed[-1] + timedelta(hours=2)

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    executing = scheduler.tasks[0]
    executing.time = datetime.now() - timedelta(seconds=1)
    scheduler.task = executing

    scheduler.infra_main()

    assert len(observed) == 2
    assert all(t is not executing for t in scheduler.tasks)
    assert len(scheduler.tasks) == 1
    replacement = scheduler.tasks[0]
    assert replacement is not executing
    assert replacement.time == data.get_dorm_by_name(name)[1].time
    assert replacement.recovery_observation_targets == {name: "dormitory_1"}
    assert replacement.recovery_observation_rooms == {"dormitory_1"}
    assert len(scheduler.waiting_group_shifts) == 1
    assert scheduler.waiting_group_shifts[0] is task
    assert task.time == original_time and task.plan == original_plan
    assert scheduler.task is None


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


def test_valid_full_sample_does_not_require_redundant_observation(resting, monkeypatch):
    scheduler, _ = resting
    op = scheduler.op_data.operators["讯使"]
    op.rest_in_full, op.mood, op.mood_is_prediction = True, 24, False
    op.time_stamp = datetime.now() - timedelta(hours=1)
    task = returning_task()
    scheduler.tasks = [task]
    monkeypatch.setattr(scheduler, "_read_recovery_rooms", lambda rooms: None)
    assert scheduler._verify_required_recovery(task)
    assert not getattr(task, "execution_failure", None) and scheduler.tasks == [task]


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


@pytest.fixture
def idle_return(resting, monkeypatch):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full, op.time_stamp = True, None
    _, bed = data.get_dorm_by_name(op.name)
    bed.name, bed.time = "", None
    op.current_room, op.current_index = "", -1
    task = returning_task()
    scheduler.tasks, scheduler.task = [task], task
    scheduler._scan_card_moods = Mock()
    monkeypatch.setattr(scheduler, "_read_recovery_rooms", Mock())
    return scheduler, task, op


@pytest.fixture(
    params=[TaskTypes.SHIFT_ON, TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER],
    ids=["shift_on", "self_correction", "re_order"],
)
def ordinary_idle_return(idle_return, request):
    scheduler, task, op = idle_return
    task.type = request.param
    if task.type == TaskTypes.RE_ORDER:
        task.meta_data = "副表内存收敛"
    return scheduler, task, op


@pytest.mark.parametrize("inferred", [False, True])
def test_idle_primary_returns_with_full_card_without_fabricating_measurement(
    ordinary_idle_return, inferred
):
    scheduler, task, op = ordinary_idle_return
    data = scheduler.op_data
    before = deepcopy(vars(op))
    original_time, original_plan = task.time, deepcopy(task.plan)
    estimate = (24, datetime.now())
    if inferred:
        estimate += (False,)
    data.dorm_mood_estimates[op.name] = estimate
    assert scheduler._verify_required_recovery(task)
    assert vars(op) == before
    assert task.plan == original_plan and task.time == original_time
    assert scheduler.tasks == [task]
    scheduler._scan_card_moods.assert_not_called()
    scheduler._read_recovery_rooms.assert_not_called()


def test_idle_unknown_return_observes_cards_before_checking_recovery(
    ordinary_idle_return,
):
    scheduler, task, op = ordinary_idle_return

    def scan(**kwargs):
        scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())

    scheduler._scan_card_moods.side_effect = scan
    assert scheduler._verify_required_recovery(task)
    scheduler._scan_card_moods.assert_called_once_with(current_task=task)
    assert op.time_stamp is None
    assert not getattr(task, "execution_failure", None)


@pytest.mark.parametrize("mood,age", [(0, 0), (23.9, 0), (24, 3600), (24, -1)])
def test_unconfirmed_card_keeps_idle_return_and_original_time(
    ordinary_idle_return, mood, age
):
    scheduler, task, op = ordinary_idle_return
    scheduler.op_data.dorm_mood_estimates[op.name] = (
        mood,
        datetime.now() - timedelta(seconds=age),
    )
    original_time, original_plan = task.time, deepcopy(task.plan)
    assert not scheduler._verify_required_recovery(task)
    assert task.execution_failure
    assert task.plan == original_plan and task.time == original_time
    assert scheduler.tasks == [task]
    assert op.time_stamp is None


def test_newer_green_card_overrides_older_low_measurement(ordinary_idle_return):
    scheduler, task, op = ordinary_idle_return
    op.mood, op.time_stamp = 3.8, datetime.now()
    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    assert scheduler._verify_required_recovery(task)
    scheduler._scan_card_moods.assert_not_called()
    assert op.mood == 3.8


def test_resting_primary_accepts_newer_card_without_room_observation(
    ordinary_idle_return,
):
    scheduler, task, op = ordinary_idle_return
    op.current_room, op.current_index = "dormitory_1", 4
    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    assert scheduler._verify_required_recovery(task)
    scheduler._read_recovery_rooms.assert_not_called()
    scheduler._scan_card_moods.assert_not_called()


def test_card_observation_releases_same_failed_idle_return(ordinary_idle_return):
    scheduler, task, op = ordinary_idle_return
    original_time = task.time
    assert not scheduler._verify_required_recovery(task)
    original_failure = deepcopy(task.execution_failure)
    for _ in range(3):
        scheduler._resume_failed_tasks()
        assert task.execution_failure == original_failure
        assert scheduler.tasks == [task]
    scheduler.op_data.dorm_mood_estimates["无关干员"] = (24, datetime.now())
    scheduler._resume_failed_tasks()
    assert task.execution_failure == original_failure
    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    scheduler._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert scheduler.tasks == [task]
    assert scheduler._verify_required_recovery(task)
    assert task.time == original_time
    assert op.time_stamp is None


@pytest.mark.parametrize("mode", ["rescue", "emergency_task", "support", "strict"])
def test_green_card_satisfies_special_recovery_mood_checks(ordinary_idle_return, mode):
    scheduler, task, op = ordinary_idle_return
    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    if mode == "rescue":
        scheduler.emergency_state = {"phase": "recovering"}
    elif mode == "emergency_task":
        task.emergency_staffing = True
    elif mode == "support":
        task.exhaust_support = True
    else:
        task.strict_mood_limit = True
    assert scheduler._verify_required_recovery(task)
    assert not getattr(task, "execution_failure", None)
    assert op.time_stamp is None
    scheduler._scan_card_moods.assert_not_called()


def test_green_card_satisfies_dorm_release_mood(idle_return):
    scheduler, task, op = idle_return
    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    task.type = TaskTypes.RELEASE_DORM
    assert scheduler._verify_required_recovery(task)
    assert not getattr(task, "execution_failure", None)
    assert op.time_stamp is None
    scheduler._scan_card_moods.assert_not_called()


@pytest.mark.parametrize("change", ["expired", "removed", "yellow", "old-snapshot"])
def test_card_cache_changes_do_not_poll_failed_return(ordinary_idle_return, change):
    scheduler, task, op = ordinary_idle_return
    now = datetime.now()
    scheduler.op_data.dorm_mood_estimates[op.name] = (0, now)
    assert not scheduler._verify_required_recovery(task)
    original_time = task.time
    if change == "expired":
        scheduler.op_data.dorm_mood_estimates[op.name] = (24, now - timedelta(hours=1))
    elif change == "removed":
        scheduler.op_data.dorm_mood_estimates.clear()
    elif change == "yellow":
        scheduler.op_data.dorm_mood_estimates[op.name] = (12, now)
    else:
        task.execution_failure["snapshot"].pop("card_moods", None)
        scheduler.op_data.dorm_mood_estimates[op.name] = (24, now)
    for _ in range(3):
        scheduler._resume_failed_tasks()
        assert task.execution_failure
        assert task.time == original_time
        assert scheduler.tasks == [task]


@pytest.mark.parametrize("full_card", [False, True])
def test_explicit_backup_slot_does_not_exempt_ordinary_return(
    ordinary_idle_return, full_card
):
    scheduler, task, op = ordinary_idle_return
    data = scheduler.op_data
    explicit = Operator(
        "阿罗玛",
        "factory",
        index=0,
        operator_type="high",
        rest_in_full=True,
        mood=3,
        time_stamp=datetime.now(),
    )
    data.add(explicit)
    data.plan[explicit.room] = [Room(explicit.name, "", [])]
    task.plan[explicit.room] = [explicit.name]
    task.backup_explicit_slots = {(explicit.room, explicit.index)}
    if full_card:
        data.dorm_mood_estimates[op.name] = (24, datetime.now())
    original_time, original_plan = task.time, deepcopy(task.plan)
    before = {
        name: deepcopy(vars(member))
        for name, member in ((op.name, op), (explicit.name, explicit))
    }

    assert scheduler._verify_required_recovery(task) is full_card

    assert task.time == original_time and task.plan == original_plan
    assert scheduler.tasks == [task]
    assert vars(op) == before[op.name]
    assert vars(explicit) == before[explicit.name]
    assert bool(getattr(task, "execution_failure", None)) is not full_card
    scheduler._read_recovery_rooms.assert_not_called()


def test_failed_return_releases_dependent_product_task_after_card_and_readback(
    idle_return, monkeypatch
):
    from arknights_mower.tests.dorm_group_tests import apply_plan
    from arknights_mower.utils import config

    scheduler, task, op = idle_return
    config.conf.product_switching.enable = True
    assert not scheduler._verify_required_recovery(task)
    product = SchedulerTask(
        task.time + timedelta(seconds=1),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data="room_2_1,exp3",
    )
    scheduler.tasks.append(product)
    scheduler.task = product
    monkeypatch.setattr(scheduler, "find", Mock(return_value=True))
    original_plan, original_time = deepcopy(task.plan), task.time
    product_time = product.time
    scheduler.infra_main()
    assert product.execution_failure["reason"] == "等待到期换班确认最终产物"
    for _ in range(3):
        scheduler._resume_failed_tasks()
        assert task.execution_failure and product.execution_failure
        assert task.plan == original_plan and task.time == original_time
        assert product.time == product_time

    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    scheduler._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert scheduler._verify_required_recovery(task)
    assert op.time_stamp is None
    assert product.execution_failure
    # 模拟换人后的真实驻员读回；预估本身不提交驻员与产物依赖。
    apply_plan(scheduler, original_plan)
    scheduler._resume_failed_tasks()
    assert not getattr(product, "execution_failure", None)
    assert task.time == original_time and product.time == product_time
    assert any(pending is product for pending in scheduler.tasks)

    scheduler._survey_manufacture_switch = Mock(
        return_value={
            "room": "room_2_1",
            "facility": "manufacture",
            "target_product": "exp3",
            "needs_switch": False,
        }
    )
    scheduler._change_manufacture_product = Mock()
    scheduler.switch_base_products([product])
    scheduler._change_manufacture_product.assert_called_once()
    assert all(pending is not product for pending in scheduler.tasks)


def test_new_green_observation_rearms_overdue_return_before_three_hour_idle(
    idle_return, monkeypatch
):
    from arknights_mower.solvers import base_schedule as base

    scheduler, task, op = idle_return
    assert not scheduler._verify_required_recovery(task)
    future = SchedulerTask(
        datetime.now() + timedelta(hours=3), task_type=TaskTypes.REFRESH_TIME
    )
    scheduler.tasks = [future, task]
    scheduler.op_data.dorm_mood_estimates[op.name] = (24, datetime.now())
    for method in (
        "_refresh_workshop_inventory",
        "_schedule_maintenance_backup_check",
        "handle_idle_action",
        "_idle_sleep",
        "check_current_focus",
    ):
        monkeypatch.setattr(scheduler, method, Mock())
    scheduler.task_count = 0
    monkeypatch.setattr(base, "send_message", Mock())
    monkeypatch.setattr(base.task_template, "render", Mock(return_value=""))
    original_time = task.time
    scheduler.rest_until_next_task()
    scheduler._idle_sleep.assert_not_called()
    assert not getattr(task, "execution_failure", None)
    assert scheduler.tasks[0] is task
    assert task.time == original_time


def test_unresolved_return_idle_reports_why_original_task_is_not_dispatched(
    idle_return, monkeypatch, caplog
):
    from arknights_mower.solvers import base_schedule as base

    scheduler, task, _ = idle_return
    assert not scheduler._verify_required_recovery(task)
    original_time, original_plan = task.time, deepcopy(task.plan)
    future = SchedulerTask(
        datetime.now() + timedelta(hours=3), task_type=TaskTypes.REFRESH_TIME
    )
    scheduler.tasks = [future, task]
    for method in (
        "_refresh_workshop_inventory",
        "_schedule_maintenance_backup_check",
        "handle_idle_action",
        "_idle_sleep",
        "check_current_focus",
    ):
        monkeypatch.setattr(scheduler, method, Mock())
    scheduler.task_count = 0
    monkeypatch.setattr(base, "send_message", Mock())
    monkeypatch.setattr(base.task_template, "render", Mock(return_value=""))
    scheduler.rest_until_next_task()
    assert task.execution_failure
    assert task.time == original_time and task.plan == original_plan
    scheduler._idle_sleep.assert_called_once()
    assert "未完成任务暂停派发：原时间=" in caplog.text
    assert "原因=需要回满的主班心情尚未满足要求，且缺少有效恢复期限" in caplog.text


@pytest.mark.parametrize("newer_card", [False, True])
def test_latest_mood_decides_return_without_changing_time_evidence(
    ordinary_idle_return, newer_card
):
    scheduler, task, op = ordinary_idle_return
    now = datetime.now()
    op.mood, op.time_stamp, op.depletion_rate = 3.8, now, 0.75
    op.exhaust_time = now + timedelta(hours=3)
    scheduler.op_data.dorm_mood_estimates[op.name] = (
        24,
        now + timedelta(seconds=-1 if not newer_card else 0),
    )
    if newer_card:
        op.time_stamp = now - timedelta(seconds=1)
    before = deepcopy(vars(op))
    assert scheduler._verify_required_recovery(task) is newer_card
    assert vars(op) == before
    assert not any(
        getattr(t, "recovery_observation_targets", None) for t in scheduler.tasks
    )


def test_fixed_slot_countdown_survives_restart_and_wakes_original_task(
    resting, monkeypatch
):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    old_bed = data.get_dorm_by_name(op.name)[1]
    old_bed.name, old_bed.time = "", None
    data.get_current_operator("dormitory_1", 1).current_room = ""
    op.current_room, op.current_index = "dormitory_1", 1
    op.rest_in_full = True
    task = returning_task()
    scheduler.tasks = [task]
    original_time, original_plan = task.time, deepcopy(task.plan)
    deadline = datetime.now() + timedelta(hours=3)

    def read(rooms):
        assert rooms == {"dormitory_1"}
        op.mood, op.time_stamp, op.mood_is_prediction = 12, datetime.now(), False
        data.refresh_dorm_time(op.current_room, 1, {"agent": op.name, "time": deadline})

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    assert data.get_dorm_by_name(op.name)[1] is None
    assert not getattr(task, "execution_failure", None)
    assert scheduler.waiting_group_shifts == [task]
    assert scheduler.tasks[0].time == deadline
    observation = deepcopy(op.dorm_recovery_observation)
    restored = pickle.loads(pickle.dumps(op))
    assert restored.dorm_recovery_observation == observation
    for _ in range(3):
        scheduler._resume_waiting_group_shifts()
        assert scheduler.waiting_group_shifts == [task]
        assert len(scheduler.tasks) == 1
    data.dorm_mood_estimates[op.name] = (24, datetime.now())
    scheduler._resume_waiting_group_shifts()
    assert not scheduler.waiting_group_shifts and task in scheduler.tasks
    assert task.time == original_time
    assert all(task.plan[room] == row for room, row in original_plan.items())
    assert op.mood == 12 and op.dorm_recovery_observation == observation
    data.invalidate_dorm_time(op.current_room)
    assert op.dorm_recovery_observation is None
    read({"dormitory_1"})
    op.current_index = 0
    assert op.dorm_recovery_observation is None


def test_unchanged_low_observation_does_not_resume_on_clock_alone(resting):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full, op.mood = True, 23.9
    op.time_stamp = datetime.now() - timedelta(minutes=10)
    data.get_dorm_by_name(op.name)[1].time = datetime.now() + timedelta(seconds=60)
    task = returning_task()
    scheduler.tasks = [task]
    task.recovery_waiting_observations = {op.name: op.time_stamp}
    scheduler._suspend_group_shift(task, set())
    original_time = task.time
    for _ in range(3):
        scheduler._resume_waiting_group_shifts()
        assert scheduler.waiting_group_shifts == [task]
        assert task not in scheduler.tasks
    data.dorm_mood_estimates[op.name] = (24, datetime.now())
    scheduler._resume_waiting_group_shifts()
    assert not scheduler.waiting_group_shifts and task in scheduler.tasks
    assert task.time == original_time and op.mood == 23.9


def test_newer_low_card_cannot_use_an_older_near_full_countdown(resting):
    from arknights_mower.utils.recovery_execution import recovery_ready_for_arrangement

    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    now = datetime.now()
    op.mood, op.time_stamp = 23.9, now - timedelta(minutes=1)
    data.get_dorm_by_name(op.name)[1].time = now + timedelta(seconds=60)
    data.dorm_mood_estimates[op.name] = (6, now)
    assert not recovery_ready_for_arrangement(
        data, op.name, sampled_after=None, now=now
    )
    assert op.mood == 23.9
