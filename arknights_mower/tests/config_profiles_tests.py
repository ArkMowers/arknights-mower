import json
import sqlite3
from contextlib import closing, contextmanager
from io import BytesIO

import pytest
from flask import Flask

from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils import config_profiles as profiles
from arknights_mower.utils import config_selection as selection
from arknights_mower.utils.config_profile_groups import CONF_GROUPS, GROUPS
from arknights_mower.views.config_profiles import config_profiles_bp


@pytest.fixture
def storage(tmp_path, monkeypatch):
    def get_path(name, space=None):
        return tmp_path / "instance" / name.removeprefix("@app/")

    monkeypatch.setattr(backup, "get_path", get_path)
    monkeypatch.setattr(profiles, "get_path", get_path)
    for attr, name in (
        ("conf_path", "conf.yml"),
        ("plan_path", "plan.json"),
        ("rescue_plan_path", "rescue_plan.json"),
        ("growth_plan_path", "growth_plan.json"),
        ("workshop_preset_path", "workshop_preset.json"),
        ("weekly_plans_path", "weekly_plans.yml"),
        ("app_state_path", "state.json"),
        ("gui_path", "gui.yml"),
    ):
        monkeypatch.setattr(config, attr, get_path(f"@app/config/{name}"))
    monkeypatch.setattr(config, "conf", config.Conf(device={}, account="original"))
    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "rescue_plan", config.PlanModel())
    config.save_conf()
    config.save_plan()
    config.app_state_path.write_text(
        json.dumps({"active_weekly_plan": "current", "window": "local"}),
        encoding="utf-8",
    )
    config.weekly_plans_path.write_text("plans:\n  current: []\n", encoding="utf-8")
    database = get_path("@app/tmp/data.db")
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute(
            "CREATE TABLE inventory(item_name TEXT PRIMARY KEY, count INTEGER)"
        )
        conn.execute("INSERT INTO inventory VALUES ('iron',17)")
        conn.execute("CREATE TABLE future_history(value TEXT NOT NULL)")
        conn.execute("INSERT INTO future_history VALUES ('original')")
        conn.execute("CREATE TABLE saved_state(state TEXT)")
        conn.execute("INSERT INTO saved_state VALUES ('old scheduler')")
    return get_path


def _read_table(storage, table):
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        return conn.execute(f'SELECT * FROM "{table}"').fetchall()


def _create(name, inherit=None):
    return profiles.create_profile(
        name, inherit or [], expected_generation=profiles.current_generation()
    )


def _activate(identifier, keep=None):
    return profiles.activate_profile(
        identifier, keep or [], expected_generation=profiles.current_generation()
    )


def test_generation_read_does_not_initialize_storage(storage):
    assert profiles.current_generation() == "0"
    assert not storage("@app/config-profiles").exists()
    profiles.check_generation(None)
    with pytest.raises(profiles.ProfileConflict):
        profiles.check_generation("wrong")


def test_existing_installation_becomes_default_without_changing_files(storage):
    before = backup.export_archive()
    result = profiles.list_profiles()
    assert result["generation"] == "0"
    assert result["profiles"] == [{"id": result["active_id"], "name": "默认档案"}]
    assert backup.read_archive(
        backup.export_archive(), include_tmp=True
    ) == backup.read_archive(before, include_tmp=True)
    assert profiles.list_profiles() == result
    assert not (storage("@app/config-profiles") / f"{result['active_id']}.zip").exists()


def test_create_uses_defaults_and_selected_groups_while_preserving_access(storage):
    config.conf.drone_count_limit = 77
    config.conf.theme = "dark"
    config.conf.ai_assistant_enabled = True
    config.conf.webview.token = "local-token"
    config.conf.webview.port = 18001
    config.save_conf()
    result = _create("新配置", ["drone"])
    assert config.conf.drone_count_limit == 77
    assert config.conf.theme == config.Conf(device={}).theme
    assert config.conf.account == ""
    assert config.conf.ai_assistant_enabled is True
    assert config.conf.webview.token == "local-token"
    assert config.conf.webview.port == 18001
    assert result["generation"] != "0"
    assert len(result["profiles"]) == 2
    assert json.loads(config.app_state_path.read_text(encoding="utf-8")) == {
        "window": "local"
    }
    assert not config.weekly_plans_path.exists()
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            == []
        )


def test_outgoing_edits_are_saved_and_each_configuration_round_trips(storage):
    original = profiles.list_profiles()["active_id"]
    new = _create("第二套", ["inventory"])
    assert _read_table(storage, "inventory") == [("iron", 17)]
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute("UPDATE inventory SET count=42")
    config.conf.account = "second"
    config.save_conf()
    _activate(original)
    assert config.conf.account == "original"
    assert _read_table(storage, "inventory") == [("iron", 17)]
    assert _read_table(storage, "future_history") == [("original",)]
    _activate(new["active_id"])
    assert config.conf.account == "second"
    assert _read_table(storage, "inventory") == [("iron", 42)]
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='saved_state'"
        ).fetchone()
        assert not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='future_history'"
        ).fetchone()


