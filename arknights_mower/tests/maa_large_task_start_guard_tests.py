from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, manual_tasks
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

files = helpers.files
scheduler = helpers.scheduler


@pytest.mark.parametrize(
    "kind,phase",
    [
        (kind, phase)
        for kind in ("rogue", "copilot")
        for phase in ("home", "terminal", "append")
    ]
    + [("copilot", "map")],
)
@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize(
    "outcome", ["maa_stop", "mower_stop", "deadline_30", "deadline_29"]
)
def test_large_task_rechecks_stop_and_deadline_before_start(
    scheduler, monkeypatch, kind, manual, phase, outcome
):
    now = datetime.now()

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(manual_tasks, "datetime", Clock)
    base_schedule.config.conf.maa_long_task_type = kind
    pending = scheduler.tasks[0]
    pending.time = now + timedelta(hours=2)
    scheduler.device = MagicMock()
    scheduler.scene_graph_navigation = MagicMock()
    scheduler.scene = MagicMock(
        return_value=Scene.OPERATOR_CHOOSE_LEVEL
        if kind == "copilot"
        else Scene.TERMINAL_MAIN
    )
    if manual:
        scheduler.task = SchedulerTask(now, task_type=TaskTypes.ROGUELIKE)
        scheduler.tasks.insert(0, scheduler.task)
    original_tasks = list(scheduler.tasks)

    def interrupt(*args):
        if outcome == "maa_stop":
            base_schedule.config.stop_maa.set()
        elif outcome == "mower_stop":
            base_schedule.config.stop_mower.set()
        else:
            pending.time = now + timedelta(seconds=int(outcome.rsplit("_", 1)[1]))
        return 1

    target = {
        "home": scheduler.back_to_index,
        "terminal": scheduler.scene_graph_navigation,
        "map": base_schedule.NavigationSolver.return_value.run,
        "append": scheduler.MAA.append_task,
    }[phase]
    target.side_effect = interrupt
    if outcome == "mower_stop":
        with pytest.raises(MowerExit):
            scheduler.maa_plan_solver([], manual=manual, long_task=kind)
    else:
        assert scheduler.maa_plan_solver([], manual=manual, long_task=kind)
    target.assert_called_once()
    scheduler.MAA.start.assert_not_called()
    if phase != "append":
        scheduler.MAA.append_task.assert_not_called()
    assert scheduler.tasks == original_tasks


@pytest.mark.parametrize("kind", ["rogue", "copilot"])
@pytest.mark.parametrize("manual", [False, True])
def test_large_task_can_start_with_more_than_thirty_seconds(
    scheduler, monkeypatch, kind, manual
):
    now = datetime.now()

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(manual_tasks, "datetime", Clock)
    base_schedule.config.conf.maa_long_task_type = kind
    scheduler.tasks[0].time = now + timedelta(seconds=31)
    scheduler.scene_graph_navigation = MagicMock()
    scheduler.scene = MagicMock(
        return_value=Scene.OPERATOR_CHOOSE_LEVEL
        if kind == "copilot"
        else Scene.TERMINAL_MAIN
    )
    if manual:
        scheduler.task = SchedulerTask(now, task_type=TaskTypes.ROGUELIKE)
        scheduler.tasks.insert(0, scheduler.task)
    scheduler.maa_plan_solver([], manual=manual, long_task=kind)
    scheduler.MAA.append_task.assert_called_once()
    scheduler.MAA.start.assert_called_once()


@pytest.mark.parametrize("kind", ["rogue", "copilot", "paradox", "sss", "rcl"])
@pytest.mark.parametrize("preempted", [False, True])
def test_large_task_does_not_restore_theme_even_when_enabled(
    scheduler, monkeypatch, kind, preempted
):
    from arknights_mower.utils import maa_copilot
    from arknights_mower.utils.config.conf import Conf

    conf = base_schedule.config.conf
    conf.maa_long_task_type = kind
    conf.maa_restore_theme_enable = True
    conf.maa_restore_theme = "夜间"
    scheduler.scene_graph_navigation = MagicMock()
    scheduler.scene = MagicMock(
        return_value=Scene.OPERATOR_CHOOSE_LEVEL
        if kind == "copilot"
        else Scene.TERMINAL_MAIN
    )
    scheduler.to_operator_list = MagicMock(return_value=True)
    scheduler.to_sss = MagicMock(return_value=False)
    scheduler.to_reclamation = MagicMock()
    if kind == "paradox":
        info = maa_copilot.store_script(
            b'{"stage_name":"mem_test_1","actions":[]}', paradox=True
        )
        conf.paradox = Conf(paradox={"scripts": [{"id": info["id"]}]}).paradox
    elif kind == "sss":
        info = maa_copilot.store_script(
            b'{"type":"SSS","stage_name":"SSS","tool_men":{},"stages":[{"stage_name":"one","draw_as_possible":true,"strategies":[],"actions":[]}]}',
            sss=True,
        )
        conf.sss = Conf(sss={"scripts": [{"id": info["id"]}]}).sss
    scheduler.MAA.running.return_value = preempted

    def tick(_):
        scheduler.tasks[0].time = datetime.now() + timedelta(seconds=25)

    monkeypatch.setattr(base_schedule, "csleep", tick)
    scheduler.maa_plan_solver([])
    scheduler.MAA.start.assert_called_once()
    scheduler.restore_maa_theme.assert_not_called()
    if preempted:
        scheduler.maa_stop.assert_called_once()
