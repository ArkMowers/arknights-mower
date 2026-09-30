import json
import sqlite3
from contextlib import closing
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from flask import Flask

from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.views.config_backup import config_backup_bp


@pytest.fixture
def storage(tmp_path, monkeypatch):
    def get_path(name, space=None):
        return tmp_path / "instance" / name.removeprefix("@app/")

    monkeypatch.setattr(backup, "get_path", get_path)
    for attr, name in (
        ("conf_path", "conf.yml"),
        ("plan_path", "plan.json"),
        ("weekly_plans_path", "weekly_plans.yml"),
        ("app_state_path", "state.json"),
        ("gui_path", "gui.yml"),
    ):
        monkeypatch.setattr(config, attr, get_path(f"@app/config/{name}"))
    monkeypatch.setattr(
        config,
        "conf",
        config.Conf(account="before"),
    )
    monkeypatch.setattr(config, "plan", config.PlanModel())
    config.save_conf()
    config.save_plan()
    database = get_path("@app/tmp/data.db")
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("CREATE TABLE saved_state(state TEXT)")
        conn.execute("INSERT INTO saved_state VALUES ('stale')")
        conn.execute("CREATE TABLE reports(value TEXT)")
        conn.execute("INSERT INTO reports VALUES ('keep')")
    return get_path


def archive(files, tmp_files=None):
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        for name, value in files.items():
            zipped.writestr(f"config/{name}", value)
        if tmp_files is not None:
            zipped.writestr("tmp/", b"")
            for name, value in tmp_files.items():
                zipped.writestr(f"tmp/{name}", value)
    return stream.getvalue()


def incoming(**files):
    return archive({**backup.read_archive(backup.export_archive()), **files})


@pytest.fixture
def populated_plan():
    return config.PlanModel(
        plan1={
            "central": {
                "plans": [{"agent": "阿米娅", "group": "中枢", "replacement": ["杜宾"]}]
            },
            "room_1_1": {
                "name": "贸易站",
                "product": "orundum",
                "plans": [{"agent": "能天使"}],
            },
            "dormitory_1": {"plans": [{"agent": "Free"}]},
        },
        conf={"ling_xi": 2, "rest_in_full": "阿米娅", "exhaust_require": "能天使"},
        backup_plans=[
            {
                "name": "备用排班",
                "plan": {
                    "central": {"plans": [{"agent": "杜宾", "replacement": ["阿米娅"]}]}
                },
                "task": {"central": ["杜宾"]},
                "trigger": {"left": "True", "operator": "==", "right": "True"},
                "conf": {"rest_in_full": "杜宾"},
            },
            {
                "name": "休息副表",
                "plan": {"dormitory_2": {"plans": [{"agent": "阿米娅"}]}},
                "trigger_timing": "BEFORE_PLANNING",
                "conf": {},
                "task": {},
                "trigger": {},
            },
        ],
    )


def test_export_preserves_original_bytes_and_includes_persistent_tmp_data(storage):
    config.conf_path.write_text(
        "# original comment\naccount: 原始账号\n", encoding="utf-8"
    )
    root = config.conf_path.parent
    (root / "nested").mkdir()
    (root / "nested/custom.yml").write_bytes(b"# custom\nx: 1\n")
    config.app_state_path.write_text('{"last_seen_app_version":"local"}')
    storage("@app/outside.txt").write_text("not included")
    files = backup.read_archive(backup.export_archive())
    assert files == {
        "conf.yml": config.conf_path.read_bytes(),
        "plan.json": config.plan_path.read_bytes(),
        "nested/custom.yml": b"# custom\nx: 1\n",
    }
    _, tables = backup.read_archive(backup.export_archive(), include_tmp=True)
    assert set(tables) == {"data.db"}