@pytest.mark.parametrize(
    "name,group,content",
    [
        ("growth_plan.json", "growth", [{"char_id": "char_002_amiya"}]),
        ("workshop_preset.json", "workshop", [{"name": "saved recipe"}]),
        (
            "rescue_plan.json",
            "rescue_plan",
            {"plan1": {"central": {"plans": [{"agent": "阿米娅"}]}}},
        ),
    ],
)
def test_migrated_configuration_files_follow_selected_group(
    storage, name, group, content
):
    path = storage("@app/config/" + name)
    path.write_text(json.dumps(content), encoding="utf-8")
    original = profiles.list_profiles()["active_id"]
    _create("keep selected", [group])
    assert json.loads(path.read_text(encoding="utf-8")) == content
    _create("clear selected", ["other_settings"])
    if name == "rescue_plan.json":
        assert config.rescue_plan.plan1.central is None
    else:
        assert not path.exists()
    _activate(original)
    assert json.loads(path.read_text(encoding="utf-8")) == content


@pytest.mark.parametrize(
    "name,group", [("growth_plan.json", "growth"), ("workshop_preset.json", "workshop")]
)
def test_legacy_tmp_group_does_not_override_current_canonical_selection(
    storage, name, group
):
    path = storage("@app/config/" + name)
    path.write_text('[{"source": "current"}]', encoding="utf-8")
    files = backup.read_archive(backup.export_archive())
    files.pop(name)
    raw = backup._archive_bytes(files, {name: b'[{"source": "legacy"}]'})
    profiles.import_profile(raw, "legacy", [group], expected_generation="0")
    assert json.loads(path.read_text(encoding="utf-8")) == [{"source": "current"}]
    assert not storage("@app/tmp/" + name).exists()


@pytest.mark.parametrize(
    "name,legacy_name",
    [
        ("growth_plan.json", "tmp/growth_plan.json"),
        ("workshop_preset.json", "tmp/workshop_preset.json"),
        ("weekly_plans.yml", "weekly_plans.yml"),
    ],
)
@pytest.mark.parametrize("fail_metadata", [False, True])
def test_profile_clearing_prevents_legacy_restart_migration_and_rolls_back(
    storage, monkeypatch, name, legacy_name, fail_metadata
):
    canonical = storage("@app/config/" + name)
    legacy = storage("@app/" + legacy_name)
    current = b"plans:\n  current: []\n" if name.endswith(".yml") else b"[]"
    obsolete = (
        b"plans:\n  obsolete: []\n"
        if name.endswith(".yml")
        else b'[{"source": "previous configuration"}]'
    )
    canonical.write_bytes(current)
    legacy.write_bytes(obsolete)
    monkeypatch.setattr(config, "_CONFIG_PATH_PAIRS", ((legacy, canonical),))
    initial = profiles.list_profiles()

    if fail_metadata:

        def fail(data):
            assert not legacy.exists()
            raise OSError("metadata failed")

        monkeypatch.setattr(profiles, "_write_registry", fail)
        with pytest.raises(OSError, match="metadata failed"):
            _create("failed clearing")
        assert canonical.read_bytes() == current
        assert legacy.read_bytes() == obsolete
        assert profiles.list_profiles() == initial
    else:
        _create("empty configuration")
        assert not canonical.exists()
        assert not legacy.exists()

    config.migrate_app_config_paths()
    if fail_metadata:
        assert canonical.read_bytes() == current
        assert legacy.read_bytes() == obsolete
    else:
        assert not canonical.exists()


@pytest.mark.parametrize("kind", ["directory", "symlink", "oversized"])
def test_invalid_obsolete_weekly_file_prevents_profile_activation(
    storage, monkeypatch, kind
):
    canonical = config.weekly_plans_path
    legacy = storage("@app/weekly_plans.yml")
    if kind == "directory":
        legacy.mkdir()
    elif kind == "symlink":
        legacy.symlink_to(config.conf_path)
    else:
        with legacy.open("wb") as stream:
            stream.truncate(backup.MAX_BACKUP_BYTES + 1)
    monkeypatch.setattr(config, "_CONFIG_PATH_PAIRS", ((legacy, canonical),))
    initial = profiles.list_profiles()
    current = canonical.read_bytes()
    with pytest.raises(backup.LocalConfigError):
        _create("invalid legacy")
    assert canonical.read_bytes() == current
    assert profiles.list_profiles() == initial
    assert not storage("@app/config-backups").exists()


