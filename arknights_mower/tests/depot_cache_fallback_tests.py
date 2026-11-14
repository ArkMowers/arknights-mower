"""Failed warehouse synchronization retains local changes and restores cache baselines."""

import csv
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.cultivate_depot_tests import stock_db as stock_db
from arknights_mower.tests.cultivate_depot_tests import syncer as syncer
from arknights_mower.utils import depot

pytestmark = pytest.mark.usefixtures("income_db")


@pytest.fixture
def cached(syncer, stock_db, monkeypatch, tmp_path):
    from arknights_mower.solvers import base_schedule, cultivate_depot

    monkeypatch.setattr(
        depot, "get_path", lambda name: tmp_path / name.rsplit("/", 1)[-1]
    )
    monkeypatch.setattr(base_schedule, "cultivateDepotSolver", lambda: syncer)
    monkeypatch.setattr(cultivate_depot, "get_binding_list", lambda _: [])
    scan = MagicMock()
    monkeypatch.setattr(base_schedule, "DepotSolver", scan)
    payload = {
        "code": 0,
        "_mower_inventory_observed_at": 100,
        "data": {
            "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
            "items": [{"id": "3303", "count": "70"}],
        },
    }
    syncer.record_path.write_text(json.dumps(payload), encoding="utf-8")
    solver = SimpleNamespace(_auto_schedule_mastery_after_scan=MagicMock())
    monkeypatch.setattr(
        stock_db, "battle_inventory_active", SimpleNamespace(is_set=lambda: False)
    )
    monkeypatch.setattr(stock_db, "workshop_inventory_changed", MagicMock())
    return SimpleNamespace(
        solver=solver,
        module=base_schedule,
        syncer=syncer,
        db=stock_db,
        scan=scan,
        path=tmp_path,
        payload=payload,
    )


def write_snapshot(path, at, counts, complete=False):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Timestamp", "Data", "json"])
        writer.writerow([at, json.dumps(counts), json.dumps({"完整": complete})])


@pytest.mark.parametrize("failure", ["no_binding", "exception"])
def test_failed_sync_skips_scan_and_restores_missing_counts_from_existing_files(
    cached, monkeypatch, failure
):
    if failure == "exception":
        monkeypatch.setattr(
            cached.syncer, "start", MagicMock(side_effect=RuntimeError("offline"))
        )
    write_snapshot(cached.path / "depotresult.csv", 90, {"龙门币": 1000})
    original = cached.syncer.record_path.read_bytes()
    assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
    stock = cached.db.get_inventory_counts()
    assert stock["技巧概要·卷3"] == 70
    assert stock["龙门币"] == 1000
    assert cached.syncer.record_path.read_bytes() == original
    cached.scan.assert_not_called()
    cached.solver._auto_schedule_mastery_after_scan.assert_not_called()
    with cached.db._conn() as conn:
        observed = dict(
            conn.execute(
                "SELECT item_name, observed_at FROM workshop_inventory_updates"
            )
        )
    assert observed["技巧概要·卷3"] == 100
    assert observed["龙门币"] == 90


@pytest.mark.parametrize("count", [-123, "-123"])
@pytest.mark.parametrize("failure", ["no_binding", "exception"])
def test_synced_negative_furniture_cache_restores_missing_materials(
    cached, monkeypatch, count, failure
):
    from arknights_mower.solvers import cultivate_depot

    cached.payload["data"]["items"].append({"id": "3401", "count": count})
    with monkeypatch.context() as refresh:
        refresh.setattr(cultivate_depot, "time", lambda: 100)
        refresh.setattr(
            cultivate_depot,
            "get_binding_list",
            lambda _: [{"gameId": 1, "isOfficial": True, "uid": "test"}],
        )
        response = MagicMock()
        response.json.return_value = cached.payload
        refresh.setattr(
            cultivate_depot, "request_with_retry", lambda *a, **kw: response
        )
        assert cached.syncer.start(force_inventory=True)
    original = cached.syncer.record_path.read_bytes()
    assert json.loads(original)["data"]["items"][-1]["count"] == count

    with cached.db._conn() as conn:
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM workshop_inventory_updates")
        conn.execute("DELETE FROM workshop_inventory_pending")
    assert cached.db.get_inventory_counts() == {}
    if failure == "exception":
        monkeypatch.setattr(
            cached.syncer, "start", MagicMock(side_effect=RuntimeError("offline"))
        )
    for _ in range(2):
        assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
        stock = cached.db.get_inventory_counts()
        assert stock["技巧概要·卷3"] == 70
        assert "家具零件" not in stock
    with cached.db._conn() as conn:
        assert conn.execute(
            "SELECT observed_at FROM workshop_inventory_updates WHERE item_name = ?",
            ("技巧概要·卷3",),
        ).fetchone() == (100,)
    assert cached.syncer.record_path.read_bytes() == original
    cached.scan.assert_not_called()
    cached.solver._auto_schedule_mastery_after_scan.assert_not_called()


@pytest.mark.parametrize(
    "item",
    [
        {"id": "3303", "count": -1},
        {"id": "3303", "count": "-1"},
        *[
            {"id": "3401", "count": count}
            for count in ("--1", "-", "-1.5", -1.5, None, True)
        ],
        {"id": 3401, "count": "-1"},
        None,
    ],
)
def test_invalid_cached_inventory_keeps_missing_materials_unknown(cached, item):
    cached.db.save_inventory_counts({"龙门币": 400})
    cached.payload["data"]["items"].append(item)
    cached.syncer.record_path.write_text(json.dumps(cached.payload), encoding="utf-8")
    original = cached.syncer.record_path.read_bytes()

    assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False

    assert cached.db.get_inventory_counts() == {"龙门币": 400}
    assert cached.syncer.record_path.read_bytes() == original
    cached.scan.assert_not_called()