def test_tmp_data_and_all_database_tables_round_trip(storage):
    for name in backup.TMP_DATA_FILES - {"data.db"}:
        storage(f"@app/tmp/{name}").write_bytes(f"original {name}\r\n".encode())
    database = storage("@app/tmp/data.db")
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("CREATE TABLE mastery_plan(char_name TEXT)")
        conn.execute("INSERT INTO mastery_plan VALUES ('阿米娅')")
        conn.execute("CREATE TABLE custom_table(value TEXT)")
        conn.execute("INSERT INTO custom_table VALUES ('custom')")
    raw = backup.export_archive()
    config_files, original_tables = backup.read_archive(raw, include_tmp=True)
    assert set(original_tables) == backup.TMP_DATA_FILES
    for name in backup.TMP_DATA_FILES - {"data.db"}:
        storage(f"@app/tmp/{name}").write_bytes(b"changed")
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("DELETE FROM mastery_plan")
        conn.execute("UPDATE custom_table SET value='changed'")
        conn.execute("CREATE TABLE local_only(value TEXT)")
    recovery = backup.import_configuration(raw)
    assert backup.read_archive(raw) == config_files
    for name in backup.TMP_DATA_FILES - {"data.db"}:
        assert storage(f"@app/tmp/{name}").read_bytes() == original_tables[name]
    with closing(sqlite3.connect(database)) as conn:
        assert conn.execute("SELECT char_name FROM mastery_plan").fetchall() == [
            ("阿米娅",)
        ]
        assert conn.execute("SELECT value FROM custom_table").fetchall() == [
            ("custom",)
        ]
        assert conn.execute("SELECT value FROM reports").fetchall() == [("keep",)]
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone() == (0,)
        assert not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='local_only'"
        ).fetchone()
    _, recovery_tables = backup.read_archive(
        Path(recovery).read_bytes(), include_tmp=True
    )
    assert recovery_tables["report.csv"] == b"changed"
    backup.import_configuration(Path(recovery).read_bytes())
    assert storage("@app/tmp/report.csv").read_bytes() == b"changed"
    with closing(sqlite3.connect(database)) as conn:
        assert conn.execute("SELECT value FROM custom_table").fetchall() == [
            ("changed",)
        ]


def test_database_snapshot_includes_committed_wal_data(storage, tmp_path):
    database = storage("@app/tmp/data.db")
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("UPDATE reports SET value='wal value'")
        conn.commit()
        assert Path(f"{database}-wal").stat().st_size > 0
        raw = backup.export_archive()
        _, tables = backup.read_archive(raw, include_tmp=True)
        snapshot = tmp_path / "exported.db"
        snapshot.write_bytes(tables["data.db"])
        with closing(sqlite3.connect(snapshot)) as reader:
            assert reader.execute("SELECT value FROM reports").fetchall() == [
                ("wal value",)
            ]
        conn.execute("UPDATE reports SET value='changed'")
        conn.commit()
        backup.import_configuration(raw)
        assert conn.execute("SELECT value FROM reports").fetchall() == [("wal value",)]


def test_legacy_and_partial_tmp_archives_preserve_missing_local_data(storage):
    local = storage("@app/tmp/cultivate.json")
    local.write_bytes(b'{"items":{}}')
    files = backup.read_archive(backup.export_archive())
    backup.import_configuration(archive(files))
    assert local.read_bytes() == b'{"items":{}}'
    backup.import_configuration(archive(files, {"report.csv": b"new report"}))
    assert local.read_bytes() == b'{"items":{}}'
    assert storage("@app/tmp/report.csv").read_bytes() == b"new report"
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT value FROM reports").fetchall() == [("keep",)]
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone() == (0,)


def test_restores_database_and_data_to_an_instance_without_tmp(storage):
    storage("@app/tmp/report.csv").write_bytes(b"report")
    raw = backup.export_archive()
    storage("@app/tmp/report.csv").unlink()
    storage("@app/tmp/data.db").unlink()
    storage("@app/tmp").rmdir()
    backup.import_configuration(raw)
    assert storage("@app/tmp/report.csv").read_bytes() == b"report"
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT value FROM reports").fetchall() == [("keep",)]


def test_export_excludes_resource_metadata_updates_and_unrelated_tmp_files(storage):
    for name in ("resource_version.json", "mower.zip", "build.log", "other.csv"):
        storage(f"@app/tmp/{name}").write_bytes(b"excluded")
    storage("@app/tmp/resource").mkdir()
    storage("@app/tmp/resource/data.json").write_bytes(b"excluded")
    _, tables = backup.read_archive(backup.export_archive(), include_tmp=True)
    assert set(tables) == {"data.db"}


