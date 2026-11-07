"""Mood reports retain local date boundaries while using the time index."""

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import mood_history_query, record
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanModel


@pytest.fixture(params=[7, 9], ids=["legacy-seven-columns", "nine-columns"])
def report_history(monkeypatch, request):
    connection = sqlite3.connect(":memory:")
    event_columns = (
        ", related_operator TEXT, mood_event TEXT" if request.param == 9 else ""
    )
    connection.execute(
        """CREATE TABLE agent_action (
            name TEXT, agent_current_room TEXT, current_room TEXT,
            is_high INTEGER, agent_group TEXT, mood REAL, current_time TEXT
        """
        + event_columns
        + ")"
    )
    monkeypatch.setattr(record, "_tables_created", False)
    record._ensure_tables(connection)
    queries = []

    def fetch(sql, *params):
        if sql.lstrip().upper().startswith("SELECT"):
            queries.append((sql, params))
        return connection.execute(sql, params).fetchall()

    monkeypatch.setattr(record, "_fetchall", fetch)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", PlanModel())
    week, month = (
        datetime.fromisoformat(value)
        for value in connection.execute(
            "SELECT DATE('now', '-7 day', 'localtime'), "
            "DATE('now', '-1 month', 'localtime')"
        ).fetchone()
    )
    recent = week + timedelta(days=1)

    def add(name, timestamp, mood):
        connection.execute(
            "INSERT INTO agent_action (name, agent_current_room, current_room, "
            "is_high, agent_group, mood, current_time, related_operator, mood_event) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                "room_1_1",
                "room_1_1",
                1,
                name,
                mood,
                timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
                None,
                None,
            ),
        )

    add("worker", month - timedelta(seconds=1), 24)
    add("worker", month, 23)
    add("worker", week - timedelta(microseconds=1), 22)
    add("worker", week, 21)
    add("worker", recent, 20)
    add("retired", week - timedelta(microseconds=1), 19)
    yield connection, queries, month, recent
    connection.close()


def test_reports_preserve_inclusive_local_midnight_boundaries(report_history):
    _, _, month, recent = report_history
    groups = record.get_mood_ratios()
    assert [group["groupName"] for group in groups] == ["worker"]
    points = groups[0]["moodData"]["datasets"][0]["data"]
    assert [point["y"] for point in points] == [21, 20]
    assert groups[0]["workRestData"]["datasets"][0]["data"] == [
        0,
        (recent - month).total_seconds(),
    ]


@pytest.mark.parametrize("operation", ["get_mood_ratios", "get_work_rest_ratios"])
def test_report_samples_use_the_existing_name_time_index(report_history, operation):
    connection, queries, _, _ = report_history
    getattr(record, operation)()
    assert queries
    for sql, params in queries:
        plan = connection.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        assert any(
            "SEARCH a USING INDEX agent_action_name_time" in row[3]
            and "current_time>?" in row[3]
            for row in plan
        ), plan


@pytest.mark.parametrize("operation", ["get_mood_ratios", "get_work_rest_ratios"])
def test_report_membership_searches_only_recent_working_history(
    report_history, operation
):
    connection, queries, _, _ = report_history
    getattr(record, operation)()
    assert queries
    for sql, params in queries:
        plan = connection.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        assert any(
            "SEARCH b USING INDEX agent_action_working_time" in row[3]
            and "current_time>?" in row[3]
            for row in plan
        ), plan


@pytest.mark.parametrize("columns", [7, 9])
def test_directory_migration_covers_query_without_changing_history(
    tmp_path, monkeypatch, columns
):
    database = tmp_path / "history.db"
    events = ", related_operator TEXT, mood_event TEXT" if columns == 9 else ""
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE TABLE agent_action (name TEXT, agent_current_room TEXT, "
            "current_room TEXT, is_high INTEGER, agent_group TEXT, mood REAL, "
            f"current_time TEXT{events})"
        )
        observations = [
            ("older", 12, "2020-01-01 12:00:00"),
            ("recent", 23, "2026-10-23 12:00:00"),
            ("recent", 22, "2026-10-24 12:00:00"),
            (None, 24, "2026-10-24 12:00:00"),
            (" ", 24, "2026-10-24 12:00:00"),
            ("unknown", None, "2026-10-24 12:00:00"),
            ("no time", 24, None),
        ]
        connection.executemany(
            'INSERT INTO agent_action(name, mood, "current_time") VALUES (?, ?, ?)',
            observations,
        )
        monkeypatch.setattr(record, "_tables_created", False)
        record._ensure_tables(connection)
        assert (
            connection.execute(
                'SELECT name, mood, "current_time" FROM agent_action ORDER BY rowid'
            ).fetchall()
            == observations
        )

    queries = []
    original_open = mood_history_query._open_history

    def open_history(path):
        connection = original_open(path)
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(mood_history_query, "_open_history", open_history)
    before = database.read_bytes()
    assert mood_history_query.available_mood_operators(database) == [
        {"name": "recent", "sampleCount": 2, "lastRecordedAt": "2026-10-24 12:00:00"},
        {"name": "older", "sampleCount": 1, "lastRecordedAt": "2020-01-01 12:00:00"},
    ]
    assert database.read_bytes() == before
    query = next(sql for sql in queries if "COUNT(*)" in sql)
    with closing(sqlite3.connect(database)) as connection, connection:
        plan = connection.execute("EXPLAIN QUERY PLAN " + query).fetchall()
        assert any(
            "USING COVERING INDEX agent_action_mood_directory" in row[3] for row in plan
        ), plan
        connection.execute("DELETE FROM agent_action WHERE name = 'recent'")
        connection.execute(
            'INSERT INTO agent_action(name, mood, "current_time") VALUES (?, ?, ?)',
            ("new", 24, "2026-10-25 12:00:00"),
        )
    assert mood_history_query.available_mood_operators(database) == [
        {"name": "new", "sampleCount": 1, "lastRecordedAt": "2026-10-25 12:00:00"},
        {"name": "older", "sampleCount": 1, "lastRecordedAt": "2020-01-01 12:00:00"},
    ]
