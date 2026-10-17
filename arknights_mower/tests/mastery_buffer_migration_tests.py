"""Legacy defaults migrate once without overwriting later or concurrent edits."""

import json
import sqlite3

import pytest

from arknights_mower.utils import mastery_db as db
from arknights_mower.utils.mastery_support_types import DEFAULT_SWAP_BUFFERS


def store_raw(path, payload):
    with db._conn(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mastery_route (profession, supports, is_default) "
            "VALUES (?, ?, 0)",
            (db._SETTINGS_PROFESSION, json.dumps(payload)),
        )
        conn.commit()


def read_raw(path):
    with db._conn(path) as conn:
        return json.loads(
            conn.execute(
                "SELECT supports FROM mastery_route WHERE profession=? AND is_default=0",
                (db._SETTINGS_PROFESSION,),
            ).fetchone()[0]
        )


@pytest.mark.parametrize("legacy", [0, 5, 10, 45])
def test_every_legacy_scalar_migrates_to_persisted_defaults(tmp_path, legacy):
    path = str(tmp_path / "mastery.db")
    store_raw(path, {"central_bonus": 5, "mastery_swap_buffer": legacy, "extra": True})
    expected = DEFAULT_SWAP_BUFFERS
    assert db.get_route_settings(path)["mastery_swap_buffers"] == expected
    saved = read_raw(path)
    assert saved["mastery_swap_buffers"] == expected
    assert saved["extra"] is True
    assert saved["central_bonus"] == 5


def test_repeated_reads_and_reopened_database_preserve_user_changes(
    tmp_path, monkeypatch
):
    path = str(tmp_path / "mastery.db")
    store_raw(path, {"mastery_swap_buffer": 10})
    assert db.get_route_settings(path)["mastery_swap_buffers"] == DEFAULT_SWAP_BUFFERS
    custom = dict.fromkeys(DEFAULT_SWAP_BUFFERS, 10)
    db.save_route_settings(path=path, mastery_swap_buffers=custom)
    before = read_raw(path)
    statements = []
    original = db._db

    def traced(path=None):
        conn = original(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(db, "_db", traced)
    for _ in range(3):
        # Every call opens a fresh connection, as after restarting the process.
        assert db.get_route_settings(path)["mastery_swap_buffers"] == custom
    assert read_raw(path) == before
    assert not any(s.lstrip().upper().startswith("UPDATE ") for s in statements)


@pytest.mark.parametrize("central", [0, 5])
def test_existing_map_is_never_reinterpreted_as_old_default(tmp_path, central):
    path = str(tmp_path / "mastery.db")
    custom = dict.fromkeys(DEFAULT_SWAP_BUFFERS, 10)
    store_raw(
        path,
        {
            "central_bonus": central,
            "mastery_swap_buffer": 10,
            "mastery_swap_buffers": custom,
        },
    )
    assert db.get_route_settings(path)["mastery_swap_buffers"] == custom
    assert read_raw(path)["mastery_swap_buffers"] == custom


def test_concurrent_user_save_wins_over_stale_migration(tmp_path, monkeypatch):
    path = str(tmp_path / "mastery.db")
    store_raw(path, {"mastery_swap_buffer": 10})
    custom = {"no_central": 3, "central": 4, "central_unhalved_m2": 6}
    payload = json.dumps({"mastery_swap_buffers": custom})
    raced = False

    class RaceConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            nonlocal raced
            if sql.startswith("UPDATE mastery_route SET supports=") and not raced:
                raced = True
                with sqlite3.connect(path) as other:
                    other.execute(
                        "UPDATE mastery_route SET supports=? WHERE profession=?",
                        (payload, db._SETTINGS_PROFESSION),
                    )
            return super().execute(sql, parameters)

    def connect(path=None):
        conn = sqlite3.connect(path, factory=RaceConnection)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(db, "_db", connect)
    assert db.get_route_settings(path)["mastery_swap_buffers"] == custom
    assert raced
    assert read_raw(path)["mastery_swap_buffers"] == custom
