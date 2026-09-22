"""肥鸭充能采样的对象名持久化与曲线输出。"""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from arknights_mower.solvers import record
from arknights_mower.utils import config


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
    assert columns[-2:] == ["related_operator", "mood_event"]
    connection.close()
    record._tables_created = False


def test_agent_action_schema_migration_is_serialized():
    class Cursor:
        def fetchall(self):
            return []

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
            pass

    active = max_active = 0
    workers = 8
    state_lock = threading.Lock()
    barrier = threading.Barrier(workers)
    record._tables_created = False

    def migrate():
        barrier.wait()
        record._ensure_tables(Connection())

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(migrate) for _ in range(workers)]
        for future in futures:
            future.result()

    assert max_active == 1
    record._tables_created = False


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
