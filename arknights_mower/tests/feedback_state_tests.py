"""反馈专项当前快照的只读边界、真实表结构和预算验证。"""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import monotonic

import pytest

from arknights_mower.agent.tools import feedback_state as state


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "data.db"
    source = Path(__file__).parents[1] / "utils/mastery_db.py"
    assignments = {
        target.id: ast.literal_eval(node.value)
        for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in ("_PLAN_SCHEMA", "_ROUTE_SCHEMA")
    }
    with closing(sqlite3.connect(path)) as connection, connection:
        for statement in assignments.values():
            connection.execute(statement)
        connection.execute(
            "INSERT INTO mastery_plan "
            "(char_id, char_name, skill_index, skill_name, target_level, status, "
            "failed_reason, priority, expires_at, swap_frozen, support_plan, support_runtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "char_103_angel",
                "能天使",
                2,
                "三技能·过载模式",
                3,
                "failed",
                "训练室驻员未匹配\n保留待执行计划",
                4,
                "2026-11-07 12:00:00.123456",
                1,
                '{"stages":[{"assistant":"陈"}]}',
                '{"stage":2,"pending_restore":{"room":"central"}}',
            ),
        )
        connection.execute(
            "INSERT INTO mastery_route (profession, supports, is_default, optimal, half_off) "
            "VALUES ('SNIPER', ?, 0, 1, 0)",
            ('[{"name":"陈"}]',),
        )
    return path


def export(database, tmp_path):
    paths, metadata = state.collect_feedback_state(database, tmp_path / "output")
    contents = {
        path.name: [json.loads(line) for line in path.read_text().splitlines()]
        for path in paths
    }
    return paths, contents, metadata


def test_real_schema_current_state_allowlist_and_readonly(
    database, tmp_path, monkeypatch
):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("ALTER TABLE mastery_plan ADD COLUMN future_secret TEXT")
        connection.execute("UPDATE mastery_plan SET future_secret='private-future'")
        connection.execute("CREATE TABLE saved_state (key TEXT, data BLOB)")
        connection.execute("INSERT INTO saved_state VALUES ('private', X'8004')")
        connection.execute("CREATE TABLE credentials (token TEXT)")
        connection.execute("INSERT INTO credentials VALUES ('private-token')")
    original = database.read_bytes()
    connect = sqlite3.connect
    accessed = set()

    def readonly_connect(database_uri, **kwargs):
        assert database_uri.endswith("?mode=ro") and kwargs["uri"]
        connection = connect(database_uri, **kwargs)

        def authorize(action, table, column, _database, _trigger):
            if action == sqlite3.SQLITE_READ:
                accessed.add(table)
                assert table not in ("saved_state", "credentials")
                assert column != "future_secret"
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden (token TEXT)")
        return connection

    monkeypatch.setattr(state.sqlite3, "connect", readonly_connect)
    paths, contents, metadata = export(database, tmp_path)
    plan = contents["mastery_plans.jsonl"][0]
    assert plan == {
        "id": 1,
        "char_id": "char_103_angel",
        "char_name": "能天使",
        "skill_index": 2,
        "skill_name": "三技能·过载模式",
        "target_level": 3,
        "status": "failed",
        "failed_reason": "训练室驻员未匹配\n保留待执行计划",
        "priority": 4,
        "expires_at": "2026-11-07 12:00:00.123456",
        "swap_frozen": 1,
        "support_plan": '{"stages":[{"assistant":"陈"}]}',
        "support_runtime": '{"stage":2,"pending_restore":{"room":"central"}}',
        "created_at": plan["created_at"],
    }
    route = contents["mastery_routes.jsonl"][0]
    assert route == {
        "profession": "SNIPER",
        "supports": '[{"name":"陈"}]',
        "is_default": 0,
        "optimal": 1,
        "half_off": 0,
        "created_at": route["created_at"],
    }
    assert accessed >= {"mastery_plan", "mastery_route"}
    assert metadata["current_snapshot_not_historical"] is True
    assert datetime.fromisoformat(metadata["collection_started_at"]).tzinfo
    assert datetime.fromisoformat(metadata["collection_finished_at"]).tzinfo
    assert metadata["scheduler_runtime"]["status"] == "unavailable"
    assert "effective_backup_plans" in metadata["scheduler_runtime"]["missing"]
    assert "task_queue" in metadata["scheduler_runtime"]["missing"]
    assert metadata["scheduler_runtime"]["reason"] == "no_synchronized_snapshot"
    for table, filename in (
        ("mastery_plan", "mastery_plans.jsonl"),
        ("mastery_route", "mastery_routes.jsonl"),
    ):
        info = metadata["tables"][table]
        assert info["status"] == "exported"
        assert info["scan_complete"] and not info["truncated"]
        assert info["row_count"] == 1
        assert info["bytes"] == next(
            p.stat().st_size for p in paths if p.name == filename
        )
        assert not info["missing_columns"]
        assert info["first_key"] == info["last_key"]
    assert metadata["tables"]["mastery_plan"]["first_key"] == {"priority": 4, "id": 1}
    assert database.read_bytes() == original
    assert all(b"private" not in path.read_bytes() for path in paths)


