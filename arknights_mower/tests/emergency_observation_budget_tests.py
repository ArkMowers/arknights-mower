"""智能救急逐房复查让出严格清退窗口并保存未完成房间。"""

import copy
import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, emergency, record
from arknights_mower.tests import mass_mood_recovery_tests
from arknights_mower.tests.automatic_rescue_tests import make_episode
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.utils import (
    emergency_recovery,
    operation_timing,
    operators,
    resting_correction,
    scheduler_task,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    protect_priority_tasks,
)

legacy_solver = mass_mood_recovery_tests.solver


@pytest.fixture
def observation_solver(legacy_solver, monkeypatch):
    solver = legacy_solver
    clock = {"now": NOW}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    for module in (
        base_schedule,
        emergency,
        emergency_recovery,
        operators,
        resting_correction,
        scheduler_task,
    ):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    monkeypatch.setattr(emergency, "emergency_mood_history", lambda name: [])
    monkeypatch.setattr(emergency, "try_workshop_tasks", MagicMock())
    state = make_episode(solver)
    state["phase"] = "staffing"
    state["next_read"] = NOW
    data = solver.op_data
    for name in PRIMARY:
        op = data.operators[name]
        data.update_detail(name, 8, op.current_room, op.current_index, True)
    limited = COVERS[0]
    data.config.operator_mood_limits = {limited: {"lower": 0, "upper": 12}}
    data.init_mood_limit()
    data.update_detail(limited, 10, "dormitory_1", 2, True)
    reads, saves = [], []

    def read_room(room, *args, **kwargs):
        assert kwargs["force_mood"]
        reads.append(room)
        clock["now"] += timedelta(seconds=30)
        return [
            {"agent": op.name}
            for op in solver.op_data.operators.values()
            if op.current_room == room
        ]

    def save():
        saves.append(copy.deepcopy(solver.emergency_state))
        return True

    monkeypatch.setattr(emergency, "save_current_state", save)
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock(side_effect=read_room)
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver._read_initial_card_mood = MagicMock()
    solver._emergency_collect = MagicMock(wraps=solver._emergency_collect)
    solver._emergency_update_targets = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_restore = MagicMock(return_value=False)
    solver._emergency_schedule_staffing = MagicMock(return_value=False)
    solver._emergency_scan_workers = MagicMock()
    solver._emergency_plan_beds = MagicMock()
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.run_order_solver = MagicMock()
    return SimpleNamespace(
        solver=solver,
        state=state,
        clock=clock,
        reads=reads,
        saves=saves,
        limited=limited,
        rooms=sorted(data.plan),
    )


def set_release_window(episode, seconds):
    solver = episode.solver
    _, bed = solver.op_data.get_dorm_by_name(episode.limited)
    bed.time = NOW + timedelta(seconds=seconds + 90)
    solver.plan_metadata()
    protect_priority_tasks(solver.tasks)
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert release.time == NOW + timedelta(seconds=seconds)
    assert release.mood_limit_deadline == bed.time
    return release


def finish_release(episode, release):
    episode.clock["now"] = release.mood_limit_deadline
    episode.solver.op_data.update_detail(episode.limited, 12, "", -1, True)
    episode.solver.op_data.operators[episode.limited].rest_mood_release_limit = 12
    episode.solver.tasks[:] = [
        task
        for task in episode.solver.tasks
        if not (
            task.strict_mood_limit and episode.limited in task.release_dorm_targets()
        )
    ]
    episode.state["next_read"] = episode.clock["now"]


@pytest.mark.parametrize("window, expected_reads", [(90, 0), (120, 1), (150, 2)])
def test_due_observation_yields_each_room_before_strict_release(
    observation_solver, window, expected_reads
):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, window)
    if window == 90:
        solver.last_execution["todo"] = NOW - timedelta(minutes=20)

    solver._emergency_tick()

    assert episode.reads == episode.rooms[:expected_reads]
    assert episode.clock["now"] < release.time
    assert episode.state["pending_read_rooms"] == episode.rooms[expected_reads:]
    assert episode.state["next_read"] == episode.clock["now"] + timedelta(minutes=1)
    assert episode.saves[-1]["pending_read_rooms"] == episode.rooms[expected_reads:]
    solver._emergency_update_targets.assert_not_called()
    solver._emergency_ready.assert_not_called()
    solver._emergency_restore.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()
    solver._emergency_scan_workers.assert_not_called()
    if window == 90:
        solver._emergency_collect.assert_not_called()


