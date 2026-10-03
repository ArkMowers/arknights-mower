"""智能救急逐房复查让出严格清退窗口并保存未完成房间。"""

import copy
import pickle
from datetime import date, datetime, timedelta
from threading import Event
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
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", True)
    # These cases resume an unfinished initialization/final reconciliation.
    state["pending_read_rooms"] = sorted(data.plan)
    state["read_collection_pending"] = True
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
            {"agent": op.name, "mood": op.mood}
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
        time=NOW + timedelta(minutes=30), meta_data=emergency.RESUME_META
    )
    solver.tasks.append(check)
    set_release_window(episode, 120)

    solver._emergency_tick()

    assert episode.reads == episode.rooms[:1]
    assert check.time == episode.state["next_read"]
    assert check.time == episode.clock["now"] + timedelta(minutes=1)
    assert [
        task for task in solver.tasks if task.meta_data == emergency.RESUME_META
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
    assert solver._emergency_startup_pending
    finish_release(episode, release)
    solver._emergency_startup()
    assert not solver._emergency_startup_pending
    assert episode.reads == [*episode.rooms[:1], *episode.rooms]
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


@pytest.mark.parametrize("cached_task", [False, True])
def test_inactive_startup_yields_before_strict_release(observation_solver, cached_task):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 1)
    if not cached_task:
        solver.tasks.remove(release)
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    solver.find = MagicMock(return_value=(1, 1))
    solver.task = SchedulerTask()
    solver.tasks.append(solver.task)
    solver.skip = MagicMock()
    solver.planned = True

    solver.infra_main()

    assert not episode.reads
    assert solver._emergency_startup_pending
    assert solver._initial_mood_refresh_rooms == set(episode.rooms)
    assert solver.defer_backup_plan_until_mood_read
    solver._read_initial_card_mood.assert_not_called()
    solver.backup_plan_solver.assert_not_called()
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert episode.clock["now"] < release.mood_limit_deadline


def test_inactive_startup_persists_and_resumes_unread_rooms(
    observation_solver, monkeypatch
):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 120)
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    monkeypatch.setattr(emergency.config.conf, "automatic_rescue_enable", False)
    from arknights_mower import __main__ as main

    monkeypatch.setattr(main, "base_scheduler", solver)
    for field in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, field, None)
    solver.task_count = 0
    solver._emergency_startup()
    assert episode.reads == episode.rooms[:1]
    snapshot = pickle.loads(pickle.dumps(record.current_state()))
    assert snapshot["initial_mood_refresh_rooms"] == episode.rooms[1:]
    assert snapshot["automatic_rescue_state"] is None
    assert snapshot["initial_mood_pending"]
    solver._initial_mood_refresh_rooms = set(snapshot["initial_mood_refresh_rooms"])
    solver.tasks = snapshot["tasks"]
    solver.op_data.operators = snapshot["operators"]
    solver.op_data.dorm = snapshot["dorm"]
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    finish_release(episode, release)

    solver._emergency_startup()

    assert episode.reads == episode.rooms
    assert not solver._emergency_startup_pending
    assert solver._initial_mood_refresh_rooms == set()
    assert not solver.defer_backup_plan_until_mood_read
    solver._read_initial_card_mood.assert_called_once()
    solver.backup_plan_solver.assert_called_once()


def test_inactive_startup_replans_new_deadline_and_defers_card_scan(
    observation_solver, monkeypatch
):
    episode = observation_solver
    solver = episode.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    monkeypatch.setattr(emergency.config.conf, "automatic_rescue_enable", False)
    previous_read = solver.get_agent_from_room.side_effect

    def read_room(room, *args, **kwargs):
        result = previous_read(room, *args, **kwargs)
        if room == "dormitory_1":
            solver.op_data.update_detail(episode.limited, 12, room, 2, True)
        return result

    solver.get_agent_from_room.side_effect = read_room
    solver._emergency_startup()

    assert episode.reads == ["dormitory_1"]
    assert solver._initial_mood_refresh_rooms == set(episode.rooms[1:])
    assert solver._emergency_startup_pending
    solver._read_initial_card_mood.assert_not_called()
    solver.backup_plan_solver.assert_not_called()
    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert release.mood_limit_deadline == episode.clock["now"]

    finish_release(episode, release)
    solver._emergency_startup()
    assert episode.reads == episode.rooms
    assert not solver._emergency_startup_pending