@pytest.mark.parametrize(
    "content", [b"not sqlite", b"SQLite format 3\x00" + b"x" * 100]
)
def test_invalid_database_is_rejected_before_any_write(storage, content):
    before = backup.export_archive()
    files = backup.read_archive(before)
    raw = archive(files, {"data.db": content, "report.csv": b"new"})
    with pytest.raises(ValueError):
        backup.import_configuration(raw)
    assert backup.read_archive(
        backup.export_archive(), include_tmp=True
    ) == backup.read_archive(before, include_tmp=True)
    assert not storage("@app/config-backups").exists()


@pytest.mark.parametrize("failure", ["tmp", "database"])
def test_tmp_or_database_failure_rolls_back_configuration_and_data(
    storage, monkeypatch, failure
):
    report = storage("@app/tmp/report.csv")
    report.write_bytes(b"original")
    files, tables = backup.read_archive(backup.export_archive(), include_tmp=True)
    files["conf.yml"] = b"account: imported\n"
    raw = archive(files, {**tables, "cultivate.json": b"new", "report.csv": b"changed"})
    before = backup.export_archive()
    previous_conf, previous_plan = config.conf, config.plan
    write = backup._write_bytes
    copy_database = backup._copy_database

    def fail_write(path, content):
        if path == report and content == b"changed":
            raise OSError("tmp write failed")
        write(path, content)

    def fail_database(source, destination):
        if destination == storage("@app/tmp/data.db"):
            raise sqlite3.OperationalError("database restore failed")
        copy_database(source, destination)

    if failure == "tmp":
        monkeypatch.setattr(backup, "_write_bytes", fail_write)
    else:
        monkeypatch.setattr(backup, "_copy_database", fail_database)
    with pytest.raises((OSError, sqlite3.Error)):
        backup.import_configuration(raw)
    assert config.conf is previous_conf and config.plan is previous_plan
    assert backup.read_archive(
        backup.export_archive(), include_tmp=True
    ) == backup.read_archive(before, include_tmp=True)
    assert not storage("@app/tmp/cultivate.json").exists()
    assert len(list(storage("@app/config-backups").glob("*.zip"))) == 1


@pytest.mark.parametrize(
    "name", ["resource_version.json", "nested/report.csv", "DATA.DB", "data.db-wal"]
)
def test_rejects_non_data_tmp_members(storage, name):
    raw = archive(backup.read_archive(backup.export_archive()), {name: b"invalid"})
    with pytest.raises(ValueError):
        backup.import_configuration(raw)
    assert not storage("@app/config-backups").exists()


@pytest.mark.parametrize("name", ["report.csv", "data.db", "REPORT.CSV"])
def test_local_tmp_links_or_case_collisions_prevent_export_and_import(storage, name):
    raw = backup.export_archive()
    path = storage(f"@app/tmp/{name}")
    path.unlink(missing_ok=True)
    path.symlink_to(config.conf_path)
    for action in (backup.export_archive, lambda: backup.import_configuration(raw)):
        with pytest.raises(backup.LocalConfigError):
            action()
    assert not storage("@app/config-backups").exists()


def test_combined_config_and_tmp_size_is_bounded(storage, monkeypatch):
    database_size = storage("@app/tmp/data.db").stat().st_size
    files = backup.read_archive(backup.export_archive())
    config_size = sum(map(len, files.values()))
    storage("@app/tmp/report.csv").write_bytes(b"x" * 128)
    monkeypatch.setattr(backup, "MAX_BACKUP_BYTES", database_size + config_size + 64)
    with pytest.raises(backup.LocalConfigError):
        backup.export_archive()


