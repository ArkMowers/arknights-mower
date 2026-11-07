"""Reconcile independently observed inventory without losing newer local changes."""

from threading import Event
from unittest.mock import patch

import pytest

from arknights_mower.solvers import record


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(record, "battle_inventory_active", Event())
    monkeypatch.setattr(record, "workshop_inventory_changed", Event())
    monkeypatch.setattr(
        record,
        "get_path",
        lambda name: tmp_path / "data.db" if name.endswith(".db") else tmp_path,
    )
    return record


@pytest.mark.parametrize(
    ("scanned", "cloud", "expected"),
    [
        (110, 100, 110),
        (1, 0, 1),
        (10, 0, 0),
        (19, 10, 19),
        (20, 10, 10),
        (200, 100, 100),
        (100, 200, 200),
    ],
)
@pytest.mark.parametrize("order", ["scan_first", "cloud_first"])
def test_nearby_observations_are_compared_regardless_of_completion_order(
    inventory, scanned, cloud, expected, order
):
    scan = {"龙门币": scanned}
    sync = {"龙门币": cloud}
    if order == "scan_first":
        inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=201.9)
        inventory.save_inventory_counts(
            sync, scanned_counts={}, cloud_counts=sync, cloud_at=201.2, force_cloud=True
        )
    else:
        inventory.save_inventory_counts(
            sync, scanned_counts={}, cloud_counts=sync, cloud_at=201.2, force_cloud=True
        )
        inventory.save_inventory_counts(
            scan,
            scanned_counts=scan,
            scanned_at=201.9,
            cloud_counts=sync,
            cloud_at=201.2,
        )
    assert inventory.get_inventory_counts()["龙门币"] == expected


