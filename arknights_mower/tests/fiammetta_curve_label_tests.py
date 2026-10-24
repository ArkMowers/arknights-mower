"""肥鸭充能采样的对象名持久化与曲线输出。"""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import record
from arknights_mower.solvers.mood_history_query import selected_mood_series
from arknights_mower.utils import config


@pytest.fixture
def curve_history(monkeypatch, tmp_path):
    database = tmp_path / "data.db"
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: database if path.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(config, "conf", config.Conf(favorite="歌蕾蒂娅"))
    exchange = datetime.now().replace(hour=10, minute=0, second=1, microsecond=123000)

    def save(seconds, mood, name="菲亚梅塔", event=None, related=None):
        record.save_agent_action(
            name,
            "dormitory_1",
            "dormitory_1",
            False,
            "",
            mood,
            mood_event=event,
            related_operator=related,
            current_time=exchange + timedelta(seconds=seconds),
        )

    return database, save


def curve_points(database, source):
    if source == "selected":
        return {
            series["name"]: series["data"]
            for series in selected_mood_series(database, ["菲亚梅塔", "歌蕾蒂娅"])
        }
    return {
        dataset["label"]: dataset["data"]
        for group in record.get_mood_ratios()
        for dataset in group["moodData"]["datasets"]
    }


@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_fiammetta_curves_hide_only_ordinary_points_within_ten_minutes(
    curve_history, source
):
    database, save = curve_history
    # Synthetic before points can be inserted after the measured after points.
    save(0, 7, event="fiammetta_charge", related="歌蕾蒂娅")
    save(-1, 24, event="fiammetta_charge", related="歌蕾蒂娅")
    save(-2, 23)
    save(0, 7.1)
    save(0.25, 7.2)
    save(599.75, 8)
    save(600, 9)
    save(601, 10)
    save(30, 24, name="歌蕾蒂娅")
    save(0, 24, name="歌蕾蒂娅", event="fiammetta_after", related="菲亚梅塔")
    original = database.read_bytes()

    points = curve_points(database, source)

    assert [point["y"] for point in points["菲亚梅塔"]] == [23, 24, 7, 9, 10]
    events = [point for point in points["菲亚梅塔"] if point.get("moodEvent")]
    assert len(events) == 2
    assert all(point["relatedOperator"] == "歌蕾蒂娅" for point in events)
    assert [point["y"] for point in points["歌蕾蒂娅"]] == [24, 24]
    assert points["歌蕾蒂娅"][0]["moodEvent"] == "fiammetta_after"
    assert database.read_bytes() == original


@pytest.mark.parametrize("source", ["grouped", "selected"])
def test_fiammetta_curve_window_restarts_without_hiding_new_exchanges(
    curve_history, source
):
    database, save = curve_history
    save(0, 7, event="fiammetta_charge", related="歌蕾蒂娅")
    save(300, 5, event="fiammetta_charge", related="煌")
    save(600, 8)
    save(899, 9)
    save(900, 10)

    points = curve_points(database, source)["菲亚梅塔"]

    assert [point["y"] for point in points] == [7, 5, 10]
    assert [point["relatedOperator"] for point in points[:2]] == ["歌蕾蒂娅", "煌"]


def test_selected_fiammetta_curve_filters_before_sample_limit(curve_history):
    database, save = curve_history
    save(0, 7, event="fiammetta_charge", related="歌蕾蒂娅")
    for index in range(601):
        save(1 + index / 2, 8)
    save(600, 9)

    points = selected_mood_series(database, ["菲亚梅塔"])[0]["data"]

    assert [point["y"] for point in points] == [7, 9]


def test_grouped_curve_uses_exchange_before_displayed_date_range(curve_history):
    database, save = curve_history
    # The grouped curve starts at midnight seven days ago; charge just before it.
    seconds = -(7 * 24 + 10) * 3600 - 2
    save(seconds, 7, event="fiammetta_charge", related="歌蕾蒂娅")
    save(seconds + 30, 8)
    save(seconds + 600, 9)

    points = curve_points(database, "grouped")["菲亚梅塔"]

    assert [point["y"] for point in points] == [9]


