"""肥鸭充能采样的对象名持久化与曲线输出。"""

import sqlite3

from arknights_mower.solvers import record
from arknights_mower.utils import config


def test_agent_action_schema_adds_related_operator_to_legacy_table():
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
    assert columns[-1] == "related_operator"
    connection.close()
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
    }