@pytest.mark.parametrize("keep", [[], ["rescue_plan"]])
def test_legacy_rescue_import_obeys_selection_with_separate_local_plan(storage, keep):
    local = {"plan1": {"central": {"plans": [{"agent": "阿米娅"}]}}}
    config.rescue_plan_path.write_text(json.dumps(local), encoding="utf-8")
    incoming = backup._archive_bytes(
        {
            "conf.yml": json.dumps(
                {
                    "automatic_rescue_plan": {
                        "plan1": {"central": {"plans": [{"agent": "银灰"}]}}
                    }
                }
            ).encode("utf-8"),
            "plan.json": b'{"plan1": {}}',
        },
        {},
    )
    profiles.import_profile(incoming, "legacy rescue", keep, expected_generation="0")
    assert config.rescue_plan.plan1.central.plans[0].agent == (
        "阿米娅" if keep else "银灰"
    )
    assert "automatic_rescue_plan" not in backup._object_file(
        backup.read_archive(backup.export_archive()), "conf.yml"
    )


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("selected", [[], ["other_settings"]])
@pytest.mark.parametrize("operation", ["create", "activate", "import"])
def test_profile_operations_preserve_current_update_authorization(
    storage, saved, selected, operation
):
    config.conf.updates_enabled = not saved
    config.save_conf()
    original = profiles.list_profiles()["active_id"]
    incoming = backup.export_archive()
    if operation == "activate":
        _create("second")
    config.conf.updates_enabled = saved
    config.save_conf()

    if operation == "create":
        _create("created", selected)
    elif operation == "activate":
        _activate(original, selected)
    else:
        profiles.import_profile(
            incoming,
            "imported",
            selected,
            expected_generation=profiles.current_generation(),
        )

    assert config.conf.updates_enabled is saved
    assert (
        backup._object_file(backup.read_archive(backup.export_archive()), "conf.yml")[
            "updates_enabled"
        ]
        is saved
    )


def test_activation_retains_selected_current_groups_and_updates_target_snapshot(
    storage,
):
    original = profiles.list_profiles()["active_id"]
    second = _create("second", ["inventory", "notifications"])
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute("UPDATE inventory SET count=29")
    config.conf.account = "kept"
    config.save_conf()
    _activate(original, ["inventory", "notifications"])
    assert config.conf.account == "kept"
    assert _read_table(storage, "inventory") == [("iron", 29)]
    assert _read_table(storage, "future_history") == [("original",)]
    _activate(second["active_id"])
    _activate(original)
    assert config.conf.account == "kept"
    assert _read_table(storage, "inventory") == [("iron", 29)]


def test_database_tables_keep_schema_indexes_and_autoincrement(storage):
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute(
            'CREATE TABLE "unusual table"(id INTEGER PRIMARY KEY AUTOINCREMENT, "a""b" TEXT UNIQUE)'
        )
        conn.execute('CREATE INDEX custom_idx ON "unusual table"("a""b")')
        conn.execute("INSERT INTO \"unusual table\" VALUES (100,'large')")
        conn.execute('DELETE FROM "unusual table"')
    _create("copy", ["other_history"])
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute('INSERT INTO "unusual table"("a""b") VALUES (\'kept\')')
        assert conn.execute('SELECT id FROM "unusual table"').fetchone() == (101,)
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name='custom_idx'"
        ).fetchone() == ("custom_idx",)


@pytest.mark.parametrize("inherit", [[], ["other_settings"]])
def test_profile_switch_preserves_the_active_gui_process_lock(
    storage, monkeypatch, inherit
):
    from arknights_mower.utils.config import gui

    monkeypatch.setattr(gui, "gui_path", config.gui_path)
    gui.save_window_mode("maximized")
    before_gui = config.gui_path.read_bytes()
    lock_path = config.gui_path.with_suffix(".yml.lock")
    with gui._gui_file_lock():
        original_inode = lock_path.stat().st_ino
        original = profiles.list_profiles()["active_id"]
        created = _create("lock preservation", inherit)
        _activate(original)
        _activate(created["active_id"])
        assert lock_path.stat().st_ino == original_inode
        assert config.gui_path.read_bytes() == before_gui
        for identifier in (original, created["active_id"]):
            snapshot = storage("@app/config-profiles") / f"{identifier}.zip"
            assert "gui.yml.lock" not in backup.read_archive(snapshot.read_bytes())
    gui.save_window_mode("normal")
    assert gui.load_window_mode() == "normal"


def test_all_selected_groups_preserve_configuration_without_saved_scheduler(storage):
    config.conf.theme = "dark"
    config.conf.automatic_rescue_enable = True
    config.save_conf()
    _create("full copy", [group["key"] for group in GROUPS])
    assert config.conf.account == "original"
    assert config.conf.theme == "dark"
    assert config.conf.automatic_rescue_enable is True
    assert _read_table(storage, "inventory") == [("iron", 17)]
    assert _read_table(storage, "future_history") == [("original",)]
    assert json.loads(config.app_state_path.read_text(encoding="utf-8")) == {
        "window": "local",
        "active_weekly_plan": "current",
    }


