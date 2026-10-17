"""Facility entry leaves the current frame available to its scene reader."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def entry_modules():
    with pytest.MonkeyPatch.context() as imports:
        imports.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
        from arknights_mower.solvers import base_mixin, base_schedule
        from arknights_mower.utils.recognize import Recognizer
        from arknights_mower.utils.scene import Scene

        yield SimpleNamespace(
            mixin=base_mixin,
            scheduler=base_schedule,
            recognizer=Recognizer,
            scene=Scene,
        )


def entry_solver(modules, monkeypatch, room, wait_frames=0):
    solver = object.__new__(modules.scheduler.BaseSchedulerSolver)
    recog = object.__new__(modules.recognizer)
    recog.clear()
    recog.w, recog.h = 1920, 1080
    page = {"room": "map", "connecting": 0}
    frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)

    def capture():
        recog._img = frame
        recog._gray = frame[:, :, 0]

    def find(name, *args, **kwargs):
        _ = recog.img
        if (
            name == "connecting"
            and page["room"] != "map"
            and page["connecting"] < wait_frames
        ):
            page["connecting"] += 1
            return ((100, 100), (200, 200))
        visible = (
            {"control_central", "infra_overview"}
            if page["room"] == "map"
            else {"train_main"}
            if room == "train"
            else {"factory_dashboard", "infra_overview"}
        )
        return ((100, 100), (200, 200)) if name in visible else None

    recog.start = MagicMock(side_effect=capture)
    recog.find = MagicMock(side_effect=find)
    recog.check_announcement = MagicMock(return_value=False)
    recog.detect_index_scene = MagicMock(return_value=False)
    recog.check_current_focus = MagicMock()
    recog.check_freeze = MagicMock()
    recog.check_loading_time = MagicMock()
    recog.update = MagicMock(side_effect=recog.clear)
    solver.recog = recog
    solver.detect_room = MagicMock(side_effect=lambda: page["room"])
    solver.adjust_room = MagicMock(return_value=((100, 100), (200, 200)))
    solver.sleep = MagicMock(side_effect=lambda *_: recog.update())

    def tap(*args, **kwargs):
        page["room"] = room
        recog.update()

    solver.tap = MagicMock(side_effect=tap)
    monkeypatch.setattr(modules.mixin.segment, "base", lambda *a, **kw: {room: ()})
    return solver


@pytest.mark.parametrize(
    "room,reader,expected",
    [
        ("train", "train_scene", "TRAIN_MAIN"),
        ("factory", "factory_scene", "FACTORY_DASHBOARD"),
    ],
)
@pytest.mark.parametrize("wait_frames", [0, 8], ids=["immediate", "last-observation"])
def test_room_entry_preserves_facility_scene_on_same_frame(
    entry_modules, monkeypatch, room, reader, expected, wait_frames
):
    solver = entry_solver(entry_modules, monkeypatch, room, wait_frames)

    solver.enter_room(room)

    assert getattr(solver, reader)() == getattr(entry_modules.scene, expected)
    assert solver.recog.start.call_count == 2 + wait_frames
    assert solver.recog.update.call_count == 1 + wait_frames
    solver.tap.assert_called_once()
    assert solver.sleep.call_count == wait_frames


@pytest.mark.parametrize("planned", [False, True], ids=["legacy", "support-plan"])
def test_support_swap_dispatch_confirms_room_before_consuming_task(
    entry_modules, monkeypatch, offline_maintenance, income_db, planned
):
    from arknights_mower.solvers import (
        mastery,
        mastery_reader,
        mastery_support_swap,
    )
    from arknights_mower.utils import config, mastery_db, mastery_recommendation
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    now = datetime.now()
    ends = now + timedelta(minutes=232)
    task = SchedulerTask(now, task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "1"
    solver = entry_solver(entry_modules, monkeypatch, "train")
    solver.task, solver.tasks = task, [task]
    solver.op_data = SimpleNamespace(operators={})
    for name in (
        "_resume_failed_tasks",
        "_refresh_deferred_product_reservations",
        "skip",
        "back",
    ):
        setattr(solver, name, MagicMock())
    solver._product_switching_enabled = MagicMock(return_value=True)
    solver._emergency_startup_pending = False
    solver._emergency_active = MagicMock(return_value=False)
    route = {
        "level": 2,
        "operator": "夜半",
        "efficiency": 75,
        "swap_target": "艾丽妮",
        "swap_efficiency": 30,
        "job_match": True,
        "central_bonus": 0,
        "mastery_swap_buffer": 10,
        "first_halves": False,
        "swap_halves": True,
        "manual": True,
    }
    plan = {
        "id": 1,
        "char_id": "char_103_angel",
        "char_name": "能天使",
        "skill_index": 0,
        "skill_name": "冲锋模式",
        "target_level": 3,
        "status": "training",
        "swap_frozen": 0,
        "support_plan": {"stages": [route]} if planned else None,
    }
    panel = mastery_reader.RoomPanel(
        operator_name="能天使",
        skill_name="冲锋模式",
        mastery_tier=2,
        countdown_state="active",
        countdown=ends,
    )
    occupants = {"support": "夜半"}

    def choose_train(names):
        occupants["support"] = names[0]

    def read_slots(_solver):
        return occupants["support"], "能天使", None, True

    solver.choose_train = MagicMock(side_effect=choose_train)
    read_panel = MagicMock(return_value=panel)
    monkeypatch.setattr(config, "plan", {})
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: plan)
    monkeypatch.setattr(mastery_db, "update_plan_status", MagicMock(return_value=True))
    monkeypatch.setattr(mastery_db, "save_support_plan", MagicMock(return_value=True))
    monkeypatch.setattr(mastery_db, "should_notify", lambda *args: False)
    monkeypatch.setattr(mastery, "get_route_config", lambda *args: dict(route))
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: {})
    for module in (mastery, mastery_reader):
        monkeypatch.setattr(module, "read_main_panel", read_panel)
        monkeypatch.setattr(module, "_read_slots_checked", read_slots)
    monkeypatch.setattr(mastery, "_read_train_countdown", lambda *_: ends)
    options = {
        "夜半": {2: {"name": "夜半", "efficiency": 75, "halves": False}},
        "艾丽妮": {2: {"name": "艾丽妮", "efficiency": 30, "halves": True}},
    }
    monkeypatch.setattr(
        mastery_support_swap, "candidates", lambda *a, **kw: (options, 0)
    )

    solver.infra_main()

    solver.choose_train.assert_called_once_with(["艾丽妮", "Current"])
    assert occupants["support"] == "艾丽妮"
    assert all(queued is not task for queued in solver.tasks)
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.SKILL_UPGRADE
    assert solver.tasks[0].time == ends
    assert solver.tasks[0].plan_key == "1"
    assert solver.train_scene() == entry_modules.scene.TRAIN_MAIN
    solver.sleep.assert_not_called()
