"""已恢复主班保床，明确离宿补偿保留整组恢复边界。"""

from datetime import timedelta

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    dorm_residents,
    restore_displaced_resting,
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
def test_completed_primary_keeps_group_beds_until_ordinary_return(
    solver, free_room, low_priority
):
    data, names, return_task = prepare_group(solver)
    data.config.free_room = free_room
    data.operators[names[0]].resting_priority = "low" if low_priority else "high"
    incoming = data.operators["陈"]
    incoming._current_room, incoming.current_index = "", -1
    incoming.mood = 5
    tasks = [return_task]

    try_add_release_dorm({}, None, data, tasks)

    assert tasks == [return_task]
    assert return_task.time == NOW + timedelta(hours=3)
    assert all(data.operators[name].is_resting() for name in names)
    assert incoming.current_room == ""


@pytest.mark.parametrize("measured", [True, False])
def test_expired_timer_or_unknown_mood_does_not_establish_completed_departure(
    solver, measured
):
    data, names, return_task = prepare_group(solver, full_mood=12 if measured else 24)
    if not measured:
        data.operators[names[0]].time_stamp = None
    before = dorm_residents(data)
    plan = {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]}
    tasks = [return_task]

    restore_displaced_resting(data, before, plan, tasks)

    assert all(data.operators[name].room in plan for name in names)
    assert return_task not in tasks


@pytest.mark.parametrize("index", [0, 2])
@pytest.mark.parametrize("stale_record", [False, True])
def test_fixed_dorm_return_survives_old_recovery_cleanup(
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
    before = dorm_residents(data)
    bed = data.get_dorm_by_name(WORKER)[1]
    assert bed is not None and before[ROOM, index] == WORKER
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

    restore_displaced_resting(
        data,
        before,
        task.plan,
        instance.tasks,
        group_transitions=task.group_shift_transitions,
    )

    assert task.plan["contact"] == [WORKER]
    assert task.plan[ROOM][index] == RESIDENT
    instance.prepare_dorm_selection(task.plan[ROOM], ROOM)
    assert task.plan[ROOM][index] == RESIDENT
    assert task.group_shift_expected[ROOM, index] == RESIDENT
    assert not bed.name


def test_displaced_group_releases_old_bed_but_keeps_new_arrival(solver):
    data, names, return_task = prepare_group(solver, full_mood=12)
    before = dorm_residents(data)
    incoming = "陈"
    plan = {"dormitory_1": ["Current", "Current", incoming, "Current", "Current"]}
    tasks = [return_task]

    restore_displaced_resting(data, before, plan, tasks)

    assert plan["dormitory_1"][2] == incoming
    assert plan["dormitory_1"][3] == "Free"
    for name in names:
        op = data.operators[name]
        assert plan[op.room][op.index] == name
    assert return_task not in tasks


@pytest.mark.parametrize("conflict", ["return_slot", "other_destination"])
def test_recall_conflict_keeps_original_and_fills_only_available_returns(
    solver, conflict
):
    data, names, return_task = prepare_group(solver, full_mood=12)
    previous = dorm_residents(data)
    plan = {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]}
    blocked = data.operators[names[1]]
    if conflict == "return_slot":
        plan[blocked.room] = ["夜刀"]
    else:
        plan["dormitory_1"][3] = names[1]
    original_targets = {
        (room, index): name
        for room, row in plan.items()
        for index, name in enumerate(row)
        if name not in ("Current", "Free", "")
    }
    _, retained_bed = data.get_dorm_by_name(names[1])
    retained_state = retained_bed.name, retained_bed.time
    tasks = [return_task]
    original_time = return_task.time

    restore_displaced_resting(data, previous, plan, tasks)

    for (room, index), name in original_targets.items():
        assert plan[room][index] == name
    first = data.operators[names[0]]
    assert plan[first.room][first.index] == names[0]
    assert (retained_bed.name, retained_bed.time) == retained_state
    assert tasks == [return_task]
    assert return_task.time == original_time
    assert return_task.plan == {blocked.room: [names[1]]}
    assert plan.get(blocked.room, ["Current"])[blocked.index] != names[1]
