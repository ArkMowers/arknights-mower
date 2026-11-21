"""副表切换的最终提示保留替班匹配或分床失败的具体原因。"""

import copy
import pickle
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

with pytest.MonkeyPatch.context() as imports:
    imports.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.tests import shift_backup_convergence_tests as convergence

from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Room

solver = convergence.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


def joining_member(solver):
    solver.op_data.backup_plans[0].plan["room_1_2"][1].replacement = ["梓兰"]
    solver.op_data.backup_plans[0].plan["contact"] = [Room("食铁兽", "红松", ["砾"])]
    plans = copy.deepcopy(solver.op_data.global_plan)
    plans["default_plan"].plan["room_1_2"][1].replacement = ["斑点"]
    plans["default_plan"].plan["dormitory_1"][1] = Room("Free", "", [])
    plans["default_plan"].config.free_room_exclusions = ["桃金娘"]
    solver.op_data = Operators(plans)
    assert solver.op_data.init_and_validate() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, datetime.now()
    resident = solver.op_data.operators["桃金娘"]
    resident._current_room, resident.current_index = "dormitory_1", 1
    bed = next(bed for bed in solver.op_data.dorm if bed.position == ("dormitory_1", 1))
    bed.name = "桃金娘"
    solver.op_data.first_init = False
    task = convergence.downshift(solver)
    task.plan["room_1_2"][1] = "斑点"
    return task


def test_shift_failure_reports_bed_admission_and_member(solver):
    task = joining_member(solver)
    original_plan = copy.deepcopy(task.plan)
    original_time = task.time
    before = convergence.positions(solver.op_data)

    with pytest.raises(convergence.base.ProductSwitchDeferred) as caught:
        solver._prepare_shift_cycle(task)

    reason = str(caught.value)
    assert "食铁兽" in reason
    assert "宿舍" in reason
    assert "替班暂不可用" not in reason
    assert task.time == original_time
    assert task.plan == original_plan
    assert convergence.positions(solver.op_data) == before
    assert solver.op_data.plan_condition == [False]


def test_direct_backup_failure_logs_bed_admission_and_member(solver, monkeypatch):
    task = joining_member(solver)
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    solver.op_data.commit_group_shifts({"红松": True})
    solver.task, solver.tasks = None, []
    before = convergence.positions(solver.op_data)
    info = MagicMock()
    monkeypatch.setattr(convergence.base.logger, "info", info)

    assert not solver.backup_plan_solver()

    messages = [str(call.args[0]) % call.args[1:] for call in info.call_args_list]
    assert any("食铁兽" in text and "宿舍" in text for text in messages)
    assert convergence.positions(solver.op_data) == before
    assert solver.op_data.plan_condition == [False]


def test_dispatch_retains_specific_reason_with_original_task(solver):
    task = joining_member(solver)
    original_plan, original_time = copy.deepcopy(task.plan), task.time
    solver.agent_arrange = MagicMock()

    solver.infra_main()

    assert solver.tasks == [task]
    assert task.plan == original_plan
    assert task.time == original_time
    assert "食铁兽" in task.execution_failure["reason"]
    assert "宿舍床位" in task.execution_failure["reason"]
    saved = pickle.loads(pickle.dumps(task))
    assert saved.execution_failure == task.execution_failure
    solver.agent_arrange.assert_not_called()
