"""A consumed swap dispatch must leave a collection or recheck task behind."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery, mastery_reader
from arknights_mower.solvers import mastery_support_state as state
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize(
    "failure",
    [
        "slots",
        "slot_exception",
        "panel",
        "panel_exception",
        "zero",
        "mismatch",
        "route",
    ],
)
def test_failed_swap_dispatch_keeps_collection(failure):
    plan = {
        "id": 1,
        "char_id": "char_test",
        "char_name": "学员",
        "skill_name": "技能",
        "skill_index": 0,
        "status": "training",
        "swap_frozen": 0,
        "target_level": 3,
        "support_plan": {
            "stages": [{"level": 2, "operator": "教官", "swap_target": "逻各斯"}]
        },
    }
    panel = SimpleNamespace(
        countdown_state="active",
        mastery_tier=2,
        operator_name="学员",
        skill_name="技能",
        countdown=datetime.now() + timedelta(hours=3),
    )
    if failure == "zero":
        panel.countdown_state = "zero"
    if failure == "route":
        plan["support_plan"]["stages"] = []
    solver = object.__new__(BaseSchedulerSolver)
    task = SchedulerTask(task_type=TaskTypes.SWAP_SUPPORT)
    task.plan_key = "1"
    solver.task, solver.tasks = task, [task]
    solver.find = MagicMock(return_value=True)
    solver.enter_room = MagicMock()
    solver.train_scene = MagicMock(return_value=mastery.Scene.TRAIN_MAIN)
    solver.choose_train = MagicMock()
    solver.skip = MagicMock()
    with (
        patch.object(config.conf, "enable_mastery", True),
        patch.object(config.conf, "assistant_follows_schedule", False),
        patch("arknights_mower.utils.mastery_db.get_active_plan", return_value=plan),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch.object(
            mastery,
            "read_main_panel",
            return_value=None if failure == "panel" else panel,
            side_effect=ValueError("OCR") if failure == "panel_exception" else None,
        ),
        patch.object(
            mastery_reader, "_plan_matches_room", return_value=failure != "mismatch"
        ),
        patch.object(
            mastery_reader,
            "_read_slots_checked",
            return_value=("教官", "学员", None, failure != "slots"),
            side_effect=ValueError("OCR") if failure == "slot_exception" else None,
        ),
        patch.object(mastery, "_read_countdown_with_retry", return_value=None),
        patch.object(state, "notify_support_failure") as notify,
    ):
        solver.infra_main()
    solver.choose_train.assert_not_called()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.SKILL_UPGRADE
    assert solver.tasks[0].plan_key == "1"
    assert solver.tasks[0].time > datetime.now()
    assert notify.call_count == int(failure != "zero")
    assert update.call_count == int(failure != "zero")