def test_weekly_selection_round_trip_keeps_other_window_state(storage):
    original = profiles.list_profiles()["active_id"]
    second = _create("other")
    config.weekly_plans_path.write_text("plans:\n  second: []\n", encoding="utf-8")
    config.app_state_path.write_text(
        json.dumps({"active_weekly_plan": "second", "window": "new local"}),
        encoding="utf-8",
    )
    _activate(original)
    assert json.loads(config.app_state_path.read_text(encoding="utf-8")) == {
        "window": "new local",
        "active_weekly_plan": "current",
    }
    _activate(second["active_id"])
    assert json.loads(config.app_state_path.read_text(encoding="utf-8")) == {
        "window": "new local",
        "active_weekly_plan": "second",
    }


def test_metadata_failure_rolls_back_configuration_database_state_and_registry(
    storage, monkeypatch
):
    baseline = profiles.list_profiles()
    before = backup.export_archive()
    previous_conf = config.conf
    previous_state = config.app_state_path.read_bytes()
    previous_index = storage("@app/config-profiles/index.json").read_bytes()

    def fail(data):
        raise OSError("metadata failed")

    monkeypatch.setattr(profiles, "_write_registry", fail)
    with pytest.raises(OSError, match="metadata failed"):
        _create("will fail")
    assert backup.read_archive(
        backup.export_archive(), include_tmp=True
    ) == backup.read_archive(before, include_tmp=True)
    assert config.conf is previous_conf
    assert config.app_state_path.read_bytes() == previous_state
    assert storage("@app/config-profiles/index.json").read_bytes() == previous_index
    assert profiles.list_profiles() == baseline
    assert _read_table(storage, "saved_state") == [("old scheduler",)]
    assert len(list(storage("@app/config-profiles").glob("*.zip"))) == 1


@pytest.mark.parametrize("initialized", ["absent", "listed", "activated"])
def test_backup_import_advances_generation_and_rejects_old_page_saves(
    storage, monkeypatch, initialized
):
    import server

    monkeypatch.setattr(server.app, "token", "secret", raising=False)
    monkeypatch.setitem(server.app.config, "CONFIG_BACKUP_BUSY", lambda: False)
    baseline = None
    if initialized == "activated":
        baseline = _create("active profile", ["inventory"])
    elif initialized == "listed":
        baseline = profiles.list_profiles()
    initial_generation = profiles.current_generation()
    raw = backup.export_archive()
    config.conf.theme = "dark"
    config.save_conf()
    client = server.app.test_client()
    imported = client.post(
        "/config-backup/import", headers=_headers(initial_generation), data=raw
    )
    assert imported.status_code == 200
    current = profiles.list_profiles()
    assert current["generation"] != initial_generation
    assert len(current["profiles"]) == (2 if initialized == "activated" else 1)
    if baseline is not None:
        assert current["active_id"] == baseline["active_id"]
        assert current["profiles"] == baseline["profiles"]
    assert config.conf.theme == "light"
    stale = client.patch(
        "/conf", headers=_headers(initial_generation), json={"theme": "dark"}
    )
    assert stale.status_code == 409
    assert stale.json["code"] == "configuration_changed"
    assert config.conf.theme == "light"
    snapshot = storage(f"@app/config-profiles/{current['active_id']}.zip")
    assert (
        backup._object_file(backup.read_archive(snapshot.read_bytes()), "conf.yml").get(
            "theme", "light"
        )
        == "light"
    )


@pytest.mark.parametrize("initialized", [False, True])
def test_backup_import_metadata_failure_rolls_back_files_database_and_generation(
    storage, monkeypatch, initialized
):
    import server

    monkeypatch.setattr(server.app, "token", "secret", raising=False)
    monkeypatch.setitem(server.app.config, "CONFIG_BACKUP_BUSY", lambda: False)
    if initialized:
        _create("second", ["inventory"])
    initial_generation = profiles.current_generation()
    raw = backup.export_archive()
    config.conf.theme = "dark"
    config.save_conf()
    before = backup.read_archive(backup.export_archive(), include_tmp=True)
    previous_conf = config.conf
    index = storage("@app/config-profiles/index.json")
    previous_index = index.read_bytes() if index.exists() else None
    snapshots = {
        path.name: path.read_bytes()
        for path in storage("@app/config-profiles").glob("*.zip")
    }

    write_registry = profiles._write_registry

    def fail(data):
        write_registry(data)
        raise OSError("metadata failed")

    monkeypatch.setattr(profiles, "_write_registry", fail)
    imported = server.app.test_client().post(
        "/config-backup/import", headers=_headers(initial_generation), data=raw
    )
    assert imported.status_code == 500
    assert config.conf is previous_conf
    assert profiles.current_generation() == initial_generation
    assert (index.read_bytes() if index.exists() else None) == previous_index
    assert {
        path.name: path.read_bytes()
        for path in storage("@app/config-profiles").glob("*.zip")
    } == snapshots
    assert backup.read_archive(backup.export_archive(), include_tmp=True) == before


