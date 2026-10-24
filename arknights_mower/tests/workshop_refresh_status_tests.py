"""Committed inventory, shared readiness and read-only crafting status."""

import copy
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, record
from arknights_mower.tests.maa_inventory_tests import inventory as inventory
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config, scheduler_task, workshop_limits, workshop_mood
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils.maa_inventory import MaaDropInventory
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.workshop_status import workshop_status


@pytest.fixture
def case(next_skill, inventory, monkeypatch):
    signal = Event()
    monkeypatch.setattr(record, "workshop_inventory_changed", signal)
    monkeypatch.setattr(base_schedule, "workshop_inventory_changed", signal)
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(auto, "_refresh_error", None)
    monkeypatch.setattr(workshop_limits, "_rejected_recipes", {})
    monkeypatch.setattr(workshop_mood, "operator_mood_rules", lambda _: ([], True))
    inventory.save_inventory_counts({"技巧概要·卷3": 0, "技巧概要·卷2": 14})
    auto.update_workshop_config()
    signal.clear()
    data = SimpleNamespace(operators={"赫拉格": SimpleNamespace(mood=2)})
    return SimpleNamespace(signal=signal, data=data, tasks=[], plans=next_skill.plans)


def receipt(count):
    return {"taskid": 7, "details": {"stats": [{"itemId": "3302", "quantity": count}]}}


def test_confirmed_drop_resumes_skipped_project_without_cloud_or_scan(case):
    drops = MaaDropInventory()
    assert not config.conf.workshop_settings
    drops.record(receipt(7))
    assert case.signal.is_set()
    scheduler_task.try_workshop_tasks(case.data, case.tasks)
    assert config.conf.workshop_auto_active
    assert [task.meta_data for task in case.tasks] == ["赫拉格"]
    generation = config.conf.workshop_generation
    queued = list(case.tasks)
    drops.record(receipt(7))
    assert not case.signal.is_set()
    scheduler_task.try_workshop_tasks(case.data, case.tasks)
    assert case.tasks == queued
    assert config.conf.workshop_generation == generation
    assert record.get_inventory_counts()["技巧概要·卷2"] == 21


@pytest.mark.parametrize("blocked", ["battle", "cancel"])
def test_external_control_and_cancellation_retain_pending_refresh(case, blocked):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    event = record.battle_inventory_active if blocked == "battle" else config.stop_mower
    event.set()
    assert not auto.refresh_workshop_after_inventory_change()
    assert case.signal.is_set() and not config.conf.workshop_settings
    event.clear()
    assert auto.refresh_workshop_after_inventory_change()
    assert config.conf.workshop_settings


def test_changes_during_recalculation_remain_pending(case, monkeypatch):
    case.signal.set()
    update = MagicMock(side_effect=case.signal.set)
    monkeypatch.setattr(auto, "update_workshop_config", update)
    assert auto.refresh_workshop_after_inventory_change()
    update.assert_called_once()
    assert case.signal.is_set()
    update.side_effect = None
    assert auto.refresh_workshop_after_inventory_change()
    assert update.call_count == 2 and not case.signal.is_set()


def test_failed_ledger_transaction_never_publishes_refresh(case, monkeypatch):
    previous = record.get_inventory_counts()
    monkeypatch.setattr(
        record,
        "_mark_workshop_inventory",
        MagicMock(side_effect=OSError("write failed")),
    )
    with pytest.raises(OSError):
        record.apply_workshop_inventory({"技巧概要·卷2": 7})
    assert not case.signal.is_set()
    assert record.get_inventory_counts() == previous


def test_duplicate_zero_or_unknown_delta_does_not_publish_stock_change(case):
    record.apply_workshop_inventory({"技巧概要·卷2": 0, "未观察材料": 1})
    assert not case.signal.is_set()
    assert "未观察材料" not in record.get_inventory_counts()


def test_disabled_automation_does_not_take_over_on_drops(case):
    config.conf.enable_mastery = False
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    assert auto.refresh_workshop_after_inventory_change()
    assert not config.conf.workshop_auto_active
    assert config.conf.workshop_settings == []