def test_observation_continues_only_unread_rooms_after_release(observation_solver):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 120)

    solver._emergency_tick()

    assert episode.reads == episode.rooms[:1]
    episode.clock["now"] = episode.state["next_read"]
    solver._emergency_tick()
    assert episode.reads == episode.rooms[:1]
    assert episode.state["pending_read_rooms"] == episode.rooms[1:]
    solver._emergency_collect.assert_called_once()
    solver._emergency_update_targets.assert_not_called()
    solver._emergency_ready.assert_not_called()
    solver._emergency_restore.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()

    finish_release(episode, release)
    solver._emergency_tick()

    assert episode.reads == episode.rooms
    assert not episode.state.get("pending_read_rooms")
    solver._emergency_collect.assert_called_once()
    solver._emergency_update_targets.assert_called_once()
    solver._emergency_ready.assert_called_once()
    solver._emergency_schedule_staffing.assert_called_once()


def test_due_observation_plans_new_strict_release_before_any_room(observation_solver):
    episode = observation_solver
    solver = episode.solver
    _, bed = solver.op_data.get_dorm_by_name(episode.limited)
    bed.time = NOW + timedelta(seconds=180)
    assert not solver.tasks
    solver.last_execution["todo"] = NOW - timedelta(minutes=20)

    solver._emergency_tick()

    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert release.time == NOW + timedelta(seconds=90)
    assert release.mood_limit_deadline == NOW + timedelta(seconds=180)
    assert not episode.reads
    assert episode.state["pending_read_rooms"] == episode.rooms
    solver._emergency_collect.assert_not_called()
    solver._emergency_ready.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


def test_each_room_uses_its_recorded_operation_budget(observation_solver):
    episode = observation_solver
    solver = episode.solver
    operation_timing._dorm_durations["room_1_1"] = [100]
    release = set_release_window(episode, 150)

    solver._emergency_tick()

    assert episode.reads == ["dormitory_1"]
    assert episode.clock["now"] < release.time
    assert episode.state["pending_read_rooms"] == episode.rooms[1:]
    assert operation_timing.estimate_dorm_minutes("room_1_1") * 60 == 135
    solver._emergency_update_targets.assert_not_called()
    solver._emergency_ready.assert_not_called()


def test_partial_observation_advances_existing_check_wakeup(observation_solver):
    episode = observation_solver
    solver = episode.solver
    check = SchedulerTask(
        time=NOW + timedelta(minutes=30), meta_data=emergency.CHECK_META
    )
    solver.tasks.append(check)
    set_release_window(episode, 120)

    solver._emergency_tick()

    assert episode.reads == episode.rooms[:1]
    assert check.time == episode.state["next_read"]
    assert check.time == episode.clock["now"] + timedelta(minutes=1)
    assert [
        task for task in solver.tasks if task.meta_data == emergency.CHECK_META
    ] == [check]


def test_collection_consumes_observation_window_before_first_room(observation_solver):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 120)

    def collect():
        episode.clock["now"] += timedelta(seconds=30)

    solver._emergency_collect = MagicMock(side_effect=collect)

    solver._emergency_tick()

    solver._emergency_collect.assert_called_once()
    assert not episode.reads
    assert episode.clock["now"] < release.time
    assert episode.state["pending_read_rooms"] == episode.rooms
    solver._emergency_update_targets.assert_not_called()
    solver._emergency_ready.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