def test_two_tables_share_read_transaction(database, tmp_path, monkeypatch):
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    original = state._collect_table

    def collect(connection, table, spec, output, metadata):
        result = original(connection, table, spec, output, metadata)
        if table == "mastery_plan":
            with closing(sqlite3.connect(database)) as writer, writer:
                writer.execute("UPDATE mastery_route SET supports='changed-after-read'")
        return result

    monkeypatch.setattr(state, "_collect_table", collect)
    _, contents, _ = export(database, tmp_path)
    assert contents["mastery_routes.jsonl"][0]["supports"] == '[{"name":"陈"}]'


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "absent.db"
    paths, _, metadata = export(path, tmp_path)
    assert paths == []
    assert not path.exists() and not (tmp_path / "output").exists()
    assert all(
        info["reason"] == "missing_database" for info in metadata["tables"].values()
    )


def test_legacy_columns_are_reported_without_migration(tmp_path):
    path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE mastery_plan (id INTEGER, status TEXT)")
        connection.execute("INSERT INTO mastery_plan VALUES (1, 'training')")
    original = path.read_bytes()
    _, contents, metadata = export(path, tmp_path)
    assert contents["mastery_plans.jsonl"] == [{"id": 1, "status": "training"}]
    info = metadata["tables"]["mastery_plan"]
    assert info["status"] == "partial" and info["reason"] == "missing_columns"
    assert info["scan_complete"]
    assert {"support_plan", "support_runtime", "failed_reason"} <= set(
        info["missing_columns"]
    )
    assert metadata["tables"]["mastery_route"]["reason"] == "missing_table"
    assert path.read_bytes() == original


def test_empty_existing_table_is_distinct_from_missing(database, tmp_path):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("DELETE FROM mastery_plan")
    _, contents, metadata = export(database, tmp_path)
    assert contents["mastery_plans.jsonl"] == []
    info = metadata["tables"]["mastery_plan"]
    assert info["status"] == "empty" and info["scan_complete"]
    assert info["bytes"] == info["row_count"] == 0
    assert "不证明字段完整或历史完整" in metadata["selection_note"]


def test_row_budget_is_explicit(database, tmp_path, monkeypatch):
    monkeypatch.setattr(state, "MAX_ROWS", 1)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "INSERT INTO mastery_plan (char_id, skill_index, target_level, priority) "
            "VALUES ('second', 0, 1, 0)"
        )
    _, contents, metadata = export(database, tmp_path)
    assert contents["mastery_plans.jsonl"][0]["char_id"] == "second"
    assert len(contents["mastery_plans.jsonl"]) == 1
    info = metadata["tables"]["mastery_plan"]
    assert info["reason"] == "row_limit" and info["truncated"]
    assert not info["scan_complete"]
    assert metadata["limits"]["rows_per_table"] == 1