@pytest.mark.parametrize("operation", ["create", "activate", "rename", "import"])
def test_stale_generation_rejects_every_mutation_before_writes(storage, operation):
    old = profiles.list_profiles()
    _create("second")
    before = profiles.list_profiles()
    snapshot = backup.export_archive()
    with pytest.raises(profiles.ProfileConflict):
        if operation == "create":
            profiles.create_profile("third", [], expected_generation=old["generation"])
        elif operation == "activate":
            profiles.activate_profile(
                old["active_id"], [], expected_generation=old["generation"]
            )
        elif operation == "rename":
            profiles.rename_profile(
                old["active_id"], "old", expected_generation=old["generation"]
            )
        else:
            profiles.import_profile(
                snapshot, "import", [], expected_generation=old["generation"]
            )
    assert profiles.list_profiles() == before
    assert backup.read_archive(
        backup.export_archive(), include_tmp=True
    ) == backup.read_archive(snapshot, include_tmp=True)


def test_rename_does_not_activate_or_advance_generation(storage):
    baseline = profiles.list_profiles()
    result = profiles.rename_profile(
        baseline["active_id"], "改名", expected_generation="0"
    )
    assert result["active_id"] == baseline["active_id"]
    assert result["generation"] == "0"
    assert result["profiles"][0]["name"] == "改名"
    assert config.conf.account == "original"


@pytest.mark.parametrize("name", ["", " ", "a" * 65, "bad\x00name", None, 7])
def test_invalid_names_do_not_create_profiles(storage, name):
    baseline = profiles.list_profiles()
    with pytest.raises(ValueError):
        _create(name)
    assert profiles.list_profiles() == baseline


def test_conf_fields_have_one_group_and_no_unmapped_current_fields():
    fields = [field for values in CONF_GROUPS.values() for field in values]
    assert len(fields) == len(set(fields))
    assert set(config.Conf.model_fields) - set(fields) == {
        "ai_assistant_enabled",
        "updates_enabled",
    }
    keys = {group["key"] for group in GROUPS}
    assert set(CONF_GROUPS) <= keys
    assert set(selection.TABLE_GROUPS.values()) <= keys
    assert set(selection.TMP_GROUPS.values()) <= keys


def test_selection_rebuilds_normal_plan_advanced_settings_from_selected_conf(storage):
    config.conf.resting_threshold = 0.8
    config.conf.group_mood_gap_exclusions = ["excluded"]
    config.save_conf()
    plan = json.loads(config.plan_path.read_text(encoding="utf-8"))
    plan["advanced_settings"] = {"resting_threshold": 0.3}
    config.plan_path.write_text(json.dumps(plan), encoding="utf-8")
    _create("plan", ["normal_plan", "base"])
    assert config.conf.resting_threshold == 0.8
    assert config.conf.group_mood_gap_exclusions == ["excluded"]
    assert config.plan.advanced_settings["resting_threshold"] == 0.8
    assert config.plan.advanced_settings["group_mood_gap_exclusions"] == ["excluded"]


@pytest.mark.parametrize("source", ["global", "advanced"])
@pytest.mark.parametrize("keep", [[], ["other_settings"]])
def test_profile_import_migrates_bed_order_before_group_selection(
    storage, source, keep
):
    files = backup.read_archive(backup.export_archive(include_tmp=False))
    order = "dormitory_2,dormitory_1,dormitory_3,dormitory_4"
    plan = json.loads(files["plan.json"])
    plan["conf"].pop("dorm_order", None)
    if source == "global":
        files["conf.yml"] += f"\ndorm_order: {order}\n".encode("utf-8")
    else:
        plan["advanced_settings"] = {"dorm_order": order}
    files["plan.json"] = json.dumps(plan).encode("utf-8")
    profiles.import_profile(
        backup._archive_bytes(files, {}),
        "legacy bed order",
        keep,
        expected_generation="0",
    )
    assert config.plan.conf.dorm_order == order
    assert (
        json.loads(config.plan_path.read_text(encoding="utf-8"))["conf"]["dorm_order"]
        == order
    )


def test_partial_cultivate_snapshot_separates_inventory_and_operators(storage):
    snapshot = storage("@app/tmp/cultivate.json")
    snapshot.write_text(
        json.dumps(
            {
                "code": 0,
                "data": {
                    "items": [{"id": "iron", "count": 17}],
                    "characters": [{"id": "amiya"}],
                },
                "_mower_inventory_observed_at": 123,
                "_mower_player": "local",
            }
        ),
        encoding="utf-8",
    )
    _create("inventory only", ["inventory"])
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    assert data == {
        "data": {"items": [{"id": "iron", "count": 17}]},
        "_mower_inventory_observed_at": 123,
    }
    from arknights_mower.utils.schedule_roster import _read_roster

    assert _read_roster(snapshot) is None


