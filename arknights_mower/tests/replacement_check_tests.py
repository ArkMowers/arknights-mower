"""普通替班的单次心情检查保留观测来源、原任务和失败期限。"""

import pickle
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from itertools import cycle
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", Mock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import record  # noqa: E402
from arknights_mower.utils import (  # noqa: E402
    operators,
    replacement_check,
    resting_correction,
    scheduler_task,  # noqa: E402
)
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.device.adb_client.server import SharedADBError  # noqa: E402
from arknights_mower.utils.device.recovery import DeviceRecoveryError  # noqa: E402
from arknights_mower.utils.operators import Dormitory, Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.recognize import RecognizeError  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    find_next_task,
    scheduling,
)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.current


@pytest.fixture
def clock(monkeypatch):
    Clock.current = Clock(2026, 10, 18, 1)
    for module in (
        base,
        operators,
        scheduler_task,
        replacement_check,
        resting_correction,
    ):
        monkeypatch.setattr(module, "datetime", Clock)
    return Clock


@pytest.fixture
def replacement_solver(clock, monkeypatch):
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(record, "save_agent_action", lambda *args, **kwargs: None)
    data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    data.plan = {
        "central": [Room("歌蕾蒂娅", "", ["薇薇安娜", "赫默"])],
        "dormitory_1": [Room("Free", "", []) for _ in range(5)],
    }
    primary = Operator(
        "歌蕾蒂娅",
        "central",
        index=0,
        replacement=["薇薇安娜", "赫默"],
        operator_type="high",
        mood=2,
        time_stamp=clock.now(),
        current_room="dormitory_1",
        current_index=2,
    )
    cover = Operator(
        "薇薇安娜",
        "",
        mood=24,
        time_stamp=clock.now(),
        current_room="central",
        current_index=0,
    )
    spare = Operator("赫默", "", mood=20, time_stamp=clock.now())
    data.operators = {op.name: op for op in (primary, cover, spare)}
    data.dorm = [
        Dormitory(("dormitory_1", 2), primary.name, clock.now() + timedelta(hours=7))
    ]
    solver = SimpleNamespace(
        op_data=data,
        tasks=[],
        task=None,
        enter_room=Mock(),
        back=Mock(),
        _protected_training_names=lambda: set(),
        _initial_mood_read_pending=lambda: False,
        _emergency_frozen=lambda: False,
    )
    solver._task_failure_snapshot = MethodType(
        base.BaseSchedulerSolver._task_failure_snapshot, solver
    )
    solver._retain_failed_task = MethodType(
        base.BaseSchedulerSolver._retain_failed_task, solver
    )
    solver._resume_failed_tasks = MethodType(
        base.BaseSchedulerSolver._resume_failed_tasks, solver
    )
    solver._discard_legacy_ordinary_requests = MethodType(
        base.BaseSchedulerSolver._discard_legacy_ordinary_requests, solver
    )
    solver._refresh_derived_correction = MethodType(
        base.BaseSchedulerSolver._refresh_derived_correction, solver
    )
    solver.reading = {
        "agent": cover.name,
        "mood": 24,
        "time": clock.now() + timedelta(hours=4),
    }

    def read(room, indices, **kwargs):
        observed = deepcopy(solver.reading)
        if observed.get("observed", True) and observed.get("agent") == cover.name:
            mood = observed.get("mood")
            if isinstance(mood, (int, float)) and 0 <= mood <= 24:
                data.update_detail(cover.name, mood, room, indices[0], True)
        return [observed]

    solver.get_agent_from_room = Mock(side_effect=read)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    return solver


def _bootstrap(solver):
    replacement_check.sync_replacement_checks(solver)
    assert len(solver.tasks) == 1
    task = solver.tasks[0]
    assert replacement_check.run_replacement_check(solver, task) is False
    return task


