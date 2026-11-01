"""Confirmed training retains assistant work when its initial placement is unreadable."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import mastery, mastery_reader, record
from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.tests.mastery_support_fixtures import swap_case
from arknights_mower.utils import config, email, mastery_db, mastery_recommendation
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def starting_support(database, monkeypatch):
    draft, panel, _, options = swap_case()
    panel.operator_name = "能天使"
    pid = mastery_db.insert_plan(
        "target", 0, 3, "一技能·测试", "能天使", support_plan=draft["support_plan"]
    )
    plan = mastery_db.get_plan_by_id(pid)
    mastery_db.save_support_plan(pid, draft["support_plan"]["stages"][0], runtime=True)
    plan = mastery_db.get_plan_by_id(pid)
    task = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    task.plan_key = str(pid)
    solver = MagicMock(tasks=[task], task=task)
    solver.recog.w, solver.recog.h = 1920, 1080
    room = mastery_reader.RoomState(
        "empty", train_slot="能天使", slots_read=True, slots_reliable=True
    )
    scene = [Scene.TRAIN_MAIN]

    def tap(*args, **kwargs):
        scene[0] = (
            Scene.TRAIN_MAIN
            if scene[0] == Scene.TRAIN_SKILL_UPGRADE
            else Scene.TRAIN_SKILL_SELECT
        )

    solver.train_scene.side_effect = lambda: scene[0]
    solver.tap.side_effect = tap
    solver.back.side_effect = lambda: scene.__setitem__(0, Scene.TRAIN_MAIN)
    solver.ctap.side_effect = lambda *args: scene.__setitem__(
        0, Scene.TRAIN_SKILL_UPGRADE
    )
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(config, "plan", {})
    monkeypatch.setattr(
        mastery_reader, "reconcile_and_act", lambda *args, **kwargs: (plan, True, room)
    )
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_requirement_error", lambda _: None
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    monkeypatch.setattr(runtime, "candidates", lambda *args, **kwargs: (options, 0))
    monkeypatch.setattr(runtime, "schedule_context", lambda: ({}, 0))
    monkeypatch.setattr(mastery, "_warn_training_room_group", lambda _: None)
    monkeypatch.setattr(mastery, "_read_train_countdown3", lambda _: ("failed", None))
    monkeypatch.setattr(mastery, "_read_train_countdown", lambda _: panel.countdown)
    monkeypatch.setattr(mastery, "_read_panel_text", lambda _: panel)
    monkeypatch.setattr(mastery, "_count_lit_mastery_icons", lambda _: 2)
    monkeypatch.setattr(mastery_reader, "_read_slot_mastery_tier", lambda *_: 1)
    monkeypatch.setattr(mastery, "_re_read_train_countdown", lambda _: panel.countdown)
    monkeypatch.setattr(mastery_reader, "read_main_panel", lambda _: panel)
    monkeypatch.setattr(record, "apply_mastery_inventory", MagicMock())
    monkeypatch.setattr(email, "send_message", MagicMock())
    return SimpleNamespace(
        solver=solver,
        plan=plan,
        panel=panel,
        task=task,
        route=draft["support_plan"]["stages"][0],
    )


@pytest.mark.parametrize("read_error", [None, ValueError("OCR")])
def test_start_dispatch_preserves_initial_support_work_after_unreadable_readback(
    starting_support, monkeypatch, read_error
):
    case = starting_support
    read = MagicMock(
        side_effect=[
            ("快教官", "能天使", [], True),
            read_error if read_error else ("", "", None, False),
        ]
    )
    monkeypatch.setattr(mastery_reader, "_read_slots_checked", read)
    mastery.run_mastery_task(case.solver)

    saved = mastery_db.get_plan_by_id(case.plan["id"])
    assert saved["status"] == "training"
    assert saved["swap_frozen"] == 0
    swaps = [task for task in case.solver.tasks if task.type == TaskTypes.SWAP_SUPPORT]
    assert len(swaps) == 1
    assert swaps[0].plan_key == str(case.plan["id"])
    assert swaps[0].time <= datetime.now()
    assert swaps[0].mastery_swap_verify_only is True
    assert not any(
        task.type == TaskTypes.SKILL_UPGRADE and task is not case.task
        for task in case.solver.tasks
    )
    case.solver.choose_train.assert_called_once_with(["快教官", "Current"])
    assert "仍按原协助位练完" not in email.send_message.call_args.args[0]


@pytest.mark.parametrize("error", [MowerExit(), DeviceRecoveryError("device")])
def test_started_training_and_support_intent_survive_control_exception(
    starting_support, monkeypatch, error
):
    case = starting_support
    monkeypatch.setattr(
        mastery_reader,
        "_read_slots_checked",
        MagicMock(side_effect=[("快教官", "能天使", [], True), error]),
    )
    with pytest.raises(type(error)) as raised:
        mastery.run_mastery_task(case.solver)
    assert raised.value is error
    saved = mastery_db.get_plan_by_id(case.plan["id"])
    assert saved["status"] == "training"
    assert saved["swap_frozen"] == 0
    assert sum(task.type == TaskTypes.SWAP_SUPPORT for task in case.solver.tasks) == 1
    case.solver.back_to_infrastructure.assert_not_called()
    assert case.solver.back.call_count == 1


def test_confirmed_start_retains_support_work_if_swap_planning_raises(
    starting_support, monkeypatch
):
    case = starting_support
    monkeypatch.setattr(
        mastery_reader,
        "_read_slots_checked",
        MagicMock(return_value=("快教官", "能天使", [], True)),
    )
    monkeypatch.setattr(
        mastery,
        "_schedule_swap_if_needed",
        MagicMock(side_effect=ValueError("路线读取")),
    )
    mastery.run_mastery_task(case.solver)
    saved = mastery_db.get_plan_by_id(case.plan["id"])
    assert saved["status"] == "training"
    assert saved["swap_frozen"] == 0
    swaps = [task for task in case.solver.tasks if task.type == TaskTypes.SWAP_SUPPORT]
    assert len(swaps) == 1
    assert swaps[0].plan_key == str(case.plan["id"])
    assert swaps[0].time <= datetime.now()
    assert swaps[0].mastery_swap_verify_only is True


@pytest.mark.parametrize("when", ["initial_assistant", "handoff_planning"])
def test_route_none_during_confirmed_start_preserves_pending_support(
    starting_support, monkeypatch, when
):
    case = starting_support
    route = dict(case.route)
    mastery_db.save_support_plan(case.plan["id"], None)
    case.plan.update(mastery_db.get_plan_by_id(case.plan["id"]))
    case.plan["expires_at"] = case.panel.countdown.isoformat()
    reads = MagicMock(return_value=("快教官", "能天使", [], True))
    monkeypatch.setattr(mastery_reader, "_read_slots_checked", reads)
    monkeypatch.setattr(
        mastery,
        "_get_plan_route",
        MagicMock(side_effect=[None] if when == "initial_assistant" else [route, None]),
    )
    mastery.run_mastery_task(case.solver)
    saved = mastery_db.get_plan_by_id(case.plan["id"])
    assert saved["status"] == "training"
    assert saved["swap_frozen"] == 0
    swaps = [task for task in case.solver.tasks if task.type == TaskTypes.SWAP_SUPPORT]
    assert len(swaps) == 1
    assert swaps[0].time <= datetime.now()
    assert swaps[0].mastery_swap_verify_only is True
    assert swaps[0].plan_key == str(case.plan["id"])
    assert not any(
        task.type == TaskTypes.SKILL_UPGRADE and task is not case.task
        for task in case.solver.tasks
    )


def test_post_arrangement_countdown_failure_never_schedules_from_old_deadline(
    starting_support, monkeypatch
):
    case = starting_support
    original_end = case.panel.countdown
    case.solver.choose_train.side_effect = lambda *_: setattr(
        case.panel, "countdown", original_end - timedelta(hours=1)
    )
    monkeypatch.setattr(
        mastery_reader,
        "_read_slots_checked",
        MagicMock(return_value=("快教官", "能天使", [], True)),
    )
    monkeypatch.setattr(mastery, "_re_read_train_countdown", lambda _: None)
    schedule = MagicMock(return_value=None)
    refresh = MagicMock()
    monkeypatch.setattr(mastery, "_schedule_swap_if_needed", schedule)
    monkeypatch.setattr(
        "arknights_mower.solvers.mastery_support_state.refresh_end", refresh
    )
    mastery.run_mastery_task(case.solver)
    saved = mastery_db.get_plan_by_id(case.plan["id"])
    assert saved["status"] == "training"
    assert saved["swap_frozen"] == 0
    swaps = [task for task in case.solver.tasks if task.type == TaskTypes.SWAP_SUPPORT]
    assert len(swaps) == 1
    assert swaps[0].time <= datetime.now()
    assert swaps[0].mastery_swap_verify_only is True
    schedule.assert_not_called()
    refresh.assert_not_called()
    assert not any(
        task.type == TaskTypes.SKILL_UPGRADE and task is not case.task
        for task in case.solver.tasks
    )
