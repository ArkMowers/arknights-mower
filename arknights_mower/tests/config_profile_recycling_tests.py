"""Saved configurations retain recycling receipts and wait for active reports."""

import json
from threading import Event, RLock, Thread
from types import SimpleNamespace

import pytest

from arknights_mower.tests.config_profiles_tests import storage as storage
from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils import config_profiles as profiles


@pytest.fixture
def recycling_storage(storage, monkeypatch):
    from arknights_mower.solvers import record
    from arknights_mower.utils import recycling_report as report

    monkeypatch.setattr(record, "get_path", storage)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(report, "get_path", storage)
    monkeypatch.setattr(report, "_running", False)
    monkeypatch.setattr(report, "_dirty", False)
    with record._conn() as connection:
        for identifier, status, offset in (
            ("submitted", "submitted", 2),
            ("failed", "failed", 1),
            ("pending", "pending", 1),
        ):
            connection.execute(
                "INSERT INTO recycling_collection VALUES (?, ?, ?, ?)",
                (identifier, 1759400000, "null", json.dumps({"装置": 2})),
            )
            connection.execute(
                "INSERT INTO recycling_report_progress "
                "(event_id,status,next_unit,base_ms,end_ms) VALUES (?, ?, ?, ?, ?)",
                (identifier, status, offset, 1759400000000, 1759400000001),
            )
        connection.commit()
    directory = storage("@app/config/recycling_report")
    directory.mkdir(parents=True)
    (directory / "state.json").write_text(
        json.dumps({"uid": "saved-report-identity"}), encoding="utf-8"
    )
    return storage, record, report


@pytest.mark.parametrize("selected", [["recycling_history"], ["other_history"]])
def test_selected_recycling_history_keeps_receipts_and_only_sends_unfinished_units(
    recycling_storage, selected
):
    storage, record, report = recycling_storage
    profiles.create_profile("selected history", selected, expected_generation="0")
    with record._conn() as connection:
        receipts = connection.execute(
            "SELECT event_id,status,next_unit FROM recycling_report_progress "
            "ORDER BY event_id"
        ).fetchall()
    state = storage("@app/config/recycling_report/state.json")
    batch, progress = report._next_batch()
    if selected == ["recycling_history"]:
        assert receipts == [
            ("failed", "failed", 1),
            ("pending", "pending", 1),
            ("submitted", "submitted", 2),
        ]
        assert json.loads(state.read_text(encoding="utf-8")) == {
            "uid": "saved-report-identity"
        }
        assert batch["drops"] == [{"itemId": "30062", "dropTime": 1759400000001}]
        assert progress == [(2, "submitted", "pending")]
    else:
        assert receipts == []
        assert not state.exists()
        assert batch["drops"] == []
        assert progress == []


def test_active_recycling_report_blocks_profile_and_backup_import_until_commit(
    recycling_storage, monkeypatch
):
    import arknights_mower.__main__ as main
    import server

    storage, record, report = recycling_storage
    monkeypatch.setattr(server.app, "token", "recycling-profile-token", raising=False)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(server, "chat_active_requests", 0)
    monkeypatch.setattr(server, "active_job", lambda: None)
    monkeypatch.setattr(server, "_job_running", lambda job: False)
    monkeypatch.setattr(server.resource_update, "running", lambda: False)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setattr(server, "maa_check_job", {"status": "idle"})
    monkeypatch.setattr(
        main,
        "device_control",
        SimpleNamespace(active=False, configuration_lock=RLock()),
    )
    initial = profiles.list_profiles()
    before_conf = config.conf_path.read_bytes()
    entered, release = Event(), Event()
    workers = []

    def submit(directory, batch):
        entered.set()
        assert release.wait(5)

    def worker(**kwargs):
        thread = Thread(**kwargs)
        workers.append(thread)
        return thread

    monkeypatch.setattr(report, "_submit", submit)
    monkeypatch.setattr(report, "Thread", worker)
    headers = {
        "token": "recycling-profile-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": initial["generation"],
    }
    client = server.app.test_client()
    assert report.start_recycling_reports()
    try:
        assert entered.wait(5)
        assert server.configuration_profiles_busy() is True
        response = client.post(
            "/config-profiles", headers=headers, json={"name": "next", "inherit": []}
        )
        assert response.status_code == 409
        imported = client.post(
            "/config-backup/import", headers=headers, data=b"not parsed while reporting"
        )
        assert imported.status_code == 409
        exported = client.get("/config-profiles/export", headers=headers)
        assert exported.status_code == 200
        assert "recycling_report/submission.lock" not in backup.read_archive(
            exported.data
        )
        assert profiles.current_generation() == initial["generation"]
        assert config.conf_path.read_bytes() == before_conf
    finally:
        release.set()
        for thread in workers:
            thread.join(5)
            assert not thread.is_alive()
    with record._conn() as connection:
        assert connection.execute(
            "SELECT status,next_unit FROM recycling_report_progress WHERE event_id='pending'"
        ).fetchone() == ("submitted", 2)
    assert server.configuration_profiles_busy() is False
    response = client.post(
        "/config-profiles", headers=headers, json={"name": "next", "inherit": []}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("incoming_lock", [False, True])
@pytest.mark.parametrize("operation", ["backup", "profile"])
def test_recycling_submission_lock_stays_local_during_export_and_import(
    recycling_storage, incoming_lock, operation
):
    storage, _, report = recycling_storage
    profiles.list_profiles()
    files, tmp = backup.read_archive(
        profiles.export_current_archive(), include_tmp=True
    )
    name = "recycling_report/submission.lock"
    if incoming_lock:
        files[name] = b"obsolete lock from an older backup"
    raw = backup._archive_bytes(files, tmp)
    path = storage("@app/config/" + name)
    with report.submission_lock(path.parent):
        original_inode = path.stat().st_ino
        assert name not in backup.read_archive(backup.export_archive())
        assert name not in backup.read_archive(profiles.export_current_archive())
        if operation == "backup":
            backup.import_configuration(raw)
        else:
            profiles.import_profile(raw, "imported lock", [], expected_generation="0")
        assert path.stat().st_ino == original_inode
    with report.submission_lock(path.parent):
        assert path.stat().st_ino == original_inode


def test_archive_rejects_contents_beneath_the_local_recycling_lock(recycling_storage):
    files, tmp = backup.read_archive(
        profiles.export_current_archive(), include_tmp=True
    )
    files["recycling_report/submission.lock/nested"] = b"invalid directory"
    with pytest.raises(ValueError, match="无效路径"):
        backup.read_archive(backup._archive_bytes(files, tmp))
