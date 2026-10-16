"""训练室巡检失败保留成功时间，仅由相关实测或安排变化重新准入。"""

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
    s.op_data = SimpleNamespace(
        plan={"train": []},
        products={},
        facility_states={},
        room_observations={"train": 1, "meeting": 1},
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


@pytest.mark.parametrize("failure", ["exception", "unknown_slots", "unread_slots"])
def test_failed_observation_preserves_success_time_without_timer_retry(
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
    assert not base._training_room_scan_disabled
    for _ in range(3):
        Clock.current += timedelta(hours=3)
        solver._read_agent_mood()
    assert read.call_count == 1
    assert solver.last_train_mood_read == old
    assert solver.tasks == []


@pytest.mark.parametrize("change", ["revision", "arrangement", "occupancy", "mood"])
def test_related_update_retries_once_despite_recent_successful_mood(
    solver, monkeypatch, change
):
    good = reader.RoomState("training", slots_read=True, slots_reliable=True)
    read = Mock(side_effect=[ValueError("unreadable"), (good, [])])
    monkeypatch.setattr(reader, "read_room_state", read)
    solver._read_agent_mood()
    assert read.call_count == 1
    recent = Clock.now() - timedelta(minutes=1)
    solver.last_train_mood_read = recent
    op = solver.op_data.operators["艾丽妮"]
    if change == "revision":
        solver.op_data.room_observations["train"] += 1
    elif change == "arrangement":
        solver.op_data.plan["train"] = [Room("艾丽妮", "", [])]
    elif change == "occupancy":
        op.current_index = 1
    else:
        op.time_stamp = recent

    solver._read_agent_mood()
    assert read.call_count == 2
    assert solver.last_train_mood_read == Clock.now()
    solver._read_agent_mood()
    assert read.call_count == 2

    op.time_stamp = Clock.now()
    Clock.current += timedelta(hours=3)
    read.side_effect = None
    read.return_value = (good, [])
    solver._read_agent_mood()
    assert read.call_count == 3


def test_unrelated_observations_do_not_reopen_failed_training_scan(solver, monkeypatch):
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    solver._read_agent_mood()
    solver.op_data.plan["meeting"] = [Room("银灰", "", [])]
    solver.op_data.operators["银灰"] = Operator(
        "银灰",
        "meeting",
        current_room="meeting",
        current_index=0,
        time_stamp=Clock.now() - timedelta(hours=3),
    )
    solver._read_room_mood = Mock()
    solver.op_data.room_observations["meeting"] += 1
    solver._read_agent_mood()

    read.assert_called_once()
    solver._read_room_mood.assert_called_once_with("meeting", force_mood=False)
    assert solver.tasks == []


def test_mastery_setting_change_allows_a_manual_training_observation(
    solver, monkeypatch
):
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    solver._read_agent_mood()
    old = solver.last_train_mood_read
    monkeypatch.setattr(base.config.conf, "enable_mastery", False)
    read.side_effect = None
    read.return_value = reader.RoomState("empty")
    solver.get_agent_from_room = Mock(
        return_value=[{"agent": "", "mood": -1}, {"agent": "", "mood": -1}]
    )

    solver._read_agent_mood()
    solver._read_agent_mood()

    assert read.call_count == 2
    solver.get_agent_from_room.assert_called_once_with("train", None)
    assert solver.last_train_mood_read > old
    assert solver._training_mood_failure is None
    assert solver.tasks == []


def test_prediction_invalidation_does_not_reopen_failed_training_scan(
    solver, monkeypatch
):
    read = Mock(side_effect=ValueError("unreadable"))
    monkeypatch.setattr(reader, "read_room_state", read)
    solver._read_agent_mood()
    op = solver.op_data.operators["艾丽妮"]
    op.mood_is_prediction = True
    Clock.current += timedelta(hours=3)

    solver._read_agent_mood()

    read.assert_called_once()


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
        return_value=(reader.RoomState("empty"), []),
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
def test_device_or_stop_interruption_does_not_become_observation_retry(
    solver, monkeypatch, error_type
):
    read = Mock(side_effect=error_type())
    monkeypatch.setattr(reader, "read_room_state", read)
    old = solver.last_train_mood_read

    with pytest.raises(error_type):
        solver._read_agent_mood()

    assert solver.last_train_mood_read == old
    assert not getattr(solver, "_training_mood_failure", None)
    assert not base._training_room_scan_disabled
    solver.back_to_infrastructure.assert_not_called()

    good = reader.RoomState("training", slots_read=True, slots_reliable=True)
    read.side_effect = None
    read.return_value = (good, [])
    solver._read_agent_mood()
    assert read.call_count == 2
    assert solver.last_train_mood_read == Clock.now()
