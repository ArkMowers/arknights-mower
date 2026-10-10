"""MAA cumulative drop receipts update shared inventory without cloud reads."""

import json
import sqlite3
import sys
from threading import Event
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, record  # noqa: E402
from arknights_mower.utils import maa_inventory  # noqa: E402
from arknights_mower.utils.maa_inventory import MaaDropInventory  # noqa: E402
from arknights_mower.utils.maa_stage_inventory import (  # noqa: E402
    load_inventory_snapshot,
    select_stages_by_inventory,
)


@pytest.fixture
def inventory(monkeypatch, tmp_path):
    active = Event()
    monkeypatch.setattr(record, "battle_inventory_active", active)
    monkeypatch.setattr(base_schedule, "battle_inventory_active", active)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda name: tmp_path / "data.db" if name.endswith(".db") else tmp_path,
    )
    return record


def drops(task_id=1, chips=1, lmd=432):
    return {
        "taskchain": "Fight",
        "taskid": task_id,
        "what": "StageDrops",
        "details": {
            "stage": {"stageCode": "PR-C-2", "stageId": "wk_fly_2"},
            "drops": [
                {"itemId": "3212", "itemName": "先锋芯片组", "quantity": 1},
                {"itemId": "4001", "itemName": "龙门币", "quantity": 432},
            ],
            "stats": [
                {
                    "itemId": "3212",
                    "itemName": "先锋芯片组",
                    "quantity": chips,
                    "addQuantity": 1,
                },
                {
                    "itemId": "4001",
                    "itemName": "龙门币",
                    "quantity": lmd,
                    "addQuantity": 432,
                },
            ],
        },
    }


def test_callback_updates_chips_and_lmd_once_without_cloud(inventory, monkeypatch):
    inventory.save_inventory_counts({"先锋芯片组": 9, "龙门币": 1000})
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.maa_callback = None
    monkeypatch.setattr(base_schedule, "stage_drop", {"details": [], "summary": []})
    cloud = MagicMock(side_effect=AssertionError("Unexpected Skland refresh"))
    monkeypatch.setattr(base_schedule, "cultivateDepotSolver", cloud)
    payload = json.dumps(drops()).encode()
    solver.on_maa_callback(20003, payload, None)
    solver.on_maa_callback(20003, payload, None)
    assert inventory.get_inventory_counts() == {"先锋芯片组": 10, "龙门币": 1432}
    stock, _ = load_inventory_snapshot()
    selection = select_stages_by_inventory(
        ["PR-C-2", "1-7"],
        [{"stage": "PR-C-2", "items": [{"item_id": "3212", "limit": 10}]}],
        inventory=stock,
    )
    assert selection["stages"] == ["1-7"]
    cloud.assert_not_called()


def test_cumulative_totals_only_apply_increases_and_tasks_are_independent(inventory):
    inventory.save_inventory_counts({"先锋芯片组": 5, "龙门币": 1000})
    receipts = MaaDropInventory()
    for payload in (
        drops(chips=1),
        drops(chips=1),
        drops(chips=3, lmd=1296),
        drops(chips=2, lmd=864),
        drops(chips=3, lmd=1296),
        drops(task_id=2, chips=1),
    ):
        receipts.record(payload)
    assert inventory.get_inventory_counts() == {"先锋芯片组": 9, "龙门币": 2728}


def test_only_stats_counts_are_applied_not_drops_or_add_quantity(inventory):
    inventory.save_inventory_counts({"先锋芯片组": 0, "龙门币": 0})
    receipts = MaaDropInventory()
    payload = drops(chips=3, lmd=1296)
    payload["details"]["stats"][0]["addQuantity"] = 100
    payload["details"]["stats"].append(dict(payload["details"]["stats"][0]))
    receipts.record(payload)
    payload["details"].pop("stats")
    receipts.record(payload)
    assert inventory.get_inventory_counts() == {"先锋芯片组": 3, "龙门币": 1296}


@pytest.mark.parametrize("task_id", [None, "1", True, -1, 1.5])
def test_invalid_task_ids_do_not_write_inventory(inventory, task_id):
    MaaDropInventory().record(drops(task_id=task_id))
    assert inventory.get_inventory_counts() == {}


