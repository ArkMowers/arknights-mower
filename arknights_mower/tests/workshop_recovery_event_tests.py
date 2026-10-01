"""加工结束按实际恢复现场触发宿舍规划，不依赖五分钟空档。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests.dorm_release_tests import ROOM
from arknights_mower.tests.dorm_release_tests import op_data as op_data
from arknights_mower.tests.workshop_batch_tests import batch as batch
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


def test_batch_replans_once_after_actual_restoration(batch):
    solver = batch.solver

    def replan():
        for room, names in solver.op_data.plan.items():
            for index, name in enumerate(names):
                op = solver.op_data.operators[name]
                assert (op.current_room, op.current_index) == (room, index)
        assert all(solver.op_data.operators[name].mood == 0 for name in batch.crafts)
        return True

    solver._plan_dorm_recovery.side_effect = replan
    solver.craft_material()

    assert batch.crafts == ["蜜莓", "年", "空爆"]
    solver._plan_dorm_recovery.assert_called_once_with()
    assert solver.agent_arrange.call_args.kwargs == {"get_time": True}
    solver.op_data.refresh_idle_dorm_search.assert_called_once()


def test_failed_restoration_does_not_plan_from_unconfirmed_positions(batch):
    solver = batch.solver
    arrange = solver.agent_arrange.side_effect

    def fail_restore(plan, get_time=False):
        if len(plan) > 1:
            raise RuntimeError("restore failed")
        return arrange(plan, get_time)

    solver.agent_arrange.side_effect = fail_restore
    solver.craft_material()

    assert batch.crafts
    solver._plan_dorm_recovery.assert_not_called()
    batch.errors.assert_called_once()


def test_idle_crafter_replaces_full_resident_despite_nearby_task(op_data):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = op_data
    op_data.operators["银灰"].current_room = "meeting"
    op_data.operators["银灰"].current_index = 0
    crafter = op_data.operators["红"]
    crafter.mood = 24
    solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="红")
    nearby = SchedulerTask(
        time=datetime.now() + timedelta(seconds=30), task_type=TaskTypes.REFRESH_TIME
    )
    solver.tasks = [solver.task, nearby]
    solver._plan_primary_recovery = MagicMock(return_value=True)

    def craft(restoration):
        crafter.current_room, crafter.current_index = "factory", 0
        crafter.mood, crafter.time_stamp = 0, datetime.now()
        restoration["factory"] = ["空爆"]
        return crafter.name

    def restore(plan, get_time=False):
        assert get_time
        crafter.current_room, crafter.current_index = "", -1

    solver._craft_material = MagicMock(side_effect=craft)
    solver.agent_arrange = MagicMock(side_effect=restore)
    solver.craft_material()

    replacements = [task for task in solver.tasks if task not in (solver.task, nearby)]
    assert [deepcopy(task.plan) for task in replacements] == [
        {ROOM: ["Current"] * 4 + ["红"]}
    ]
    assert op_data.operators["空爆"].current_room == ROOM
    solver._plan_primary_recovery.assert_called_once_with()
