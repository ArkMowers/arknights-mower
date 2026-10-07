"""Native settlements own one confirmed inventory delta per battle batch."""

from datetime import datetime
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import operation, record
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.recognize import Scene


@pytest.fixture
def native(monkeypatch, tmp_path):
    active = Event()
    monkeypatch.setattr(record, "battle_inventory_active", active)
    monkeypatch.setattr(operation, "battle_inventory_active", active)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda name: tmp_path / "data.db" if name.endswith(".db") else tmp_path,
    )
    conf = config.Conf()
    conf.maa_stage_inventory_enable = True
    conf.maa_stage_limit_rules = [
        {"stage": "AP-5", "items": [{"item_id": "4006", "limit": 20}]}
    ]
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(operation, "record_operation_batch", MagicMock())
    reader = MagicMock(return_value={"采购凭证": 3})
    monkeypatch.setattr(operation, "read_operation_drops", reader)
    solver = object.__new__(operation.OperationSolver)
    solver.stage_id = "AP-5"
    solver.recog = SimpleNamespace(img=object())
    solver.sleep = MagicMock()
    solver.scene = MagicMock(return_value=Scene.OPERATOR_FINISH)
    solver.tap = MagicMock()
    solver.inventory_unconfirmed = False
    solver.remaining_runs = 12
    solver.simulated_current_ap = 720
    solver.ap_cost = 30
    solver._prepare_batch_state()
    return SimpleNamespace(
        solver=solver, reader=reader, active=active, record=record, conf=conf
    )


def test_stable_batch_total_is_added_once_without_repeat_multiplier(native):
    record.save_inventory_counts({"采购凭证": 10})
    native.solver.current_batch_repeat_count = 6
    native.solver._record_batch_drops()
    native.solver._record_batch_drops()
    assert record.get_inventory_counts() == {"采购凭证": 13}
    assert native.reader.call_count == 2
    assert native.solver.current_batch_inventory_recorded


def test_identical_drops_in_distinct_batches_are_both_counted(native):
    record.save_inventory_counts({"采购凭证": 10})
    native.solver._record_batch_drops()
    native.solver._prepare_batch_state()
    native.solver._record_batch_drops()
    assert record.get_inventory_counts() == {"采购凭证": 16}


@pytest.mark.parametrize(
    "observations", [[None, None, None], [{"采购凭证": 3}, {"采购凭证": 8}, None]]
)
def test_uncertain_settlement_preserves_stock_and_stops_dispatch(native, observations):
    record.save_inventory_counts({"采购凭证": 10})
    native.reader.side_effect = observations
    native.solver._record_batch_drops()
    assert record.get_inventory_counts() == {"采购凭证": 10}
    assert native.solver.inventory_unconfirmed
    assert not native.solver.current_batch_inventory_recorded


def test_unknown_inventory_never_becomes_the_drop_quantity(native):
    native.solver._record_batch_drops()
    assert record.get_inventory_counts() == {}


def test_settlement_animation_can_settle_within_bounded_observations(native):
    record.save_inventory_counts({"采购凭证": 10})
    native.reader.side_effect = [None, {"采购凭证": 3}, {"采购凭证": 3}]
    native.solver._record_batch_drops()
    assert record.get_inventory_counts() == {"采购凭证": 13}
    assert native.reader.call_count == 3
    assert not native.solver.inventory_unconfirmed


def fake_batch(solver):
    assert operation.battle_inventory_active.is_set()
    solver.current_batch_repeat_count = solver.desired_repeat_times
    solver.current_batch_started_at = datetime.now()
    solver._record_batch_drops()
    solver._finish_batch(True)


def run_native(native, monkeypatch):
    battle = MagicMock(side_effect=lambda: fake_batch(native.solver))
    monkeypatch.setattr(operation.SceneGraphSolver, "run", battle)
    result = native.solver.run(
        stage_id="AP-5",
        target_total_runs=12,
        simulated_current_ap=720,
        ap_cost=30,
        stage_duration_seconds=30,
    )
    return result, battle


def test_cap_ends_current_stage_after_one_confirmed_batch(native, monkeypatch):
    record.save_inventory_counts({"采购凭证": 19})
    result, battle = run_native(native, monkeypatch)
    assert record.get_inventory_counts() == {"采购凭证": 22}
    assert result["stopped_by_inventory"]
    assert result["executed_runs"] == 6
    assert result["remaining_runs"] == 6
    assert result["simulated_current_ap"] == 540
    battle.assert_called_once()
    assert not native.active.is_set()


def test_already_capped_stage_never_starts_a_batch(native, monkeypatch):
    record.save_inventory_counts({"采购凭证": 20})
    result, battle = run_native(native, monkeypatch)
    assert result["stopped_by_inventory"]
    assert result["executed_runs"] == 0
    battle.assert_not_called()
    assert not native.active.is_set()


def test_disabled_limits_still_record_each_batch(native, monkeypatch):
    native.conf.maa_stage_inventory_enable = False
    record.save_inventory_counts({"采购凭证": 20})
    result, battle = run_native(native, monkeypatch)
    assert result["executed_runs"] == 12
    assert battle.call_count == 2
    assert record.get_inventory_counts() == {"采购凭证": 26}
    assert not result["stopped_by_inventory"]


def test_unknown_settlement_stops_further_batches(native, monkeypatch):
    native.reader.return_value = None
    result, battle = run_native(native, monkeypatch)
    assert result["inventory_unconfirmed"]
    assert result["executed_runs"] == 6
    battle.assert_called_once()
    assert not native.active.is_set()


def test_leftover_settlement_without_owned_battle_is_not_recorded(native):
    record.save_inventory_counts({"采购凭证": 10})
    assert native.solver.transition() is None
    native.reader.assert_not_called()
    assert not native.solver.current_batch_success
    assert record.get_inventory_counts() == {"采购凭证": 10}


@pytest.mark.parametrize("failure", [MowerExit, DeviceRecoveryError])
def test_cancellation_propagates_and_releases_cloud_hold(native, monkeypatch, failure):
    native.solver.sleep.side_effect = failure()
    with pytest.raises(failure):
        run_native(native, monkeypatch)
    assert not native.active.is_set()
    assert not native.solver.current_batch_inventory_recorded


def test_failed_transaction_does_not_mark_receipt_complete(native, monkeypatch):
    record.save_inventory_counts({"采购凭证": 10})
    monkeypatch.setattr(
        operation,
        "apply_workshop_inventory",
        MagicMock(side_effect=RuntimeError("db unavailable")),
    )
    native.solver._record_batch_drops()
    assert not native.solver.current_batch_inventory_recorded
    assert native.solver.inventory_unconfirmed
    assert record.get_inventory_counts() == {"采购凭证": 10}


def test_cloud_snapshot_cannot_lead_pending_native_receipt(native, monkeypatch):
    record.save_inventory_counts({"采购凭证": 19})

    def read_with_cloud(*_):
        now = datetime.now().timestamp()
        record.save_inventory_counts(
            {"采购凭证": 22},
            scanned_counts={},
            cloud_counts={"采购凭证": 22},
            cloud_at=now,
        )
        assert record.get_inventory_counts() == {"采购凭证": 19}
        return {"采购凭证": 3}

    native.reader.side_effect = read_with_cloud
    result, _ = run_native(native, monkeypatch)
    assert result["stopped_by_inventory"]
    assert record.get_inventory_counts() == {"采购凭证": 22}