def test_malformed_items_and_counts_are_ignored(inventory):
    inventory.save_inventory_counts({"先锋芯片组": 0})
    payload = drops()
    payload["details"]["stats"] = [
        None,
        1,
        {},
        {"itemId": "not-an-item", "quantity": 2},
        *({"itemId": item_id, "quantity": 1} for item_id in (None, [], 3212)),
        *(
            {"itemId": "3212", "quantity": count}
            for count in (None, "2", True, -1, 1.5)
        ),
        {"itemId": "3212", "quantity": 2},
    ]
    MaaDropInventory().record(payload)
    assert inventory.get_inventory_counts() == {"先锋芯片组": 2}


def test_failed_write_does_not_advance_receipt(inventory, monkeypatch):
    inventory.save_inventory_counts({"先锋芯片组": 0, "龙门币": 0})
    receipts = MaaDropInventory()
    apply = inventory.apply_workshop_inventory
    failing = MagicMock(side_effect=sqlite3.OperationalError("write failed"))
    monkeypatch.setattr(maa_inventory, "apply_workshop_inventory", failing)
    with pytest.raises(sqlite3.OperationalError):
        receipts.record(drops())
    monkeypatch.setattr(maa_inventory, "apply_workshop_inventory", apply)
    receipts.record(drops())
    receipts.record(drops())
    assert inventory.get_inventory_counts() == {"先锋芯片组": 1, "龙门币": 432}


def test_callback_contains_inventory_failure_and_retries_receipt(
    inventory, monkeypatch
):
    inventory.save_inventory_counts({"先锋芯片组": 0, "龙门币": 0})
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.maa_callback = None
    monkeypatch.setattr(base_schedule, "stage_drop", {"details": [], "summary": []})
    apply = inventory.apply_workshop_inventory
    monkeypatch.setattr(
        maa_inventory,
        "apply_workshop_inventory",
        MagicMock(side_effect=sqlite3.OperationalError("write failed")),
    )
    payload = json.dumps(drops()).encode()
    solver.on_maa_callback(20003, payload, None)
    monkeypatch.setattr(maa_inventory, "apply_workshop_inventory", apply)
    solver.on_maa_callback(20003, payload, None)
    assert inventory.get_inventory_counts() == {"先锋芯片组": 1, "龙门币": 432}


def test_drop_preserves_unseen_and_invalidated_stock_as_unknown(inventory):
    inventory.save_inventory_counts({"先锋芯片组": 9})
    inventory.invalidate_workshop_inventory(["先锋芯片组"])
    MaaDropInventory().record(drops())
    assert inventory.get_inventory_counts() == {}
    stock, _ = load_inventory_snapshot()
    assert "3212" not in stock


def test_stale_cloud_keeps_callback_counts_for_inventory_selection(inventory):
    old = {"先锋芯片组": 9, "龙门币": 1000}
    inventory.save_inventory_counts(old)
    MaaDropInventory().record(drops())
    inventory.save_inventory_counts(
        old, scanned_counts={}, cloud_counts=old, cloud_at=10_000_000_000
    )
    stock, _ = load_inventory_snapshot()
    assert stock == {"3212": 10, "4001": 1432}


def test_new_assistant_has_independent_task_receipts(inventory):
    inventory.save_inventory_counts({"先锋芯片组": 0, "龙门币": 0})
    MaaDropInventory().record(drops())
    MaaDropInventory().record(drops())
    assert inventory.get_inventory_counts() == {"先锋芯片组": 2, "龙门币": 864}


def test_active_maa_does_not_rebase_ahead_cloud_then_add_same_drop_again(inventory):
    inventory.save_inventory_counts({"先锋芯片组": 10})
    inventory.battle_inventory_active.set()
    receipts = MaaDropInventory()
    receipts.record(drops(chips=1))
    assert inventory.get_inventory_counts()["先锋芯片组"] == 11
    ahead = {"先锋芯片组": 12}
    inventory.save_inventory_counts(
        ahead, scanned_counts={}, cloud_counts=ahead, cloud_at=10_000_000_000
    )
    assert inventory.get_inventory_counts()["先锋芯片组"] == 11
    receipts.record(drops(chips=2))
    assert inventory.get_inventory_counts()["先锋芯片组"] == 12


def fight_params(stage, targets):
    return {
        "stage": stage,
        "times": 999,
        "series": 0,
        "medicine": 3,
        "stone": 999,
        "medicine_expire_days": 4,
        "client_type": "Bilibili",
        "server": "CN",
        "report_to_penguin": True,
        "penguin_id": "penguin-test",
        "report_to_yituliu": True,
        "yituliu_id": "yituliu-test",
        "DrGrandet": False,
        "drops": targets,
    }


