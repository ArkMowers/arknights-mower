"""附加反馈时段的范围、原始记录和失败隔离。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from zipfile import ZipExtFile

import pytest

from arknights_mower.agent.tools import feedback_windows as windows
from arknights_mower.tests import feedback_records_tests

database = feedback_records_tests.database
PRIMARY_START = datetime(2026, 11, 6, 12, 0)
PRIMARY_END = datetime(2026, 11, 6, 12, 1)


def window(start="2026-11-06 10:00:00", end="2026-11-06 10:01:00", reason="原任务创建"):
    return {"start_time": start, "end_time": end, "reason": reason}


@pytest.fixture
def sources(tmp_path):
    logs, screenshots, output = (
        tmp_path / name for name in ("log", "screenshots", "output")
    )
    logs.mkdir()
    screenshots.mkdir()
    return logs, screenshots, output


def collect(selected, sources, db_path):
    logs, screenshots, output = sources
    return windows.collect_feedback_windows(
        selected, PRIMARY_START, PRIMARY_END, logs, screenshots, db_path, output
    )


def test_actual_sources_preserve_full_logs_and_database_final_second(
    sources, database, monkeypatch
):
    logs, screenshots, _ = sources
    long_message = "原始记录" * 20000
    original = (
        f"2026-11-06 10:00:00 solver.py:1 ERROR {long_message}\n"
        "  traceback continuation\n"
        "2026-11-06 10:01:00 solver.py:2 INFO task created\n"
        "2026-11-06 10:01:00 solver.py:2 INFO task created\n"
    )
    later = "2026-11-06 13:00:01 solver.py:3 INFO later handling\n"
    (logs / "runtime.log").write_text(
        original + "2026-11-06 11:00:00 solver.py:1 INFO unselected gap\n" + later,
        encoding="utf-8",
    )
    start = datetime(2026, 11, 6, 10).timestamp()
    end = start + 60
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO log VALUES (?, '{}', 'INFO', ?)",
            [
                (start - 0.1, "before"),
                (start + 0.5, "created"),
                (end + 0.999, "final second"),
                (end + 1, "after"),
            ],
        )
        connection.executemany(
            "INSERT INTO agent_action (name, current_time, mood) VALUES ('能天使', ?, 12)",
            [("2026-11-06 10:01:00.999",), ("2026-11-06 10:01:01",)],
        )
    stamp = int(start * 10**9)
    (screenshots / f"{stamp}.jpg").write_bytes(b"unselected screenshot")
    reads = []
    original_read = ZipExtFile.read

    def bounded_read(stream, size=-1):
        reads.append(size)
        assert 0 < size <= 64 * 1024
        return original_read(stream, size)

    monkeypatch.setattr(ZipExtFile, "read", bounded_read)
    members, metadata = collect(
        [window(), window("2026-11-06 13:00:00", "2026-11-06 13:01:00", "后续处理")],
        sources,
        database,
    )
    assert reads and len(reads) > 4
    expected = {
        "runtime.log",
        "runtime.txt",
        "evidence.json",
        "task_history.jsonl",
        "operator_history.jsonl",
    }
    assert set(members) == {
        f"windows/{index}/{name}" for index in (1, 2) for name in expected
    }
    assert all(
        name.isascii() and not name.endswith((".zip", ".db", ".jpg"))
        for name in members
    )
    assert members["windows/1/runtime.log"].read_text(encoding="utf-8") == original
    assert members["windows/2/runtime.log"].read_text(encoding="utf-8") == later
    tasks = [
        json.loads(line)
        for line in members["windows/1/task_history.jsonl"].read_text().splitlines()
    ]
    assert [row["message"] for row in tasks] == ["created", "final second"]
    operators = [
        json.loads(line)
        for line in members["windows/1/operator_history.jsonl"].read_text().splitlines()
    ]
    assert [row["current_time"] for row in operators] == ["2026-11-06 10:01:00.999"]
    info = metadata["windows"][0]
    assert info["reason"] == "原任务创建"
    assert info["logs"]["status"] == "exported"
    assert info["logs"]["log_archive"]["first_time"] == "2026-11-06 10:00:00"
    assert info["logs"]["log_archive"]["last_time"] == "2026-11-06 10:01:00"
    assert info["logs"]["log_archive"]["record_count"] == 3
    assert "不证明连续完整覆盖" in metadata["selection_note"]
    assert metadata["limits"]["additional_screenshots"] == 0
    assert metadata["limits"]["uncompressed_log_bytes_total"] == 3 * 64 * 1024**2
    manifest = json.loads(members["windows/1/evidence.json"].read_text())
    assert manifest["screenshots"] == []
    assert manifest["log_archive"]["file"] == "windows/1/runtime.log"
    assert manifest["database_records"] == info["database_records"]
    assert (
        manifest["database_records"]["tables"]["log"]["file"]
        == "windows/1/task_history.jsonl"
    )
    assert set(manifest["additional_window"]["members"]) == {
        name for name in members if name.startswith("windows/1/")
    }


@pytest.mark.parametrize(
    "selected",
    [
        "invalid",
        {},
        1,
        False,
        [window()] * 4,
        [None],
        [{}],
        [{**window(), "extra": "unknown"}],
        [window(reason=None)],
        [window(reason=False)],
        [window(reason="  ")],
        [window(reason="字" * 501)],
        [window(start=False)],
        [window(end=20261106)],
        [window(start="2026-11-6 10:00:00")],
        [window(start="2026-11-31 10:00:00")],
        [window(end="2026-11-06 10:00:00")],
        [window(end="2026-11-06 10:15:01")],
        [window(start="2026-11-06 11:59:00", end="2026-11-06 12:00:00")],
        [window(start="2026-11-06 12:01:00", end="2026-11-06 12:02:00")],
        [window(), window("2026-11-06 10:01:00", "2026-11-06 10:02:00")],
        [window(), window("2026-11-06 10:00:30", "2026-11-06 10:00:45")],
        [window(), window(end="2026-11-06 10:16:00")],
    ],
)
def test_all_validation_precedes_any_read(selected, sources, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid windows must not read any evidence")

    monkeypatch.setattr(windows, "collect_evidence", forbidden)
    monkeypatch.setattr(windows, "collect_feedback_records", forbidden)
    with pytest.raises(ValueError):
        collect(selected, sources, tmp_path / "missing.db")
    assert not sources[2].exists()


@pytest.mark.parametrize("selected", [None, []])
def test_omitted_windows_do_not_read_sources(selected, sources, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("omitted windows must not read evidence")

    monkeypatch.setattr(windows, "collect_evidence", forbidden)
    monkeypatch.setattr(windows, "collect_feedback_records", forbidden)
    members, metadata = collect(selected, sources, tmp_path / "missing.db")
    assert members == {} and metadata["windows"] == []
    assert not sources[2].exists()


def test_validation_accepts_three_nonoverlapping_fifteen_minute_windows():
    selected = windows.validate_feedback_windows(
        [
            window(end="2026-11-06 10:15:00", reason="字" * 500),
            window("2026-11-06 10:15:01", "2026-11-06 10:30:01"),
            window("2026-11-06 12:01:01", "2026-11-06 12:16:01"),
        ],
        PRIMARY_START,
        PRIMARY_END,
    )
    assert len(selected) == 3
    assert selected[0]["start"] == datetime(2026, 11, 6, 10)


def test_missing_logs_keep_database_and_state_unavailable(sources, database):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "INSERT INTO log VALUES (?, '{}', 'INFO', 'created')",
            (datetime(2026, 11, 6, 10).timestamp(),),
        )
    members, metadata = collect([window()], sources, database)
    assert set(members) == {
        f"windows/1/{name}"
        for name in ("evidence.json", "task_history.jsonl", "operator_history.jsonl")
    }
    info = metadata["windows"][0]
    assert info["logs"]["status"] == "unavailable"
    assert info["logs"]["reason"] == "no_logs"
    assert info["database_records"]["tables"]["log"]["row_count"] == 1
    assert "log_archive" not in json.loads(
        members["windows/1/evidence.json"].read_text()
    )


def test_missing_database_is_recorded_without_creating_it(sources, tmp_path):
    (sources[0] / "runtime.log").write_text(
        "2026-11-06 10:00:00 solver.py:1 INFO created\n"
    )
    missing = tmp_path / "absent.db"
    members, metadata = collect([window()], sources, missing)
    assert not missing.exists()
    assert all(
        info["reason"] == "missing_database"
        for info in metadata["windows"][0]["database_records"]["tables"].values()
    )
    assert set(members) == {
        f"windows/1/{name}" for name in ("runtime.log", "runtime.txt", "evidence.json")
    }


def test_failed_window_does_not_change_primary_or_stop_later_window(
    sources, tmp_path, monkeypatch
):
    sources[2].mkdir()
    primary = sources[2] / "runtime.log"
    primary.write_bytes(b"existing primary evidence")
    (sources[0] / "runtime.log").write_text(
        "2026-11-06 13:00:00 solver.py:1 INFO handled\n"
    )
    original = windows.collect_evidence

    def collect_or_fail(logs, screenshots, start, end, output, screenshot_times):
        assert screenshot_times == []
        if start.hour == 10:
            raise OSError("private user path must not enter evidence")
        return original(logs, screenshots, start, end, output, screenshot_times)

    monkeypatch.setattr(windows, "collect_evidence", collect_or_fail)
    members, metadata = collect(
        [window(), window("2026-11-06 13:00:00", "2026-11-06 13:01:00")],
        sources,
        tmp_path / "absent.db",
    )
    assert primary.read_bytes() == b"existing primary evidence"
    assert metadata["windows"][0]["logs"] == {
        "status": "unavailable",
        "reason": "collection_failed",
        "error_type": "OSError",
    }
    assert "windows/1/runtime.log" not in members
    assert "windows/2/runtime.log" in members
    assert all("private user path" not in path.read_text() for path in members.values())


def test_extraction_failure_keeps_preview_without_publishing_partial_log(
    sources, tmp_path, monkeypatch
):
    (sources[0] / "runtime.log").write_text(
        "2026-11-06 10:00:00 solver.py:1 INFO " + "x" * 1000 + "\n"
    )
    monkeypatch.setattr(windows, "MAX_LOG_UNCOMPRESSED_BYTES", 128)
    members, metadata = collect([window()], sources, tmp_path / "absent.db")
    assert "windows/1/runtime.log" not in members
    assert not (sources[2] / "windows/1/runtime.log").exists()
    assert "windows/1/runtime.txt" in members
    assert metadata["windows"][0]["logs"]["status"] == "partial"
    assert metadata["windows"][0]["logs"]["reason"] == "collection_failed"
    assert (
        json.loads(members["windows/1/evidence.json"].read_text())["log_archive"][
            "file"
        ]
        is None
    )