def test_repeated_failure_keeps_confirmed_consumption_and_invalidated_counts(cached):
    cached.db.save_inventory_counts({"技巧概要·卷3": 70, "糖组": 9})
    cached.db.apply_workshop_inventory({"技巧概要·卷3": -8})
    cached.db.invalidate_workshop_inventory(["糖组"])
    write_snapshot(
        cached.path / "depotmerged.csv",
        110,
        {"技巧概要·卷3": 70, "糖组": 9, "龙门币": 1000},
        True,
    )
    with cached.db._conn() as conn:
        before = list(conn.execute("SELECT * FROM workshop_inventory_pending"))
    for _ in range(2):
        assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
        stock = cached.db.get_inventory_counts()
        assert stock["技巧概要·卷3"] == 62
        assert "糖组" not in stock
        assert stock["龙门币"] == 1000
    with cached.db._conn() as conn:
        assert list(conn.execute("SELECT * FROM workshop_inventory_pending")) == before
    cached.scan.assert_not_called()
    cached.solver._auto_schedule_mastery_after_scan.assert_not_called()


@pytest.mark.parametrize("cache", ["missing", "malformed", "untimed", "future"])
def test_unusable_caches_keep_current_stock_without_fabricating_baselines(
    cached, cache
):
    cached.db.save_inventory_counts({"龙门币": 400})
    if cache == "missing":
        cached.syncer.record_path.unlink()
    elif cache == "malformed":
        cached.syncer.record_path.write_text("broken", encoding="utf-8")
    else:
        cached.payload["_mower_inventory_observed_at"] = (
            0 if cache == "untimed" else 10**20
        )
        cached.syncer.record_path.write_text(
            json.dumps(cached.payload), encoding="utf-8"
        )
    assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
    assert cached.db.get_inventory_counts() == {"龙门币": 400}
    cached.scan.assert_not_called()


def test_latest_explicit_snapshot_count_wins_without_inventing_missing_zero(cached):
    cached.syncer.record_path.unlink()
    write_snapshot(cached.path / "depotresult.csv", 90, {"龙门币": 800, "赤金": 3})
    write_snapshot(cached.path / "depotmerged.csv", 110, {"龙门币": 1000}, True)
    assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
    assert cached.db.get_inventory_counts() == {"龙门币": 1000, "赤金": 3}


@pytest.mark.parametrize("invalidated", [False, True])
def test_unordered_csv_uses_each_items_latest_time_even_across_invalidation(
    cached, monkeypatch, invalidated
):
    cached.syncer.record_path.unlink()
    if invalidated:
        cached.db.save_inventory_counts({"龙门币": 800})
        with monkeypatch.context() as patch:
            patch.setattr(
                cached.db,
                "datetime",
                SimpleNamespace(now=lambda: SimpleNamespace(timestamp=lambda: 200)),
            )
            cached.db.invalidate_workshop_inventory(["龙门币"])
    with (cached.path / "depotmerged.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["Timestamp", "Data", "json"])
        for at, counts in [
            (300, {"龙门币": 600}),
            (250, {"赤金": 5}),
            (100, {"龙门币": 1000, "赤金": 3}),
        ]:
            writer.writerow([at, json.dumps(counts), "{}"])
    assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
    assert cached.db.get_inventory_counts() == {"龙门币": 600, "赤金": 5}
    with cached.db._conn() as conn:
        observed = dict(
            conn.execute(
                "SELECT item_name, observed_at FROM workshop_inventory_updates"
            )
        )
    assert observed == {"龙门币": 300, "赤金": 250}


def test_active_battle_does_not_seed_a_baseline_from_an_old_cache(cached, monkeypatch):
    monkeypatch.setattr(
        cached.db, "battle_inventory_active", SimpleNamespace(is_set=lambda: True)
    )
    assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
    assert cached.db.get_inventory_counts() == {}


def test_confirmed_mastery_payment_is_deducted_once_and_survives_cache_reuse(
    cached, monkeypatch
):
    from arknights_mower.utils import mastery_recommendation

    monkeypatch.setattr(
        mastery_recommendation,
        "get_skill_data",
        lambda: {
            "characters": {
                "char_test": {
                    "skills": [
                        {"levels": [{"materials": [{"id": "3303", "count": 8}]}]}
                    ]
                }
            },
            "items": {"3303": {"name": "技巧概要·卷3"}},
        },
    )
    cached.db.save_inventory_counts({"技巧概要·卷3": 70})
    assert cached.db.apply_mastery_inventory("char_test", 0, 1)
    assert cached.db.apply_mastery_inventory("char_test", 0, 1) is False
    for _ in range(2):
        assert cached.module.BaseSchedulerSolver.仓库扫描(cached.solver) is False
        assert cached.db.get_inventory_counts()["技巧概要·卷3"] == 62


@pytest.mark.parametrize("interruption", ["cancel", "device", "adb"])
def test_sync_cancellation_and_device_failures_do_not_restore_cached_baselines(
    cached, monkeypatch, interruption
):
    kinds = {
        "cancel": cached.module.MowerExit,
        "device": cached.module.DeviceRecoveryError,
        "adb": cached.module.SharedADBError,
    }
    error = kinds[interruption]
    monkeypatch.setattr(
        cached.syncer, "start", MagicMock(side_effect=error("interrupted"))
    )
    with pytest.raises(error):
        cached.module.BaseSchedulerSolver.仓库扫描(cached.solver)
    assert cached.db.get_inventory_counts() == {}
    cached.scan.assert_not_called()