def test_bootstrap_reads_work_timer_even_with_full_mood(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)

    assert task.type == TaskTypes.NOT_SPECIFIC and task.plan == {}
    assert task.time == clock.now() + timedelta(hours=4)
    solver.get_agent_from_room.assert_called_once_with(
        "central",
        [0],
        force_mood=True,
        strict_observation=True,
        force_working_time=True,
    )
    solver.back.assert_called_once()


def test_bootstrap_ignores_unknown_legacy_work_segment(replacement_solver, clock):
    solver = replacement_solver
    cover = solver.op_data.operators["薇薇安娜"]
    cover.depletion_rate = 9
    cover.time_stamp = clock.now() - timedelta(hours=1)
    replacement_check.sync_replacement_checks(solver)

    assert solver.tasks[0].time == clock.now()
    assert solver.get_agent_from_room.call_count == 0


def test_personal_floor_uses_exact_remaining_fraction(replacement_solver, clock):
    solver = replacement_solver
    solver.op_data.operators["薇薇安娜"].lower_limit = 6
    solver.reading.update(mood=12, time=clock.now() + timedelta(hours=4))

    task = _bootstrap(solver)

    assert task.time == clock.now() + timedelta(hours=2)


def test_unchanged_sync_keeps_object_and_deadline(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)
    original_time = task.time
    for _ in range(5):
        clock.current += timedelta(minutes=10)
        replacement_check.sync_replacement_checks(solver)
        assert solver.tasks == [task] and solver.tasks[0] is task
        assert task.time == original_time
    solver.get_agent_from_room.assert_called_once()


def _prepare_same_room_reader(solver, clock, count):
    data = solver.op_data
    covers = [data.operators["薇薇安娜"]]
    for index, (owner_name, cover_name) in enumerate(
        [("陈", "红隼"), ("阿米娅", "临光")][: count - 1], 1
    ):
        data.plan["central"].append(Room(owner_name, "", [cover_name, "赫默"]))
        data.operators[owner_name] = Operator(
            owner_name,
            "central",
            index=index,
            replacement=[cover_name, "赫默"],
            operator_type="high",
            mood=2,
            time_stamp=clock.now(),
        )
        cover = Operator(
            cover_name,
            "",
            mood=20,
            time_stamp=clock.now(),
            current_room="central",
            current_index=index,
        )
        data.operators[cover_name] = cover
        covers.append(cover)
    deadlines = [clock.now() + timedelta(hours=4 + index) for index in range(count)]
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
    )
    solver._can_refresh_idle_dorm_search = lambda: False
    solver.refresh_facility_state = Mock()
    solver.turn_on_room_detail = Mock()
    solver.wait_product_complete = Mock()
    solver.find = Mock(return_value=None)
    solver.read_screen = Mock(side_effect=cycle(op.name for op in covers))
    solver.read_accurate_mood = Mock(side_effect=cycle(op.mood for op in covers))
    solver.read_operator_time = Mock(
        side_effect=lambda room, index, scope: deadlines[index]
    )
    solver.get_agent_from_room = MethodType(
        base.BaseSchedulerSolver.get_agent_from_room, solver
    )
    solver._reconcile_room_observation = MethodType(
        base.BaseSchedulerSolver._reconcile_room_observation, solver
    )
    return covers, deadlines


@pytest.mark.parametrize("count", [2, 3])
def test_same_room_checks_keep_deadlines_after_full_room_reads(
    replacement_solver, clock, count
):
    solver = replacement_solver
    data = solver.op_data
    covers, deadlines = _prepare_same_room_reader(solver, clock, count)
    solver.read_accurate_mood.side_effect = [
        op.mood - step / 10 for step in range(count) for op in covers
    ]
    replacement_check.sync_replacement_checks(solver)
    checks = list(solver.tasks)

    for task in checks:
        clock.current += timedelta(seconds=6)
        assert replacement_check.run_replacement_check(solver, task) is False
        replacement_check.sync_replacement_checks(solver)

    independent = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(3):
        replacement_check.sync_replacement_checks(solver)
        assert [task.time for task in checks] == deadlines
        scheduling(solver.tasks, time_now=clock.now(), op_data=data)
        assert find_next_task(solver.tasks) is independent
    assert solver.read_operator_time.call_count == count
    assert data.room_observations["central"] == count