@pytest.mark.parametrize("save_fails", [False, True])
def test_recalculation_failure_blocks_old_tasks_even_if_pause_cannot_persist(
    case, monkeypatch, save_fails
):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    assert auto.refresh_workshop_after_inventory_change()
    old = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="赫拉格")
    auto.stamp_workshop_task(old)
    backup = copy.deepcopy(config.conf.workshop_manual_backup)
    monkeypatch.setattr(
        auto,
        "calculate_workshop_plan",
        MagicMock(side_effect=ValueError("bad resources")),
    )
    if save_fails:
        monkeypatch.setattr(
            config, "save_conf", MagicMock(side_effect=OSError("disk full"))
        )
    case.signal.set()
    assert not auto.refresh_workshop_after_inventory_change()
    assert case.signal.is_set()
    assert auto.workshop_task_snapshot(old) is None
    assert config.conf.workshop_manual_backup == backup
    assert auto._refresh_error


def test_unchanged_projection_keeps_generation_and_old_current_task(case):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    auto.refresh_workshop_after_inventory_change()
    generation = config.conf.workshop_generation
    task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="赫拉格")
    auto.stamp_workshop_task(task)
    record.save_inventory_counts(record.get_inventory_counts())
    assert auto.workshop_task_snapshot(task).generation == generation
    assert not case.signal.is_set()


def test_post_battle_boundary_refreshes_before_idle_and_queues_affordable_worker(
    case, monkeypatch
):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.MAA = case.data, case.tasks, None
    monkeypatch.setattr(base_schedule, "scheduling", MagicMock())
    solver._refresh_workshop_inventory()
    assert [task.meta_data for task in solver.tasks] == ["赫拉格"]
    assert not case.signal.is_set()


def test_post_battle_boundary_keeps_external_control_and_staffing_protected(case):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.MAA = case.data, case.tasks, object()
    solver._refresh_workshop_inventory()
    assert case.signal.is_set() and not solver.tasks
    solver.MAA = None
    task = SchedulerTask()
    task.emergency_staffing = True
    solver.tasks.append(task)
    solver._refresh_workshop_inventory()
    assert case.signal.is_set() and solver.tasks == [task]


@pytest.mark.parametrize(
    "mood,expected",
    [(10, True), (2, True), (1, False), (0, False), (-1, False), (None, False)],
)
def test_automatic_first_task_uses_known_batch_mood(case, mood, expected):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    auto.refresh_workshop_after_inventory_change()
    if mood is None:
        case.data.operators.clear()
    else:
        case.data.operators["赫拉格"].mood = mood
    scheduler_task.try_workshop_tasks(case.data, case.tasks)
    assert bool(case.tasks) is expected


def test_manual_threshold_and_automatic_reservations_remain_binding(case):
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    auto.refresh_workshop_after_inventory_change()
    setting = config.conf.workshop_settings[0]
    setting.source = "manual"
    scheduler_task.try_workshop_tasks(case.data, case.tasks)
    assert not case.tasks
    setting.source = "mastery"
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"train": ["赫拉格"]})
    case.tasks.append(task)
    scheduler_task.try_workshop_tasks(case.data, case.tasks)
    assert case.tasks == [task]


def test_status_shares_dispatch_eligibility_and_preserves_all_state(case, monkeypatch):
    from arknights_mower.utils import growth_workshop

    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    auto.refresh_workshop_after_inventory_change()
    scheduler = SimpleNamespace(op_data=case.data, tasks=case.tasks, sleeping=False)
    stock = record.get_inventory_counts()
    workshop_limits.reject_workshop_recipe(
        "技巧概要·卷3", {**stock, "技巧概要·卷2": 20}
    )
    rejections = dict(workshop_limits._rejected_recipes)
    conf = config.conf.model_dump()
    monkeypatch.setattr(
        config, "save_conf", MagicMock(side_effect=AssertionError("read must not save"))
    )
    monkeypatch.setattr(
        auto,
        "restore_if_no_plans",
        MagicMock(side_effect=AssertionError("read must not restore")),
    )
    auto.clear_workshop_plan_cache()
    compute = MagicMock(wraps=growth_workshop.growth_workshop_config)
    monkeypatch.setattr(growth_workshop, "growth_workshop_config", compute)
    status = workshop_status(scheduler, running=True)
    assert status["execution"] == "ready" and status["blockers"] == []
    assert config.conf.model_dump() == conf
    assert record.get_inventory_counts() == stock
    assert workshop_limits._rejected_recipes == rejections
    assert not case.tasks
    case.data.operators["赫拉格"].mood = 1
    status = workshop_status(scheduler, running=True)
    assert status["execution"] == "waiting"
    assert status["blockers"][0]["code"] == "mood_insufficient"
    assert status["blockers"][0]["required"] == 2
    compute.assert_called_once()


