"""反馈历史附件的只读、范围和容量约束。"""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import monotonic

import pytest

from arknights_mower.agent.tools import feedback_records as records

START = datetime(2026, 11, 6, 12, 0)
END = datetime(2026, 11, 6, 12, 15)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "data.db"
    # 静态读取生产建表语句，避免导入调度器或用户数据访问代码。
    source = Path(__file__).parents[1] / "solvers/record.py"
    assignment = next(
        node
        for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_DB_TABLE_STMTS"
            for target in node.targets
        )
    )
    with closing(sqlite3.connect(path)) as connection, connection:
        for statement in ast.literal_eval(assignment.value):
            connection.execute(statement)
        # 当前生产初始化另以迁移加入这两列。
        connection.execute("ALTER TABLE agent_action ADD COLUMN context_key TEXT")
        connection.execute("ALTER TABLE agent_action ADD COLUMN current_index INTEGER")
    return path


def export(database, tmp_path):
    paths, metadata = records.collect_feedback_records(
        database, START, END, tmp_path / "output"
    )
    contents = {
        path.name: [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        for path in paths
    }
    return paths, contents, metadata["tables"]


def test_actual_schema_interval_fields_and_more_than_one_hundred_rows(
    database, tmp_path
):
    start, end = START.timestamp(), END.timestamp()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO log VALUES (?, ?, ?, ?)",
            [(start - 1, "outside", "INFO", "before")]
            + [
                (start + index, '{"operator":"能天使"}', "ERROR", "第一行\n第二行")
                for index in range(150)
            ]
            + [
                (end + 0.75, "end-second", "INFO", "included"),
                (end + 1, "outside", "INFO", "after"),
            ],
        )
        connection.executemany(
            "INSERT INTO agent_action "
            "(name, agent_current_room, current_room, is_high, agent_group, mood, "
            "current_time, related_operator, mood_event, context_key, current_index) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "能天使",
                    "room_1_1",
                    "dorm_1",
                    1,
                    "贸易组",
                    3.75,
                    when,
                    "菲亚梅塔",
                    "charge",
                    "normal",
                    2,
                )
                for when in (
                    "2026-11-06 11:59:59.999",
                    "2026-11-06 12:00:00",
                    "2026-11-06 12:15:00.999999",
                    "2026-11-06 12:15:01",
                )
            ],
        )
        connection.execute(
            "INSERT INTO saved_state VALUES ('private', ?)", (b"private-blob",)
        )
        connection.execute("CREATE TABLE credentials (secret TEXT)")
        connection.execute("INSERT INTO credentials VALUES ('private-secret')")
    original = database.read_bytes()
    paths, contents, tables = export(database, tmp_path)
    tasks = contents["task_history.jsonl"]
    operators = contents["operator_history.jsonl"]
    assert len(tasks) == 151
    assert tasks[0] == {
        "time": start,
        "task": '{"operator":"能天使"}',
        "level": "ERROR",
        "message": "第一行\n第二行",
    }
    assert tasks[-1]["time"] == end + 0.75
    assert [row["current_time"] for row in operators] == [
        "2026-11-06 12:00:00",
        "2026-11-06 12:15:00.999999",
    ]
    assert operators[0] == {
        "name": "能天使",
        "agent_current_room": "room_1_1",
        "current_room": "dorm_1",
        "is_high": 1,
        "agent_group": "贸易组",
        "mood": 3.75,
        "current_time": "2026-11-06 12:00:00",
        "related_operator": "菲亚梅塔",
        "mood_event": "charge",
        "context_key": "normal",
        "current_index": 2,
    }
    for name, table in (
        ("task_history.jsonl", "log"),
        ("operator_history.jsonl", "agent_action"),
    ):
        info = tables[table]
        assert info["status"] == "exported"
        assert info["scan_complete"] and not info["truncated"]
        assert info["row_count"] == len(contents[name])
        assert info["bytes"] == next(
            path.stat().st_size for path in paths if path.name == name
        )
    assert tables["agent_action"]["last_time"] == "2026-11-06 12:15:00.999999"
    assert all(b"private" not in path.read_bytes() for path in paths)
    assert database.read_bytes() == original


def test_real_row_limit_is_reported(database, tmp_path):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO log VALUES (?, '{}', 'INFO', 'task')",
            [(START.timestamp(),)] * 5001,
        )
    _, contents, tables = export(database, tmp_path)
    assert len(contents["task_history.jsonl"]) == 5000
    assert tables["log"]["reason"] == "row_limit"
    assert tables["log"]["truncated"] and not tables["log"]["scan_complete"]