def test_operator_only_selection_can_be_read_by_real_depot_reader(storage, monkeypatch):
    from arknights_mower.utils import depot

    snapshot = storage("@app/tmp/cultivate.json")
    snapshot.write_text(
        json.dumps(
            {
                "code": 0,
                "data": {
                    "items": [{"id": "30013", "count": 99}],
                    "characters": [{"id": "amiya"}],
                },
                "_mower_inventory_observed_at": 123,
            }
        ),
        encoding="utf-8",
    )
    _create("operators only", ["operators"])
    monkeypatch.setattr(depot, "get_path", storage)
    monkeypatch.setattr(depot, "save_inventory_counts", lambda counts, **_: counts)
    result = depot.读取仓库()
    assert isinstance(result[0], dict)
    assert json.loads(snapshot.read_text(encoding="utf-8"))["data"]["items"] == []


@pytest.mark.parametrize(
    "schema",
    [
        "CREATE VIEW unexpected AS SELECT 1",
        "CREATE TRIGGER unexpected AFTER INSERT ON inventory BEGIN SELECT 1; END",
    ],
)
def test_untrusted_database_objects_are_rejected_without_writes(storage, schema):
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute(schema)
    baseline = profiles.list_profiles()
    with pytest.raises(ValueError, match="视图或触发器"):
        _create("bad", ["inventory"])
    assert profiles.list_profiles() == baseline


@pytest.fixture
def client(storage):
    app = Flask(__name__)
    app.token = "secret"
    app.register_blueprint(config_profiles_bp)
    return app.test_client()


def _headers(generation="0", **extra):
    return {
        "token": "secret",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": generation,
        **extra,
    }


def test_http_auth_settings_origin_and_generation_guards(client):
    assert client.get("/config-profiles").status_code == 403
    assert (
        client.get("/config-profiles", headers={"token": "secret"}).status_code == 200
    )
    body = {"name": "new", "inherit": []}
    assert (
        client.post(
            "/config-profiles", json=body, headers={"token": "secret"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/config-profiles", json=body, headers=_headers(Origin="https://other.test")
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/config-profiles",
            json=body,
            headers={"token": "secret", "X-Mower-Settings": "1"},
        ).json["code"]
        == "configuration_changed"
    )
    result = client.post("/config-profiles", json=body, headers=_headers())
    assert result.status_code == 200
    assert result.json["generation"] != "0"
    assert (
        client.patch(
            f"/config-profiles/{result.json['active_id']}",
            json={"name": "stale"},
            headers=_headers(),
        ).status_code
        == 409
    )


def test_http_busy_callback_is_inside_maintenance_locks_and_prevents_mutation(client):
    state = {"locked": False}

    @contextmanager
    def locks():
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False

    def busy():
        assert state["locked"]
        return True

    client.application.config["CONFIG_PROFILES_LOCKS"] = locks
    client.application.config["CONFIG_PROFILES_BUSY"] = busy
    assert client.get("/config-profiles", headers=_headers()).json["busy"] is True
    response = client.post(
        "/config-profiles", json={"name": "blocked"}, headers=_headers()
    )
    assert response.status_code == 409
    assert "code" not in response.json
    assert len(profiles.list_profiles()["profiles"]) == 1


def test_http_export_and_import_include_weekly_selection(client, storage):
    exported = client.get("/config-profiles/export", headers=_headers())
    assert exported.status_code == 200
    files = backup.read_archive(exported.data)
    assert json.loads(files[selection.WEEKLY_SELECTION_FILE]) == {
        "active_weekly_plan": "current"
    }
    response = client.post(
        "/config-profiles/import",
        headers=_headers(),
        data={
            "backup": (BytesIO(exported.data), "mower.zip"),
            "name": "imported",
            "keep": '["inventory"]',
        },
    )
    assert response.status_code == 200
    assert response.json["profiles"][-1]["name"] == "imported"
    assert config.conf.account == "original"
    assert _read_table(storage, "inventory") == [("iron", 17)]


def test_corrupt_registry_blocks_generation_checks(storage):
    storage("@app/config-profiles").mkdir(parents=True)
    storage("@app/config-profiles/index.json").write_text("{}", encoding="utf-8")
    with pytest.raises(backup.LocalConfigError):
        profiles.check_generation(None)


def test_actual_application_table_definitions_survive_selected_copy(
    storage, monkeypatch
):
    from arknights_mower.solvers import record
    from arknights_mower.utils.mastery_db import (
        _NOTIFY_SCHEMA,
        _PLAN_SCHEMA,
        _ROUTE_SCHEMA,
    )

    monkeypatch.setattr(record, "_tables_created", False)
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        record._ensure_tables(conn)
        for statement in (
            _PLAN_SCHEMA,
            _ROUTE_SCHEMA,
            _NOTIFY_SCHEMA,
        ):
            conn.execute(statement)
        conn.execute(
            "INSERT INTO mastery_plan(char_id,skill_index,target_level) VALUES ('char_002_amiya',0,3)"
        )
        conn.execute("INSERT INTO mastery_route(profession) VALUES ('CASTER')")
        conn.execute(
            "INSERT INTO mastery_notify(notify_type,dedup_key) VALUES ('plan','1')"
        )
        expected = dict(
            conn.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'saved_state'"
            )
        )
    _create("all application tables", [group["key"] for group in GROUPS])
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert (
            dict(
                conn.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            )
            == expected
        )
        assert conn.execute(
            "SELECT char_id,skill_index,target_level FROM mastery_plan"
        ).fetchall() == [("char_002_amiya", 0, 3)]
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='agent_action_working_time'"
        ).fetchone() == ("agent_action_working_time",)