def test_missing_stock_stopped_scheduler_and_waiting_focus_are_distinct(case):
    status = workshop_status()
    assert status["execution"] == "stopped"
    assert status["project_key"]
    assert status["blockers"]
    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    auto.refresh_workshop_after_inventory_change()
    record.invalidate_workshop_inventory(["技巧概要·卷3"])
    case.signal.clear()
    scheduler = SimpleNamespace(op_data=case.data, tasks=[])
    status = workshop_status(scheduler, running=True)
    assert status["execution"] == "waiting"
    assert status["blockers"][0]["code"] == "inventory_unknown"
    assert status["blockers"][0]["available"] is None


def test_status_api_is_additive_and_requires_authentication(case, monkeypatch):
    import server

    monkeypatch.setattr(server, "mower_thread", None)
    client = server.app.test_client()
    assert client.get("/workshop-status").json["execution"] == "stopped"
    result = client.post("/workshop-auto-config", json={})
    assert result.status_code == 200 and "crafting_status" in result.json
    monkeypatch.setattr(server.app, "token", "private")
    assert client.get("/workshop-status").status_code in (401, 403)


def test_saved_operator_policy_requests_refresh_after_success_only(case, monkeypatch):
    from arknights_mower.utils import workshop_config

    wake = MagicMock()
    monkeypatch.setattr(workshop_config, "_wake_scheduler_if_running", wake)
    workshop_config.save_user_config({"book_operators": ["空爆"]})
    assert case.signal.is_set()
    wake.assert_called_once()
    case.signal.clear()
    monkeypatch.setattr(
        config, "save_conf", MagicMock(side_effect=OSError("disk full"))
    )
    with pytest.raises(OSError):
        workshop_config.save_user_config({"book_operators": ["赫拉格"]})
    assert not case.signal.is_set()
    assert config.conf.book_operators == ["空爆"]


def test_scheduler_start_requests_reconciliation_without_changing_config(
    case, monkeypatch
):
    monkeypatch.setattr(
        base_schedule.SceneGraphSolver, "__init__", lambda *a, **k: None
    )
    monkeypatch.setattr(base_schedule, "DigitReader", MagicMock())
    monkeypatch.setattr(base_schedule, "TradingOrder", MagicMock())
    before = config.conf.model_dump()
    base_schedule.BaseSchedulerSolver()
    assert case.signal.is_set()
    assert config.conf.model_dump() == before


def test_local_drop_boundary_defers_crafting_for_imminent_tasks(case, monkeypatch):
    from datetime import datetime, timedelta

    record.apply_workshop_inventory({"技巧概要·卷2": 7})
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    task = SchedulerTask(
        time=datetime.now() + timedelta(minutes=1), task_type=TaskTypes.RUN_ORDER
    )
    solver.op_data, solver.tasks, solver.MAA = case.data, [task], None
    solver._refresh_workshop_inventory()
    assert config.conf.workshop_settings
    assert solver.tasks == [task]
    assert not case.signal.is_set()


def test_missing_box_returns_unavailable_without_losing_the_original_config(
    case, next_skill
):
    before = config.conf.model_dump()
    next_skill.cultivate.unlink()
    result = workshop_status()
    assert result["execution"] == "unavailable"
    assert result["blockers"][0]["code"] == "data_unavailable"
    assert config.conf.model_dump() == before