@pytest.mark.parametrize("partial_read", [False, True])
def test_same_room_failed_checks_wait_for_candidate_release(
    replacement_solver, clock, partial_read
):
    solver = replacement_solver
    data = solver.op_data
    covers, _ = _prepare_same_room_reader(solver, clock, 2)
    for cover in covers:
        cover.mood = cover.lower_limit = 6
    solver.read_accurate_mood.side_effect = None
    solver.read_accurate_mood.return_value = 6
    spare = data.operators["赫默"]
    spare.current_room, spare.current_index = "meeting", 0
    replacement_check.sync_replacement_checks(solver)
    checks = list(solver.tasks)
    original_times = [task.time for task in checks]

    for index, task in enumerate(checks):
        clock.current += timedelta(seconds=6)
        if index == 1 and partial_read:
            solver.read_accurate_mood.side_effect = [6, RecognizeError("未确认")]
        assert replacement_check.run_replacement_check(solver, task) is False
        assert task.execution_failure
        replacement_check.sync_replacement_checks(solver)

    independent = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(4):
        clock.current += timedelta(minutes=5)
        replacement_check.sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        assert all(any(queued is task for queued in solver.tasks) for task in checks)
        assert [task.time for task in checks] == original_times
        assert all(getattr(task, "execution_failure", None) for task in checks)
        scheduling(solver.tasks, time_now=clock.now(), op_data=data)
        assert find_next_task(solver.tasks) is independent
    assert solver.enter_room.call_count == 2
    assert solver.read_operator_time.call_count == (1 if partial_read else 2)
    assert data.room_observations["central"] == (1 if partial_read else 2)

    solver.read_accurate_mood.side_effect = None
    data.update_detail(spare.name, 20, "", -1, True)
    replacement_check.sync_replacement_checks(solver)
    solver._resume_failed_tasks()
    assert not getattr(checks[0], "execution_failure", None)
    assert checks[0].retains_execution and checks[0].time == original_times[0]
    assert replacement_check.run_replacement_check(solver, checks[0]) is True
    assert solver.tasks[-1].plan == {"central": [spare.name, "Current"]}
    assert solver.enter_room.call_count == 3


@pytest.mark.parametrize("during_read", [False, True])
def test_peer_check_does_not_consume_candidate_release(
    replacement_solver, clock, during_read
):
    solver = replacement_solver
    covers, _ = _prepare_same_room_reader(solver, clock, 2)
    for cover in covers:
        cover.mood = cover.lower_limit = 6
    solver.read_accurate_mood.side_effect = None
    solver.read_accurate_mood.return_value = 6
    spare = solver.op_data.operators["赫默"]
    spare.current_room, spare.current_index = "meeting", 0
    replacement_check.sync_replacement_checks(solver)
    first, second = solver.tasks
    assert replacement_check.run_replacement_check(solver, first) is False
    assert first.execution_failure
    clock.current += timedelta(seconds=6)

    def release(*args):
        solver.op_data.update_detail(spare.name, 20, "", -1, True)

    if during_read:
        solver.refresh_facility_state.side_effect = release
    else:
        release()
    assert replacement_check.run_replacement_check(solver, second) is True
    solver._resume_failed_tasks()

    assert not getattr(first, "execution_failure", None)
    assert first.retains_execution