def test_completed_startup_rooms_not_repeated_when_card_scan_yields(
    observation_solver, monkeypatch
):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 300)
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    monkeypatch.setattr(emergency.config.conf, "automatic_rescue_enable", False)
    solver._initial_mood_refresh_rooms = {episode.rooms[0]}
    episode.clock["now"] = release.time - timedelta(seconds=120)
    previous_read = solver.get_agent_from_room.side_effect

    def slow_read(*args, **kwargs):
        result = previous_read(*args, **kwargs)
        episode.clock["now"] += timedelta(seconds=60)
        return result

    solver.get_agent_from_room.side_effect = slow_read
    solver._emergency_startup()
    assert episode.reads == [episode.rooms[0]]
    assert solver._initial_mood_refresh_rooms == set()
    assert solver._emergency_startup_pending
    solver._read_initial_card_mood.assert_not_called()
    solver.backup_plan_solver.assert_not_called()

    finish_release(episode, release)
    solver._emergency_startup()
    assert episode.reads == [episode.rooms[0]]
    assert solver._initial_mood_refresh_rooms == set()
    assert not solver._emergency_startup_pending
    solver._read_initial_card_mood.assert_called_once()


def test_pending_inactive_startup_allows_selected_release_to_dispatch(
    observation_solver,
):
    episode = observation_solver
    solver = episode.solver
    release = set_release_window(episode, 1)
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    solver.find = MagicMock(return_value=(1, 1))
    solver.skip = MagicMock()
    solver.planned = True
    solver.task = release
    episode.clock["now"] = release.time
    solver.arrange_release_dorm = MagicMock(return_value=(False, False))

    solver.infra_main()

    solver.arrange_release_dorm.assert_called_once()
    assert release in solver.tasks
    assert solver._emergency_startup_pending
    assert solver.defer_backup_plan_until_mood_read
    assert not episode.reads
    solver._read_initial_card_mood.assert_not_called()
    solver.backup_plan_solver.assert_not_called()


@pytest.mark.parametrize("pending", [[], ["room_1_2", "room_1_3"]])
@pytest.mark.parametrize("enabled", [False, True])
def test_real_restart_restores_unfinished_startup_with_setting_disabled(
    observation_solver, monkeypatch, pending, enabled
):
    from arknights_mower import __main__ as main

    episode = observation_solver
    solver = episode.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = False
    solver.defer_backup_plan_until_mood_read = True
    solver._initial_mood_refresh_rooms = set(pending)
    for field in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, field, date.min)
    solver.task_count = 0
    monkeypatch.setattr(main, "base_scheduler", solver)
    snapshot = pickle.loads(pickle.dumps(record.current_state()))
    monkeypatch.setattr(main.config, "stop_mower", Event())
    monkeypatch.setattr(main.config.conf, "automatic_rescue_enable", enabled)
    monkeypatch.setattr(main, "initialize", lambda *args, **kwargs: solver)
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", lambda: None)
    monkeypatch.setattr(
        main, "_apply_version_update_resting_threshold", lambda *a: None
    )
    solver.initialize_operators = MagicMock(return_value=None)
    solver.run = MagicMock(side_effect=emergency.MowerExit)

    main.simulate(snapshot)

    solver.run.assert_called_once()
    assert solver._emergency_startup_pending
    assert solver._initial_mood_refresh_rooms == set(pending)
    assert solver.defer_backup_plan_until_mood_read
    assert any(not task.meta_data and not task.plan for task in solver.tasks)
    assert not any(task.meta_data == emergency.RESUME_META for task in solver.tasks)
    assert solver.emergency_state is None


@pytest.mark.parametrize("pending", [[], ["room_1_2"]])
def test_real_restart_discards_progress_from_completed_initialization(
    observation_solver, monkeypatch, pending
):
    from arknights_mower import __main__ as main

    episode = observation_solver
    solver = episode.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = False
    solver.defer_backup_plan_until_mood_read = False
    solver._initial_mood_refresh_rooms = set(pending)
    for field in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, field, date.min)
    solver.task_count = 0
    monkeypatch.setattr(main, "base_scheduler", solver)
    snapshot = pickle.loads(pickle.dumps(record.current_state()))
    monkeypatch.setattr(main.config, "stop_mower", Event())
    monkeypatch.setattr(main.config.conf, "automatic_rescue_enable", True)
    monkeypatch.setattr(main, "initialize", lambda *args, **kwargs: solver)
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", lambda: None)
    monkeypatch.setattr(
        main, "_apply_version_update_resting_threshold", lambda *a: None
    )
    solver.initialize_operators = MagicMock(return_value=None)
    solver.run = MagicMock(side_effect=emergency.MowerExit)

    main.simulate(snapshot)

    assert solver._emergency_startup_pending
    assert solver._initial_mood_refresh_rooms == set(episode.rooms)
    solver._emergency_startup()
    assert episode.reads == episode.rooms