@pytest.mark.parametrize("database_exists", [False, True])
def test_database_backup_timeout_rolls_back_partially_copied_pages(
    storage, monkeypatch, database_exists
):
    database = storage("@app/tmp/data.db")
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("CREATE TABLE large_table(value BLOB)")
        conn.execute("INSERT INTO large_table VALUES (zeroblob(1200000))")
    raw = backup.export_archive()
    files, tables = backup.read_archive(raw, include_tmp=True)
    files["conf.yml"] = b"account: imported\n"
    raw = archive(files, {**tables, "report.csv": b"new"})
    if database_exists:
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute("UPDATE reports SET value='local'")
    else:
        database.unlink()
    copy_database = backup._copy_database

    def timeout(source, destination):
        if destination == database:
            with monkeypatch.context() as patch:
                clock = iter((0, 11))
                patch.setattr(backup, "monotonic", lambda: next(clock))
                copy_database(source, destination)
        else:
            copy_database(source, destination)

    monkeypatch.setattr(backup, "_copy_database", timeout)
    previous = config.conf_path.read_bytes()
    with pytest.raises(sqlite3.OperationalError, match="超时"):
        backup.import_configuration(raw)
    assert config.conf_path.read_bytes() == previous
    assert not storage("@app/tmp/report.csv").exists()
    if database_exists:
        with closing(sqlite3.connect(database)) as conn:
            assert conn.execute("SELECT value FROM reports").fetchall() == [("local",)]
            assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone() == (1,)
            assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
    else:
        assert not database.exists()


def test_completed_database_copy_does_not_report_a_post_commit_timeout(
    storage, tmp_path, monkeypatch
):
    destination = tmp_path / "copy.db"
    clock = iter((0, 11))
    monkeypatch.setattr(backup, "monotonic", lambda: next(clock))
    backup._copy_database(storage("@app/tmp/data.db"), destination)
    with closing(sqlite3.connect(destination)) as conn:
        assert conn.execute("SELECT value FROM reports").fetchall() == [("keep",)]


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_rejects_local_database_auxiliary_links(storage, suffix):
    raw = backup.export_archive()
    storage(f"@app/tmp/data.db{suffix}").symlink_to(config.conf_path)
    with pytest.raises(backup.LocalConfigError):
        backup.import_configuration(raw)
    assert not storage("@app/config-backups").exists()


def test_populated_plan_and_original_files_survive_restore_and_repeated_reload(
    storage, populated_plan
):
    original_plan = populated_plan.model_dump(exclude_none=True)
    migrated_plan = json.loads(json.dumps(original_plan))
    migrated_plan["conf"]["dorm_order"] = (
        "dormitory_2,dormitory_1,dormitory_3,dormitory_4"
    )
    for backup_plan in migrated_plan["backup_plans"]:
        backup_plan["conf"]["dorm_order"] = ""
    raw = incoming(
        **{
            "conf.yml": (
                "# backup\naccount: restored\nexperimental_dorm_logic: true\n"
                "dorm_order: dormitory_2_4,dormitory_1_3\n"
            ),
            "plan.json": json.dumps(original_plan),
            "weekly_plans.yml": "plans: {日常: [{weekday: 周一, stage: ['1-7']}]}\n",
            "nested/custom.yml": b"# retained raw\nkey: value\n",
        }
    )
    (config.conf_path.parent / "obsolete.yml").write_text("remove")
    outside = storage("@app/outside.yml")
    outside.write_text("keep")
    before = config.conf_path.read_bytes()
    recovery = backup.import_configuration(raw)
    assert backup.read_archive(Path(recovery).read_bytes())["conf.yml"] == before
    for _ in range(3):
        config.load_conf()
        config.load_plan()
        assert config.conf.account == "restored"
        assert config.plan.conf.dorm_order == (
            "dormitory_2,dormitory_1,dormitory_3,dormitory_4"
        )
        assert config.plan.model_dump(exclude_none=True) == migrated_plan
    assert json.loads(config.plan_path.read_text(encoding="utf-8")) == migrated_plan
    assert "dorm_order:" not in config.conf_path.read_text(encoding="utf-8")
    assert "experimental_dorm_logic" not in config.conf_path.read_text(encoding="utf-8")
    assert (
        config.conf_path.parent / "nested/custom.yml"
    ).read_bytes() == b"# retained raw\nkey: value\n"
    assert not (config.conf_path.parent / "obsolete.yml").exists()
    assert outside.read_text() == "keep"
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone()[0] == 0
        assert conn.execute("SELECT value FROM reports").fetchone()[0] == "keep"


