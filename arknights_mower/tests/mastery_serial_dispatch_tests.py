"""A single training slot admits one start and hands off after collection."""

import json
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import (  # noqa: E402
    base_schedule,
    mastery,
    mastery_reader,
    record,
)
from arknights_mower.utils import (  # noqa: E402
    config,
    mastery_db,
    mastery_recommendation,
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def serial(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=True))
    db_path = tmp_path / "data.db"

    def resolve(value):
        return db_path if value.endswith("data.db") else tmp_path

    monkeypatch.setattr(mastery_db, "get_path", resolve)
    monkeypatch.setattr(mastery_db, "_tables_created", set())
    monkeypatch.setattr(record, "get_path", resolve)
    monkeypatch.setattr(record, "_tables_created", False)
    record.save_inventory_counts({"测试材料": 3})
    skills = tmp_path / "skill_data.json"
    skills.write_text(json.dumps({"items": {"fixture": {"name": "测试材料"}}}))
    monkeypatch.setattr(mastery_recommendation, "_find_skill_data", lambda: skills)
    operators = []
    ids = []
    for priority, name in enumerate(("当前干员", "下一干员", "后续干员")):
        char_id = f"char_fixture_{priority}"
        ids.append(
            mastery_db.insert_plan(
                char_id, 0, 3, char_name=name, skill_name="测试技能", priority=priority
            )
        )
        operators.append(
            {
                "char_id": char_id,
                "name": name,
                "profession": "CASTER",
                "recommendations": [
                    {
                        "skill_index": 0,
                        "skill_name": "测试技能",
                        "current_level": 0,
                        "chain_needed_materials": [{"name": "测试材料", "count": 1}],
                    }
                ],
            }
        )
    monkeypatch.setattr(
        mastery_recommendation,
        "get_mastery_recommendations",
        lambda: {"has_data": True, "operators": operators},
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    monkeypatch.setattr(mastery_reader, "resolve_panel_skill", lambda *_: 0)
    collect = MagicMock()
    confirm = MagicMock()
    monkeypatch.setattr(mastery_reader, "collect_flow", collect)
    monkeypatch.setattr(mastery_reader, "_tap_collect_confirm", confirm)
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.tasks = []
    solver.task = None
    solver.train_room_state = None
    solver.train_scene = MagicMock(return_value=mastery_reader.Scene.TRAIN_MAIN)
    solver.back = MagicMock()
    room = mastery_reader.RoomState(
        state="waiting_collect",
        panel=mastery_reader.RoomPanel(
            operator_name="当前干员",
            skill_name="测试技能",
            mastery_tier=3,
            countdown_state="zero",
        ),
    )
    return SimpleNamespace(
        solver=solver,
        ids=ids,
        room=room,
        collect=collect,
        confirm=confirm,
        operators=operators,
    )


def dispatch(serial):
    ready = mastery_recommendation.auto_schedule_mastery_tasks()["scheduled"]
    serial.solver._dispatch_scan_start_tasks(ready)


def test_many_ready_plans_admit_only_first_without_refreshing_queued_start(serial):
    before = mastery_db.get_all_plans()
    ready = [
        {"char_id": plan["char_id"], "skill_index": plan["skill_index"]}
        for plan in reversed(before)
    ]
    serial.solver._dispatch_scan_start_tasks(ready)
    assert len(serial.solver.tasks) == 1
    task = serial.solver.tasks[0]
    assert task.plan_key == str(serial.ids[0])
    original_time = task.time = datetime.now() - timedelta(minutes=5)
    for _ in range(3):
        serial.solver._dispatch_scan_start_tasks(ready)
    assert serial.solver.tasks == [task]
    assert task.time == original_time
    assert mastery_db.get_all_plans() == before


@pytest.mark.parametrize("status", ["arranging", "training", "waiting_collect"])
@pytest.mark.parametrize("with_task", [False, True])
def test_active_training_does_not_admit_another_plan(serial, status, with_task):
    mastery_db.update_plan_status(serial.ids[0], status)
    deadline = datetime.now() + timedelta(hours=4)
    collect = SchedulerTask(time=deadline, task_type=TaskTypes.SKILL_UPGRADE)
    collect.plan_key = str(serial.ids[0])
    original_tasks = [collect] if with_task else []
    serial.solver.tasks = list(original_tasks)
    before = mastery_db.get_all_plans()
    for _ in range(3):
        dispatch(serial)
    assert serial.solver.tasks == original_tasks
    assert collect.time == deadline
    assert mastery_db.get_all_plans() == before


@pytest.mark.parametrize("status", ["training", "waiting_collect"])
def test_observed_unplanned_training_blocks_start_without_creating_tasks(
    serial, status
):
    serial.solver.train_room_state = mastery_reader.RoomState(state=status)
    for _ in range(3):
        dispatch(serial)
    assert serial.solver.tasks == []
    serial.solver.train_room_state = mastery_reader.RoomState(state="empty")
    dispatch(serial)
    assert [task.plan_key for task in serial.solver.tasks] == [str(serial.ids[0])]


def test_completed_training_dispatches_and_executes_next_skill_immediately(
    serial, monkeypatch
):
    mastery_db.update_plan_status(serial.ids[0], "training")
    current = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    current.plan_key = str(serial.ids[0])
    independent = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    serial.solver.task = current
    serial.solver.tasks = [current, independent]
    serial.solver.train_room_state = mastery_reader.RoomState(state="training")
    monkeypatch.setattr(
        mastery_reader, "read_room_state", lambda *_a, **_k: serial.room
    )
    start = MagicMock()
    monkeypatch.setattr(mastery, "_start_new_training", start)
    started = datetime.now()
    mastery.run_mastery_task(serial.solver)
    serial.confirm.assert_called_once()
    assert mastery_db.get_plan_by_id(serial.ids[0])["status"] == "completed"
    pending = [
        task
        for task in serial.solver.tasks
        if task is not current and task is not independent
    ]
    assert len(pending) == 1
    assert pending[0].plan_key == str(serial.ids[1])
    assert started <= pending[0].time <= datetime.now()
    assert independent in serial.solver.tasks
    start.assert_not_called()

    serial.solver.tasks.remove(current)
    serial.solver.task = pending[0]
    empty = mastery_reader.RoomState(state="empty")
    monkeypatch.setattr(mastery_reader, "read_room_state", lambda *_a, **_k: empty)
    mastery.run_mastery_task(serial.solver)
    start.assert_called_once()
    assert start.call_args.args[1]["id"] == serial.ids[1]


def test_opportunistic_collection_also_queues_next_ready_skill(serial):
    mastery_db.update_plan_status(serial.ids[0], "training")
    serial.solver.train_room_state = serial.room
    assert mastery_reader.reconcile_short(serial.solver, serial.room)
    assert [task.plan_key for task in serial.solver.tasks] == [str(serial.ids[1])]


def test_intermediate_collection_releases_stale_occupancy_for_material_retry(serial):
    mastery_db.update_plan_status(serial.ids[0], "training")
    serial.room.panel.mastery_tier = 2
    serial.solver.train_room_state = mastery_reader.RoomState(state="training")
    result = mastery_reader._collect_plan(
        serial.solver, mastery_db.get_plan_by_id(serial.ids[0]), serial.room
    )
    assert result["id"] == serial.ids[0]
    assert serial.solver.train_room_state is serial.room
    assert serial.solver.tasks == []
    dispatch(serial)
    assert [task.plan_key for task in serial.solver.tasks] == [str(serial.ids[0])]


def test_shortage_after_collection_preserves_plans_and_resumes_on_stock_refresh(serial):
    mastery_db.update_plan_status(serial.ids[0], "training")
    record.save_inventory_counts({"测试材料": 0})
    independent = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    serial.solver.tasks = [independent]
    assert mastery_reader.reconcile_short(serial.solver, serial.room)
    assert serial.solver.tasks == [independent]
    remaining = mastery_db.get_all_plans()
    assert [plan["id"] for plan in remaining] == serial.ids[1:]
    assert all(plan["status"] == "idle" for plan in remaining)
    record.save_inventory_counts({"测试材料": 1})
    dispatch(serial)
    assert serial.solver.tasks[0] is independent
    assert [task.plan_key for task in serial.solver.tasks[1:]] == [str(serial.ids[1])]


def test_collection_skips_unstarted_shortage_and_admits_first_ready_skill(serial):
    mastery_db.update_plan_status(serial.ids[0], "training")
    serial.operators[1]["recommendations"][0]["chain_needed_materials"][0]["count"] = 4
    assert mastery_reader.reconcile_short(serial.solver, serial.room)
    assert [task.plan_key for task in serial.solver.tasks] == [str(serial.ids[2])]
    assert mastery_db.get_plan_by_id(serial.ids[1])["status"] == "idle"


def test_unplanned_collection_releases_occupancy_and_admits_one_skill(serial):
    serial.room.panel.operator_name = "计划外干员"
    serial.solver.train_room_state = serial.room
    assert mastery_reader.reconcile_short(serial.solver, serial.room)
    assert [task.plan_key for task in serial.solver.tasks] == [str(serial.ids[0])]


@pytest.mark.parametrize("task_type", [TaskTypes.SKILL_UPGRADE, TaskTypes.SWAP_SUPPORT])
def test_pending_mastery_task_retains_deadline_and_blocks_new_start(serial, task_type):
    existing = SchedulerTask(
        time=datetime.now() + timedelta(hours=1), task_type=task_type
    )
    existing.plan_key = str(serial.ids[0])
    serial.solver.tasks = [existing]
    deadline = existing.time
    for _ in range(3):
        dispatch(serial)
    assert serial.solver.tasks == [existing]
    assert existing.time == deadline


def test_unconfirmed_collection_does_not_dispatch_next(serial):
    mastery_db.update_plan_status(serial.ids[0], "training")
    serial.confirm.side_effect = RuntimeError("收取确认未完成")
    with pytest.raises(RuntimeError, match="收取确认未完成"):
        mastery_reader.reconcile_short(serial.solver, serial.room)
    assert serial.solver.tasks == []


def test_no_start_after_collection_when_automation_is_disabled(serial):
    config.conf.enable_mastery = False
    mastery_reader._collect_silent(serial.solver, serial.room)
    assert serial.solver.tasks == []


def test_protected_rejection_observation_releases_next_eligible_candidate(
    serial, monkeypatch
):
    room = mastery_reader.RoomState(
        state="empty",
        support_slot="逻各斯",
        train_slot="下一干员",
        protected=True,
        slots_reliable=True,
    )
    monkeypatch.setattr(mastery_reader, "read_room_state", lambda *_a, **_k: room)
    monkeypatch.setattr("arknights_mower.utils.email.send_message", MagicMock())
    start = MagicMock()
    monkeypatch.setattr(mastery, "_start_new_training", start)
    before = mastery_db.get_all_plans()
    # 首次没有观测时选择 A，实读保护后拒绝；后续扫描应允许 B 推进。
    dispatch(serial)
    rejected = serial.solver.tasks.pop()
    assert rejected.plan_key == str(serial.ids[0])
    serial.solver.task = rejected
    mastery.run_mastery_task(serial.solver)
    start.assert_not_called()
    independent = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    serial.solver.tasks = [independent]
    serial.solver.task = None
    for _ in range(3):
        dispatch(serial)
    assert serial.solver.tasks[0] is independent
    assert len(serial.solver.tasks) == 2
    allowed = serial.solver.tasks[1]
    assert allowed.plan_key == str(serial.ids[1])
    deadline = allowed.time
    dispatch(serial)
    assert serial.solver.tasks[1] is allowed
    assert allowed.time == deadline
    serial.solver.task = allowed
    mastery.run_mastery_task(serial.solver)
    start.assert_called_once()
    assert start.call_args.args[1]["id"] == serial.ids[1]
    assert room.protected
    assert mastery_db.get_all_plans() == before


@pytest.mark.parametrize(
    "reliable,read_failed", [(True, False), (False, False), (True, True)]
)
def test_protection_preserves_blocked_plans_until_new_observation(
    serial, monkeypatch, reliable, read_failed
):
    room = mastery_reader.RoomState(
        state="empty",
        support_slot="艾丽妮",
        train_slot="计划外干员",
        protected=True,
        slots_reliable=reliable,
        read_failed=read_failed,
    )
    serial.solver.train_room_state = room
    notify = MagicMock()
    monkeypatch.setattr("arknights_mower.utils.email.send_message", notify)
    before = mastery_db.get_all_plans()
    for _ in range(3):
        dispatch(serial)
    assert serial.solver.tasks == []
    assert mastery_db.get_all_plans() == before
    notify.assert_called_once()
    message = notify.call_args.args[0]
    assert "艾丽妮" in message and "计划外干员" in message
    assert "确认放弃" in message and "手动清空" in message and "协助位" in message
    serial.solver.train_room_state = mastery_reader.RoomState(
        state="empty", slots_reliable=True
    )
    dispatch(serial)
    assert [task.plan_key for task in serial.solver.tasks] == [str(serial.ids[0])]
    assert mastery_db.get_all_plans() == before


def test_protected_material_wait_keeps_boundary_instead_of_skipping_to_same_trainee(
    serial, monkeypatch
):
    mastery_db.update_plan_status(
        serial.ids[0],
        "idle",
        failed_reason="材料不足",
        expires_at="2026-10-23 12:00:00",
    )
    serial.solver.train_room_state = mastery_reader.RoomState(
        state="empty",
        support_slot="逻各斯",
        train_slot="下一干员",
        protected=True,
        slots_reliable=True,
    )
    monkeypatch.setattr("arknights_mower.utils.email.send_message", MagicMock())
    before = mastery_db.get_all_plans()
    for _ in range(3):
        dispatch(serial)
    assert serial.solver.tasks == []
    assert mastery_db.get_all_plans() == before


@pytest.mark.parametrize("tiers", [[0, 0, 0], [3, 3, 3], [0, 3, 0]])
def test_observed_no_partial_mastery_allows_replacing_trainee(
    serial, monkeypatch, tiers
):
    solver = serial.solver
    room = mastery_reader.RoomState(
        state="empty",
        support_slot="逻各斯",
        train_slot="计划外干员",
        slots_reliable=True,
    )
    solver.train_scene.return_value = mastery_reader.Scene.TRAIN_SKILL_SELECT
    monkeypatch.setattr(
        mastery_reader, "_read_slot_mastery_tier", MagicMock(side_effect=tiers)
    )
    monkeypatch.setattr(mastery_reader, "_back_to_train_main", MagicMock())
    room.protected = mastery_reader._compute_protected(solver, room)
    assert not room.protected
    solver.train_room_state = room
    dispatch(serial)
    assert [task.plan_key for task in solver.tasks] == [str(serial.ids[0])]
    solver.task = solver.tasks[0]
    monkeypatch.setattr(mastery_reader, "read_room_state", lambda *_a, **_k: room)
    start = MagicMock()
    monkeypatch.setattr(mastery, "_start_new_training", start)
    mastery.run_mastery_task(solver)
    start.assert_called_once()
    assert start.call_args.args[1]["id"] == serial.ids[0]


def test_correction_notification_explains_manual_release_and_shares_throttle(
    serial, monkeypatch
):
    solver = serial.solver
    solver.op_data = MagicMock()
    solver.op_data.get_current_room.return_value = ["逻各斯", "下一干员"]
    notify = MagicMock()
    monkeypatch.setattr("arknights_mower.utils.email.send_message", notify)
    for _ in range(3):
        solver._notify_train_correction_skipped()
    room = mastery_reader.RoomState(
        state="empty", support_slot="逻各斯", train_slot="下一干员", protected=True
    )
    mastery_reader._notify_protected(solver, room)
    notify.assert_called_once()
    message = notify.call_args.args[0]
    assert "逻各斯" in message and "下一干员" in message
    assert "确认放弃减半效果" in message and "手动清空训练室协助位" in message
    assert "下次进入训练室" in message
