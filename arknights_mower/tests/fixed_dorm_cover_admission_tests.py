"""固定宿舍替班可留任自己的岗位，其他岗位仍不能借走。"""

from copy import deepcopy
from datetime import datetime

import pytest

from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.tests.dorm_group_tests import solver as solver
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, try_reorder

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def occupied_covers(solver):
    slots = solver.global_plan["default_plan"].plan["dormitory_1"]
    slots[:2] = [Room("琴柳", "联动", ["赫默"]), Room("蜜莓", "联动", ["埃癸斯"])]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.group else 24, datetime.now()
    apply_plan(
        solver, {"dormitory_1": ["赫默", "埃癸斯", "Current", "Current", "Current"]}
    )
    return solver


@pytest.mark.parametrize("mood", [0, 24])
@pytest.mark.parametrize("full_cycle", [False, True])
def test_own_fixed_covers_admit_and_confirm_complete_group(
    occupied_covers, mood, full_cycle
):
    s = occupied_covers
    data = s.op_data
    for name in ("赫默", "埃癸斯"):
        data.operators[name].mood = mood
    before = {n: (o.current_room, o.current_index) for n, o in data.operators.items()}
    plan, replacements = {}, []
    assert s.get_resting_plan(data.groups["联动"].copy(), replacements, plan, 0)
    assert plan["dormitory_1"][:2] == ["赫默", "埃癸斯"]
    assert not data.is_auto_free_dorm_slot("dormitory_1", 0)
    assert not data.is_auto_free_dorm_slot("dormitory_1", 1)
    plan.update(try_reorder(data, plan) or {})
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=plan)
    s.task, s.tasks = task, [task]
    if full_cycle:
        s._prepare_group_shift(task)
        s._prepare_shift_cycle(task)
    s._prepare_group_shift(task, remember_targets=True)
    assert not data.group_is_resting("联动")
    assert before == {
        n: (o.current_room, o.current_index) for n, o in data.operators.items()
    }
    projected = data.project_arrangements([task.plan])
    data.operators, data.dorm = projected.operators, projected.dorm
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert data.group_is_resting("联动")
    assert data.get_current_room("dormitory_1", True)[:2] == ["赫默", "埃癸斯"]


@pytest.mark.parametrize(
    "blocked_by", ["other_slot", "other_room", "reserved", "claimed"]
)
def test_retaining_cover_does_not_allow_borrowing_or_double_booking(
    occupied_covers, blocked_by
):
    s = occupied_covers
    data = s.op_data
    used = []
    if blocked_by == "other_slot":
        data.operators["赫默"].current_index = 1
        data.plan["dormitory_1"][1].replacement.append("赫默")
    elif blocked_by == "other_room":
        data.plan["dormitory_2"] = deepcopy(data.plan["dormitory_1"])
        data.operators["赫默"]._current_room = "dormitory_2"
    elif blocked_by == "reserved":
        lock = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
        lock.product_shift_locked = True
        lock.product_lock_names = {"赫默"}
        s.tasks = [lock]
    else:
        used = ["赫默"]
    plan = {}
    before = deepcopy(data.group_shift_state)
    assert not s.get_resting_plan(data.groups["联动"].copy(), used, plan, 0)
    assert plan == {}
    assert data.group_shift_state == before