def test_disabled_restart_completes_and_clears_progress_before_reenable(
    observation_solver, monkeypatch
):
    from arknights_mower import __main__ as main

    episode = observation_solver
    solver = episode.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = False
    solver.defer_backup_plan_until_mood_read = True
    solver._initial_mood_refresh_rooms = set()
    for field in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, field, date.min)
    solver.task_count = 0
    monkeypatch.setattr(main, "base_scheduler", solver)
    snapshots = []

    def persist():
        snapshots.append(pickle.loads(pickle.dumps(record.current_state())))
        return True

    monkeypatch.setattr(emergency, "save_current_state", persist)
    snapshot = pickle.loads(pickle.dumps(record.current_state()))
    monkeypatch.setattr(main.config, "stop_mower", Event())
    monkeypatch.setattr(main.config.conf, "automatic_rescue_enable", False)
    monkeypatch.setattr(main, "initialize", lambda *args, **kwargs: solver)
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", lambda: None)
    monkeypatch.setattr(
        main, "_apply_version_update_resting_threshold", lambda *a: None
    )
    solver.initialize_operators = MagicMock(return_value=None)
    solver.run = MagicMock(side_effect=emergency.MowerExit)

    main.simulate(snapshot)
    assert solver._emergency_startup_pending
    solver._emergency_startup()
    assert not episode.reads
    assert solver.emergency_state is None
    assert not solver._emergency_startup_pending
    assert snapshots[-1]["initial_mood_refresh_rooms"] == []
    assert not snapshots[-1]["initial_mood_pending"]
    solver._emergency_schedule_staffing.assert_not_called()

    monkeypatch.setattr(main.config.conf, "automatic_rescue_enable", True)
    main.simulate(snapshots[-1])
    assert solver._emergency_startup_pending
    assert solver._initial_mood_refresh_rooms == set(episode.rooms)
    solver._emergency_startup()
    assert episode.reads == episode.rooms


def test_shared_initial_reader_logs_facilities_before_rescue_admission(
    observation_solver, monkeypatch
):
    episode = observation_solver
    solver = episode.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    solver._emergency_read_rooms = MagicMock(
        side_effect=AssertionError("startup must use the ordinary mood reader")
    )
    monkeypatch.setattr(emergency.config.conf, "automatic_rescue_enable", True)
    events, logs = [], []
    monkeypatch.setattr(
        base_schedule.logger, "info", lambda message, *args: logs.append(message)
    )

    def cards():
        assert episode.reads == episode.rooms
        assert solver.emergency_state is None
        events.append("cards")

    def backup():
        assert events == ["cards"]
        events.append("backup")
        return False

    def admission(*args, **kwargs):
        assert events == ["cards", "backup"]
        events.append("admission")
        return emergency_recovery.NativeProjection(episode.clock["now"], True)

    solver._read_initial_card_mood.side_effect = cards
    solver.backup_plan_solver.side_effect = backup
    monkeypatch.setattr(emergency, "native_opportunity", admission)
    solver._emergency_startup()
    assert events == ["cards", "backup", "admission"]
    for room in episode.rooms:
        assert any(
            f"房间 {solver.translate_room(room)}" in line and "心情:" in line
            for line in logs
        )
    assert not solver._emergency_startup_pending
    assert solver.emergency_state is None


def test_initial_wakeup_does_not_block_its_own_card_scan(observation_solver):
    solver = observation_solver.solver
    solver.emergency_state = None
    solver._emergency_startup_pending = True
    solver.task = SchedulerTask(time=NOW)
    solver.tasks = [solver.task]
    solver.find = MagicMock(return_value=(1, 1))
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.handle_error = MagicMock(return_value=True)

    def initialize():
        assert solver.task is None
        assert solver.no_pending_task(1)
        solver._emergency_startup_pending = False

    solver._emergency_startup = MagicMock(side_effect=initialize)
    assert solver.infra_main()
    solver._emergency_startup.assert_called_once()
    assert not solver.tasks
