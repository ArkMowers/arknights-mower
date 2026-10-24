"""Keep unconfirmed handoffs intact through the real scheduler dispatch."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery, mastery_reader
from arknights_mower.solvers import mastery_support_state as state
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.news_checker import NewsChecker
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
def test_swap_dispatch_retains_unconfirmed_work_and_collects_confirmed_completion(
    failure,
):
    plan = {
        "id": 1,
        "char_id": "char_103_angel",
        "char_name": "能天使",
        "skill_name": "过载模式",
        "skill_index": 2,
        "status": "training",
        "swap_frozen": 0,
        "target_level": 3,
        "support_plan": {
            "stages": [{"level": 2, "operator": "教官", "swap_target": "逻各斯"}]
        },
    }
    panel = mastery_reader.RoomPanel(
        countdown_state="active",
        mastery_tier=2,
        operator_name="能天使",
        skill_name="过载模式",
        countdown=datetime.now() + timedelta(hours=3),
    )
    if failure == "zero":
        panel.countdown_state, panel.countdown = "zero", None
    if failure == "mismatch":
        panel.operator_name = "蓝毒"
    if failure == "route":
        plan["support_plan"]["stages"] = []
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = SimpleNamespace(
        plan={}, operators={}, products={}, facility_states={}, room_observations={}
    )
    solver._refresh_deferred_product_reservations = MagicMock()
    task = SchedulerTask(
        task_type=TaskTypes.SWAP_SUPPORT,
        time=datetime.now() - timedelta(minutes=8),
    )
    task.plan_key = "1"
    due = task.time
    solver.task, solver.tasks = task, [task]
    solver.find = MagicMock(return_value=True)
    solver.enter_room = MagicMock()
    solver.train_scene = MagicMock(return_value=mastery.Scene.TRAIN_MAIN)
    solver.choose_train = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.sleep = MagicMock()
    solver.skip = MagicMock()
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.handle_error = MagicMock()
    before = datetime.now()
    with (
        patch.object(config.conf, "enable_mastery", True),
        patch.object(config.conf, "assistant_follows_schedule", False),
        patch.object(NewsChecker, "get_maintenance", return_value=None),
        patch.object(NewsChecker, "get_update_time", return_value=None),
        patch("arknights_mower.utils.mastery_db.get_active_plan", return_value=plan),
        patch("arknights_mower.utils.mastery_db.get_plan_by_id", return_value=plan),
        patch("arknights_mower.utils.mastery_db.get_all_plans", return_value=[plan]),
        patch("arknights_mower.utils.mastery_db.get_route_settings", return_value={}),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_skill_data",
            return_value={},
        ),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch.object(
            mastery,
            "read_main_panel",
            return_value=None if failure == "panel" else panel,
            side_effect=ValueError("OCR") if failure == "panel_exception" else None,
        ) as read_panel,
        patch.object(
            mastery_reader,
            "_read_slots_checked",
            return_value=("教官", "能天使", None, failure != "slots"),
            side_effect=ValueError("OCR") if failure == "slot_exception" else None,
        ),
        patch.object(state, "notify_support_failure") as notify,
    ):
        solver.infra_main()
        solver.choose_train.assert_not_called()
        update.assert_not_called()
        notify.assert_not_called()
        assert solver.task is None
        assert len(solver.tasks) == 1
        if failure == "zero":
            collect = solver.tasks[0]
            assert collect is not task
            assert collect.type == TaskTypes.SKILL_UPGRADE
            assert collect.plan_key == "1"
            assert before <= collect.time <= datetime.now()
            assert not hasattr(task, "execution_failure")
            assert read_panel.call_count == 1
        else:
            assert solver.tasks[0] is task
            assert task.type == TaskTypes.SWAP_SUPPORT
            assert task.plan_key == "1"
            assert task.time == due
            assert task.execution_failure["rooms"] == ("train",)
            assert task.mastery_observation_pending is True
            assert plan["swap_frozen"] == 0
            assert read_panel.call_count == 3
            attempts = read_panel.call_count
            solver.task = task
            solver.infra_main()
            assert solver.task is None
            assert solver.tasks == [task]
            assert task.time == due
            assert read_panel.call_count == attempts
