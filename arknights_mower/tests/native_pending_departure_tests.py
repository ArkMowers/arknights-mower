"""普通下班的完整待执行安排保留原请求，无关组继续规划。"""

from datetime import datetime, timedelta

from arknights_mower.tests import native_replacement_coordination_tests as source
from arknights_mower.utils.scheduler_task import TaskTypes

solver = source.solver
isolate_live_log_delivery = source.isolate_live_log_delivery


def test_ordinary_planning_keeps_original_departure_and_plans_unrelated_group(solver):
    old = source._queue_ordinary_departure(solver)
    old.time = datetime.now() - timedelta(hours=3)
    old.execution_retained = True
    original_time, original_plan = (
        old.time,
        {room: list(row) for room, row in old.plan.items()},
    )
    solver.task = None
    data = solver.op_data
    data.operators["能天使"].mood = 0
    solver.total_agent = list(data.operators.values())
    plan = solver.resting()
    assert "room_3_3" not in plan
    assert plan["meeting"] == ["陈"]
    unrelated = next(
        task
        for task in solver.tasks
        if task is not old and task.plan.get("meeting") == ["陈"]
    )
    data = solver.op_data
    bed = next(
        bed
        for bed in data.dorm
        if data.get_current_operator(*bed.position) is None
        and old.plan.get(bed.position[0], [])[bed.position[1] : bed.position[1] + 1]
        == ["Current"]
    )
    completed = {room: list(row) for room, row in unrelated.plan.items()}
    completed[bed.position[0]] = ["Current"] * len(data.plan[bed.position[0]])
    completed[bed.position[0]][bed.position[1]] = "能天使"
    solver.op_data = data.project_arrangements([completed])
    data = solver.op_data
    solver.tasks.remove(unrelated)
    solver.total_agent = list(data.operators.values())
    assert data.operators["能天使"].is_resting()
    for _ in range(3):
        solver.resting()
    assert old in solver.tasks
    assert old.time == original_time and old.plan == original_plan
    assert (
        sum(
            task.type == TaskTypes.SHIFT_OFF and "room_3_3" in task.plan
            for task in solver.tasks
        )
        == 1
    )
    assert (
        sum(
            task.type == TaskTypes.SHIFT_OFF and "meeting" in task.plan
            for task in solver.tasks
        )
        == 0
    )

    solver.tasks.remove(old)
    bed = data.get_dorm_by_name("机械师")[1]
    if bed is not None:
        bed.reset()
    plan = solver.resting()
    assert plan["room_3_3"] == ["槐琥"]
    assert any(
        task is not old
        and task.type == TaskTypes.SHIFT_OFF
        and task.plan.get("room_3_3") == ["槐琥"]
        for task in solver.tasks
    )