def test_byte_budget_preserves_whole_utf8_rows(database, tmp_path, monkeypatch):
    monkeypatch.setattr(state, "MAX_FILE_BYTES", 100)
    paths, contents, metadata = export(database, tmp_path)
    assert contents["mastery_plans.jsonl"] == []
    for info in metadata["tables"].values():
        assert info["reason"] == "byte_limit" and info["truncated"]
        assert not info["scan_complete"]
    assert all(path.stat().st_size == 0 for path in paths)


def test_field_budget_and_blob_omit_values_without_decoding(database, tmp_path):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE mastery_plan SET support_plan=?, support_runtime=?",
            ("中" * state.MAX_FIELD_BYTES, b"\x80\x04private-pickle"),
        )
    _, contents, metadata = export(database, tmp_path)
    record = contents["mastery_plans.jsonl"][0]
    assert record["status"] == "failed"
    assert record["_omitted_fields"] == ["support_plan", "support_runtime"]
    assert "support_plan" not in record and "support_runtime" not in record
    info = metadata["tables"]["mastery_plan"]
    assert info["status"] == "partial" and info["scan_complete"]
    assert info["reason"] == "field_limit_or_blob" and info["truncated"]
    assert info["omitted_value_count"] == 2
    assert info["omitted_columns"] == ["support_plan", "support_runtime"]


def test_locked_database_returns_within_budget(database, tmp_path, monkeypatch):
    monkeypatch.setattr(state, "QUERY_TIMEOUT_SECONDS", 0.03)
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        started = monotonic()
        paths, _, metadata = export(database, tmp_path)
        elapsed = monotonic() - started
        writer.rollback()
    assert elapsed < 1 and paths == []
    assert all(
        info["reason"] == "database_locked" for info in metadata["tables"].values()
    )


def test_expired_budget_is_reported(database, tmp_path, monkeypatch):
    monkeypatch.setattr(state, "QUERY_TIMEOUT_SECONDS", 0)
    paths, _, metadata = export(database, tmp_path)
    assert paths == []
    assert all(
        info["reason"] == "query_timeout" for info in metadata["tables"].values()
    )


def test_corrupt_database_is_unavailable_without_path_disclosure(tmp_path):
    path = tmp_path / "private-user.db"
    path.write_bytes(b"not a database")
    paths, _, metadata = export(path, tmp_path)
    assert paths == []
    assert all(
        info["reason"] == "collection_failed" for info in metadata["tables"].values()
    )
    assert "private-user" not in json.dumps(metadata)


def test_sqlite_progress_handler_interrupts_work(database, tmp_path, monkeypatch):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO mastery_plan (char_id, skill_index, target_level) VALUES ('x', 0, 1)",
            [()] * 1000,
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

    monkeypatch.setattr(state.sqlite3, "connect", connect)
    monkeypatch.setattr(state, "monotonic", lambda: clock[0])
    _, _, metadata = export(database, tmp_path)
    assert progress_calls
    info = metadata["tables"]["mastery_plan"]
    assert info["reason"] == "query_timeout"
    assert not info["scan_complete"]


def test_unusable_first_table_does_not_prevent_second(database, tmp_path):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("DROP TABLE mastery_plan")
        connection.execute("CREATE TABLE mastery_plan (private_token TEXT)")
        connection.execute("UPDATE mastery_route SET supports='legacy non-JSON value'")
    paths, contents, metadata = export(database, tmp_path)
    assert [path.name for path in paths] == ["mastery_routes.jsonl"]
    assert metadata["tables"]["mastery_plan"]["reason"] == "missing_columns"
    assert metadata["tables"]["mastery_route"]["status"] == "exported"
    assert contents["mastery_routes.jsonl"][0]["supports"] == "legacy non-JSON value"