def test_profile_zip_import_clears_missing_data_instead_of_reusing_local(storage):
    raw = backup.export_archive(include_tmp=False)
    report = storage("@app/tmp/report.csv")
    report.write_bytes(b"old report")
    unrelated = storage("@app/tmp/unrelated.json")
    unrelated.write_bytes(b"keep unrelated")
    profiles.import_profile(raw, "legacy ZIP", [], expected_generation="0")
    assert not report.exists()
    assert unrelated.read_bytes() == b"keep unrelated"
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_activation_metadata_failure_restores_existing_target_snapshot(
    storage, monkeypatch
):
    original = profiles.list_profiles()["active_id"]
    _create("second", ["inventory"])
    config.conf.account = "current"
    config.save_conf()
    before = backup.export_archive()
    baseline = profiles.list_profiles()
    target = storage(f"@app/config-profiles/{original}.zip")
    target_before = target.read_bytes()

    def fail(data):
        raise OSError("index failed")

    monkeypatch.setattr(profiles, "_write_registry", fail)
    with pytest.raises(OSError, match="index failed"):
        _activate(original, ["notifications"])
    assert profiles.list_profiles() == baseline
    assert target.read_bytes() == target_before
    assert backup.read_archive(
        backup.export_archive(), include_tmp=True
    ) == backup.read_archive(before, include_tmp=True)


@pytest.mark.parametrize("failure", [False, True])
def test_only_successful_activation_clears_process_local_workshop_observations(
    storage, monkeypatch, failure
):
    from arknights_mower.solvers import record
    from arknights_mower.utils import (
        workshop_automation,
        workshop_limits,
        workshop_status,
    )

    profiles.list_profiles()
    monkeypatch.setattr(
        workshop_automation, "_refresh_error", "old configuration failure"
    )
    monkeypatch.setattr(workshop_limits, "_rejected_recipes", {"recipe": ((0, ()), 1)})
    record.workshop_inventory_changed.set()
    monkeypatch.setattr(record, "get_inventory_counts", lambda: {})
    if failure:

        def fail(data):
            raise OSError("metadata failed")

        monkeypatch.setattr(profiles, "_write_registry", fail)
        with pytest.raises(OSError):
            _create("second")
        assert workshop_automation._refresh_error == "old configuration failure"
        assert record.workshop_inventory_changed.is_set()
        assert workshop_limits._rejected_recipes
    else:
        _create("second")
        status = workshop_status.workshop_status()
        assert status["pending_refresh"] is False
        assert not any(
            block["code"] == "refresh_failed" for block in status["blockers"]
        )
        assert workshop_automation._refresh_error is None
        assert workshop_limits._rejected_recipes == {}
    record.workshop_inventory_changed.clear()


@pytest.mark.parametrize(
    "invalid", [None, "inventory", ["inventory", "inventory"], ["unknown"], [1]]
)
def test_invalid_selected_groups_are_rejected(storage, invalid):
    profiles.list_profiles()
    with pytest.raises(ValueError):
        profiles.create_profile("invalid", invalid, expected_generation="0")
    assert len(profiles.list_profiles()["profiles"]) == 1


def test_nonregular_snapshot_is_rejected_before_generation_allows_writes(storage):
    data = profiles.list_profiles()
    snapshot = storage(f"@app/config-profiles/{data['active_id']}.zip")
    snapshot.mkdir()
    with pytest.raises(backup.LocalConfigError):
        profiles.current_generation()


def test_initial_list_and_bootstrap_do_not_require_a_database_snapshot(
    client, storage, monkeypatch
):
    calls = []
    previous_conf = config.conf
    before = backup.read_archive(backup.export_archive(), include_tmp=True)

    def oversized_database():
        calls.append("snapshot")
        raise backup.LocalConfigError("本机数据库超过 16 MB，无法生成备份")

    monkeypatch.setattr(profiles, "export_current_archive", oversized_database)
    response = client.get("/config-profiles", headers=_headers())
    assert response.status_code == 200
    baseline = response.json
    assert baseline["generation"] == "0"
    assert baseline["profiles"] == [{"id": baseline["active_id"], "name": "默认档案"}]
    assert calls == []
    assert profiles.current_generation() == "0"
    profiles.check_generation("0", allow_legacy=False)
    profiles.check_generation(None)
    assert not list(storage("@app/config-profiles").glob("*.zip"))
    rejected = client.post(
        "/config-profiles",
        json={"name": "too large", "inherit": []},
        headers=_headers(),
    )
    assert rejected.status_code == 409
    assert "16 MB" in rejected.json["message"]
    assert calls == ["snapshot"]
    assert profiles.list_profiles()["profiles"] == baseline["profiles"]
    assert profiles.current_generation() == "0"
    assert config.conf is previous_conf
    assert backup.read_archive(backup.export_archive(), include_tmp=True) == before
    assert not list(storage("@app/config-profiles").glob("*.zip"))


