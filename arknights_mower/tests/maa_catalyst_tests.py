"""Custom-only catalyst admission, payment receipts and stale-cloud recovery."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import growth as runner
from arknights_mower.solvers import record
from arknights_mower.utils import config
from arknights_mower.utils import maa_catalyst as catalyst
from arknights_mower.utils.growth_execution import reconcile_snapshot

pytestmark = pytest.mark.usefixtures("income_db")


@pytest.fixture
def stock(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(maa_growth_enable=True))
    monkeypatch.setattr(config, "stop_mower", config.Event())
    monkeypatch.setattr(config, "stop_maa", config.Event())
    record.battle_inventory_active.clear()
    record.save_inventory_counts({"芯片助剂": 3, "采购凭证": 180})


def test_custom_purchase_stops_at_one_item_without_manufacturing():
    tasks = catalyst.custom_tasks()
    assert tasks[catalyst.ENTRY]["text"] == ["凭证交易所"]
    assert tasks["MowerGrowthCatalyst@Quantity"]["text"] == ["1"]
    assert tasks["MowerGrowthCatalyst@Quantity"]["fullMatch"] is True
    assert tasks["MowerGrowthCatalyst@Purchase"]["next"] == [catalyst.RECEIPT]
    assert tasks[catalyst.RECEIPT]["next"] == []
    assert tasks["MowerGrowthCatalyst@Swipe"]["maxTimes"] == 5
    for task in tasks.values():
        assert set(task.get("next", []) + task.get("exceededNext", [])) <= tasks.keys()
    serialized = json.dumps(tasks)
    assert "ChooseMax" not in serialized
    assert "OperProgress" not in serialized
    assert "Mfg" not in serialized


@pytest.mark.parametrize("count", [2, 5, 99])
def test_batch_task_sets_and_verifies_exact_quantity(count):
    tasks = catalyst.custom_tasks(count)
    prefix = catalyst.entry_for_count(count).removesuffix("Begin")
    assert tasks[prefix + "Quantity"]["text"] == [str(count)]
    increases = [task for name, task in tasks.items() if "@Increase" in name]
    assert len(increases) == count - 1
    assert tasks[prefix + "Find"]["next"] == [prefix + "Increase1"]
    assert tasks[prefix + f"Increase{count - 1}"]["next"] == [prefix + "Quantity"]
    assert tasks[prefix + "Purchase"]["next"] == [catalyst.receipt_for_count(count)]
    for task in tasks.values():
        assert set(task.get("next", []) + task.get("exceededNext", [])) <= tasks.keys()


def test_quantity_scope_loads_only_current_tasks_and_restores_after_error(tmp_path):
    from arknights_mower.utils import growth_execution as execution

    path = tmp_path / "resource/tasks/tasks.json"
    execution.prepare_guard(tmp_path, split=True)
    with pytest.raises(RuntimeError):
        with catalyst.task_quantity(5):
            execution.prepare_guard(tmp_path, split=True)
            tasks = json.loads(path.read_text())
            assert catalyst.entry_for_count(5) in tasks
            assert catalyst.ENTRY not in tasks
            raise RuntimeError("test scope")
    assert catalyst.ENTRY in catalyst.custom_tasks()


def test_purchase_receipt_charges_once_and_failure_needs_new_observation(stock):
    token = catalyst.begin_purchase("test")
    assert catalyst.finish_purchase(token, success=True)
    assert not catalyst.finish_purchase(token, success=True)
    assert record.get_inventory_counts() == {"芯片助剂": 4, "采购凭证": 90}
    token = catalyst.begin_purchase("test")
    assert catalyst.finish_purchase(token)
    assert record.get_inventory_counts() == {}
    assert catalyst.begin_purchase("test") is None
    assert catalyst.begin_purchase("test") is None
    record.save_inventory_counts({"芯片助剂": 4, "采购凭证": 90})
    assert catalyst.begin_purchase("test") is not None


def test_restart_does_not_replay_a_potentially_paid_purchase(stock):
    assert catalyst.begin_purchase("test")
    assert catalyst.begin_purchase("test") is None
    assert record.get_inventory_counts() == {}
    assert catalyst.begin_purchase("test") is None


def test_startup_recovers_purchase_even_without_another_purchase_target(stock):
    catalyst.begin_purchase("test")
    catalyst.recover_purchase()
    assert record.get_inventory_counts() == {}
    catalyst.recover_purchase()
    assert catalyst.begin_purchase("test") is None


def snapshot(vouchers=180, owned=3, uid="test"):
    return {
        "_mower_player": {"uid": uid},
        "data": {
            "characters": [],
            "items": [
                {"id": "32001", "count": owned},
                {"id": "4006", "count": vouchers},
            ],
        },
    }


def test_old_cloud_and_force_refresh_keep_both_sides_of_payment(stock):
    token = catalyst.begin_purchase("test")
    catalyst.finish_purchase(token, success=True)
    _, protected = reconcile_snapshot(snapshot())
    assert protected == {"芯片助剂", "采购凭证"}
    record.save_inventory_counts(
        {"芯片助剂": 3, "采购凭证": 180},
        scanned_counts={},
        cloud_counts={"芯片助剂": 3, "采购凭证": 180},
        cloud_at=9999999999,
        force_cloud=True,
        preserve_cloud=protected,
    )
    assert record.get_inventory_counts() == {"芯片助剂": 4, "采购凭证": 90}
    assert reconcile_snapshot(snapshot(uid="other"))[1] == set()
    assert reconcile_snapshot(snapshot(vouchers=90, owned=4))[1] == set()


def test_next_unaccepted_purchase_retains_previous_cloud_protection(stock):
    catalyst.finish_purchase(catalyst.begin_purchase("test"), success=True)
    token = catalyst.begin_purchase("test")
    catalyst.finish_purchase(token, accepted=False)
    assert reconcile_snapshot(snapshot())[1] == {"芯片助剂", "采购凭证"}
    assert record.get_inventory_counts() == {"芯片助剂": 4, "采购凭证": 90}


def test_cloud_convergence_cannot_overwrite_next_purchase_receipt(stock, monkeypatch):
    catalyst.finish_purchase(catalyst.begin_purchase("test"), success=True)
    token = catalyst.begin_purchase("test")
    read, resume = threading.Event(), threading.Event()
    original_write = catalyst._write

    def paused_write(conn, value):
        if threading.current_thread().name.startswith("catalyst-cloud"):
            read.set()
            assert resume.wait(3)
        return original_write(conn, value)

    monkeypatch.setattr(catalyst, "_write", paused_write)
    with (
        ThreadPoolExecutor(1, thread_name_prefix="catalyst-cloud") as cloud,
        ThreadPoolExecutor(1) as callback,
    ):
        sync = cloud.submit(catalyst.preserve_cloud, snapshot(vouchers=90, owned=4))
        try:
            assert read.wait(3)
            receipt = callback.submit(catalyst.finish_purchase, token, success=True)
            try:
                receipt.result(timeout=0.2)
            except TimeoutError:
                pass
        finally:
            resume.set()
        sync.result(timeout=4)
        assert receipt.result(timeout=4)
    catalyst.recover_purchase()
    assert record.get_inventory_counts() == {"芯片助剂": 5, "采购凭证": 0}
    assert not catalyst.finish_purchase(token, success=True)
    assert catalyst.preserve_cloud(snapshot(vouchers=90, owned=4)) == {
        "芯片助剂",
        "采购凭证",
    }


@pytest.fixture
def solver(stock):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    solver = object.__new__(BaseSchedulerSolver)
    solver.MAA = None
    solver.scene_graph_navigation = MagicMock()
    solver.find_next_task = MagicMock(return_value=None)
    solver.recog = MagicMock()
    solver.sleep = MagicMock()
    core = MagicMock()
    core.append_task.return_value = 7
    core.running.return_value = False

    def initialize():
        solver.MAA = core
        solver._maa_activity_generation = object()

    solver.initialize_maa = initialize
    return solver, core


def emit(
    solver,
    message=20002,
    *,
    taskid=7,
    chain="Custom",
    node=catalyst.RECEIPT,
    generation=None,
):
    solver.on_maa_callback(
        message,
        json.dumps(
            {
                "taskid": taskid,
                "taskchain": chain,
                "subtask": "ProcessTask",
                "details": {"task": node},
            }
        ).encode(),
        None,
        observation_run=generation or solver._maa_activity_generation,
    )


def test_real_callback_and_run_only_submit_custom_and_record_confirmed_purchase(solver):
    solver, core = solver

    def running():
        emit(solver, generation=object())
        emit(solver, taskid=8)
        emit(solver, chain="OperProgress")
        emit(solver, node="MowerGrowthCatalyst@Purchase")
        assert record.get_inventory_counts() == {"芯片助剂": 3, "采购凭证": 180}
        emit(solver)
        emit(solver)
        return False

    core.running.side_effect = running
    assert runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )
    core.append_task.assert_called_once_with("Custom", {"task_names": [catalyst.ENTRY]})
    assert record.get_inventory_counts() == {"芯片助剂": 4, "采购凭证": 90}
    core.close.assert_called_once()
    assert solver.MAA is None
    assert solver.maa_catalyst_run is None
    assert not record.battle_inventory_active.is_set()
    solver.recog.reset_after_external_control.assert_called_once()


def test_real_batch_callback_accounts_for_all_items_once(solver):
    solver, core = solver
    record.save_inventory_counts({"芯片助剂": 0, "采购凭证": 450})

    def running():
        emit(solver, node=catalyst.RECEIPT)
        assert record.get_inventory_counts() == {"芯片助剂": 0, "采购凭证": 450}
        emit(solver, node=catalyst.receipt_for_count(5))
        emit(solver, node=catalyst.receipt_for_count(5))
        return False

    core.running.side_effect = running
    assert runner.purchase_catalyst(
        solver,
        {"uid": "test", "catalyst_purchase": 5},
        datetime.now() + timedelta(minutes=5),
    )
    core.append_task.assert_called_once_with(
        "Custom", {"task_names": [catalyst.entry_for_count(5)]}
    )
    assert record.get_inventory_counts() == {"芯片助剂": 5, "采购凭证": 0}


def test_custom_completion_without_obtained_receipt_cannot_credit_inventory(solver):
    solver, core = solver
    core.running.side_effect = lambda: (emit(solver, message=10002), False)[1]
    assert not runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )
    assert record.get_inventory_counts() == {}
    assert not runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )
    assert core.append_task.call_count == 1


def test_unaccepted_task_keeps_known_inventory_and_blocks_unchanged_retry(solver):
    solver, core = solver
    core.append_task.side_effect = RuntimeError("unsupported task")
    with pytest.raises(RuntimeError, match="unsupported"):
        runner.purchase_catalyst(
            solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
        )
    assert record.get_inventory_counts() == {"芯片助剂": 3, "采购凭证": 180}
    assert not runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )
    assert core.append_task.call_count == 1
    core.close.assert_called_once()


def test_stop_during_accepted_task_invalidates_unconfirmed_payment(solver):
    solver, core = solver

    def running():
        config.stop_maa.set()
        return True

    core.running.side_effect = running
    assert not runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )
    assert record.get_inventory_counts() == {}
    core.stop.assert_called()
    core.close.assert_called_once()


def test_due_task_after_navigation_does_not_block_a_later_purchase(solver):
    solver, core = solver
    solver.scene_graph_navigation.side_effect = lambda _: setattr(
        solver.find_next_task, "return_value", SimpleNamespace(time=datetime.now())
    )
    assert not runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )
    core.append_task.assert_not_called()
    solver.find_next_task.return_value = None
    solver.scene_graph_navigation.side_effect = None
    core.running.side_effect = lambda: (emit(solver), False)[1]
    assert runner.purchase_catalyst(
        solver, {"uid": "test"}, datetime.now() + timedelta(minutes=5)
    )


@pytest.mark.parametrize("reason", ["off", "due", "stop", "deadline"])
def test_purchase_yields_without_spending_or_starting_maa(solver, reason):
    solver, core = solver
    deadline = datetime.now() + timedelta(minutes=5)
    if reason == "off":
        config.conf.maa_growth_enable = False
    elif reason == "due":
        solver.find_next_task.return_value = SimpleNamespace(time=datetime.now())
    elif reason == "stop":
        config.stop_maa.set()
    else:
        deadline = datetime.now() - timedelta(seconds=1)
    assert not runner.purchase_catalyst(solver, {"uid": "test"}, deadline)
    core.append_task.assert_not_called()
    assert record.get_inventory_counts() == {"芯片助剂": 3, "采购凭证": 180}