def test_byte_limit_keeps_whole_utf8_records(database, tmp_path):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO log VALUES (?, '{}', 'INFO', ?)",
            [(START.timestamp(), "干员" * 100000)] * 3,
        )
    paths, contents, tables = export(database, tmp_path)
    info = tables["log"]
    assert len(contents["task_history.jsonl"]) == 1
    assert info["bytes"] == paths[0].stat().st_size <= 1024 * 1024
    assert info["reason"] == "byte_limit"
    assert info["truncated"] and not info["scan_complete"]


def test_empty_results_do_not_claim_complete_history(database, tmp_path):
    paths, metadata = records.collect_feedback_records(
        database, START, END, tmp_path / "output"
    )
    assert len(paths) == 2
    for info in metadata["tables"].values():
        assert info["status"] == "empty"
        assert info["first_time"] is info["last_time"] is None
        assert info["row_count"] == info["bytes"] == 0
        assert info["scan_complete"]
    assert "不证明历史记录完整" in metadata["selection_note"]


def test_missing_database_is_not_created(tmp_path):
    database = tmp_path / "absent.db"
    paths, metadata = records.collect_feedback_records(
        database, START, END, tmp_path / "output"
    )
    assert paths == []
    assert not database.exists()
    assert not (tmp_path / "output").exists()
    assert all(
        info["reason"] == "missing_database" for info in metadata["tables"].values()
    )


def test_readonly_uri_and_query_only_prevent_writes(database):
    with closing(records._connect_readonly(database)) as connection:
        assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden (secret TEXT)")
        connection.execute("PRAGMA query_only = OFF")
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO log VALUES (0, '{}', 'INFO', 'write')")


def test_legacy_columns_and_missing_table_are_explicit(tmp_path):
    database = tmp_path / "legacy.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE TABLE agent_action (name TEXT, mood REAL, current_time TEXT)"
        )
        connection.execute(
            "INSERT INTO agent_action VALUES ('能天使', 0, '2026-11-06 12:01:00')"
        )
    _, contents, tables = export(database, tmp_path)
    assert contents["operator_history.jsonl"] == [
        {
            "name": "能天使",
            "mood": 0.0,
            "current_time": "2026-11-06 12:01:00",
        }
    ]
    assert tables["log"]["reason"] == "missing_table"
    assert tables["agent_action"]["status"] == "partial"
    assert "related_operator" in tables["agent_action"]["missing_columns"]
    assert "context_key" in tables["agent_action"]["missing_columns"]
    assert tables["agent_action"]["scan_complete"]


def test_exclusive_lock_returns_without_writing(database, tmp_path, monkeypatch):
    monkeypatch.setattr(records, "QUERY_TIMEOUT_SECONDS", 0.03)
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        began = monotonic()
        paths, metadata = records.collect_feedback_records(
            database, START, END, tmp_path / "output"
        )
        elapsed = monotonic() - began
        writer.rollback()
    assert paths == []
    assert elapsed < 1
    assert all(not info["scan_complete"] for info in metadata["tables"].values())
    assert all(info["status"] == "unavailable" for info in metadata["tables"].values())
    assert all(
        info["reason"] == "database_locked" for info in metadata["tables"].values()
    )


def test_query_execution_has_a_deadline(database, tmp_path, monkeypatch):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO log VALUES (?, '{}', 'INFO', 'task')",
            [(START.timestamp(),)] * 1000,
        )
    monkeypatch.setattr(records, "QUERY_TIMEOUT_SECONDS", 0)
    paths, metadata = records.collect_feedback_records(
        database, START, END, tmp_path / "output"
    )
    assert all(
        info["reason"] == "query_timeout" for info in metadata["tables"].values()
    )
    assert all(not info["scan_complete"] for info in metadata["tables"].values())
    assert all(path.stat().st_size == 0 for path in paths)


def test_sqlite_progress_handler_interrupts_query(database, tmp_path, monkeypatch):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO log VALUES (?, '{}', 'INFO', 'task')",
            [(START.timestamp(),)] * 1000,
        )
    original_connect = sqlite3.connect
    clock = [0.0]
    progress_calls = []

    class ObservedConnection(sqlite3.Connection):
        def set_progress_handler(self, callback, operations):
            def deadline_passed():
                progress_calls.append(True)
                clock[0] += 3
                return callback()

            return super().set_progress_handler(deadline_passed, operations)

    def connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=ObservedConnection)

    monkeypatch.setattr(records.sqlite3, "connect", connect)
    monkeypatch.setattr(records, "monotonic", lambda: clock[0])
    _, metadata = records.collect_feedback_records(
        database, START, END, tmp_path / "output"
    )
    assert progress_calls
    info = metadata["tables"]["log"]
    assert info["reason"] == "query_timeout"
    assert not info["scan_complete"]