@pytest.mark.parametrize("local_exists", [False, True])
@pytest.mark.parametrize("in_archive", [False, True])
def test_preserves_access_gui_and_state(storage, local_exists, in_archive):
    config.conf.webview.port = 18080
    config.conf.webview.token = "local-token"
    config.conf.webview.tray = False
    config.save_conf()
    for name in backup.IMPORT_PRESERVED_FILES:
        if local_exists:
            (config.conf_path.parent / name).write_bytes(b"local bytes")
    files = {
        "conf.yml": "account: restored\nwebview: {port: invalid, token: other, tray: invalid}\n"
    }
    if in_archive:
        files.update(
            {name: b"ignored invalid bytes" for name in backup.IMPORT_PRESERVED_FILES}
        )
    backup.import_configuration(incoming(**files))
    config.load_conf()
    assert config.conf.webview.port == 18080
    assert config.conf.webview.token == "local-token"
    assert config.conf.webview.tray is False
    for name in backup.IMPORT_PRESERVED_FILES:
        path = config.conf_path.parent / name
        assert path.exists() == local_exists
        if local_exists:
            assert path.read_bytes() == b"local bytes"


@pytest.mark.parametrize(
    "value",
    [
        b"not zip",
        b'{"data":{"plan":{}}}',
        archive({}),
        archive({"conf.yml": "{}"}),
        archive({"conf.yml": "[]", "plan.json": "{}"}),
        archive({"conf.yml": "{}", "plan.json": "{}"}),
        archive({"conf.yml": b"\xff", "plan.json": "{}"}),
    ],
)
def test_invalid_backup_changes_nothing(storage, value):
    before = backup.export_archive()
    with pytest.raises((ValueError, TypeError)):
        backup.import_configuration(value)
    assert backup.read_archive(backup.export_archive()) == backup.read_archive(before)
    assert not storage("@app/config-backups").exists()


@pytest.mark.parametrize(
    "names",
    [
        ["../conf.yml"],
        ["other/conf.yml"],
        ["config/../conf.yml"],
        ["config/a", "config/a"],
        ["config/a", "config/a/b"],
        ["config/STATE.JSON", "config/state.json"],
        ["config/state.json/a", "config/STATE.JSON"],
        ["config/CON"],
        ["config/a."],
        ["config/a", "config/a/"],
        ["config/A/b", "config/a/c"],
    ],
)
def test_rejects_ambiguous_or_outside_archive_paths(names):
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        for name in names:
            zipped.writestr(name, b"x")
    with pytest.raises(ValueError):
        backup.read_archive(stream.getvalue())


def test_rejects_symlinks_and_size_limits(storage, monkeypatch):
    (config.conf_path.parent / "link").symlink_to(config.conf_path)
    with pytest.raises(ValueError):
        backup.export_archive()
    (config.conf_path.parent / "link").unlink()
    raw = backup.export_archive()
    monkeypatch.setattr(backup, "MAX_BACKUP_BYTES", 32)
    with pytest.raises(ValueError):
        backup.read_archive(raw)
    with pytest.raises(ValueError):
        backup.export_archive()


def test_write_failure_rolls_back_files_runtime_and_database(storage, monkeypatch):
    raw = incoming(**{"conf.yml": "account: new\n", "z-last.yml": "new"})
    before = backup.read_archive(backup.export_archive())
    previous_conf, previous_plan = config.conf, config.plan
    write = config.atomic_write

    def fail(path, writer):
        if path.name == "z-last.yml":
            raise OSError("disk failure")
        return write(path, writer)

    monkeypatch.setattr(config, "atomic_write", fail)
    with pytest.raises(OSError):
        backup.import_configuration(raw)
    assert config.conf is previous_conf and config.plan is previous_plan
    assert backup.read_archive(backup.export_archive()) == before
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone()[0] == 1


def test_import_without_database_does_not_create_one(storage):
    storage("@app/tmp/data.db").unlink()
    backup.import_configuration(backup.export_archive())
    assert not storage("@app/tmp/data.db").exists()


