"""排除层级不迁入动态床位，也不留下无法完成的换班目标。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests.group_shift_confirmation_tests import observe_arrangement
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    rebalance_closing_dorm_slots,
    rebalance_plan_swap_dorms,
)


@pytest.fixture
def dorm_solver(solver):
    solver.global_plan["default_plan"].plan["dormitory_2"] = [
        Room(name, "", []) for name in ["杜林", "车尔尼", "爱丽丝", "Free", "Free"]
    ]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    for name in ["但书", "诗怀雅"]:
        solver.op_data.add(Operator(name, ""))
        solver.op_data.operators[name].mood = 14 if name == "但书" else 24
        solver.op_data.operators[name].time_stamp = datetime.now()
    return solver


@pytest.mark.parametrize("reorder", [False, True])
@pytest.mark.parametrize("source", ["snapshot", "current", "displaced"])
@pytest.mark.parametrize("exclusion", ["blacklist", "workaholic"])
def test_rebalance_releases_excluded_resident_without_migrating(
    dorm_solver, reorder, source, exclusion
):
    data = dorm_solver.op_data
    if exclusion == "blacklist":
        data.config.free_blacklist.append("但书")
    else:
        data.operators["但书"].workaholic = True
    observe_arrangement(dorm_solver, {"dormitory_2": ["Current"] * 4 + ["但书"]})
    data.operators["但书"].dorm_recovery_room = "dormitory_2"
    data.operators["但书"].dorm_recovery_index = 4
    bed = data.get_dorm_by_name("但书")[1]
    bed.time = datetime.now() + timedelta(hours=2)
    previous = deepcopy(data.dorm) if source == "snapshot" else None
    if source == "displaced":
        data.displaced_dorms = [deepcopy(bed)]
        bed.reset()

    plan = rebalance_plan_swap_dorms(data, previous, reorder=reorder)

    assert "但书" not in [name for names in plan.values() for name in names]
    assert plan["dormitory_2"][4] == "Free"
    assert all(bed.name != "但书" for bed in data.dorm)
    assert not data.operators["但书"].dorm_recovery_room
    # 规划只改变床位预约；实际位置等待执行读回。
    assert data.get_current_operator("dormitory_2", 4).name == "但书"


def test_closing_beds_does_not_move_excluded_resident(dorm_solver):
    data = dorm_solver.op_data
    data.config.free_blacklist.append("但书")
    observe_arrangement(dorm_solver, {"dormitory_2": ["Current"] * 4 + ["但书"]})
    data.plan["dormitory_2"][4] = Room("爱丽丝", "", ["Free"])
    plan = {"dormitory_2": ["Current"] * 4 + ["爱丽丝"]}

    rebalance_closing_dorm_slots(data, plan, set())

    assert "但书" not in [name for names in plan.values() for name in names]
    assert all(bed.name != "但书" for bed in data.dorm)


@pytest.mark.parametrize("other_confirmed", [False, True])
@pytest.mark.parametrize("selection_prepared", [False, True])
@pytest.mark.parametrize("exclusion", ["blacklist", "workaholic"])
def test_excluded_dorm_target_cannot_requeue_after_replacement(
    dorm_solver, other_confirmed, selection_prepared, exclusion
):
    data = dorm_solver.op_data
    task = SchedulerTask(
        task_type=TaskTypes.RE_ORDER,
        task_plan={
            "meeting": ["Current", "初雪"],
            "dormitory_1": ["Current", "Current", "但书", "Current", "Current"],
        },
    )
    dorm_solver.task, dorm_solver.tasks = task, [task]
    dorm_solver._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_expected["dormitory_1", 2] == "但书"
    if exclusion == "blacklist":
        data.config.free_blacklist.append("但书")
    else:
        data.operators["但书"].workaholic = True
    observe_arrangement(
        dorm_solver,
        {"dormitory_1": ["Current", "Current", "诗怀雅", "Current", "Current"]},
    )
    if other_confirmed:
        observe_arrangement(
            dorm_solver,
            {
                room: names
                for room, names in task.plan.items()
                if not room.startswith("dorm")
            },
        )
    if selection_prepared:
        dorm_solver.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")
        assert task.plan["dormitory_1"][2] == "诗怀雅"
    task.plan.clear()

    assert dorm_solver._complete_group_shift(task) is other_confirmed
    assert "但书" not in task.group_shift_expected.values()
    if not other_confirmed:
        assert task.plan == {"meeting": ["Current", "初雪"], "contact": ["黑角"]}
        observe_arrangement(dorm_solver, task.plan)
        task.plan.clear()
        assert dorm_solver._complete_group_shift(task)


@pytest.mark.parametrize("excluded", [False, True])
def test_fixed_dorm_target_still_requires_observation(dorm_solver, excluded):
    data = dorm_solver.op_data
    if excluded:
        data.config.free_blacklist.append("塑心")
    task = SchedulerTask(task_type=TaskTypes.RE_ORDER)
    task.group_shift_transitions = {}
    task.group_shift_expected = {("dormitory_1", 0): "塑心"}
    data.operators["塑心"]._current_room = ""
    data.operators["塑心"].current_index = -1

    assert not dorm_solver._complete_group_shift(task)
    assert task.plan == {"dormitory_1": ["塑心", *["Current"] * 4]}


def test_eligible_dorm_target_still_requires_observation(dorm_solver):
    task = SchedulerTask(task_type=TaskTypes.RE_ORDER)
    task.group_shift_transitions = {}
    task.group_shift_expected = {("dormitory_1", 2): "但书"}

    assert not dorm_solver._complete_group_shift(task)
    assert task.plan == {
        "dormitory_1": ["Current", "Current", "但书", "Current", "Current"]
    }


def test_zero_measured_mood_without_workaholic_setting_remains_eligible(dorm_solver):
    data = dorm_solver.op_data
    data.operators["但书"].mood = 0
    observe_arrangement(dorm_solver, {"dormitory_2": ["Current"] * 4 + ["但书"]})
    bed = data.get_dorm_by_name("但书")[1]
    deadline = bed.time = datetime.now() + timedelta(hours=6)

    assert rebalance_plan_swap_dorms(data) == {}
    assert data.get_dorm_by_name("但书")[1].time == deadline
