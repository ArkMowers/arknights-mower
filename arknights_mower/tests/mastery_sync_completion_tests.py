"""Fresh mastery-three snapshots finish collected plans without game operations."""

from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import jsonpickle
import pytest

from arknights_mower.tests.cultivate_depot_tests import syncer as syncer
from arknights_mower.tests.scheduler_recovery_preservation_tests import (
    scheduler as scheduler,
)
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("income_db")


@pytest.fixture
def plans(tmp_path, monkeypatch):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "workshop_inventory_changed", Event())
    monkeypatch.setattr(record, "battle_inventory_active", Event())
    path = tmp_path / "mastery.db"
    monkeypatch.setattr(
        mastery_db, "get_path", lambda name: path if name.endswith(".db") else tmp_path
    )
    monkeypatch.setattr(mastery_db, "_tables_created", set())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    ids = [
        mastery_db.insert_plan(
            "char_test", index, 3, char_name="测试干员", skill_name=f"技能{index + 1}"
        )
        for index in (0, 1)
    ]
    assert all(plan_id > 0 for plan_id in ids)
    from arknights_mower.utils import yituliu_sync

    monkeypatch.setattr(yituliu_sync, "sync_after_cultivate", lambda _: None)
    return ids


def payload(level=3):
    return {
        "code": 0,
        "data": {
            "characters": [
                {
                    "id": "char_test",
                    "evolvePhase": 2,
                    "level": 60,
                    "skills": [{"level": level}, {"level": 2}],
                }
            ],
            "items": [],
        },
    }


@pytest.mark.parametrize(
    "status", ["idle", "arranging", "training", "waiting_collect", "failed"]
)
def test_fresh_sync_closes_only_matching_mastery_three_plan(
    syncer, plans, monkeypatch, status
):
    mastery_db.update_plan_status(
        plans[0],
        status,
        expires_at="2999-01-01 00:00:00",
        swap_frozen=1,
        failed_reason="旧状态",
    )
    with mastery_db._conn() as conn:
        conn.execute(
            "UPDATE mastery_plan SET support_runtime=? WHERE id=?",
            ('{"old": true}', plans[0]),
        )
        conn.commit()
    monkeypatch.setattr(
        "arknights_mower.solvers.cultivate_depot.request_with_retry",
        lambda *a, **kw: SimpleNamespace(json=payload),
    )
    assert syncer.start(force_inventory=True)
    first = mastery_db.get_plan_by_id(plans[0])
    assert first["status"] == "completed"
    assert first["expires_at"] is None and first["swap_frozen"] == 0
    assert first["support_runtime"] is None and not first["failed_reason"]
    assert mastery_db.get_plan_by_id(plans[1])["status"] == "idle"
    assert not mastery_db.is_operator_busy("测试干员")
    assert config.wake_scheduler.is_set()
    config.wake_scheduler.clear()
    assert syncer.start(force_inventory=True)
    assert not config.wake_scheduler.is_set()


@pytest.mark.parametrize("level", [None, 0, 1, 2, True, "3", 4])
def test_incomplete_or_invalid_synced_mastery_keeps_active_plan(
    syncer, plans, monkeypatch, level
):
    mastery_db.update_plan_status(plans[0], "training")
    monkeypatch.setattr(
        "arknights_mower.solvers.cultivate_depot.request_with_retry",
        lambda *a, **kw: SimpleNamespace(json=lambda: payload(level)),
    )
    assert syncer.start(force_inventory=True)
    assert mastery_db.get_plan_by_id(plans[0])["status"] == "training"
    assert not config.wake_scheduler.is_set()


def test_completion_is_terminal_against_late_training_updates(plans):
    mastery_db.update_plan_status(plans[0], "completed")
    assert (
        mastery_db.update_plan_status(plans[0], "training", expires_at="2999-01-01")
        is False
    )
    assert mastery_db.get_plan_by_id(plans[0])["status"] == "completed"