def test_first_scan_is_not_overwritten_by_an_older_delayed_sync(inventory):
    scan = {"龙门币": 123}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=201.9)
    inventory.save_inventory_counts(
        {"龙门币": 120},
        scanned_counts={},
        cloud_counts={"龙门币": 120},
        cloud_at=200.2,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 123


def test_old_scan_does_not_override_a_new_cloud_sync(inventory):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=100)
    inventory.save_inventory_counts(
        {"龙门币": 103},
        scanned_counts={},
        cloud_counts={"龙门币": 103},
        cloud_at=1901,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 103


def test_scan_and_cloud_are_compared_at_the_30_minute_boundary(inventory):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=100)
    inventory.save_inventory_counts(
        {"龙门币": 103},
        scanned_counts={},
        cloud_counts={"龙门币": 103},
        cloud_at=1900,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 100


def test_old_cloud_response_cannot_recompare_against_a_newer_scan(inventory):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=201.9)
    inventory.save_inventory_counts(
        scan, scanned_counts={}, cloud_counts=scan, cloud_at=201.2, force_cloud=True
    )
    inventory.save_inventory_counts(
        {"龙门币": 0},
        scanned_counts={},
        cloud_counts={"龙门币": 0},
        cloud_at=201.1,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 100


def test_battle_settlement_does_not_apply_cached_scan_before_drop_receipts(inventory):
    inventory.save_inventory_counts({"龙门币": 100})
    inventory.battle_inventory_active.set()
    inventory.save_inventory_counts(
        {"龙门币": 110},
        scanned_counts={"龙门币": 110},
        scanned_at=100,
        cloud_counts={"龙门币": 110},
        cloud_at=101,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 100
    with patch.object(inventory, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 102
        inventory.apply_workshop_inventory({"龙门币": 10})
    inventory.battle_inventory_active.clear()
    assert inventory.get_inventory_counts()["龙门币"] == 110


def test_completion_invalidates_a_cached_scan_without_a_current_baseline(inventory):
    inventory.battle_inventory_active.set()
    inventory.save_inventory_counts(
        {"龙门币": 100},
        scanned_counts={"龙门币": 100},
        scanned_at=100,
        cloud_counts={"龙门币": 0},
        cloud_at=101,
    )
    assert "龙门币" not in inventory.get_inventory_counts()
    inventory.battle_inventory_active.clear()
    inventory.save_inventory_counts(
        {},
        scanned_counts={"碳": 1},
        scanned_at=150,
        cloud_counts={},
        cloud_at=151,
        invalidate_missing=True,
        invalidation_scope={"龙门币"},
    )
    inventory.save_inventory_counts(
        {"龙门币": 70},
        scanned_counts={},
        cloud_counts={"龙门币": 70},
        cloud_at=160,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 70


def test_selected_older_partial_scan_reports_its_actual_observation_time(
    inventory, monkeypatch
):
    from arknights_mower.utils import workshop_limits

    inventory.save_inventory_counts(
        {"龙门币": 100}, scanned_counts={"龙门币": 100}, scanned_at=100
    )
    observed = []
    monkeypatch.setattr(
        workshop_limits, "clear_workshop_recipe_rejections", observed.append
    )
    inventory.workshop_inventory_changed.clear()
    inventory.save_inventory_counts(
        {"龙门币": 110},
        scanned_counts={},
        scanned_observations={"龙门币": (100, 199)},
        cloud_counts={"龙门币": 110},
        cloud_at=201,
    )
    assert observed[-1]["龙门币"] == 199
    assert inventory.workshop_inventory_changed.is_set()


def test_unreported_cloud_item_is_not_a_zero_for_comparison(inventory):
    scan = {"固源岩": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=200)
    inventory.save_inventory_counts(
        {"固源岩": 0},
        scanned_counts={},
        cloud_counts={"固源岩": 0},
        cloud_explicit_names=set(),
        cloud_at=201,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["固源岩"] == 100


def test_cloud_selected_for_large_discrepancy_cannot_overwrite_later_crafting(
    inventory,
):
    scan = {"龙门币": 200}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=201)
    with patch.object(inventory, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 202
        inventory.apply_workshop_inventory({"龙门币": -5})
    inventory.save_inventory_counts(
        {"龙门币": 100},
        scanned_counts={},
        cloud_counts={"龙门币": 100},
        cloud_at=200,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 195


def test_scan_before_local_change_is_not_reused_after_cloud_calibration(inventory):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=100)
    with patch.object(inventory, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 101
        inventory.apply_workshop_inventory({"龙门币": -10})
    sync = {"龙门币": 80}
    inventory.save_inventory_counts(
        sync, scanned_counts={}, cloud_counts=sync, cloud_at=102, force_cloud=True
    )
    # Reading the warehouse again replays the same scan and cloud cache.
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, cloud_counts=sync, cloud_at=102
    )
    assert inventory.get_inventory_counts()["龙门币"] == 80


def test_cached_read_does_not_replay_a_scan_from_before_invalidation(inventory):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=100)
    with patch.object(inventory, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 101
        inventory.invalidate_workshop_inventory(["龙门币"])
    sync = {"龙门币": 90}
    inventory.save_inventory_counts(
        sync, scanned_counts={}, cloud_counts=sync, cloud_at=102, force_cloud=True
    )
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, cloud_counts=sync, cloud_at=102
    )
    assert inventory.get_inventory_counts()["龙门币"] == 90


def test_sync_does_not_reinstate_an_old_scan_it_just_invalidated(inventory):
    scan = {"龙门币": 999}
    inventory.save_inventory_counts(scan)
    inventory.save_inventory_counts(
        {},
        scanned_counts=scan,
        scanned_at=100,
        cloud_counts={},
        cloud_at=200,
        invalidate_missing=True,
        invalidation_scope={"龙门币"},
    )
    assert "龙门币" not in inventory.get_inventory_counts()


def test_goal_completion_invalidates_an_old_scan_even_without_an_existing_baseline(
    inventory,
):
    inventory.save_inventory_counts(
        {},
        scanned_counts={"龙门币": 999},
        scanned_at=100,
        cloud_counts={},
        cloud_at=200,
        invalidate_missing=True,
        invalidation_scope={"龙门币"},
    )
    assert "龙门币" not in inventory.get_inventory_counts()


def test_scan_after_sync_request_survives_goal_completion_invalidation(inventory):
    inventory.save_inventory_counts({"龙门币": 999})
    inventory.save_inventory_counts(
        {},
        scanned_counts={"龙门币": 1100},
        scanned_at=201,
        cloud_counts={},
        cloud_at=200,
        invalidate_missing=True,
        invalidation_scope={"龙门币"},
    )
    assert inventory.get_inventory_counts()["龙门币"] == 1100
