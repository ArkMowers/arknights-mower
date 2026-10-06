"""已恢复组员让床保留未恢复成员及整组回班任务。"""

from datetime import timedelta

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    dorm_residents,
    plan_metadata,
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
def test_completed_group_member_fill_keeps_unfinished_group_resting(
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

    fill = next(task for task in tasks if task is not return_task)
    assert set(fill.plan) == {"dormitory_1"}
    assert return_task in tasks
    assert return_task.time == NOW + timedelta(hours=3)
    projected = data.project_arrangements([fill.plan])
    assert projected.operators[names[0]].current_room == ""
    assert projected.operators[names[1]].is_resting()
    assert data.operators[names[0]].is_resting()
    # 换床执行后读房重新建立恢复时间，仍由未完成成员带整组回班。
    _, remaining_bed = projected.get_dorm_by_name(names[1])
    remaining_bed.time = NOW + timedelta(hours=3)
    rebuilt = plan_metadata(projected, [return_task])
    assert any(
        task.type == TaskTypes.SHIFT_ON
        and all(
            name in [n for row in task.plan.values() for n in row] for name in names
        )
        and task.time > NOW
        for task in rebuilt
    )


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
