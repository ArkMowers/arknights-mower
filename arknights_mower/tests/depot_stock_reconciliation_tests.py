"""Reconcile retained scan observations without reviving orphaned inventory rows."""

import csv
import json
from unittest.mock import patch

import pytest

from arknights_mower.data import key_mapping
from arknights_mower.solvers import record
from arknights_mower.utils import depot


@pytest.fixture
def stock(tmp_path, monkeypatch, income_db):
    monkeypatch.setattr(
        depot, "get_path", lambda key: tmp_path / key.rsplit("/", 1)[-1]
    )
    monkeypatch.setattr(depot, "_快照行缓存", None)
    (tmp_path / "cultivate.json").write_text(
        json.dumps({"data": {"items": []}}), encoding="utf-8"
    )
    return tmp_path


def scans(stock, rows):
    with (stock / "depotresult.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Data", "json"])
        for at, counts in rows:
            writer.writerow([at, json.dumps(counts), "{}"])


def view_counts(categories):
    return {
        name: entry["number"]
        for category in categories.values()
        for name, entry in category.items()
        if name not in depot.抽数档位 and name != "全部经验（计算）"
    }


@pytest.mark.parametrize(
    "name,count",
    [
        ("可露希尔精选券I", 999999),
        ("应急理智小样", 999999),
        ("高级资深干员特训装置", 40000),
        ("应急救援包", 999999),
    ],
)
def test_orphaned_rows_do_not_reappear_in_current_export_or_history(stock, name, count):
    record.save_inventory_counts({name: count, "至纯源石": 12})
    scans(stock, [(100, {"至纯源石": 12})])

    for _ in range(2):
        categories, exported, _ = depot.读取仓库(记录快照时刻=100)
        assert name not in view_counts(categories)
        assert key_mapping[name][0] not in json.loads(exported)
        assert name not in record.get_inventory_counts()
        snapshot = depot.读取仓库历史()[0]
        assert snapshot["complete"] is True
        assert snapshot["items"].get(name, 0) == 0
        assert snapshot["items"]["至纯源石"] == 12


@pytest.mark.parametrize("order", [(100, 200), (200, 100)])
def test_partial_scans_recover_legacy_counts_with_their_actual_observation_time(
    stock, order
):
    record.save_inventory_counts({"合成玉": 999999, "至纯源石": 12})
    rows = {100: {"合成玉": 1200}, 200: {"至纯源石": 12}}
    scans(stock, [(at, rows[at]) for at in order])

    categories, exported, _ = depot.读取仓库(记录快照时刻=200)

    assert categories["A常用"]["合成玉"]["number"] == 1200
    assert json.loads(exported)[key_mapping["合成玉"][0]] == 1200
    assert record.get_inventory_counts()["合成玉"] == 1200
    assert depot.读取仓库历史()[-1]["items"]["合成玉"] == 1200
    with record._conn() as conn:
        times = dict(conn.execute("SELECT * FROM workshop_inventory_updates"))
    assert times["合成玉"] == 100
    assert times["至纯源石"] == 200


def test_later_confirmed_zero_survives_reopening_and_partial_scan(stock):
    scans(stock, [(100, {"应急理智小样": 3}), (200, {"至纯源石": 12})])
    depot.读取仓库()
    record.save_inventory_counts(
        {"应急理智小样": 0},
        scanned_counts={"应急理智小样": 0},
        scanned_at=150,
    )

    for _ in range(2):
        categories, exported, _ = depot.读取仓库(记录快照时刻=200)
        assert view_counts(categories)["应急理智小样"] == 0
        assert json.loads(exported)[key_mapping["应急理智小样"][0]] == 0
        assert record.get_inventory_counts()["应急理智小样"] == 0
        assert depot.读取仓库历史()[-1]["items"].get("应急理智小样", 0) == 0


def test_partial_scan_keeps_newer_local_change_and_pending_baseline(stock):
    scans(stock, [(100, {"合成玉": 1200}), (200, {"至纯源石": 12})])
    depot.读取仓库()
    with patch.object(record, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 150
        record.apply_workshop_inventory({"合成玉": -600})

    categories, _, _ = depot.读取仓库(记录快照时刻=200)

    assert categories["A常用"]["合成玉"]["number"] == 600
    assert record.get_inventory_counts()["合成玉"] == 600
    assert depot.读取仓库历史()[-1]["items"]["合成玉"] == 600
    with record._conn() as conn:
        assert conn.execute(
            "SELECT baseline FROM workshop_inventory_pending WHERE item_name = ?",
            ("合成玉",),
        ).fetchone() == (1200,)
        assert conn.execute(
            "SELECT observed_at FROM workshop_inventory_updates WHERE item_name = ?",
            ("合成玉",),
        ).fetchone() == (150,)


def test_cloud_competes_with_each_items_scan_time_not_the_latest_partial_scan(stock):
    scans(stock, [(100, {"合成玉": 1200}), (200, {"至纯源石": 12})])
    (stock / "cultivate.json").write_text(
        json.dumps(
            {
                "_mower_inventory_observed_at": 150,
                "data": {"items": [{"id": key_mapping["合成玉"][0], "count": 600}]},
            }
        ),
        encoding="utf-8",
    )

    categories, _, _ = depot.读取仓库()

    assert categories["A常用"]["合成玉"]["number"] == 600
    assert record.get_inventory_counts()["合成玉"] == 600


@pytest.mark.parametrize("content", ["Timestamp,Data,json\n", "broken csv\n"])
def test_unavailable_scan_history_does_not_delete_legacy_database_rows(stock, content):
    record.save_inventory_counts({"应急理智小样": 3})
    (stock / "depotresult.csv").write_text(content, encoding="utf-8")

    depot.读取仓库()

    assert record.get_inventory_counts()["应急理智小样"] == 3


@pytest.mark.parametrize("value", [-1, "999999", True])
def test_malformed_scan_counts_cannot_supply_a_legacy_source(stock, value):
    record.save_inventory_counts({"应急理智小样": 999999})
    scans(stock, [(100, {"至纯源石": 12, "应急理智小样": value})])

    categories, _, _ = depot.读取仓库()

    assert "应急理智小样" not in view_counts(categories)
    assert "应急理智小样" not in record.get_inventory_counts()


def test_active_battle_defers_removal_of_orphaned_rows(stock, monkeypatch):
    from threading import Event

    active = Event()
    active.set()
    monkeypatch.setattr(record, "battle_inventory_active", active)
    record.save_inventory_counts({"应急理智小样": 999999})
    scans(stock, [(100, {"至纯源石": 12})])

    depot.读取仓库()
    assert record.get_inventory_counts()["应急理智小样"] == 999999

    active.clear()
    depot.读取仓库()
    assert "应急理智小样" not in record.get_inventory_counts()