@pytest.fixture
def client(storage):
    app = Flask(__name__)
    app.register_blueprint(config_backup_bp)
    app.token = "old-token"
    app.config["CONFIG_BACKUP_BUSY"] = lambda: False
    return app.test_client()


def test_routes_validate_auth_busy_format_and_download(client):
    headers = {"token": "old-token", "X-Mower-Settings": "1"}
    assert client.get("/config-backup/export").status_code == 403
    response = client.get("/config-backup/export", headers=headers)
    assert response.mimetype == "application/zip"
    assert response.headers["Cache-Control"] == "no-store"
    raw = response.data
    assert (
        client.post(
            "/config-backup/import", data=raw, headers={"token": "old-token"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/config-backup/import",
            data=raw,
            headers={**headers, "Origin": "https://other.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/config-backup/import", json={"data": {}}, headers=headers
        ).status_code
        == 400
    )
    client.application.config["CONFIG_BACKUP_BUSY"] = lambda: True
    assert (
        client.post("/config-backup/import", data=raw, headers=headers).status_code
        == 409
    )
    client.application.config["CONFIG_BACKUP_BUSY"] = lambda: False
    imported = client.post(
        "/config-backup/import",
        data={"backup": (BytesIO(raw), "backup.zip")},
        headers=headers,
    )
    assert imported.status_code == 200
    assert Path(imported.json["recovery_path"]).is_file()
    assert client.application.token == "old-token"


def test_route_rejects_invalid_database_without_writing_configuration(client, storage):
    files = backup.read_archive(backup.export_archive())
    previous = config.conf_path.read_bytes()
    response = client.post(
        "/config-backup/import",
        data=archive(files, {"data.db": b"not a database"}),
        headers={"token": "old-token", "X-Mower-Settings": "1"},
    )
    assert response.status_code == 400
    assert response.json["ok"] is False
    assert config.conf_path.read_bytes() == previous
    assert not storage("@app/config-backups").exists()


def test_oversized_import_is_rejected(client, monkeypatch):
    monkeypatch.setattr("arknights_mower.views.config_backup.MAX_BACKUP_BYTES", 32)
    assert (
        client.post(
            "/config-backup/import",
            data=b"x" * 33,
            headers={"token": "old-token", "X-Mower-Settings": "1"},
        ).status_code
        == 413
    )


@pytest.fixture
def plan_client(storage, monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "test-token", raising=False)
    return server.app.test_client()


def post_plan_file(client, value, filename="plan.json", mimetype="application/json"):
    return client.post(
        "/import",
        headers={"token": "test-token"},
        data={
            "img": (
                BytesIO(
                    value if isinstance(value, bytes) else json.dumps(value).encode()
                ),
                filename,
                mimetype,
            )
        },
    )


@pytest.mark.parametrize("zip_backup", [False, True])
def test_plan_entry_imports_json_or_zip_without_other_settings(
    plan_client, populated_plan, zip_backup
):
    value = populated_plan.model_dump(exclude_none=True)
    before = config.conf_path.read_bytes()
    if zip_backup:
        value = incoming(
            **{"plan.json": json.dumps(value), "conf.yml": "account: other\n"}
        )
    result = post_plan_file(
        plan_client,
        value,
        "backup.zip" if zip_backup else "plan.json",
        "application/octet-stream",
    )
    assert result.get_data(as_text=True) == "排班已加载"
    config.load_plan()
    assert config.plan.model_dump(exclude_none=True) == populated_plan.model_dump(
        exclude_none=True
    )
    assert config.conf_path.read_bytes() == before


def test_plan_entry_reads_new_zip_without_restoring_tmp_data(
    plan_client, storage, populated_plan
):
    files, tables = backup.read_archive(backup.export_archive(), include_tmp=True)
    files["plan.json"] = populated_plan.model_dump_json()
    raw = archive(files, {**tables, "report.csv": b"archive report"})
    storage("@app/tmp/report.csv").write_bytes(b"local report")
    database = storage("@app/tmp/data.db")
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("UPDATE reports SET value='local'")
    response = post_plan_file(plan_client, raw, "backup.zip", "application/zip")
    assert response.get_data(as_text=True) == "排班已加载"
    assert config.plan == populated_plan
    assert storage("@app/tmp/report.csv").read_bytes() == b"local report"
    with closing(sqlite3.connect(database)) as conn:
        assert conn.execute("SELECT value FROM reports").fetchall() == [("local",)]
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone() == (1,)


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        {"conf": {}},
        {"data": {"plan": {}}},
        {"plan1": None},
        {"plan1": {}, "default": "plan2"},
    ],
)
def test_plan_entry_rejects_unrelated_json_without_clearing_plan(
    plan_client, populated_plan, value
):
    config.plan = populated_plan
    config.save_plan()
    previous = config.plan_path.read_bytes()
    result = post_plan_file(plan_client, value)
    assert "导入失败" in result.get_data(as_text=True)
    assert config.plan == populated_plan
    assert config.plan_path.read_bytes() == previous


