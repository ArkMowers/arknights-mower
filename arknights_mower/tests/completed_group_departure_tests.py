"""已恢复主班让床和正常离宿保留整组回班边界。"""

from datetime import timedelta

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)


def prepare_group(solver, full_mood=24):
    data = solver.op_data
    names = PRIMARY[:2]
    data.groups["轮休"] = names
    for name in names:
        data.operators[name].group = "轮休"
    for bed, name in zip(data.dorm, PRIMARY[:3]):
        op = data.operators[name]
        op._current_room, op.current_index = bed.position
        op.mood = full_mood if name == names[0] else 10
        op.time_stamp = NOW
        bed.name = name
        bed.time = NOW + timedelta(hours=3)
    data.dorm[0].time = NOW - timedelta(minutes=1)
    plan = {}
    for name in names:
        op = data.operators[name]
        plan[op.room] = [name]
    task = SchedulerTask(
        time=NOW + timedelta(hours=3), task_type=TaskTypes.SHIFT_ON, task_plan=plan
    )
    return data, names, task


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("low_priority", [False, True])
@pytest.mark.parametrize("retained", [False, True])
def test_completed_primary_yields_bed_without_changing_group_return(
    solver, free_room, low_priority, retained
):
    data, names, return_task = prepare_group(solver)
    data.config.free_room = free_room
    data.operators[names[0]].resting_priority = "low" if low_priority else "high"
    if retained:
        data.config.free_room_exclusions.append(names[0])
    incoming = data.operators["陈"]
    incoming._current_room, incoming.current_index = "", -1
    incoming.mood = 5
    tasks = [return_task]

    try_add_release_dorm({}, None, data, tasks)

    assert return_task in tasks
    fills = [task for task in tasks if task is not return_task]
    if retained:
        assert fills == []
    else:
        assert len(fills) == 1
        assert set(fills[0].plan) == {"dormitory_1"}
        projected = data.project_arrangements([fills[0].plan])
        assert not projected.operators[names[0]].is_resting()
        assert projected.operators[names[1]].is_resting()
        assert projected.operators[incoming.name].is_resting()
    assert return_task.time == NOW + timedelta(hours=3)
    assert all(data.operators[name].is_resting() for name in names)
    assert incoming.current_room == ""


@pytest.mark.parametrize("index", [0, 2])
@pytest.mark.parametrize("stale_record", [False, True])
def test_fixed_dorm_return_keeps_named_confirmation_with_stale_recovery_record(
    monkeypatch, index, stale_record
):
    from arknights_mower.tests.same_group_dorm_replacement_tests import (
        RESIDENT,
        ROOM,
        WORKER,
        initialize,
        make_solver,
    )

    instance = make_solver(monkeypatch, reciprocal=True, index=index)
    initialize(instance)
    instance.op_data = instance.op_data.project_arrangements(
        [
            {
                "contact": [RESIDENT],
                ROOM: [WORKER if i == index else "Current" for i in range(5)],
            }
        ]
    )
    data = instance.op_data
    bed = data.get_dorm_by_name(WORKER)[1]
    assert bed is not None and bed.name == WORKER
    if stale_record:
        bed.name = ""
    row = ["Current"] * 5
    row[index] = RESIDENT
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"contact": [WORKER], ROOM: row}
    )
    task.group_shift_transitions = {"公招": False}
    task.group_shift_expected = {("contact", 0): WORKER, (ROOM, index): RESIDENT}
    instance.task, instance.tasks = task, [task]

    assert task.plan["contact"] == [WORKER]
    assert task.plan[ROOM][index] == RESIDENT
    instance.prepare_dorm_selection(task.plan[ROOM], ROOM)
    assert task.plan[ROOM][index] == RESIDENT
    assert task.group_shift_expected[ROOM, index] == RESIDENT
    assert bed.name == ("" if stale_record else WORKER)


