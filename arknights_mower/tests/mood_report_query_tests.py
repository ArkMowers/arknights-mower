"""Mood reports retain local date boundaries while using the time index."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import record
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanModel


@pytest.fixture
def report_history(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """CREATE TABLE agent_action (
            name TEXT, agent_current_room TEXT, current_room TEXT,
            is_high INTEGER, agent_group TEXT, mood REAL, current_time TEXT,
            related_operator TEXT, mood_event TEXT
        )"""
    )
    connection.execute(
        'CREATE INDEX agent_action_name_time ON agent_action(name, "current_time")'
    )
    queries = []

    def fetch(sql, *params):
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
            "INSERT INTO agent_action VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
