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


@pytest.mark.parametrize("name", ["龙门币", "应急理智顶液"])
@pytest.mark.parametrize("later_source", ["scan", "cloud"])
@pytest.mark.parametrize("commit_order", ["scan_first", "cloud_first"])
def test_separate_scans_and_syncs_use_the_later_observation(
    inventory, name, later_source, commit_order
):
    if later_source == "scan":
        scan, scan_start, scan_end = {name: 105}, 800, 810
        cloud, cloud_start, cloud_end = {name: 100}, 100, 110
    else:
        scan, scan_start, scan_end = {name: 100}, 100, 110
        cloud, cloud_start, cloud_end = {name: 105}, 800, 810

    def save_scan():
        inventory.save_inventory_counts(
            scan,
            scanned_counts=scan,
            scanned_at=scan_start,
            scanned_finished_at=scan_end,
            cloud_counts=cloud if commit_order == "cloud_first" else None,
            cloud_at=cloud_start,
            cloud_finished_at=cloud_end,
        )

    def save_cloud():
        inventory.save_inventory_counts(
            cloud,
            scanned_counts={},
            cloud_counts=cloud,
            cloud_at=cloud_start,
            cloud_finished_at=cloud_end,
            force_cloud=True,
        )

    for operation in (
        (save_scan, save_cloud)
        if commit_order == "scan_first"
        else (save_cloud, save_scan)
    ):
        operation()
    assert inventory.get_inventory_counts()[name] == 105