def test_scheduler_discards_only_completed_plan_tasks_and_keeps_other_work(
    plans, monkeypatch
):
    from arknights_mower.solvers import mastery_reader as reader
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    mastery_db.update_plan_status(plans[0], "completed")
    now = datetime.now()
    stale = []
    for kind in (TaskTypes.SKILL_UPGRADE, TaskTypes.SWAP_SUPPORT):
        task = SchedulerTask(now, task_type=kind)
        task.plan_key = str(plans[0])
        task.execution_failure = {"reason": "未确认", "rooms": ("train",)}
        stale.append(task)
    other = SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.SKILL_UPGRADE)
    other.plan_key = str(plans[1])
    unrelated = SchedulerTask(now, task_type=TaskTypes.DEPOT)
    room = reader.RoomState(
        "training",
        panel=reader.RoomPanel(
            operator_name="测试干员", skill_name="技能1", mastery_tier=3
        ),
    )
    monkeypatch.setattr(reader, "resolve_panel_skill", lambda *args: 0)
    solver = object.__new__(BaseSchedulerSolver)
    solver.tasks = jsonpickle.decode(jsonpickle.encode([*stale, other, unrelated]))
    solver.task = solver.tasks[0]
    solver.train_room_state = room
    retained = solver.tasks[2:]
    reader.discard_completed_mastery_tasks(solver)
    assert solver.tasks == retained
    assert solver.task is None
    assert solver.train_room_state is None
    for _ in range(3):
        reader.discard_completed_mastery_tasks(solver)
        assert solver.tasks == retained
    assert solver.tasks[0].time == other.time


@pytest.mark.parametrize("kind", [TaskTypes.SKILL_UPGRADE, TaskTypes.SWAP_SUPPORT])
def test_completed_task_never_enters_training_room(plans, monkeypatch, kind):
    from arknights_mower.solvers import mastery
    from arknights_mower.solvers import mastery_reader as reader

    monkeypatch.setattr(config.conf, "enable_mastery", True)
    mastery_db.update_plan_status(plans[0], "completed")
    task = SchedulerTask(datetime.now(), task_type=kind)
    task.plan_key = str(plans[0])
    solver = SimpleNamespace(task=task, amiya_pending_plan_id=plans[0])
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    forbidden = Mock(side_effect=AssertionError("completed task entered room"))
    monkeypatch.setattr(reader, "reconcile_and_act", forbidden)
    monkeypatch.setattr(reader, "read_room_state", forbidden)
    if kind == TaskTypes.SKILL_UPGRADE:
        mastery.run_mastery_task(solver)
    else:
        mastery.run_swap_support(solver)
    forbidden.assert_not_called()


@pytest.mark.parametrize("failure", ["network", "missing_inventory", "invalid_roster"])
def test_failed_sync_never_completes_training(syncer, plans, monkeypatch, failure):
    mastery_db.update_plan_status(plans[0], "training")
    response = payload()
    if failure == "missing_inventory":
        del response["data"]["items"]
    elif failure == "invalid_roster":
        response["data"]["characters"] = []
    request = Mock(return_value=SimpleNamespace(json=lambda: response))
    if failure == "network":
        request.side_effect = RuntimeError("offline")
    monkeypatch.setattr(
        "arknights_mower.solvers.cultivate_depot.request_with_retry", request
    )
    with pytest.raises((RuntimeError, ValueError)):
        syncer.start(force_inventory=True)
    assert mastery_db.get_plan_by_id(plans[0])["status"] == "training"
    assert not config.wake_scheduler.is_set()


def test_mastery_three_sync_preserves_lower_targets_and_other_skills(plans):
    lower = mastery_db.insert_plan(
        "char_test", 0, 2, char_name="测试干员", skill_name="技能1"
    )
    mastery_db.update_plan_status(lower, "training")
    assert mastery_db.complete_synced_mastery_plans(payload()["data"]) == 1
    assert mastery_db.get_plan_by_id(lower)["status"] == "training"
    assert mastery_db.get_plan_by_id(plans[1])["status"] == "idle"