def test_agent_action_schema_adds_fiammetta_fields_to_legacy_table():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE agent_action (
            name TEXT, agent_current_room TEXT, current_room TEXT,
            is_high INTEGER, agent_group TEXT, mood REAL, current_time TEXT
        )
        """
    )
    record._tables_created = False

    record._ensure_tables(connection)

    columns = [row[1] for row in connection.execute("PRAGMA table_info(agent_action)")]
    assert columns[-4:] == [
        "related_operator",
        "mood_event",
        "context_key",
        "current_index",
    ]
    connection.close()
    record._tables_created = False


def test_agent_action_schema_migration_is_serialized(monkeypatch):
    class Cursor:
        def fetchall(self):
            return []

        def __iter__(self):
            return iter(self.fetchall())

    class Connection:
        def execute(self, _statement):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.005)
            with state_lock:
                active -= 1
            return Cursor()

        def commit(self):
            nonlocal commits
            commits += 1

    active = max_active = 0
    commits = 0
    workers = 8
    state_lock = threading.Lock()
    barrier = threading.Barrier(workers)
    monkeypatch.setattr(record, "_tables_created", False)

    def migrate():
        barrier.wait()
        record._ensure_tables(Connection())

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(migrate) for _ in range(workers)]
        for future in futures:
            future.result()

    assert max_active == 1
    assert commits == 1


def test_fiammetta_curve_point_contains_charged_operator(monkeypatch):
    rows = [
        (
            "菲亚梅塔",
            "dormitory_1",
            "dormitory_1",
            0,
            "",
            7.5,
            "2026-09-22 10:00:00.000000",
            "伊内丝",
            "fiammetta_charge",
        )
    ]
    monkeypatch.setattr(record, "_fetchall", lambda *args: rows)
    monkeypatch.setattr(
        record,
        "get_work_rest_ratios",
        lambda: {
            "菲亚梅塔": {
                "labels": ["休息时间", "工作时间"],
                "datasets": [{"data": [1, 0]}],
            }
        },
    )
    monkeypatch.setattr(config, "conf", config.Conf())

    data = record.get_mood_ratios()

    point = data[0]["moodData"]["datasets"][0]["data"][0]
    assert point == {
        "x": "2026-09-22T10:00:00.000000+08:00",
        "y": 7.5,
        "relatedOperator": "伊内丝",
        "moodEvent": "fiammetta_charge",
    }


def test_charged_operator_curve_contains_before_and_after_points(monkeypatch):
    rows = [
        (
            "歌蕾蒂娅",
            "control",
            "dormitory_1",
            1,
            "深海猎人",
            0,
            "2026-09-22 10:00:00.000000",
            "菲亚梅塔",
            "fiammetta_before",
        ),
        (
            "歌蕾蒂娅",
            "control",
            "dormitory_1",
            1,
            "深海猎人",
            24,
            "2026-09-22 10:00:01.000000",
            "菲亚梅塔",
            "fiammetta_after",
        ),
    ]
    monkeypatch.setattr(record, "_fetchall", lambda *args: rows)
    monkeypatch.setattr(
        record,
        "get_work_rest_ratios",
        lambda: {
            "歌蕾蒂娅": {
                "labels": ["休息时间", "工作时间"],
                "datasets": [{"data": [1, 0]}],
            }
        },
    )
    monkeypatch.setattr(config, "conf", config.Conf())

    points = record.get_mood_ratios()[0]["moodData"]["datasets"][0]["data"]

    assert points == [
        {
            "x": "2026-09-22T10:00:00.000000+08:00",
            "y": 0,
            "relatedOperator": "菲亚梅塔",
            "moodEvent": "fiammetta_before",
        },
        {
            "x": "2026-09-22T10:00:01.000000+08:00",
            "y": 24,
            "relatedOperator": "菲亚梅塔",
            "moodEvent": "fiammetta_after",
        },
    ]