@pytest.mark.parametrize("task_type", [TaskTypes.RELEASE_DORM, TaskTypes.RE_ORDER])
@pytest.mark.parametrize("upper_limit", [18, 24])
def test_ordinary_completed_departure_readback_preserves_group_return(
    solver, monkeypatch, task_type, upper_limit
):
    from unittest.mock import MagicMock

    from arknights_mower.solvers import record
    from arknights_mower.tests.emergency_release_failure_tests import (
        release_room_readback,
    )

    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    data, names, return_task = prepare_group(solver, full_mood=upper_limit)
    data.group_shift_state["轮休"] = True
    for name, cover_name in zip(PRIMARY[:3], COVERS):
        primary, cover = data.operators[name], data.operators[cover_name]
        cover._current_room, cover.current_index = primary.room, primary.index
    operator = data.operators[names[0]]
    operator.upper_limit = upper_limit
    operator.depletion_rate = -2
    if upper_limit < 24:
        data.config.operator_mood_limits[operator.name] = {
            "lower": 0,
            "upper": upper_limit,
        }
    data.add(Operator("芬", "", mood=5, time_stamp=NOW))
    room = operator.current_room
    row = data.get_current_room(room, True)
    row[operator.current_index] = "芬"
    task = SchedulerTask(
        task_type=task_type, task_plan={room: row}, meta_data=operator.name
    )
    solver.task, solver.tasks = task, [task, return_task]
    release_room_readback(solver, monkeypatch)

    solver.agent_arrange(task.plan, get_time=True)

    assert not operator.current_room
    assert operator.mood == upper_limit
    assert operator.time_stamp == NOW
    assert not operator.mood_is_prediction
    assert operator.depletion_rate == 0
    assert data.operators[names[1]].is_resting()
    assert data.operators["芬"].current_room == room
    assert data.group_is_resting("轮休")
    for _ in range(2):
        assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    assert return_task in solver.tasks
    assert return_task.time == NOW + timedelta(hours=3)
    assert return_task.plan == {data.operators[name].room: [name] for name in names}


@pytest.mark.parametrize(
    "unconfirmed",
    [
        "no_task",
        "no_plan",
        "prediction",
        "unknown",
        "below_limit",
        "partial",
        "mismatch",
    ],
)
@pytest.mark.parametrize("temporary", [False, True])
def test_unconfirmed_ordinary_departure_invalidates_old_measurement(
    solver, unconfirmed, temporary
):
    data, names, _ = prepare_group(solver)
    operator = data.operators[names[0]]
    room = operator.current_room
    row = data.get_current_room(room, True)
    row[operator.current_index] = ""
    task = SchedulerTask(task_type=TaskTypes.RELEASE_DORM, task_plan={room: row.copy()})
    solver.task = task
    if unconfirmed == "no_task":
        solver.task = None
    elif unconfirmed == "no_plan":
        task.plan.clear()
    elif unconfirmed == "prediction":
        operator.mood_is_prediction = True
    elif unconfirmed == "unknown":
        operator.time_stamp = None
    elif unconfirmed == "below_limit":
        operator.mood = operator.upper_limit - 0.1
    expected = row.copy() if temporary and room in task.plan else None
    if temporary and room in task.plan:
        task.plan[room][operator.current_index] = "Free"
    if unconfirmed == "mismatch":
        row[-1] = ""
    observed = [{"agent": name} for name in row]
    if unconfirmed == "partial":
        observed[-1]["observed"] = False

    solver._reconcile_room_observation(room, observed, expected_agents=expected)

    assert not operator.current_room
    assert operator.time_stamp is None


@pytest.mark.parametrize("unconfirmed", ["occupied_tail", "partial"])
def test_short_roster_requires_confirmed_empty_remaining_slots(solver, unconfirmed):
    data, names, _ = prepare_group(solver)
    operator = data.operators[names[0]]
    room = operator.current_room
    expected = data.get_current_room(room, True)[:2]
    solver.task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, task_plan={room: expected.copy()}
    )
    observed = [{"agent": name} for name in expected + ["", "", ""]]
    if unconfirmed == "occupied_tail":
        observed[-1]["agent"] = "芬"
    else:
        observed[-1]["observed"] = False

    solver._reconcile_room_observation(room, observed, expected_agents=expected)

    assert not operator.current_room
    assert operator.time_stamp is None
    assert solver.task.plan == {room: expected}