def test_new_measured_floor_advances_existing_check(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current += timedelta(minutes=10)
    solver.op_data.update_detail("薇薇安娜", 0, "central", 0, True)

    replacement_check.sync_replacement_checks(solver)

    assert solver.tasks[0] is task and task.time == clock.now()
    solver.reading.update(mood=0, time=clock.now())
    assert replacement_check.run_replacement_check(solver, task) is True
    assert solver.tasks[-1].plan == {"central": ["赫默"]}


def test_new_observation_above_floor_keeps_deadline_after_pickle(
    replacement_solver, clock
):
    solver = replacement_solver
    task = _bootstrap(solver)
    deadline = task.time
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    restored = solver.tasks[0]
    clock.current += timedelta(minutes=10)
    solver.op_data.update_detail("薇薇安娜", 20, "central", 0, True)

    replacement_check.sync_replacement_checks(solver)

    assert solver.tasks[0] is restored and restored.time == deadline


@pytest.mark.parametrize(
    "change", ["primary_returns", "cover_leaves", "removed", "sole", "zero_work"]
)
def test_irrelevant_check_is_removed(replacement_solver, change):
    solver = replacement_solver
    task = _bootstrap(solver)
    data = solver.op_data
    if change == "primary_returns":
        data.operators["薇薇安娜"].current_room = ""
        data.operators["歌蕾蒂娅"].current_room = "central"
        data.operators["歌蕾蒂娅"].current_index = 0
    elif change == "cover_leaves":
        data.operators["薇薇安娜"].current_room = ""
    elif change in ("removed", "sole"):
        replacements = ["赫默"] if change == "removed" else ["薇薇安娜"]
        data.operators["歌蕾蒂娅"].replacement = replacements
        data.plan["central"][0].replacement = replacements
    else:
        data.config.workaholic = ["薇薇安娜"]

    replacement_check.sync_replacement_checks(solver)

    assert not any(queued is task for queued in solver.tasks)


@pytest.mark.parametrize("change", ["product", "occupant", "refresh_drained"])
def test_work_environment_change_requests_one_new_read(
    replacement_solver, clock, change
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current += timedelta(minutes=10)
    if change == "product":
        solver.op_data.products["central"] = "changed"
    elif change == "occupant":
        other = Operator("砾", "", current_room="central", current_index=1)
        solver.op_data.operators[other.name] = other
    else:
        replacement_check.invalidate_replacement_checks(solver)

    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks[0] is task and task.time == clock.now()
    solver.reading["time"] = clock.now() + timedelta(hours=2)
    assert replacement_check.run_replacement_check(solver, task) is False
    assert task.time == clock.now() + timedelta(hours=2)
    replacement_check.sync_replacement_checks(solver)
    assert task.time == clock.now() + timedelta(hours=2)


def test_due_check_uses_real_matching_and_retains_primary_rest(
    replacement_solver, clock
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())

    assert replacement_check.run_replacement_check(solver, task) is True

    corrections = [
        queued for queued in solver.tasks if queued.type == TaskTypes.SELF_CORRECTION
    ]
    assert [queued.plan for queued in corrections] == [{"central": ["赫默"]}]
    assert solver.op_data.operators["歌蕾蒂娅"].is_resting()
    assert solver.op_data.operators["薇薇安娜"].current_room == "central"
    assert solver.op_data.dorm[0].name == "歌蕾蒂娅"


@pytest.mark.parametrize(
    "reading",
    [
        {"agent": "薇薇安娜", "observed": False, "mood": 0},
        {"agent": "薇薇安娜", "mood": -1},
        {"agent": "薇薇安娜", "mood": float("nan")},
        {"agent": "薇薇安娜", "mood": 10, "time": None},
        {"agent": "薇薇安娜", "mood": 10},
        {"mood": 0},
    ],
)
def test_unknown_reading_is_retained_without_new_timer(
    replacement_solver, clock, reading
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading = reading
    original_time = task.time

    assert replacement_check.run_replacement_check(solver, task) is False

    assert task.time == original_time and task.execution_failure
    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks[0] is task and task.time == original_time
    assert not [
        queued for queued in solver.tasks if queued.type == TaskTypes.SELF_CORRECTION
    ]


def test_missing_countdown_with_remaining_mood_does_not_mean_exhaustion(
    replacement_solver, clock
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=10, time=clock.now())

    assert replacement_check.run_replacement_check(solver, task) is False
    assert task.execution_failure and task.time == clock.now()
    assert len(solver.tasks) == 1


def test_failed_read_uses_existing_retention(replacement_solver):
    solver = replacement_solver
    replacement_check.sync_replacement_checks(solver)
    task = solver.tasks[0]
    solver.get_agent_from_room.side_effect = RecognizeError("未确认")

    assert replacement_check.run_replacement_check(solver, task) is False
    assert task.execution_failure["rooms"] == ("central",)


@pytest.mark.parametrize("error", [MowerExit, DeviceRecoveryError, SharedADBError])
def test_cancellation_and_device_failure_propagate(replacement_solver, error):
    solver = replacement_solver
    replacement_check.sync_replacement_checks(solver)
    solver.get_agent_from_room.side_effect = error("stop")

    with pytest.raises(error):
        replacement_check.run_replacement_check(solver, solver.tasks[0])


def test_unavailable_cover_does_not_rearm_from_its_own_read(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.op_data.operators["赫默"].current_room = "meeting"
    solver.op_data.operators["赫默"].current_index = 0
    solver.reading.update(mood=0, time=clock.now())

    assert replacement_check.run_replacement_check(solver, task) is False
    failed_source = deepcopy(replacement_check.replacement_check_snapshot(solver, task))
    original_time = task.time
    independent = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(4):
        clock.current += timedelta(hours=1)
        replacement_check.sync_replacement_checks(solver)
        assert (
            replacement_check.replacement_check_snapshot(solver, task) == failed_source
        )
        assert task.execution_failure and task.time == original_time
        scheduling(solver.tasks, time_now=clock.now(), op_data=solver.op_data)
        assert find_next_task(solver.tasks) is independent


def test_snapshot_tracks_remote_candidate_release_and_reservation(replacement_solver):
    solver = replacement_solver
    replacement_check.sync_replacement_checks(solver)
    task = solver.tasks[0]
    spare = solver.op_data.operators["赫默"]
    spare.current_room, spare.current_index = "meeting", 0
    occupied = replacement_check.replacement_check_snapshot(solver, task)
    spare.current_room, spare.current_index = "", -1
    released = replacement_check.replacement_check_snapshot(solver, task)
    assert occupied != released
    reservation = SchedulerTask(
        task_plan={"meeting": ["赫默"]}, task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks.append(reservation)
    assert replacement_check.replacement_check_snapshot(solver, task) != released
    solver.tasks.remove(reservation)
    assert replacement_check.replacement_check_snapshot(solver, task) == released


def test_reserved_spare_waits_without_arranging_another_room(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())
    solver.tasks.append(
        SchedulerTask(task_plan={"meeting": ["赫默"]}, task_type=TaskTypes.SHIFT_OFF)
    )

    assert replacement_check.run_replacement_check(solver, task) is False
    assert task.execution_failure
    assert not any(queued.type == TaskTypes.SELF_CORRECTION for queued in solver.tasks)


def test_pickle_preserves_deadline_source_and_failed_state(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())
    solver.op_data.operators["赫默"].mood = 0
    assert replacement_check.run_replacement_check(solver, task) is False
    old_source = deepcopy(task.replacement_check_source)
    original_time = task.time
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    restored = solver.tasks[0]

    assert restored.time == original_time
    assert restored.replacement_check_source == old_source
    assert restored.execution_failure
    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks[0] is restored and restored.time == original_time


def test_future_primary_return_does_not_hide_replacement_check(
    replacement_solver, clock
):
    solver = replacement_solver
    returning = SchedulerTask(
        clock.now() + timedelta(hours=7),
        {"central": ["歌蕾蒂娅"]},
        TaskTypes.SHIFT_ON,
    )
    solver.tasks.append(returning)

    replacement_check.sync_replacement_checks(solver)

    checks = [task for task in solver.tasks if getattr(task, "replacement_check", None)]
    assert len(checks) == 1 and checks[0].time == clock.now()
    assert any(task is returning for task in solver.tasks)


def test_changed_primary_cancels_old_check_and_bootstraps_new_owner(replacement_solver):
    solver = replacement_solver
    old = _bootstrap(solver)
    owner = solver.op_data.operators.pop("歌蕾蒂娅")
    owner.name = "陈"
    solver.op_data.operators[owner.name] = owner
    solver.op_data.plan["central"][0].agent = owner.name

    replacement_check.sync_replacement_checks(solver)

    assert len(solver.tasks) == 1 and solver.tasks[0] is not old
    assert solver.tasks[0].replacement_check["owner"] == owner.name


def test_concrete_correction_prevents_duplicate_bootstrap(replacement_solver, clock):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())
    assert replacement_check.run_replacement_check(solver, task) is True
    solver.tasks[:] = [queued for queued in solver.tasks if queued is not task]

    replacement_check.sync_replacement_checks(solver)

    assert len(solver.tasks) == 1 and solver.tasks[0].type == TaskTypes.SELF_CORRECTION


def test_failed_check_keeps_identity_despite_due_other_arrangement(
    replacement_solver, clock
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())
    solver.op_data.operators["赫默"].mood = 0
    assert replacement_check.run_replacement_check(solver, task) is False
    deadline = task.time
    solver.tasks.append(SchedulerTask(task_plan={"central": ["赫默"]}))
    clock.current += timedelta(hours=1)

    replacement_check.invalidate_replacement_checks(solver)
    replacement_check.sync_replacement_checks(solver)

    assert any(queued is task for queued in solver.tasks)
    assert task.time == deadline and task.execution_failure


def test_resumed_check_finishes_before_scheduling_next_deadline(
    replacement_solver, clock
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())
    solver.op_data.operators["赫默"].mood = 0
    assert replacement_check.run_replacement_check(solver, task) is False
    original_time = task.time
    clock.current += timedelta(hours=1)
    replacement_check.invalidate_replacement_checks(solver)
    replacement_check.sync_replacement_checks(solver)
    solver._resume_failed_tasks()
    assert task.retains_execution and not getattr(task, "execution_failure", None)
    solver.reading.update(mood=12, time=clock.now() + timedelta(hours=3))

    assert replacement_check.run_replacement_check(solver, task) is True

    assert task.time == original_time
    successors = [queued for queued in solver.tasks if queued is not task]
    assert len(successors) == 1
    successor = successors[0]
    assert successor.time == clock.now() + timedelta(hours=3)
    assert not successor.retains_execution
    solver.tasks[:] = [successor]
    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks[0] is successor


def test_prediction_and_prediction_invalidation_do_not_reopen_failure(
    replacement_solver, clock
):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.op_data.operators["赫默"].mood = 0
    solver.reading.update(mood=0, time=clock.now())
    assert replacement_check.run_replacement_check(solver, task) is False
    original_time = task.time
    cover = solver.op_data.operators["薇薇安娜"]
    cover.mood_is_prediction = True
    for mood in (1, 5, 10):
        cover.mood = mood
        cover.depletion_rate = mood / 2
        replacement_check.sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        assert task.execution_failure and task.time == original_time
    cover.time_stamp = None
    cover.mood_is_prediction = False
    replacement_check.sync_replacement_checks(solver)
    solver._resume_failed_tasks()
    assert task.execution_failure and task.time == original_time


def test_unconfirmed_room_cache_is_retained(replacement_solver, clock, monkeypatch):
    solver = replacement_solver
    task = _bootstrap(solver)
    clock.current = task.time
    solver.reading.update(mood=0, time=clock.now())
    monkeypatch.setattr(solver.op_data, "get_current_room", lambda *args: None)

    assert replacement_check.run_replacement_check(solver, task) is False
    assert task.execution_failure