def test_plan_entry_keeps_runtime_plan_on_write_failure(
    plan_client, populated_plan, monkeypatch
):
    previous = config.plan
    previous_bytes = config.plan_path.read_bytes()

    def fail_save():
        raise OSError("test write failure")

    monkeypatch.setattr(config, "save_plan", fail_save)
    result = post_plan_file(plan_client, populated_plan.model_dump(exclude_none=True))
    assert "文件写入失败" in result.get_data(as_text=True)
    assert config.plan is previous
    assert config.plan_path.read_bytes() == previous_bytes


def test_plan_advanced_settings_round_trip_without_drone_room(
    plan_client, populated_plan
):
    config.conf.drone_room = "room_1_1"
    config.conf.resting_threshold = 0.65
    config.save_conf()
    value = populated_plan.model_dump(exclude_none=True)
    value["advanced_settings"] = {
        "resting_threshold": 0.75,
        "drone_count_limit": 140,
        "product_switching": {"waiting_seconds": 5},
        "experimental_dorm_logic": True,
        "group_rest_in_full_on_mood_gap": False,
        "group_mood_gap_max_extra_wait_hours": 1.5,
    }
    result = post_plan_file(plan_client, value)
    assert result.get_data(as_text=True) == "排班已加载"
    assert config.conf.resting_threshold == 0.75
    assert config.conf.drone_count_limit == 140
    assert config.conf.product_switching.waiting_seconds == 5
    assert config.conf.group_rest_in_full_on_mood_gap is False
    assert config.conf.group_mood_gap_max_extra_wait_hours == 1.5
    assert config.conf.drone_room == "room_1_1"

    exported = plan_client.get("/export-json", headers={"token": "test-token"}).json
    assert exported["advanced_settings"]["resting_threshold"] == 0.75
    assert exported["advanced_settings"]["product_switching"]["waiting_seconds"] == 5
    assert exported["advanced_settings"]["group_rest_in_full_on_mood_gap"] is False
    assert exported["advanced_settings"]["group_mood_gap_max_extra_wait_hours"] == 1.5
    assert "drone_room" not in exported["advanced_settings"]
    assert "reload_room" not in exported["advanced_settings"]


def test_plan_import_ignores_legacy_reload_room(plan_client, populated_plan):
    value = populated_plan.model_dump(exclude_none=True)
    value["advanced_settings"] = {
        "reload_room": "room_1_1",
        "drone_count_limit": 140,
    }
    result = post_plan_file(plan_client, value)

    assert result.get_data(as_text=True) == "排班已加载"
    assert config.conf.drone_count_limit == 140
    assert "reload_room" not in config.conf.model_dump()


def test_plan_entry_rejects_invalid_advanced_settings(plan_client, populated_plan):
    value = populated_plan.model_dump(exclude_none=True)
    value["advanced_settings"] = {"product_switching": {"waiting_seconds": 70}}
    before_plan = config.plan_path.read_bytes()
    before_conf = config.conf_path.read_bytes()
    result = post_plan_file(plan_client, value)
    assert "高级设置无效" in result.get_data(as_text=True)
    assert config.plan_path.read_bytes() == before_plan
    assert config.conf_path.read_bytes() == before_conf


