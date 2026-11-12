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
def test_large_task_enters_terminal_before_maa_submission(scheduler, kind, manual):
    base_schedule.config.conf.maa_long_task_type = kind
    scheduler.task = SimpleNamespace(type=None)
    scheduler.scene_graph_navigation = MagicMock()
    scheduler.scene = MagicMock(
        return_value=Scene.OPERATOR_CHOOSE_LEVEL
        if kind == "copilot"
        else Scene.TERMINAL_MAIN
    )
    order = MagicMock()
    order.attach_mock(scheduler.back_to_index, "home")
    order.attach_mock(scheduler.scene_graph_navigation, "navigate")
    if kind == "copilot":
        order.attach_mock(base_schedule.NavigationSolver.return_value.run, "map")
    order.attach_mock(scheduler.MAA.append_task, "append")
    order.attach_mock(scheduler.MAA.start, "start")

    scheduler.maa_plan_solver([], manual=manual, long_task=kind)

    assert order.mock_calls[:2] == [call.home(), call.navigate(Scene.TERMINAL_MAIN)]
    if kind == "copilot":
        assert order.mock_calls[2:4] == [
            call.map("1-7"),
            call.navigate(Scene.OPERATOR_CHOOSE_LEVEL),
        ]
        append_index = 4
    else:
        append_index = 2
    assert (
        order.mock_calls[append_index].args[0]
        == {"rogue": "Roguelike", "copilot": "Copilot"}[kind]
    )
    assert order.mock_calls[append_index + 1] == call.start()


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


def boss_pause_payload():
    return {
        "taskchain": "Roguelike",
        "taskid": 1,
        "subtask": "ProcessTask",
        "what": "ExceededLimit",
        "details": {
            "task": "BlackFlow@Roguelike@StageDreadfulFoe-5",
            "exec_times": 0,
            "max_times": 0,
        },
    }


@pytest.mark.parametrize("manual", [False, True])
def test_blackflow_boss_pause_is_preserved_across_dispatch_and_restart(
    scheduler, manual
):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    conf.maa_long_task_type = "rogue"
    conf.maa_rg_theme = "BlackFlow"
    conf.rogue.mode = 0
    conf.rogue.stop_at_final_boss = True
    scheduler.task = SimpleNamespace(type=None)
    original = scheduler.tasks[0]
    original_time = original.time
    opening = {"key": "existing-opening", "completed": True}
    record.save_maa_blackflow_progress(opening)

    def pause():
        scheduler.on_maa_callback(
            20003, json.dumps(boss_pause_payload()).encode(), None
        )
        return False

    scheduler.MAA.running.side_effect = pause
    scheduler.maa_plan_solver([], manual=manual, long_task="rogue")
    assert scheduler.MAA.append_task.call_args.args[1]["stop_at_final_boss"] is True
    assert record.load_maa_blackflow_progress(boss=True)["completed"] is True
    for _ in range(3):
        scheduler.maa_plan_solver([], manual=manual, long_task="rogue")
    conf.maa_rg_enable = 0
    scheduler.maa_plan_solver([])
    conf.maa_rg_enable = 1
    scheduler.maa_plan_solver([], manual=manual, long_task="rogue")
    scheduler.MAA.append_task.assert_called_once()
    assert scheduler.tasks == [original]
    assert original.time == original_time

    record._tables_created = False
    fresh = object.__new__(base_schedule.BaseSchedulerSolver)
    fresh.__dict__.update(scheduler.__dict__)
    fresh.maa_plan_solver([], manual=manual, long_task="rogue")
    scheduler.MAA.append_task.assert_called_once()
    assert fresh._maa_blackflow_run(conf.rogue)["completed"] is True

    scheduler.MAA.running.side_effect = None
    conf.maa_long_task_type = "copilot"
    scheduler.maa_plan_solver([], manual=manual, long_task="copilot")
    assert scheduler.MAA.append_task.call_count == 2
    assert scheduler.MAA.append_task.call_args.args[0] == "Copilot"
    assert scheduler.tasks == [original]

    conf.maa_long_task_type = "rogue"
    conf.rogue.blackflow_boss_run_id = "explicit-new-boss-round"
    scheduler.maa_plan_solver([], manual=manual, long_task="rogue")
    assert scheduler.MAA.append_task.call_count == 3
    assert scheduler.MAA.append_task.call_args.args[0] == "Roguelike"
    assert record.load_maa_blackflow_progress(boss=True)["completed"] is False
    assert record.load_maa_blackflow_progress() == opening


@pytest.mark.parametrize(
    "msg,outer,inner",
    [
        (10002, {}, {}),
        (10004, {}, {}),
        (20000, {}, {}),
        (20003, {"taskid": 2}, {}),
        (20003, {"taskid": True}, {}),
        (20003, {"taskchain": "Copilot"}, {}),
        (20003, {"subtask": "Other"}, {}),
        (20003, {"what": "BlackFlowStartRun"}, {"status": "completed"}),
        (20003, {"what": "BlackFlowStrategyResult"}, {"succeeded": True}),
        (20003, {}, {"task": "BlackFlow@Roguelike@StageDreadfulFoe-3"}),
        (20003, {}, {"task": "StageDreadfulFoe-5"}),
        (20003, {}, {"max_times": 1}),
        (20003, {}, {"exec_times": 1}),
        (20003, {}, {"max_times": False}),
        (20003, {}, {"exec_times": "0"}),
    ],
)
def test_blackflow_boss_pause_requires_its_current_task_and_exact_stop_callback(
    scheduler, msg, outer, inner
):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    conf.maa_long_task_type = "rogue"
    conf.maa_rg_theme = "BlackFlow"
    conf.rogue.mode = 0
    conf.rogue.stop_at_final_boss = True
    scheduler.maa_plan_solver([])
    data = boss_pause_payload()
    data.update(outer)
    data["details"].update(inner)
    scheduler.on_maa_callback(msg, json.dumps(data).encode(), None)
    assert record.load_maa_blackflow_progress(boss=True)["completed"] is False


def test_boss_callback_does_not_complete_opening_run(scheduler):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    conf.maa_long_task_type = "rogue"
    conf.maa_rg_theme = "BlackFlow"
    conf.rogue.mode = 30003
    scheduler.maa_plan_solver([])
    scheduler.on_maa_callback(20003, json.dumps(boss_pause_payload()).encode(), None)
    assert record.load_maa_blackflow_progress()["completed"] is False
    assert record.load_maa_blackflow_progress(boss=True) == {}


@pytest.mark.parametrize(
    "field,value",
    [("difficulty", 6), ("squad", "指挥分队"), ("investment_enabled", False)],
)
def test_boss_round_can_restart_when_its_settings_change(scheduler, field, value):
    from arknights_mower.solvers import record

    conf = base_schedule.config.conf
    conf.maa_long_task_type = "rogue"
    conf.maa_rg_theme = "BlackFlow"
    conf.rogue.mode = 0
    conf.rogue.stop_at_final_boss = True
    scheduler.maa_plan_solver([])
    scheduler.on_maa_callback(20003, json.dumps(boss_pause_payload()).encode(), None)
    before = record.load_maa_blackflow_progress(boss=True)
    setattr(conf.rogue, field, value)
    scheduler.maa_plan_solver([])
    assert scheduler.MAA.append_task.call_count == 2
    after = record.load_maa_blackflow_progress(boss=True)
    assert after["key"] != before["key"]
    assert after["completed"] is False
