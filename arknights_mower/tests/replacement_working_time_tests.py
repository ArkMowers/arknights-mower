"""普通替班的正心情读数不要求倒计时，游戏工作倒计时保持归零终点。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.exhausted_working_timer_tests import base
from arknights_mower.tests.exhausted_working_timer_tests import (
    room_reader as room_reader,
)
from arknights_mower.utils.recognize import RecognizeError


@pytest.mark.parametrize(
    "room", ["central", "room_1_1", "contact", "meeting", "factory"]
)
@pytest.mark.parametrize(
    "lower,mood", [(0, 1), (0, 2), (0, 16), (0, 24), (6, 7), (20, 21)]
)
def test_replacement_mood_observation_does_not_request_countdown(
    room_reader, room, lower, mood
):
    solver, cover, _ = room_reader(room=room, name="红", mood=mood)
    cover.operator_type = "low"
    cover.lower_limit = lower
    cover.mood = 1
    cover.need_to_refresh.return_value = False
    cover.current_mood.return_value = 1

    observed = solver.get_agent_from_room(
        room, force_mood=True, strict_observation=True
    )[0]

    assert observed["agent"] == "红"
    assert observed["mood"] == cover.mood == mood
    assert "time" not in observed
    solver.read_accurate_mood.assert_called_once()
    solver.read_operator_time.assert_not_called()


@pytest.mark.parametrize("lower", [0, 1, 6])
def test_optional_working_countdown_keeps_game_zero_endpoint(
    room_reader, monkeypatch, lower
):
    mood = 2
    room = "central"
    solver, cover, _ = room_reader(room=room, name="红", mood=mood)
    cover.lower_limit = lower
    captured_at = datetime(2026, 10, 18, 8)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return captured_at

    monkeypatch.setattr(base, "datetime", Clock)
    solver.read_operator_time = base.BaseSchedulerSolver.read_operator_time.__get__(
        solver
    )
    solver.read_time = MagicMock(return_value=3600)

    observed = solver.get_agent_from_room(
        room,
        [0],
        force_mood=True,
        strict_observation=True,
    )[0]

    assert observed["agent"] == "红"
    assert observed["mood"] == cover.mood == mood
    assert observed["time"] == captured_at + timedelta(hours=1)
    assert (cover.current_room, cover.current_index) == (room, 0)
    assert solver.op_data.room_observations[room] == 1
    solver.read_accurate_mood.assert_called_once()
    solver.read_time.assert_called_once_with(((1650, 270), (1780, 305)), None)


@pytest.mark.parametrize("mood", [0, 1, 2, 16, 23, 24])
@pytest.mark.parametrize("request_timer", [False, True])
def test_recycle_never_reads_operator_countdown(room_reader, mood, request_timer):
    solver, cover, _ = room_reader(room="recycle", name="红", mood=mood)
    solver.op_data.recycle_capacity = 1

    observed = solver.get_agent_from_room(
        "recycle", [0] if request_timer else [], force_mood=True
    )[0]

    assert observed["mood"] == cover.mood == mood
    assert "time" not in observed
    solver.read_operator_time.assert_not_called()


def test_ordinary_full_mood_read_keeps_existing_timer_shortcut(room_reader):
    solver, _, _ = room_reader(room="contact", name="红", mood=24)
    before = datetime.now()

    observed = solver.get_agent_from_room("contact", [0], force_mood=True)[0]

    assert before <= observed["time"] <= datetime.now()
    solver.read_operator_time.assert_not_called()


@pytest.mark.parametrize("mood", [float("nan"), -1, 25])
def test_unconfirmed_replacement_mood_never_produces_work_deadline(room_reader, mood):
    solver, cover, _ = room_reader(room="contact", name="红", mood=mood)
    cover.mood = 7
    sampled_at = cover.time_stamp

    with pytest.raises(RecognizeError, match="心情未核实"):
        solver.get_agent_from_room(
            "contact",
            force_mood=True,
            strict_observation=True,
        )

    assert cover.mood == 7
    assert cover.time_stamp == sampled_at
    assert not getattr(solver.op_data, "room_observations", {})
    solver.read_operator_time.assert_not_called()


def test_replacement_deadline_read_reconciles_former_room_occupant(room_reader):
    solver, cover, deadline = room_reader(room="contact", name="红", mood=24)
    former = SimpleNamespace(
        current_room="contact",
        current_index=0,
        mood=12,
        time_stamp=datetime.now(),
    )
    solver.op_data.operators["梓兰"] = former

    observed = solver.get_agent_from_room(
        "contact",
        force_mood=True,
        strict_observation=True,
    )

    assert observed[0]["agent"] == "红"
    assert "time" not in observed[0]
    solver.read_operator_time.assert_not_called()
    assert (cover.current_room, cover.current_index) == ("contact", 0)
    assert (former.current_room, former.current_index) == ("", -1)
    assert former.time_stamp is None
    assert solver.op_data.room_observations["contact"] == 1