@pytest.mark.parametrize("endpoint", ["/config-backup/import", "/import"])
def test_damaged_compression_reports_import_error_without_writes(
    client, plan_client, monkeypatch, endpoint
):
    from zlib import error as ZlibError

    raw = backup.export_archive()
    previous = backup._local_snapshot()[0]

    def damaged(*args, **kwargs):
        raise ZlibError("damaged deflate stream")

    monkeypatch.setattr(ZipFile, "read", damaged)
    if endpoint == "/import":
        response = post_plan_file(plan_client, raw, "backup.zip", "application/zip")
        assert response.status_code == 200
        assert "排班表导入失败" in response.get_data(as_text=True)
    else:
        response = client.post(
            endpoint, data=raw, headers={"token": "old-token", "X-Mower-Settings": "1"}
        )
        assert response.status_code == 400
        assert "备份格式不正确" in response.json["message"]
    assert backup._local_snapshot()[0] == previous
    assert not config.conf_path.parent.parent.joinpath("config-backups").exists()


def test_incomplete_plan_image_reports_import_error_without_clearing_plan(
    plan_client, monkeypatch
):
    import sys
    from types import ModuleType
    from zlib import error as ZlibError

    from PIL import Image

    from arknights_mower import utils

    image = BytesIO()
    Image.new("RGB", (1, 1), "white").save(image, format="PNG")
    previous = config.plan_path.read_bytes()
    plan = config.plan

    def damaged(*args):
        raise ZlibError("incomplete compressed QR data")

    # This test covers the route's error handling, not native QR recognition.
    # Keep it runnable in Linux CI without the optional system libzbar library.
    qrcode = ModuleType("arknights_mower.utils.qrcode")
    qrcode.decode = damaged
    monkeypatch.setitem(sys.modules, qrcode.__name__, qrcode)
    monkeypatch.setattr(utils, "qrcode", qrcode, raising=False)
    response = post_plan_file(plan_client, image.getvalue(), "plan.png", "image/png")
    assert response.status_code == 200
    assert "排班表导入失败" in response.get_data(as_text=True)
    assert config.plan is plan
    assert config.plan_path.read_bytes() == previous


def test_local_directory_failure_is_not_reported_as_invalid_backup(client, monkeypatch):
    raw = backup.export_archive()
    previous = config.conf_path.read_bytes()

    def linked_directory():
        raise backup.LocalConfigError("本机 config 目录包含符号链接，请移除链接后重试")

    monkeypatch.setattr(backup, "_local_snapshot", linked_directory)
    headers = {"token": "old-token", "X-Mower-Settings": "1"}
    exported = client.get("/config-backup/export", headers=headers)
    imported = client.post("/config-backup/import", data=raw, headers=headers)
    for response in (exported, imported):
        assert response.status_code == 409
        assert "本机 config" in response.json["message"]
        assert "符号链接" in response.json["message"]
        assert "备份格式不正确" not in response.json["message"]
    assert config.conf_path.read_bytes() == previous


def test_import_preserves_running_access_settings_when_disk_was_replaced(storage):
    config.conf.webview.port = 18080
    config.conf.webview.token = "running-token"
    config.conf.webview.tray = False
    config.conf_path.write_text(
        "webview: {port: 19090, token: disk-token, tray: true}\n", encoding="utf-8"
    )
    raw = incoming(
        **{
            "conf.yml": "account: imported\nwebview: {port: 20000, token: archive-token, tray: true}\n"
        }
    )
    backup.import_configuration(raw)
    config.load_conf()
    assert config.conf.webview.port == 18080
    assert config.conf.webview.token == "running-token"
    assert config.conf.webview.tray is False


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_imported_plan_encoding_survives_reload_without_rewriting_original(
    storage, populated_plan, bom
):
    original = bom + json.dumps(
        populated_plan.model_dump(exclude_none=True), ensure_ascii=False
    ).encode("utf-8")
    backup.import_configuration(incoming(**{"plan.json": original}))
    for _ in range(2):
        config.load_plan()
        assert config.plan == populated_plan
        assert config.plan_path.read_bytes() == original