def test_only_the_initial_active_profile_may_have_no_snapshot(storage):
    baseline = profiles.list_profiles()
    data = json.loads(
        storage("@app/config-profiles/index.json").read_text(encoding="utf-8")
    )
    data["profiles"].append({"id": "f" * 32, "name": "missing inactive"})
    storage("@app/config-profiles/index.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(backup.LocalConfigError):
        profiles.current_generation()
    data["profiles"] = baseline["profiles"]
    data["generation"] = "a" * 32
    storage("@app/config-profiles/index.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    with pytest.raises(backup.LocalConfigError):
        profiles.current_generation()


def test_mixed_case_saved_state_is_not_restored_by_real_scheduler_reader(
    storage, monkeypatch
):
    import pickle

    from arknights_mower.solvers import record

    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute("DROP TABLE saved_state")
        conn.execute("CREATE TABLE Saved_State(time TEXT,state BLOB)")
        conn.execute(
            "INSERT INTO Saved_State VALUES (?,?)",
            ("2026-10-18", pickle.dumps({"old_configuration": True})),
        )
    raw = profiles.export_current_archive()
    profiles.import_profile(raw, "mixed case", [], expected_generation="0")
    monkeypatch.setattr(record, "get_path", storage)
    monkeypatch.setattr(record, "_tables_created", False)
    assert record.load_state() is None
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM saved_state").fetchone() == (0,)


def test_partial_database_copy_preserves_rowids_and_without_rowid_tables(storage):
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn, conn:
        conn.execute("CREATE TABLE row_history(value TEXT)")
        conn.execute(
            "INSERT INTO row_history(rowid,value) VALUES (100,'first'),(200,'second')"
        )
        conn.execute(
            "CREATE TABLE keyed_history(code TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID"
        )
        conn.execute("INSERT INTO keyed_history VALUES ('code','value')")
    _create("table identity", ["other_history"])
    with closing(sqlite3.connect(storage("@app/tmp/data.db"))) as conn:
        assert conn.execute(
            "SELECT rowid,value FROM row_history ORDER BY rowid"
        ).fetchall() == [(100, "first"), (200, "second")]
        assert conn.execute("SELECT * FROM keyed_history").fetchall() == [
            ("code", "value")
        ]


@pytest.mark.parametrize("mode", ["auto", "high"])
@pytest.mark.parametrize("failure", [False, True])
def test_only_successful_activation_resets_observed_performance_without_changing_user_parameters(
    storage, monkeypatch, mode, failure
):
    from arknights_mower.utils.performance import effective_performance_profile

    config.conf.performance_mode = mode
    config.conf.screenshot_interval = 900
    config.conf.selection_poll_interval = 0.3
    config.conf.selection_transition_timeout = 4.5
    config.save_conf()
    profiles.list_profiles()
    observed = {
        "operation_feedback_avg": 2,
        "operation_feedback_count": 9,
        "operation_feedback_mode": "low",
        "operation_feedback_cap": "low",
        "operation_failure_streak": 3,
        "operation_recovery_successes": 2,
    }
    for key, value in observed.items():
        monkeypatch.setattr(config, key, value)

    def effective():
        return effective_performance_profile(
            config.conf,
            config.operation_feedback_avg,
            config.operation_feedback_count,
            config.operation_feedback_mode,
            config.operation_feedback_cap,
        )

    assert effective().mode == ("low" if mode == "auto" else "high")
    if failure:

        def fail(data):
            raise OSError("metadata failed")

        monkeypatch.setattr(profiles, "_write_registry", fail)
        with pytest.raises(OSError, match="metadata failed"):
            _create("performance", ["runtime"])
        assert {key: getattr(config, key) for key in observed} == observed
        assert effective().mode == ("low" if mode == "auto" else "high")
    else:
        _create("performance", ["runtime"])
        assert {key: getattr(config, key) for key in observed} == {
            "operation_feedback_avg": None,
            "operation_feedback_count": 0,
            "operation_feedback_mode": None,
            "operation_feedback_cap": None,
            "operation_failure_streak": 0,
            "operation_recovery_successes": 0,
        }
        assert effective().mode == ("xhigh" if mode == "auto" else "high")
    assert config.conf.performance_mode == mode
    result = effective()
    assert (
        result.screenshot_interval,
        result.poll_interval,
        result.transition_timeout,
    ) == (900, 0.3, 4.5)
