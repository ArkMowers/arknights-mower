import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.tests import maa_copilot_tests as helpers  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402

files = helpers.files
scheduler = helpers.scheduler


@pytest.mark.parametrize("kind", ["rogue", "copilot"])
@pytest.mark.parametrize("manual", [False, True])
def test_large_task_returns_home_then_delegates_navigation_to_maa(
    scheduler, kind, manual
):
    base_schedule.config.conf.maa_long_task_type = kind
    scheduler.task = SimpleNamespace(type=None)
    scheduler.scene_graph_navigation = MagicMock()
    scheduler.scene = MagicMock(return_value=Scene.TERMINAL_MAIN)
    order = MagicMock()
    order.attach_mock(scheduler.back_to_index, "home")
    order.attach_mock(scheduler.scene_graph_navigation, "navigate")
    order.attach_mock(scheduler.MAA.append_task, "append")
    order.attach_mock(scheduler.MAA.start, "start")

    scheduler.maa_plan_solver([], manual=manual, long_task=kind)

    scheduler.scene_graph_navigation.assert_not_called()
    scheduler.scene.assert_not_called()
    assert order.mock_calls[0] == call.home()
    assert (
        order.mock_calls[1].args[0]
        == {"rogue": "Roguelike", "copilot": "Copilot"}[kind]
    )
    assert order.mock_calls[2] == call.start()


def test_reclamation_keeps_its_theme_navigation(scheduler):
    base_schedule.config.conf.maa_long_task_type = "rcl"
    scheduler.to_reclamation = MagicMock()
    scheduler.scene_graph_navigation = MagicMock()
    order = MagicMock()
    order.attach_mock(scheduler.to_reclamation, "navigate")
    order.attach_mock(scheduler.MAA.append_task, "append")
    scheduler.maa_plan_solver([])
    assert order.mock_calls[0] == call.navigate(
        base_schedule.config.conf.maa_rcl_theme, base_schedule.config.conf.rcl.mode
    )
    assert order.mock_calls[1].args[0] == "Reclamation"
    scheduler.scene_graph_navigation.assert_not_called()


def test_blackflow_completion_survives_new_scheduler_and_requires_explicit_new_round(
    scheduler,
):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    conf.maa_long_task_type = "rogue"
    conf.maa_rg_theme = "BlackFlow"
    conf.rogue.mode = 30003

    def complete():
        scheduler.on_maa_callback(
            20003,
            json.dumps(
                {
                    "taskchain": "Roguelike",
                    "taskid": 1,
                    "what": "BlackFlowStartRun",
                    "details": {"status": "completed"},
                }
            ).encode(),
            None,
        )
        return False

    scheduler.MAA.running.side_effect = complete
    scheduler.maa_plan_solver([])
    assert record.load_maa_blackflow_progress()["completed"] is True
    for _ in range(3):
        scheduler.maa_plan_solver([])
    scheduler.MAA.append_task.assert_called_once()
    fresh = object.__new__(base_schedule.BaseSchedulerSolver)
    assert fresh._maa_blackflow_run(conf.rogue)["completed"] is True
    conf.rogue.blackflow_start_run_id = "new-round"
    scheduler.MAA.running.side_effect = None
    scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 2
    assert record.load_maa_blackflow_progress()["completed"] is False


@pytest.mark.parametrize(
    "status", ["preparing", "target_run", "reward_missed", "reward_unrecognized"]
)
def test_blackflow_noncompletion_and_unrelated_callbacks_do_not_finish_run(
    scheduler, status
):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    conf.maa_long_task_type = "rogue"
    conf.maa_rg_theme = "BlackFlow"
    conf.rogue.mode = 30003
    scheduler.maa_plan_solver([])
    for taskid, chain, current_status in [
        (1, "Roguelike", status),
        (2, "Roguelike", "completed"),
        (1, "Copilot", "completed"),
    ]:
        scheduler.on_maa_callback(
            20003,
            json.dumps(
                {
                    "taskchain": chain,
                    "taskid": taskid,
                    "what": "BlackFlowStartRun",
                    "details": {"status": current_status},
                }
            ).encode(),
            None,
        )
    assert record.load_maa_blackflow_progress()["completed"] is False