def target_solver(monkeypatch, tasks):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.maa_callback = None
    solver.maa_drop_inventory = MaaDropInventory()
    solver.maa_inventory_tasks = tasks
    solver.MAA = MagicMock()
    solver.MAA.set_task_params.return_value = True
    monkeypatch.setattr(base_schedule, "stage_drop", {"details": [], "summary": []})
    return solver


def test_callback_promotes_and_rule_then_stops_only_fight_task(inventory, monkeypatch):
    inventory.save_inventory_counts({"先锋芯片组": 4, "辅助芯片组": 3, "龙门币": 1000})
    rules = [
        {
            "stage": "PR-C-2",
            "operator": "and",
            "items": [
                {"item_id": "3212", "limit": 5},
                {"item_id": "3272", "limit": 5},
            ],
        }
    ]
    params = fight_params("PR-C-2", {})
    solver = target_solver(monkeypatch, {1: (params, rules)})
    solver.on_maa_callback(20003, json.dumps(drops()).encode(), None)
    task_id, updated = solver.MAA.set_task_params.call_args.args
    assert task_id == 1
    assert updated == {**params, "drops": {"3272": 2}}
    complete = drops()
    complete["details"]["stats"].append({"itemId": "3272", "quantity": 2})
    solver.on_maa_callback(20003, json.dumps(complete).encode(), None)
    stopped = solver.MAA.set_task_params.call_args.args[1]
    assert stopped == {
        **params,
        "times": 0,
        "medicine": 0,
        "stone": 0,
        "expiring_medicine": 0,
        "drops": {},
    }
    solver.MAA.stop.assert_not_called()
    assert solver.maa_inventory_tasks[1][0] == stopped


def test_preceding_stage_drops_refresh_queued_stage_targets(inventory, monkeypatch):
    inventory.save_inventory_counts({"先锋芯片组": 4, "龙门币": 1000})
    rules = [
        {"stage": "PR-C-2", "items": [{"item_id": "3212", "limit": 8}]},
        {"stage": "CE-6", "items": [{"item_id": "4001", "limit": 2000}]},
    ]
    primary = fight_params("PR-C-2", {"3212": 4})
    queued = fight_params("CE-6", {"4001": 1000})
    solver = target_solver(monkeypatch, {1: (primary, rules), 2: (queued, rules)})
    solver.on_maa_callback(20003, json.dumps(drops()).encode(), None)
    solver.MAA.set_task_params.assert_called_once_with(
        2, {**queued, "drops": {"4001": 568}}
    )
    solver.MAA.set_task_params.reset_mock()
    solver.on_maa_callback(20003, json.dumps(drops(chips=2, lmd=1000)).encode(), None)
    task_id, stopped = solver.MAA.set_task_params.call_args.args
    assert task_id == 2
    assert stopped["times"] == 0
    assert stopped["series"] == 0
    assert solver.maa_inventory_tasks[1][0] == primary
    solver.on_maa_callback(
        10002, json.dumps({"taskchain": "Fight", "taskid": 1}).encode(), None
    )
    assert 1 not in solver.maa_inventory_tasks
    assert 2 in solver.maa_inventory_tasks


def test_task_start_refreshes_targets_and_retries_rejected_updates(
    inventory, monkeypatch
):
    inventory.save_inventory_counts({"先锋芯片组": 3})
    params = fight_params("PR-C-2", {"3212": 5})
    rules = [{"stage": "PR-C-2", "items": [{"item_id": "3212", "limit": 5}]}]
    solver = target_solver(monkeypatch, {1: (params, rules)})
    solver.MAA.set_task_params.side_effect = [False, True]
    payload = json.dumps({"taskchain": "Fight", "taskid": 1}).encode()
    solver.on_maa_callback(10001, payload, None)
    assert solver.maa_inventory_tasks[1][0] == params
    solver.on_maa_callback(10001, payload, None)
    assert solver.maa_inventory_tasks[1][0] == {**params, "drops": {"3212": 2}}
    assert solver.MAA.set_task_params.call_count == 2


def test_all_tasks_complete_releases_cloud_inventory_guard(inventory, monkeypatch):
    solver = target_solver(monkeypatch, {})
    inventory.battle_inventory_active.set()
    solver.on_maa_callback(3, b"{}", None)
    assert not inventory.battle_inventory_active.is_set()