@pytest.mark.parametrize("name", ["龙门币", "应急理智顶液"])
def test_sync_soon_after_scan_preserves_scan_during_expected_cloud_delay(
    inventory, name
):
    scan = {name: 100}
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, scanned_finished_at=110
    )
    inventory.save_inventory_counts(
        {name: 105},
        scanned_counts={},
        cloud_counts={name: 105},
        cloud_at=350,
        cloud_finished_at=360,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()[name] == 100


@pytest.mark.parametrize("gap,expected", [(300, 100), (301, 105)])
def test_later_sync_prefers_cloud_only_after_the_five_minute_delay(
    inventory, gap, expected
):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, scanned_finished_at=110
    )
    inventory.save_inventory_counts(
        {"龙门币": 105},
        scanned_counts={},
        cloud_counts={"龙门币": 105},
        cloud_at=110 + gap,
        cloud_finished_at=111 + gap,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == expected


@pytest.mark.parametrize(
    "name,scanned,cloud,expected",
    [
        ("龙门币", 3_000_000, 2_000_000, 2_000_000),
        ("龙门币", 2_999_999, 2_000_000, 2_999_999),
        ("龙门币", 2_000_000, 3_000_000, 2_000_000),
        ("龙门币", 10_000_000, 9_000_000, 9_000_000),
        ("龙门币", 900_000, 400_000, 400_000),
        ("赤金", 3_000_000, 2_000_000, 3_000_000),
    ],
)
@pytest.mark.parametrize("cloud_start", [105, 350])
def test_large_lmd_increase_has_a_separate_comparison_threshold(
    inventory, name, scanned, cloud, expected, cloud_start
):
    scan = {name: scanned}
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, scanned_finished_at=110
    )
    inventory.save_inventory_counts(
        {name: cloud},
        scanned_counts={},
        cloud_counts={name: cloud},
        cloud_at=cloud_start,
        cloud_finished_at=cloud_start + 10,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()[name] == expected


def test_large_lmd_increase_after_a_recent_sync_uses_cloud(inventory):
    cloud = {"龙门币": 2_000_000}
    inventory.save_inventory_counts(
        cloud,
        scanned_counts={},
        cloud_counts=cloud,
        cloud_at=100,
        cloud_finished_at=110,
    )
    scan = {"龙门币": 3_000_000}
    inventory.save_inventory_counts(
        scan,
        scanned_counts=scan,
        scanned_at=120,
        scanned_finished_at=130,
        cloud_counts=cloud,
        cloud_at=100,
        cloud_finished_at=110,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 2_000_000


def test_late_scan_wins_even_with_a_large_difference(inventory):
    cloud = {"龙门币": 2_000_000}
    inventory.save_inventory_counts(
        cloud,
        scanned_counts={},
        cloud_counts=cloud,
        cloud_at=100,
        cloud_finished_at=110,
    )
    scan = {"龙门币": 3_000_000}
    inventory.save_inventory_counts(
        scan,
        scanned_counts=scan,
        scanned_at=411,
        scanned_finished_at=420,
        cloud_counts=cloud,
        cloud_at=100,
        cloud_finished_at=110,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 3_000_000


@pytest.mark.parametrize("gap,expected", [(300, 2_000_000), (301, 3_000_000)])
def test_scan_after_sync_uses_the_five_minute_boundary(inventory, gap, expected):
    cloud = {"龙门币": 2_000_000}
    inventory.save_inventory_counts(
        cloud,
        scanned_counts={},
        cloud_counts=cloud,
        cloud_at=100,
        cloud_finished_at=110,
    )
    scan = {"龙门币": 3_000_000}
    inventory.save_inventory_counts(
        scan,
        scanned_counts=scan,
        scanned_at=110 + gap,
        scanned_finished_at=111 + gap,
        cloud_counts=cloud,
        cloud_at=100,
        cloud_finished_at=110,
    )
    assert inventory.get_inventory_counts()["龙门币"] == expected


@pytest.mark.parametrize("name", ["龙门币", "应急理智顶液"])
@pytest.mark.parametrize(
    "scan_count,cloud_count,expected", [(110, 100, 110), (200, 100, 100)]
)
@pytest.mark.parametrize("commit_order", ["scan_first", "cloud_first"])
def test_overlapping_scan_and_sync_keep_the_existing_difference_rule(
    inventory, name, scan_count, cloud_count, expected, commit_order
):
    scan, cloud = {name: scan_count}, {name: cloud_count}

    def save_scan():
        inventory.save_inventory_counts(
            scan,
            scanned_counts=scan,
            scanned_at=100,
            scanned_finished_at=130,
            cloud_counts=cloud if commit_order == "cloud_first" else None,
            cloud_at=110,
            cloud_finished_at=140,
        )

    def save_cloud():
        inventory.save_inventory_counts(
            cloud,
            scanned_counts={},
            cloud_counts=cloud,
            cloud_at=110,
            cloud_finished_at=140,
            force_cloud=True,
        )

    for operation in (
        (save_scan, save_cloud)
        if commit_order == "scan_first"
        else (save_cloud, save_scan)
    ):
        operation()
    assert inventory.get_inventory_counts()[name] == expected


def test_materials_keep_the_previous_nearby_difference_rule(inventory):
    scan = {"固源岩组": 100}
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, scanned_finished_at=110
    )
    inventory.save_inventory_counts(
        {"固源岩组": 105},
        scanned_counts={},
        cloud_counts={"固源岩组": 105},
        cloud_at=120,
        cloud_finished_at=130,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["固源岩组"] == 100


def test_scan_without_a_known_finish_time_uses_the_previous_comparison(inventory):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(scan, scanned_counts=scan, scanned_at=100)
    inventory.save_inventory_counts(
        {"龙门币": 105},
        scanned_counts={},
        cloud_counts={"龙门币": 105},
        cloud_at=800,
        cloud_finished_at=810,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 100


def test_source_intervals_survive_database_reopen(inventory, monkeypatch):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, scanned_finished_at=110
    )
    monkeypatch.setattr(inventory, "_tables_created", False)
    inventory.save_inventory_counts(
        {"龙门币": 105},
        scanned_counts={},
        cloud_counts={"龙门币": 105},
        cloud_at=800,
        cloud_finished_at=810,
        force_cloud=True,
    )
    assert inventory.get_inventory_counts()["龙门币"] == 105


@pytest.mark.parametrize("reported,expected", [(True, 0), (False, 100)])
def test_only_an_explicit_cloud_zero_updates_a_scan_only_item(
    inventory, reported, expected
):
    scan = {"龙门币": 100}
    inventory.save_inventory_counts(
        scan, scanned_counts=scan, scanned_at=100, scanned_finished_at=110
    )
    cloud = {"龙门币": 0} if reported else {}
    inventory.save_inventory_counts(
        cloud,
        scanned_counts={},
        cloud_counts=cloud,
        cloud_explicit_names=set(cloud),
        cloud_at=800,
        cloud_finished_at=810,
        force_cloud=True,
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
        scanned_observations={"龙门币": (100, 199, None)},
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
