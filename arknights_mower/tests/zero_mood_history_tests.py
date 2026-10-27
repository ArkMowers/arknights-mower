"""零心情保留实读，曲线展示工作设施切换和已确认耗尽。"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.solvers.mood_history_query import selected_mood_series
from arknights_mower.tests.mood_estimate_sampling_tests import (
    room_reader as room_reader,
)
from arknights_mower.utils import calculated_mood, config
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.plan import Room
from arknights_mower.utils.recognize import RecognizeError

_REAL_CONNECTION = record._conn


@pytest.fixture
def history_reader(room_reader, monkeypatch, tmp_path):
    solver, target, clock = room_reader
    clock.current = datetime.now()
    monkeypatch.setattr(record, "datetime", clock)
    monkeypatch.setattr(config, "plan", PlanModel())
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
    solver.read_operator_time = BaseSchedulerSolver.read_operator_time.__get__(solver)
    solver.leifeng_mode = True
    solver.find = MagicMock(
        side_effect=lambda name, scope=None: (
            name == "infra_no_operator" and scope[0][1] == 344
        )
    )
    return solver, target, clock


def curve_points(source, target):
    if source == "selected":
        return selected_mood_series(record.get_path("@app/tmp/data.db"), [target.name])[
            0
        ]["data"]
    return record.get_mood_ratios(include_work_rest=False)[0]["moodData"]["datasets"][
        0
    ]["data"]


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
def test_same_facility_zero_with_countdown_keeps_reading_and_raw_history(
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
        assert data["time"] == clock.now() + timedelta(seconds=3009)
    assert target.time_stamp == clock.now()
    assert record._fetchall("SELECT mood FROM agent_action") == [
        (1.2,),
        (0,),
        (0,),
        (0,),
    ]
    assert solver.tasks == []
    assert solver.read_time.call_count == 3
    assert target.depletion_rate == 0.8
    assert target.work_rate_sample_eligible is False
    assert record._fetchall("SELECT mood_event FROM agent_action") == [(None,)] * 4
    for source in ["grouped", "selected"]:
        assert [point["y"] for point in curve_points(source, target)] == [1.2]


@pytest.mark.parametrize(
    "previous_room,expected",
    [
        ("central", [(1.2,), (0,)]),
        ("meeting", [(1.2,), (0,)]),
        ("dormitory_1", [(1.2,), (0,)]),
        (None, [(0,)]),
    ],
)
def test_cleared_recovery_position_preserves_zero_observation(
    history_reader, previous_room, expected
):
    solver, target, clock = history_reader
    if previous_room:
        seed_history(target, clock, previous_room)
    target.current_room, target.current_index, target.time_stamp = "", -1, None
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert (target.current_room, target.current_index, target.mood) == ("central", 0, 0)
    assert record._fetchall("SELECT mood FROM agent_action") == expected


@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_reading_departure_before_arrival_keeps_zero_working_transition(
    history_reader, source
):
    solver, target, clock = history_reader
    seed_history(target, clock, "central")
    solver.read_screen.return_value = "絮雨"
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert target.current_room == ""
    solver.read_screen.return_value = target.name
    solver.get_agent_from_room("contact", force_mood=True, strict_observation=True)
    assert record._fetchall(
        "SELECT agent_current_room, current_room, mood FROM agent_action WHERE name = ?",
        target.name,
    ) == [("central", "central", 1.2), ("", "contact", 0)]
    assert [point["y"] for point in curve_points(source, target)] == [1.2, 0]


@pytest.mark.parametrize(
    "previous_room", ["meeting", "factory", "train", "recycle", "dormitory_1"]
)
@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_zero_with_countdown_records_actual_facility_change(
    history_reader, previous_room, source
):
    solver, target, clock = history_reader
    seed_history(target, clock, previous_room)
    target.current_room = previous_room
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT current_room, mood FROM agent_action") == [
        (previous_room, 1.2),
        ("central", 0),
    ]
    assert [point["y"] for point in curve_points(source, target)] == (
        [1.2] if previous_room == "dormitory_1" else [1.2, 0]
    )


@pytest.mark.parametrize("remaining", [None, 0])
@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_zero_without_countdown_records_exhaustion(history_reader, remaining, source):
    solver, target, clock = history_reader
    seed_history(target, clock, "central")
    solver.read_time.return_value = remaining
    solver.detect_room = MagicMock(return_value="central")
    solver.find = MagicMock(side_effect=lambda name, **kw: name == "room_detail")
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,), (0,)]
    assert target.exhaust_time == clock.now()
    assert record._fetchall("SELECT mood_event FROM agent_action") == [
        (None,),
        ("exhausted",),
    ]
    points = curve_points(source, target)
    assert [point["y"] for point in points] == [1.2, 0]
    assert points[-1]["moodEvent"] == "exhausted"
    assert target.depletion_rate == 0.8
    assert target.work_rate_sample_eligible is False


@pytest.mark.parametrize("remaining", [float("nan"), float("inf"), -1, "bad"])
def test_invalid_countdown_does_not_record_observation(history_reader, remaining):
    solver, target, clock = history_reader
    seed_history(target, clock, "central")
    solver.read_time.return_value = remaining
    with pytest.raises(RecognizeError):
        solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,)]


@pytest.mark.parametrize("mood", [1, 24])
def test_positive_mood_keeps_curve_without_extra_countdown(history_reader, mood):
    solver, target, clock = history_reader
    seed_history(target, clock, "central")
    solver.read_accurate_mood.return_value = mood
    solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,), (mood,)]
    for source in ["grouped", "selected"]:
        assert [point["y"] for point in curve_points(source, target)] == [1.2, mood]
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
    assert record._fetchall("SELECT mood FROM agent_action") == [(1.2,), (0,)]


@pytest.mark.parametrize("include_events", [False, True], ids=["legacy", "events"])
@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_curves_filter_stored_zero_mood_and_preserve_raw_events(
    monkeypatch, tmp_path, include_events, source
):
    database = tmp_path / "data.db"
    event_columns = ", related_operator TEXT, mood_event TEXT" if include_events else ""
    now = datetime.now()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE agent_action (name TEXT, agent_current_room TEXT, "
            "current_room TEXT, is_high INTEGER, agent_group TEXT, mood REAL, "
            f"current_time TEXT{event_columns})"
        )
        for index, mood in enumerate([1.2, 0.0, 0.5, 0.0]):
            values = [
                "夕",
                "central",
                "dormitory_1" if index == 1 else "central",
                1,
                "感知",
                mood,
                str(now + timedelta(seconds=index)),
            ]
            if include_events:
                values.extend(["菲亚梅塔", "fiammetta_before" if mood == 0 else None])
            connection.execute(
                f"INSERT INTO agent_action VALUES ({','.join('?' for _ in values)})",
                values,
            )
    monkeypatch.setattr(record, "_conn", _REAL_CONNECTION)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: database if path.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", PlanModel())
    original = database.read_bytes()
    if source == "selected":
        points = selected_mood_series(database, ["夕"])[0]["data"]
        assert database.read_bytes() == original
    else:
        points = record.get_mood_ratios()[0]["moodData"]["datasets"][0]["data"]
        # 零值进出设施与充能事件仍保留在原始记录中，工休比包含那一秒休息时间。
        assert record.get_work_rest_ratios()["夕"]["datasets"][0]["data"] == [1, 2]
    assert [point["y"] for point in points] == [1.2, 0.5]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT mood FROM agent_action").fetchall() == [
            (1.2,),
            (0,),
            (0.5,),
            (0,),
        ]
        if include_events:
            assert connection.execute(
                "SELECT COUNT(*) FROM agent_action WHERE mood_event = 'fiammetta_before'"
            ).fetchone() == (2,)


def test_selected_curve_filters_zero_before_sample_limit(income_db):
    with sqlite3.connect(income_db) as connection:
        connection.execute(
            "INSERT INTO agent_action (name, mood, current_time, current_room) "
            "VALUES (?, ?, ?, ?)",
            ("夕", 1.2, "2026-09-11 12:00:00.000000", "central"),
        )
        connection.execute(
            "INSERT INTO agent_action "
            "(name, mood, current_time, agent_current_room, current_room) "
            "VALUES (?, ?, ?, ?, ?)",
            ("夕", 0, "2026-09-11 12:00:30.000000", "", "contact"),
        )
        connection.execute(
            "INSERT INTO agent_action (name, mood, current_time, mood_event) "
            "VALUES (?, ?, ?, ?)",
            ("夕", 0, "2026-09-11 12:01:00.000000", "exhausted"),
        )
        connection.executemany(
            "INSERT INTO agent_action (name, mood, current_time) VALUES (?, ?, ?)",
            [("夕", 0.0, "2026-09-11 13:00:00.000000")] * 601,
        )
    assert [
        point["y"] for point in selected_mood_series(income_db, ["夕"])[0]["data"]
    ] == [1.2, 0, 0]


@pytest.mark.parametrize("include_events", [False, True])
@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_curves_preserve_working_transitions_in_legacy_history(
    tmp_path, monkeypatch, include_events, source
):
    database = tmp_path / "legacy.db"
    fields = ", related_operator TEXT, mood_event TEXT" if include_events else ""
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE agent_action (name TEXT, agent_current_room TEXT, "
            "current_room TEXT, is_high INTEGER, agent_group TEXT, mood REAL, "
            f"current_time TEXT{fields})"
        )
        for minute, (previous, current, mood, event) in enumerate(
            [
                ("central", "central", 1.2, None),
                ("central", "meeting", 0, None),
                ("meeting", "room_1_2", 0, None),
                ("room_1_2", "contact", 0, None),
                ("contact", "factory", 0, None),
                ("factory", "train", 0, None),
                ("train", "recycle", 0, None),
                ("recycle", "gaming_1", 0, None),
                ("gaming_1", "unknown", 0, None),
                ("unknown", "central", 0, None),
                ("contact", "contact", 0, None),
                ("contact", "dormitory_1", 0, None),
                ("dormitory_1", "central", 0, None),
                ("", "central", 0, None),
                (None, "central", 0, None),
                ("central", "", 0, None),
                ("central", None, 0, None),
                ("central", "central", 0, "exhausted"),
            ]
        ):
            values = [
                "夕",
                previous,
                current,
                1,
                "感知",
                mood,
                str(datetime.now().replace(hour=12, minute=minute)),
            ]
            if include_events:
                values.extend([None, event])
            connection.execute(
                f"INSERT INTO agent_action VALUES ({','.join('?' for _ in values)})",
                values,
            )
    original = database.read_bytes()

    @contextmanager
    def read_only_connection():
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(record, "_conn", read_only_connection)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", PlanModel())
    if source == "selected":
        points = selected_mood_series(database, ["夕"])[0]["data"]
    else:
        points = record.get_mood_ratios(include_work_rest=False)[0]["moodData"][
            "datasets"
        ][0]["data"]
    assert [point["y"] for point in points] == (
        [1.2, 0, 0, 0, 0, 0, 0, 0, 0] if include_events else [1.2, 0, 0, 0, 0, 0, 0, 0]
    )
    if include_events:
        assert points[-1]["moodEvent"] == "exhausted"
    assert database.read_bytes() == original


@pytest.mark.parametrize("room_column", [None, "agent_current_room", "current_room"])
@pytest.mark.parametrize("include_events", [False, True])
def test_minimal_history_without_facility_pair_keeps_only_confirmed_zero(
    tmp_path, room_column, include_events
):
    database = tmp_path / "minimal.db"
    fields = ["name TEXT", "mood REAL", "current_time TEXT"]
    if room_column:
        fields.append(f"{room_column} TEXT")
    if include_events:
        fields.append("mood_event TEXT")
    with sqlite3.connect(database) as connection:
        connection.execute(f"CREATE TABLE agent_action ({','.join(fields)})")
        for minute, (mood, event) in enumerate(
            [(1.2, None), (0, None), (0, "exhausted")]
        ):
            values = ["夕", mood, f"2026-10-27 12:{minute:02}:00"]
            if room_column:
                values.append("central")
            if include_events:
                values.append(event)
            connection.execute(
                f"INSERT INTO agent_action VALUES ({','.join('?' for _ in values)})",
                values,
            )
    original = database.read_bytes()
    assert [
        point["y"] for point in selected_mood_series(database, ["夕"])[0]["data"]
    ] == ([1.2, 0] if include_events else [1.2])
    assert database.read_bytes() == original


@pytest.mark.parametrize("source", ["grouped", "selected"])
@pytest.mark.parametrize("include_events", [False, True])
@pytest.mark.parametrize(
    "before,after,explicit_source,keep_zero",
    [
        ([("central", -1)], [], "", True),
        ([("central", -1)], [], None, True),
        ([("dormitory_1", -1)], [], "", False),
        ([("unknown", -1)], [], "", False),
        ([("", -1)], [], "", False),
        ([(None, -1)], [], "", False),
        ([], [], "", False),
        ([("central", -2), ("dormitory_1", -1)], [], "", False),
        ([("central", -2), ("contact", -1)], [], "", False),
        ([("central", 1)], [], "", False),
        ([("central", 0)], [], "", True),
        ([], [("central", 0)], "", False),
        ([("central", -1)], [], "contact", False),
        ([("central", -1)], [], "dormitory_1", False),
        ([("dormitory_1", -1)], [], "central", True),
    ],
)
def test_missing_source_uses_only_nearest_prior_facility(
    tmp_path,
    monkeypatch,
    source,
    include_events,
    before,
    after,
    explicit_source,
    keep_zero,
):
    database = tmp_path / "history.db"
    event_columns = ", related_operator TEXT, mood_event TEXT" if include_events else ""
    observed = datetime.now()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE agent_action (name TEXT, agent_current_room TEXT, "
            "current_room TEXT, is_high INTEGER, agent_group TEXT, mood REAL, "
            f"current_time TEXT{event_columns})"
        )
        connection.execute(
            'CREATE INDEX agent_action_name_time ON agent_action(name, "current_time")'
        )

        def save(previous, room, mood, seconds):
            connection.execute(
                "INSERT INTO agent_action "
                "(name, agent_current_room, current_room, is_high, agent_group, mood, "
                "current_time) VALUES (?, ?, ?, 1, '感知', ?, ?)",
                (
                    "夕",
                    previous,
                    room,
                    mood,
                    str(observed + timedelta(seconds=seconds)),
                ),
            )

        for room, seconds in before:
            save(room, room, 1.2, seconds)
        save(explicit_source, "contact", 0, 0)
        for room, seconds in after:
            save(room, room, 1.2, seconds)

    @contextmanager
    def read_only_connection():
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(record, "_conn", read_only_connection)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", PlanModel())
    original = database.read_bytes()
    if source == "selected":
        points = selected_mood_series(database, ["夕"])[0]["data"]
    else:
        groups = record.get_mood_ratios(include_work_rest=False)
        points = groups[0]["moodData"]["datasets"][0]["data"] if groups else []
    assert [point["y"] for point in points if point["y"] == 0] == (
        [0] if keep_zero else []
    )
    assert database.read_bytes() == original