def test_completed_plan_cleanup_preserves_another_skills_room_state(plans, monkeypatch):
    from arknights_mower.solvers import mastery_reader as reader

    mastery_db.update_plan_status(plans[0], "completed")
    room = reader.RoomState(
        "training", panel=reader.RoomPanel(operator_name="测试干员", skill_name="技能2")
    )
    solver = SimpleNamespace(tasks=[], task=None, train_room_state=room)
    monkeypatch.setattr(reader, "resolve_panel_skill", lambda *args: 1)
    reader.discard_completed_mastery_tasks(solver)
    assert solver.train_room_state is room
    monkeypatch.setattr(reader, "resolve_panel_skill", lambda *args: None)
    reader.discard_completed_mastery_tasks(solver)
    assert solver.train_room_state is room


def test_completion_transaction_rolls_back_all_matched_plans(plans):
    import sqlite3

    with mastery_db._conn() as conn:
        conn.execute(
            "CREATE TRIGGER reject_completion BEFORE UPDATE ON mastery_plan "
            f"WHEN NEW.id={plans[1]} AND NEW.status='completed' "
            "BEGIN SELECT RAISE(ABORT, 'write failed'); END"
        )
        conn.commit()
    box = payload()["data"]
    box["characters"][0]["skills"][1]["level"] = 3
    with pytest.raises(sqlite3.IntegrityError, match="write failed"):
        mastery_db.complete_synced_mastery_plans(box)
    assert [mastery_db.get_plan_by_id(key)["status"] for key in plans] == [
        "idle",
        "idle",
    ]


def test_normal_scheduler_boundary_releases_completed_work_and_runs_unrelated_task(
    scheduler, plans, monkeypatch
):
    solver = scheduler.solver
    mastery_db.update_plan_status(plans[0], "completed")
    stale = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SKILL_UPGRADE)
    stale.plan_key = str(plans[0])
    stale.execution_failure = {"reason": "未确认", "rooms": ("train",)}
    other = SchedulerTask(
        scheduler.clock.now() + timedelta(hours=1), task_type=TaskTypes.SKILL_UPGRADE
    )
    other.plan_key = str(plans[1])
    ready = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks = [stale, other, ready]
    scan = Mock(return_value=True)
    monkeypatch.setattr(solver, "仓库扫描", scan)
    solver.run()
    scan.assert_called_once_with()
    assert all(task is not stale and task is not ready for task in solver.tasks)
    assert any(task is other for task in solver.tasks)
    assert other.time == scheduler.clock.now() + timedelta(hours=1)
    scheduler.io.assert_not_called()


def test_new_mastery_completion_calibrates_stock_without_charging_again(
    syncer, plans, monkeypatch
):
    from arknights_mower.solvers import record

    record.save_inventory_counts({"技巧概要·卷3": 70})
    with pytest.MonkeyPatch.context() as clock_patch:
        clock = Mock()
        clock.now.return_value.timestamp.return_value = 100
        clock_patch.setattr(record, "datetime", clock)
        record.apply_workshop_inventory({"技巧概要·卷3": 6})
    monkeypatch.setattr("arknights_mower.solvers.cultivate_depot.time", lambda: 200)
    response = payload()
    response["data"]["items"] = [{"id": "3303", "count": 7}]
    monkeypatch.setattr(
        "arknights_mower.solvers.cultivate_depot.request_with_retry",
        lambda *a, **kw: SimpleNamespace(json=lambda: response),
    )
    forbidden = Mock(side_effect=AssertionError("collection charged materials twice"))
    monkeypatch.setattr(record, "apply_mastery_inventory", forbidden)
    assert syncer.start()
    assert record.get_inventory_counts()["技巧概要·卷3"] == 7
    assert mastery_db.get_plan_by_id(plans[0])["status"] == "completed"
    forbidden.assert_not_called()