def test_restart_preserves_partial_observation_before_release(observation_solver):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 120)
    episode.reads.append(episode.rooms[0])
    episode.clock["now"] += timedelta(seconds=30)
    episode.state["pending_read_rooms"] = episode.rooms[1:]
    episode.state["next_read"] = episode.clock["now"] + timedelta(minutes=1)
    solver._emergency_save()
    persisted = pickle.loads(pickle.dumps(episode.saves[-1]))
    solver.emergency_state = persisted
    episode.state = persisted
    solver.op_data = pickle.loads(pickle.dumps(solver.op_data))
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    solver._emergency_startup_pending = True

    solver._emergency_startup()

    assert episode.reads == episode.rooms[:1]
    assert persisted["pending_read_rooms"] == episode.rooms[1:]
    assert "observed_at" not in persisted
    assert not solver._emergency_startup_pending
    finish_release(episode, release)
    solver._emergency_tick()
    assert episode.reads == episode.rooms
    assert not persisted.get("pending_read_rooms")


def test_final_handoff_observation_yields_and_resumes_without_clearing_episode(
    observation_solver,
):
    episode = observation_solver
    solver = episode.solver
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        solver.op_data.update_detail(name, 24, op.current_room, op.current_index, True)
    episode.state["phase"] = "returning"
    episode.state["handoff_plan"] = {}
    solver._emergency_restore = solver.__class__._emergency_restore.__get__(solver)
    solver._emergency_ready = solver.__class__._emergency_ready.__get__(solver)
    solver.agent_get_mood = MagicMock(wraps=solver.agent_get_mood)
    solver.agent_arrange = MagicMock(
        side_effect=AssertionError("empty handoff must not arrange")
    )
    release = set_release_window(episode, 120)

    assert not solver._emergency_restore()

    assert episode.reads == episode.rooms[:1]
    assert solver.emergency_state is episode.state
    assert episode.state["phase"] == "returning"
    assert episode.state["pending_read_rooms"] == episode.rooms[1:]
    assert episode.saves[-1]["pending_read_rooms"] == episode.rooms[1:]
    assert episode.state["next_read"] == episode.clock["now"] + timedelta(minutes=1)
    assert not solver._emergency_handoff
    solver.agent_get_mood.assert_not_called()
    finish_release(episode, release)

    assert solver._emergency_restore()

    assert episode.reads == episode.rooms
    assert solver.emergency_state is None
    solver.agent_get_mood.assert_called_once()
    solver.agent_arrange.assert_not_called()


def prepare_observing_handoff(episode):
    solver = episode.solver
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        solver.op_data.update_detail(name, 24, op.current_room, op.current_index, True)
    episode.state["phase"] = "returning"
    episode.state["handoff_plan"] = {}
    solver._emergency_restore = solver.__class__._emergency_restore.__get__(solver)
    solver._emergency_ready = solver.__class__._emergency_ready.__get__(solver)
    solver.agent_get_mood = MagicMock(wraps=solver.agent_get_mood)
    solver.agent_arrange = MagicMock(
        side_effect=AssertionError("observing handoff must not arrange")
    )
    release = set_release_window(episode, 120)
    assert not solver._emergency_restore()
    assert episode.state["handoff_observing"]
    assert episode.state["pending_read_rooms"] == episode.rooms[1:]
    finish_release(episode, release)


def test_delayed_handoff_rechecks_native_rotation_after_mood_changes(
    observation_solver,
):
    episode = observation_solver
    solver = episode.solver
    prepare_observing_handoff(episode)
    data = solver.op_data
    primary = data.operators[PRIMARY[0]]
    data.update_detail(
        primary.name, 8, primary.current_room, primary.current_index, True
    )
    for name in COVERS:
        cover = data.operators[name]
        data.update_detail(name, 0, cover.current_room, cover.current_index, True)
    assert primary.is_working()
    assert primary.mood < data.rescue_mood_threshold(primary)
    native = emergency_recovery.native_opportunity(solver, PRIMARY)
    assert native.opportunity is None

    solver._emergency_tick()

    assert episode.reads == episode.rooms
    assert solver.emergency_state is episode.state
    assert episode.state["phase"] == "recovering"
    assert "handoff_observing" not in episode.state
    assert "handoff_plan" not in episode.state
    solver.agent_get_mood.assert_not_called()
    solver.agent_arrange.assert_not_called()
    solver.run_order_solver.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()
    assert not solver._emergency_handoff


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_delayed_handoff_waits_for_queued_specialized_compensation(
    observation_solver, kind
):
    episode = observation_solver
    solver = episode.solver
    prepare_observing_handoff(episode)
    room = solver.op_data.operators[PRIMARY[1]].room
    compensation = SchedulerTask(
        time=episode.clock["now"] + timedelta(minutes=10),
        task_type=kind,
        task_plan={room: [COVERS[1]]},
    )
    compensation.emergency_original_roster = {room: [COVERS[1]]}
    solver.tasks.append(compensation)
    assert not solver._emergency_ready()

    solver._emergency_tick()

    assert solver.emergency_state is episode.state
    assert episode.state["handoff_observing"]
    assert episode.state["phase"] == "returning"
    assert compensation in solver.tasks
    solver.agent_get_mood.assert_not_called()
    solver.agent_arrange.assert_not_called()
    solver.run_order_solver.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()
    assert not solver._emergency_handoff

    solver.tasks.remove(compensation)
    episode.state["next_read"] = episode.clock["now"]
    solver._emergency_tick()

    assert solver.emergency_state is None
    solver.agent_get_mood.assert_called_once()
    solver.agent_arrange.assert_not_called()
    solver.run_order_solver.assert_called_once()


