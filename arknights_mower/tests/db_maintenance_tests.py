"""Offline database maintenance and configurable backup-size checks."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from io import BytesIO
from threading import RLock
from unittest.mock import Mock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from flask import Flask

from arknights_mower.solvers import record
from arknights_mower.tests.config_backup_tests import archive
from arknights_mower.tests.config_backup_tests import storage as storage
from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils import config_profiles as profiles
from arknights_mower.utils.config import gui
from arknights_mower.views.config_backup import config_backup_bp
from arknights_mower.views.config_profiles import config_profiles_bp
from arknights_mower.views.db_admin import db_admin_bp

HEADERS = {"token": "test-token", "X-Mower-Settings": "1"}


@pytest.fixture
def client(storage, monkeypatch):
    monkeypatch.setattr(gui, "gui_path", config.gui_path)

    @contextmanager
    def connect():
        with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
            yield conn

    monkeypatch.setattr(record, "_conn", connect)
    app = Flask(__name__)
    app.token = "test-token"
    app.config["CONFIG_BACKUP_BUSY"] = lambda: False
    app.register_blueprint(db_admin_bp)
    app.register_blueprint(config_backup_bp)
    app.register_blueprint(config_profiles_bp)
    return app.test_client()


@pytest.mark.parametrize("wal", [False, True])
def test_compaction_restores_export_without_deleting_retained_data(
    client, storage, wal
):
    database = storage("@app/tmp/data.db")
    with closing(sqlite3.connect(database)) as conn, conn:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE discarded(value BLOB)")
        conn.execute("INSERT INTO discarded VALUES (zeroblob(18000000))")
        conn.commit()
        conn.execute("DELETE FROM discarded")
    before = client.get("/db-admin/maintenance", headers=HEADERS).json
    assert before["database_bytes"] > 16 * 1024 * 1024
    assert before["reclaimable_bytes"] > 16 * 1024 * 1024
    rejected = client.get("/config-backup/export", headers=HEADERS)
    assert rejected.status_code == 409
    assert "16 MiB" in rejected.json["message"]
    compacted = client.post(
        "/db-admin/compact",
        headers={
            **HEADERS,
            "Host": "127.0.0.1:58000",
            "Origin": "https://mower.example:8443",
        },
    )
    assert compacted.status_code == 200
    assert compacted.json["before_bytes"] == before["database_bytes"]
    assert compacted.json["after_bytes"] < 100000
    assert compacted.json["reclaimable_bytes"] == 0
    with closing(sqlite3.connect(database)) as conn:
        assert conn.execute("SELECT value FROM reports").fetchall() == [("keep",)]
        assert conn.execute("SELECT state FROM saved_state").fetchall() == [("stale",)]
        assert conn.execute("SELECT COUNT(*) FROM discarded").fetchone() == (0,)
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert database.stat().st_size < 100000
    exported = client.get("/config-backup/export", headers=HEADERS)
    assert exported.status_code == 200
    assert "data.db" in backup.read_archive(exported.data, include_tmp=True)[1]


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/db-admin/stats"),
        ("POST", "/db-admin/delete"),
        ("GET", "/db-admin/maintenance"),
        ("POST", "/db-admin/compact"),
        ("PUT", "/db-admin/backup-limit"),
    ],
)
@pytest.mark.parametrize("token", [None, "incorrect"])
def test_authentication_precedes_database_and_settings_access(
    client, monkeypatch, method, path, token
):
    access = Mock(side_effect=AssertionError("unauthorized storage access"))
    monkeypatch.setattr(record, "_conn", access)
    monkeypatch.setattr(backup, "get_backup_limit_bytes", access)
    monkeypatch.setattr(gui, "update_gui_data", access)
    headers = {"X-Mower-Settings": "1"}
    if token:
        headers["token"] = token
    assert (
        client.open(
            path, method=method, headers=headers, data="invalid JSON"
        ).status_code
        == 403
    )
    access.assert_not_called()


@pytest.mark.parametrize(
    "path,method", [("/db-admin/compact", "POST"), ("/db-admin/backup-limit", "PUT")]
)
def test_busy_maintenance_and_invalid_credentials_preserve_storage(
    client, monkeypatch, path, method
):
    compact = Mock(side_effect=AssertionError("busy compaction"))
    save = Mock(side_effect=AssertionError("busy settings save"))
    monkeypatch.setattr("arknights_mower.views.db_admin._compact_database", compact)
    monkeypatch.setattr(gui, "update_gui_data", save)
    client.application.config["CONFIG_PROFILES_BUSY"] = lambda: True
    assert (
        client.open(
            path, method=method, headers=HEADERS, json={"backup_limit_mib": 32}
        ).status_code
        == 409
    )
    assert (
        client.open(path, method=method, headers={"token": "test-token"}).status_code
        == 403
    )
    assert (
        client.open(
            path,
            method=method,
            headers={
                **HEADERS,
                "Host": "127.0.0.1:58000",
                "Origin": "https://mower.example:8443",
            },
        ).status_code
        == 409
    )
    assert (
        client.open(
            path,
            method=method,
            headers={
                **HEADERS,
                "token": "wrong",
                "Origin": "https://mower.example:8443",
            },
        ).status_code
        == 403
    )
    compact.assert_not_called()
    save.assert_not_called()


@pytest.mark.parametrize("value", [None, True, "32", 0, -1, 1.5, 1025])
def test_invalid_limit_preserves_settings(client, value):
    config.gui_path.write_text("window_ratio: 0.8\n", encoding="utf-8")
    previous = config.gui_path.read_bytes()
    response = client.put(
        "/db-admin/backup-limit", headers=HEADERS, json={"backup_limit_mib": value}
    )
    assert response.status_code == 400
    assert config.gui_path.read_bytes() == previous


def test_configured_limit_applies_to_export_full_import_and_profile_import(
    client, storage
):
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute("CREATE TABLE retained(value BLOB)")
        conn.execute("INSERT INTO retained VALUES (zeroblob(18000000))")
    assert client.get("/config-backup/export", headers=HEADERS).status_code == 409
    config.gui_path.write_text("window_ratio: 0.8\n", encoding="utf-8")
    response = client.put(
        "/db-admin/backup-limit",
        headers={
            **HEADERS,
            "Host": "127.0.0.1:58000",
            "Origin": "https://mower.example:8443",
        },
        json={"backup_limit_mib": 32},
    )
    assert response.status_code == 200
    assert response.json["backup_limit_mib"] == 32
    assert gui.read_gui_data()["window_ratio"] == 0.8
    exported = client.get("/config-backup/export", headers=HEADERS)
    assert exported.status_code == 200
    incoming = exported.data
    imported = client.post("/config-backup/import", headers=HEADERS, data=incoming)
    assert imported.status_code == 200
    assert backup.get_backup_limit_bytes() == 32 * 1024 * 1024
    generation = profiles.current_generation()
    imported_profile = client.post(
        "/config-profiles/import",
        headers={**HEADERS, "X-Mower-Config-Generation": generation},
        data={
            "backup": (BytesIO(incoming), "backup.zip"),
            "name": "large database",
            "keep": "[]",
        },
    )
    assert imported_profile.status_code == 200
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT length(value) FROM retained").fetchone() == (
            18000000,
        )
    # Imported GUI settings never replace this instance's maintenance choice.
    backup.import_configuration(
        archive(
            {
                "conf.yml": "{}",
                "plan.json": '{"plan1": {}}',
                "gui.yml": "backup_limit_mib: 1\n",
            }
        )
    )
    assert backup.get_backup_limit_bytes() == 32 * 1024 * 1024


def test_reduced_limit_rejects_expanded_archive_and_keeps_profile_registry_readable(
    client, storage
):
    assert (
        client.put(
            "/db-admin/backup-limit", headers=HEADERS, json={"backup_limit_mib": 1}
        ).status_code
        == 200
    )
    expanded = archive(
        {"conf.yml": "{}", "plan.json": '{"plan1": {}}'},
        {"report.csv": "x" * (1024 * 1024)},
    )
    compressed = BytesIO()
    with (
        ZipFile(BytesIO(expanded)) as source,
        ZipFile(compressed, "w", compression=ZIP_DEFLATED) as target,
    ):
        for entry in source.infolist():
            target.writestr(entry.filename, source.read(entry))
    expanded = compressed.getvalue()
    assert len(expanded) < 1024 * 1024
    assert (
        client.post("/config-backup/import", headers=HEADERS, data=expanded).status_code
        == 400
    )
    assert not storage("@app/config-backups").exists()
    original = profiles.list_profiles()
    identifier = original["active_id"]
    # The registry lists retained archives even when they exceed a reduced limit.
    profiles._profile_path(identifier).write_bytes(
        archive(
            {"conf.yml": "{}", "plan.json": '{"plan1": {}}'},
            {"report.csv": os.urandom(1024 * 1024 + 1)},
        )
    )
    assert client.get("/config-profiles", headers=HEADERS).status_code == 200


def test_sqlite_failure_releases_maintenance_lock(client, monkeypatch):
    maintenance_lock = RLock()

    @contextmanager
    def locks():
        with maintenance_lock:
            yield

    client.application.config["CONFIG_PROFILES_LOCKS"] = locks
    monkeypatch.setattr(
        "arknights_mower.views.db_admin._compact_database",
        Mock(side_effect=sqlite3.OperationalError("database is locked")),
    )
    assert client.post("/db-admin/compact", headers=HEADERS).status_code == 503
    assert (
        client.put(
            "/db-admin/backup-limit", headers=HEADERS, json={"backup_limit_mib": 64}
        ).status_code
        == 200
    )

    def acquire_after_error():
        for lock in (backup.backup_lock, maintenance_lock):
            assert lock.acquire(timeout=1)
            lock.release()

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(acquire_after_error).result(timeout=5)


@pytest.mark.parametrize("path", ["/config-backup/import", "/config-profiles/import"])
def test_configured_limit_accepts_large_zip_and_rejects_larger_request(
    client, monkeypatch, path
):
    assert (
        client.put(
            "/db-admin/backup-limit", headers=HEADERS, json={"backup_limit_mib": 32}
        ).status_code
        == 200
    )
    raw = archive(
        {"conf.yml": "{}", "plan.json": '{"plan1": {}}'},
        {"report.csv": os.urandom(17 * 1024 * 1024)},
    )
    if path == "/config-backup/import":
        response = client.post(path, headers=HEADERS, data=raw)
    else:
        profiles.list_profiles()
        response = client.post(
            path,
            headers={**HEADERS, "X-Mower-Config-Generation": "0"},
            data={"backup": (BytesIO(raw), "large.zip"), "name": "large ZIP"},
        )
    assert response.status_code == 200
    # A reduced setting also governs HTTP request bounds before archive parsing.
    assert (
        client.put(
            "/db-admin/backup-limit", headers=HEADERS, json={"backup_limit_mib": 1}
        ).status_code
        == 200
    )
    response = client.post(path, headers=HEADERS, data=b"x" * (1024 * 1024 + 1))
    assert response.status_code == 413


def test_integrity_failure_does_not_execute_vacuum(client, monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = ("damaged page",)

    @contextmanager
    def connect():
        yield connection

    # Status observation is independently successful; the compaction check fails.
    from arknights_mower.views import db_admin

    monkeypatch.setattr(db_admin, "_maintenance_status", lambda: {"busy": False})
    monkeypatch.setattr(record, "_conn", connect)
    response = client.post("/db-admin/compact", headers=HEADERS)
    assert response.status_code == 503
    assert "完整性检查未通过" in response.json["message"]
    assert not any(
        call.args[0] == "VACUUM" for call in connection.execute.call_args_list
    )
    assert connection.set_progress_handler.call_args.args == (None, 0)


def test_sqlite_progress_deadline_preserves_data_and_releases_connection(
    client, storage, monkeypatch
):
    from arknights_mower.views import db_admin

    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute("CREATE TABLE large(value INTEGER)")
        conn.executemany(
            "INSERT INTO large VALUES (?)", ((value,) for value in range(10000))
        )
    times = iter([0])
    monkeypatch.setattr(db_admin, "monotonic", lambda: next(times, 61))
    failed = client.post("/db-admin/compact", headers=HEADERS)
    assert failed.status_code == 503
    assert "interrupted" in failed.json["message"]
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT value FROM reports").fetchall() == [("keep",)]
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert client.get("/db-admin/maintenance", headers=HEADERS).status_code == 200
