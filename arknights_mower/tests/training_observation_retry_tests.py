"""训练室巡检失败保留成功时间，随后按原有周期再次观察。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room


class Clock(datetime):
    current = datetime(2026, 10, 13, 10)

    @classmethod
    def now(cls, tz=None):
        return cls.current


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(Clock, "current", Clock(2026, 10, 13, 10))
    monkeypatch.setattr(base, "_training_room_scan_disabled", False)
    monkeypatch.setattr(base.config.conf, "enable_mastery", True)
    monkeypatch.setattr(reader, "reconcile_short", Mock())
    s = object.__new__(base.BaseSchedulerSolver)
    s.task, s.tasks = None, []
    old = Clock.now() - timedelta(hours=3)
    s.last_train_mood_read = old
    s.last_train_mood_attempt = old
    s.op_data = SimpleNamespace(
        plan={"train": []},
        operators={
            "艾丽妮": Operator(
                "艾丽妮",
                "",
                current_room="train",
                current_index=0,
                mood=17,
                time_stamp=old,
            )
        },
    )
    s.enter_room = Mock()
    s.back = Mock()
    s.back_to_infrastructure = Mock()
    return s


def test_failed_scan_repeats_at_normal_interval_without_cache_changes(
    solver, monkeypatch
):
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    old = solver.last_train_mood_read
    solver._read_agent_mood()
    assert read.call_count == 1
    assert solver.last_train_mood_read == old

    Clock.current += timedelta(hours=2.5)
    solver._read_agent_mood()

    assert read.call_count == 2
    assert solver.last_train_mood_read == old


@pytest.mark.parametrize("failure", ["exception", "unknown_slots", "unread_slots"])
def test_failed_observation_preserves_success_time_and_normal_patrol_interval(
    solver, monkeypatch, failure
):
    old = solver.last_train_mood_read
    failed = reader.RoomState("training", slots_read=failure == "unknown_slots")
    read = Mock(
        side_effect=ValueError("unreadable") if failure == "exception" else None,
        return_value=(failed, []),
    )
    monkeypatch.setattr(reader, "read_room_state", read)

    solver._read_agent_mood()

    assert solver.last_train_mood_read == old
    assert solver.last_train_mood_attempt == Clock.now()
    assert not base._training_room_scan_disabled
    attempt = Clock.now()
    for elapsed in (
        timedelta(),
        timedelta(minutes=2),
        timedelta(hours=2.5, seconds=-1),
    ):
        Clock.current = attempt + elapsed
        solver._read_agent_mood()
        assert read.call_count == 1
    Clock.current = attempt + timedelta(hours=2.5)
    solver._read_agent_mood()
    assert read.call_count == 2
    assert solver.last_train_mood_attempt == Clock.now()
    assert solver.last_train_mood_read == old
    assert solver.tasks == []


def test_repeated_failures_use_bounded_patrols_and_success_restores_normal_interval(
    solver, monkeypatch
):
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    old = solver.last_train_mood_read
    for count in range(1, 4):
        solver._read_agent_mood()
        solver._read_agent_mood()
        assert read.call_count == count
        assert solver.last_train_mood_read == old
        Clock.current += timedelta(hours=2.5)

    good = reader.RoomState("training", slots_read=True, slots_reliable=True)
    read.side_effect = None
    read.return_value = (good, [])
    solver._read_agent_mood()
    assert read.call_count == 4
    assert solver.last_train_mood_read == Clock.now()
    solver._read_agent_mood()
    assert read.call_count == 4
    Clock.current += timedelta(hours=2.5)
    solver._read_agent_mood()
    assert read.call_count == 5
    assert solver.tasks == []


def test_failed_training_scan_keeps_other_room_observations_running(
    solver, monkeypatch
):
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    solver.op_data.plan["meeting"] = [Room("银灰", "", [])]
    solver.op_data.operators["银灰"] = Operator(
        "银灰",
        "meeting",
        current_room="meeting",
        current_index=0,
        time_stamp=Clock.now() - timedelta(hours=3),
    )
    solver._read_room_mood = Mock()
    solver._read_agent_mood()

    read.assert_called_once()
    solver._read_room_mood.assert_called_once_with("meeting", force_mood=False)
    solver._read_agent_mood()
    assert read.call_count == 1
    assert solver._read_room_mood.call_count == 2
    Clock.current += timedelta(hours=2.5)
    solver._read_agent_mood()
    assert read.call_count == 2
    assert solver._read_room_mood.call_count == 3
    assert solver.tasks == []


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("configured", [False, True])
def test_empty_unstaffed_room_returns_to_normal_patrol_after_failure(
    solver, monkeypatch, enabled, configured
):
    monkeypatch.setattr(base.config.conf, "enable_mastery", enabled)
    solver.op_data.operators = {}
    solver.op_data.plan = {"train": []} if configured else {}
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    solver._read_agent_mood()
    old = solver.last_train_mood_read
    read.side_effect = None
    empty = reader.RoomState("empty", slots_read=True, slots_reliable=True)
    read.return_value = (empty, []) if enabled else empty
    solver.get_agent_from_room = Mock(
        return_value=[{"agent": "", "mood": -1}, {"agent": "", "mood": -1}]
    )

    solver._read_agent_mood()
    assert read.call_count == 1
    Clock.current += timedelta(hours=2.5)
    solver._read_agent_mood()
    solver._read_agent_mood()

    assert read.call_count == 2
    if enabled:
        solver.get_agent_from_room.assert_not_called()
    else:
        solver.get_agent_from_room.assert_called_once_with("train", None)
    assert solver.last_train_mood_read > old
    Clock.current += timedelta(hours=2.5)
    solver._read_agent_mood()
    assert read.call_count == 3
    assert solver.tasks == []


@pytest.mark.parametrize("failure", ["exception", "unknown_slots"])
def test_failed_scan_keeps_previously_confirmed_training_protection(
    solver, monkeypatch, failure
):
    confirmed = reader.RoomState("training", slots_read=True, slots_reliable=True)
    solver.train_room_state = confirmed
    solver._train_mastery_active = Mock(return_value=False)
    solver._train_protected = Mock(return_value=False)
    read = Mock(
        side_effect=ValueError("unreadable") if failure == "exception" else None,
        return_value=(reader.RoomState("empty", slots_read=True), []),
    )
    monkeypatch.setattr(reader, "read_room_state", read)

    solver._read_agent_mood()

    assert solver._train_scheduling_protected()
    assert solver.op_data.operators["艾丽妮"].current_room == "train"


def test_successful_empty_slots_keep_normal_room_throttle(solver, monkeypatch):
    room = reader.RoomState("empty", slots_read=True, slots_reliable=True)
    read = Mock(return_value=(room, [{"agent": "", "mood": -1}] * 2))
    monkeypatch.setattr(reader, "read_room_state", read)

    solver._read_agent_mood()
    solver._read_agent_mood()

    assert read.call_count == 1
    assert solver.last_train_mood_read == Clock.now()
    Clock.current += timedelta(hours=3)
    solver._read_agent_mood()
    assert read.call_count == 2


@pytest.mark.parametrize("has_previous_attempt", [False, True])
def test_recent_successful_read_throttles_patrol_after_an_older_attempt(
    solver, monkeypatch, has_previous_attempt
):
    solver.last_train_mood_attempt = (
        Clock.now() - timedelta(hours=3) if has_previous_attempt else None
    )
    solver.last_train_mood_read = Clock.now() - timedelta(minutes=1)
    read = Mock()
    monkeypatch.setattr(reader, "read_room_state", read)

    solver._read_agent_mood()

    read.assert_not_called()
    solver.enter_room.assert_not_called()


def test_failed_entry_retains_process_scan_disable(solver, monkeypatch):
    solver.enter_room.side_effect = RuntimeError("unbuilt training room")
    read = Mock()
    monkeypatch.setattr(reader, "read_room_state", read)
    old = solver.last_train_mood_read

    solver._read_agent_mood()
    Clock.current += timedelta(hours=3)
    solver._read_agent_mood()

    assert solver.last_train_mood_read == old
    assert base._training_room_scan_disabled
    assert solver.enter_room.call_count == 1
    read.assert_not_called()


@pytest.mark.parametrize("error_type", [reader.MowerExit, reader.DeviceRecoveryError])
@pytest.mark.parametrize("failure_site", ["entry", "reading"])
def test_device_or_stop_interruption_does_not_become_observation_retry(
    solver, monkeypatch, error_type, failure_site
):
    read = Mock(side_effect=error_type() if failure_site == "reading" else None)
    if failure_site == "entry":
        solver.enter_room.side_effect = error_type()
    monkeypatch.setattr(reader, "read_room_state", read)
    old = solver.last_train_mood_read
    old_attempt = solver.last_train_mood_attempt

    with pytest.raises(error_type):
        solver._read_agent_mood()

    assert solver.last_train_mood_read == old
    assert solver.last_train_mood_attempt == old_attempt
    assert not base._training_room_scan_disabled
    solver.back_to_infrastructure.assert_not_called()

    good = reader.RoomState("training", slots_read=True, slots_reliable=True)
    solver.enter_room.side_effect = None
    read.side_effect = None
    read.return_value = (good, [])
    solver._read_agent_mood()
    assert read.call_count == (2 if failure_site == "reading" else 1)
    assert solver.last_train_mood_read == Clock.now()
