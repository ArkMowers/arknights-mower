"""重建床位集合时保留适用的已观测恢复记录，并拒绝过期入住记录。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.tests.dorm_group_tests import solver as solver
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "dormitory_1"


@pytest.fixture(params=["free_only", "mixed_dynamic", "mixed_fixed"])
def recovery_snapshot(solver, monkeypatch, request):
    mode = request.param
    plans = solver.global_plan["default_plan"].plan
    plans["meeting"][1].group = "另一组"
    plans[ROOM][0].replacement = ["Free"] if mode == "free_only" else ["伊内丝"]
    plans[ROOM][0].group_bindings = [{"group": "另一组", "replacement": ["Free"]}]
    plans["dormitory_2"] = [
        Room("闪灵", "", []),
        Room("杜林", "", []),
        *[Room("Free", "", []) for _ in range(3)],
    ]
    assert solver.initialize_operators() is None
    data = solver.op_data
    for name in ("泥岩", "能天使", "年"):
        data.add(Operator(name, ""))
    fixed = mode == "mixed_fixed"
    work = {
        "meeting": ["陈", "银灰"] if fixed else ["伊内丝", "初雪"],
        "contact": ["红"] if fixed else ["讯使"],
    }
    apply_plan(solver, work)
    data.commit_group_shifts({"联动": False, "另一组": fixed})
    task = SchedulerTask(
        time=datetime.now() - timedelta(seconds=1),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"contact": ["Current"]},
    )
    task.group_shift_transitions = (
        {"联动": True, "另一组": False} if fixed else {"另一组": True}
    )
    incoming = "伊内丝" if fixed else "银灰"
    task.group_shift_expected = {
        (room, index): name
        for room, names in work.items()
        for index, name in enumerate(names)
    }
    task.group_shift_expected[ROOM, 0] = incoming
    solver.task, solver.tasks = task, [task]
    monkeypatch.setattr(record, "save_agent_action", lambda *a, **kw: None)
    data.update_detail(
        incoming, 5, ROOM, 0, group_transitions=task.group_shift_transitions
    )
    due = datetime.now() + timedelta(hours=2)
    bed = data.get_dorm_by_name(
        incoming, group_transitions=task.group_shift_transitions
    )[1]
    assert bed is not None and bed.name == incoming
    bed.time = due
    return solver, task, incoming, due


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_restore_retains_observed_bed_in_either_record_order(
    recovery_snapshot, confirmed, reverse
):
    solver, task, incoming, due = recovery_snapshot
    if confirmed:
        solver.op_data.commit_group_shifts(task.group_shift_transitions)
    saved = deepcopy(solver.op_data.all_dorms())
    if reverse:
        saved.reverse()
    occupants = deepcopy(solver.op_data.operators)
    states = dict(solver.op_data.group_shift_state)
    assert solver.initialize_operators() is None
    data = solver.op_data
    data.operators = occupants
    data.restore_group_shift_state(states)
    order = [bed.position for bed in data.all_dorms()]
    displaced = data.restore_dorm_state(
        saved, group_transitions=None if confirmed else task.group_shift_transitions
    )
    assert [bed.position for bed in data.all_dorms()] == order
    assert data.group_shift_state == states
    assert [(bed.name, bed.time) for bed in data.all_dorms() if bed.name] == [
        (incoming, due)
    ]
    assert not displaced
    task.plan.clear()
    assert solver._complete_group_shift(task)
    data.correct_dorm()
    assert data.get_dorm_by_name(incoming)[1].time == due


def test_restore_prefers_observed_occupant_and_reports_stale_record(recovery_snapshot):
    solver, task, incoming, due = recovery_snapshot
    data = solver.op_data
    saved = [Dormitory((ROOM, 0), "泥岩", due + timedelta(hours=1))]
    saved.extend(deepcopy(data.all_dorms()))
    for bed in data.all_dorms():
        bed.reset()
    displaced = data.restore_dorm_state(
        saved, group_transitions=task.group_shift_transitions
    )
    assert (
        data.get_dorm_by_name(incoming, group_transitions=task.group_shift_transitions)[
            1
        ].time
        == due
    )
    assert [(bed.name, bed.position) for bed in displaced] == [("泥岩", (ROOM, 0))]


def test_restore_does_not_replace_observed_fixed_resident(recovery_snapshot):
    solver, task, incoming, _ = recovery_snapshot
    data = solver.op_data
    saved = deepcopy(data.all_dorms())
    data.operators[incoming].current_room, data.operators[incoming].current_index = (
        "",
        -1,
    )
    data.operators["塑心"].current_room, data.operators["塑心"].current_index = ROOM, 0
    for bed in data.all_dorms():
        bed.reset()
    displaced = data.restore_dorm_state(
        saved, group_transitions=task.group_shift_transitions
    )
    assert all(not bed.name for bed in data.all_dorms())
    assert [bed.name for bed in displaced] == [incoming]