@pytest.mark.parametrize("known_deadline", [False, True])
def test_new_measured_limit_replans_before_next_room(
    observation_solver, known_deadline
):
    episode = observation_solver
    solver = episode.solver
    if known_deadline:
        set_release_window(episode, 150)
    previous_read = solver.get_agent_from_room.side_effect

    def read_room(room, *args, **kwargs):
        result = previous_read(room, *args, **kwargs)
        if room == "dormitory_1":
            solver.op_data.update_detail(episode.limited, 12, room, 2, True)
            _, bed = solver.op_data.get_dorm_by_name(episode.limited)
            bed.time = episode.clock["now"]
        return result

    solver.get_agent_from_room.side_effect = read_room
    solver._emergency_tick()

    assert episode.reads == ["dormitory_1"]
    assert episode.state["pending_read_rooms"] == episode.rooms[1:]
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert release.mood_limit_deadline == episode.clock["now"]
    assert release.time <= episode.clock["now"]
    solver._emergency_update_targets.assert_not_called()
    solver._emergency_ready.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


def test_new_countdown_replans_previously_unknown_limit_before_next_room(
    observation_solver,
):
    episode = observation_solver
    solver = episode.solver
    previous_read = solver.get_agent_from_room.side_effect

    def read_room(room, *args, **kwargs):
        result = previous_read(room, *args, **kwargs)
        if room == "dormitory_1":
            solver.op_data.update_detail(episode.limited, 11, room, 2, True)
            solver.op_data.refresh_dorm_time(
                room,
                2,
                {
                    "agent": episode.limited,
                    "time": episode.clock["now"] + timedelta(minutes=26),
                },
            )
        return result

    solver.get_agent_from_room.side_effect = read_room
    solver._emergency_tick()

    assert episode.reads == ["dormitory_1"]
    assert episode.state["pending_read_rooms"] == episode.rooms[1:]
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert release.mood_limit_deadline == episode.clock["now"] + timedelta(minutes=2)
    solver._emergency_update_targets.assert_not_called()
    solver._emergency_ready.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


def test_handoff_does_not_restore_old_deadline_over_new_observation(
    observation_solver,
):
    episode = observation_solver
    solver = episode.solver
    episode.state["phase"] = "returning"
    episode.state["handoff_plan"] = {}
    solver._emergency_restore = solver.__class__._emergency_restore.__get__(solver)
    release = set_release_window(episode, 600)
    earlier = episode.clock["now"] + timedelta(seconds=120)
    previous_read = solver.get_agent_from_room.side_effect

    def read_room(room, *args, **kwargs):
        result = previous_read(room, *args, **kwargs)
        if room == "dormitory_1":
            _, bed = solver.op_data.get_dorm_by_name(episode.limited)
            bed.time = earlier
        return result

    solver.get_agent_from_room.side_effect = read_room
    assert not solver._emergency_restore()
    _, bed = solver.op_data.get_dorm_by_name(episode.limited)
    assert bed.time == earlier
    assert bed.time < release.mood_limit_deadline
