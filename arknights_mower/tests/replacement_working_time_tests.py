"""普通替班的工作期限使用实读心情和倒计时，保留完整读房的缓存核对。"""

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
def test_full_mood_replacement_reads_work_countdown(room_reader, monkeypatch, room):
    solver, cover, _ = room_reader(room=room, name="红", mood=24)
    cover.operator_type = "low"
    cover.mood = 3
    cover.need_to_refresh.return_value = False
    cover.current_mood.return_value = 3
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
        force_working_time=True,
    )[0]

    assert observed["agent"] == "红"
    assert observed["mood"] == cover.mood == 24
    assert observed["time"] == captured_at + timedelta(hours=1)
    assert (cover.current_room, cover.current_index) == (room, 0)
    assert solver.op_data.room_observations[room] == 1
    solver.read_accurate_mood.assert_called_once()
    solver.read_time.assert_called_once_with(((1650, 270), (1780, 305)), None)


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
            [0],
            force_mood=True,
            strict_observation=True,
            force_working_time=True,
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
        [0],
        force_mood=True,
        strict_observation=True,
        force_working_time=True,
    )

    assert observed[0]["agent"] == "红"
    assert observed[0]["time"] == deadline
    assert (cover.current_room, cover.current_index) == ("contact", 0)
    assert (former.current_room, former.current_index) == ("", -1)
    assert former.time_stamp is None
    assert solver.op_data.room_observations["contact"] == 1
