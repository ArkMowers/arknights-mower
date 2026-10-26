"""有工作倒计时的零心情保留实读，只省略同设施的曲线记录。"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests.mood_estimate_sampling_tests import (
    room_reader as room_reader,
)
from arknights_mower.utils import calculated_mood, config
from arknights_mower.utils.plan import Room

_REAL_CONNECTION = record._conn


@pytest.fixture
def history_reader(room_reader, monkeypatch, tmp_path):
    solver, target, clock = room_reader
    monkeypatch.setattr(record, "_conn", _REAL_CONNECTION)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path / "data.db" if path.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(calculated_mood, "datetime", clock)
    target.mood, target.depletion_rate = 1.2, 0.8
    solver.read_accurate_mood.return_value = 0
    solver.read_time = MagicMock(return_value=3009)
    solver.leifeng_mode = True
    solver.find = MagicMock(
        side_effect=lambda name, scope=None: (
            name == "infra_no_operator" and scope[0][1] == 344
        )
    )
    return solver, target, clock


def seed_history(target, clock, room):
    record.save_agent_action(
        target.name,
        room,
        room,
        True,
        target.group,
        1.2,
        current_time=clock.now() - timedelta(hours=1),
    )


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("room", ["central", "contact", "meeting", "room_1_2"])
@pytest.mark.parametrize("request_time", [False, True])
def test_same_facility_zero_with_countdown_keeps_reading_without_curve_point(
    history_reader, enabled, room, request_time
):
    solver, target, clock = history_reader
    config.conf.test_mood_calculation = enabled
    solver.op_data.plan[room] = solver.op_data.plan["central"]
    target.current_room = room
    seed_history(target, clock, room)
    for _ in range(3):
        data = solver.get_agent_from_room(
            room,
            [0] if request_time else [],
            force_mood=True,
            strict_observation=True,
        )[0]
        assert data["mood"] == target.mood == 0
        assert (target.current_room, target.current_index) == (room, 0)
        if request_time:
            assert data["time"] == clock.now() + timedelta(seconds=3009)
    assert target.time_stamp == clock.now()
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,)]
    assert solver.tasks == []
    solver.read_operator_time.assert_not_called()


@pytest.mark.parametrize(
    "previous_room,expected",
    [
        ("central", [(1.2,)]),
        ("meeting", [(1.2,), (0,)]),
        ("dormitory_1", [(1.2,), (0,)]),
        (None, [(0,)]),
    ],
)
def test_cleared_recovery_position_uses_last_recorded_facility(
    history_reader, previous_room, expected
):
    solver, target, clock = history_reader
    if previous_room:
        seed_history(target, clock, previous_room)
    target.current_room, target.current_index, target.time_stamp = "", -1, None
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert (target.current_room, target.current_index, target.mood) == ("central", 0, 0)
    assert record._fetchall("SELECT mood FROM agent_action") == expected


@pytest.mark.parametrize("previous_room", ["meeting", "dormitory_1"])
def test_zero_with_countdown_records_actual_facility_change(
    history_reader, previous_room
):
    solver, target, clock = history_reader
    seed_history(target, clock, previous_room)
    target.current_room = previous_room
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT current_room, mood FROM agent_action") == [
        (previous_room, 1.2),
        ("central", 0),
    ]


@pytest.mark.parametrize("remaining", [None, 0, float("nan"), float("inf"), -1, "bad"])
def test_zero_without_positive_countdown_still_records(history_reader, remaining):
    solver, target, clock = history_reader
    seed_history(target, clock, "central")
    solver.read_time.return_value = remaining
    solver.detect_room = MagicMock(return_value="central")
    solver.find = MagicMock(side_effect=lambda name, **kw: name == "room_detail")
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,), (0,)]


def test_positive_mood_keeps_curve_without_extra_countdown(history_reader):
    solver, target, clock = history_reader
    seed_history(target, clock, "central")
    solver.read_accurate_mood.return_value = 1
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,), (1,)]
    solver.read_time.assert_not_called()


@pytest.mark.parametrize("previous_index", [0, 4])
def test_zero_mood_in_fifth_central_slot_keeps_positive_countdown(
    history_reader, previous_index
):
    solver, target, clock = history_reader
    solver.op_data.plan["central"] = [Room("Free", "", []) for _ in range(4)] + [
        Room(target.name, "", [])
    ]
    target.current_index = previous_index
    seed_history(target, clock, "central")
    solver.scroll_room_operators = MagicMock()
    solver.find = MagicMock(
        side_effect=lambda name, scope=None: (
            name == "infra_no_operator" and scope[0][1] != 741
        )
    )
    solver.read_time.return_value = 314
    result = solver.get_agent_from_room(
        "central", [4], force_mood=True, strict_observation=True
    )
    assert result[4]["agent"] == target.name
    assert result[4]["mood"] == target.mood == 0
    assert result[4]["time"] == clock.now() + timedelta(seconds=314)
    solver.read_time.assert_called_once_with(((1650, 877), (1780, 912)), None)
    solver.read_operator_time.assert_not_called()
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,)]
