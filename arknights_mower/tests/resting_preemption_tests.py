"""主班跨级接管床位后，候补待命或整组回班均不依赖纠错补救。"""

from datetime import datetime, timedelta

from arknights_mower.tests import group_resting_capacity_tests
from arknights_mower.tests.group_resting_capacity_tests import (
    DEEP,
    OTHERS,
    apply_plan,
    shift_off,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_reorder,
)

solver = group_resting_capacity_tests.solver


def fill_remaining_beds(solver):
    data = solver.op_data
    plan = {}
    for name, bed in zip(OTHERS[1:], [bed for bed in data.dorm if not bed.name]):
        op = data.operators[name]
        plan.setdefault(op.room, ["Current"] * len(data.plan[op.room]))[op.index] = (
            op.replacement[0]
        )
        room, index = bed.position
        plan.setdefault(room, ["Current"] * 5)[index] = name
    apply_plan(solver, plan)


def admit_newcomer(solver):
    data = solver.op_data
    newcomer = data.operators[OTHERS[0]]
    newcomer.mood = 0
    plan = {}
    solver.get_resting_plan([newcomer.name], [], plan, data.active_high_resting_count())
    beds = try_reorder(data, plan)
    apply_plan(
        solver,
        {room: names for room, names in plan.items() if not room.startswith("dorm")},
    )
    solver.task = SchedulerTask(task_plan=plan)
    for room, names in plan.items():
        if room.startswith("dorm"):
            selected = names.copy()
            solver.preserve_resting_crafters(selected, room)
            apply_plan(solver, {room: selected})
    solver.task = SchedulerTask(task_plan=beds)
    for room, names in beds.items():
        selected = names.copy()
        solver.preserve_resting_crafters(selected, room)
        apply_plan(solver, {room: selected})
    assert newcomer.is_resting()
    return plan


def test_displaced_candidate_waits_with_group_without_recalling_anchor(solver):
    shift_off(solver)
    fill_remaining_beds(solver)
    data = solver.op_data
    data.operators[OTHERS[0]].resting_priority = "low"
    solver.tasks = plan_metadata(data, [])
    plan = admit_newcomer(solver)
    assert not any(name in DEEP for names in plan.values() for name in names)
    displaced = [name for name in DEEP if not data.operators[name].is_resting()]
    assert len(displaced) == 1
    assert data.is_group_standby(displaced[0])
    assert data.operators[DEEP[0]].is_resting()
    assert any(
        displaced[0] in names for task in solver.tasks for names in task.plan.values()
    )
    for _ in range(3):
        assert solver.agent_get_mood() is None, [task.plan for task in solver.tasks]
        assert solver.resting() == {}


def test_displaced_required_member_returns_whole_group_and_cancels_old_tasks(solver):
    data = solver.op_data
    data.config.ope_resting_priority = []
    for name in DEEP:
        data.operators[name].resting_priority = "low"
    shift_off(solver)
    fill_remaining_beds(solver)
    solver.tasks = plan_metadata(data, [])
    for bed in data.dorm:
        if bed.name in DEEP:
            room, index = bed.position
            names = ["Current"] * 5
            names[index] = "Free"
            solver.tasks.append(
                SchedulerTask(
                    time=datetime.now() + timedelta(hours=4),
                    task_type=TaskTypes.RELEASE_DORM,
                    task_plan={room: names},
                )
            )
    plan = admit_newcomer(solver)
    for name in DEEP:
        op = data.operators[name]
        assert plan[op.room][op.index] == name
        assert (op.current_room, op.current_index) == (op.room, op.index)
    assert not any(
        name in DEEP
        for task in solver.tasks
        for names in task.plan.values()
        for name in names
    )
    assert not any(task.type == TaskTypes.RELEASE_DORM for task in solver.tasks)
    for _ in range(3):
        assert solver.agent_get_mood() is None, [task.plan for task in solver.tasks]
        assert solver.resting() == {}


def test_explicit_priority_can_preempt_when_normal_rest_quota_is_full(solver):
    data = solver.op_data
    data.config.ope_resting_priority = []
    for name in DEEP:
        data.operators[name].resting_priority = "high"
    shift_off(solver)
    fill_remaining_beds(solver)
    assert data.available_free() == 0
    newcomer = data.operators[OTHERS[0]]
    newcomer.mood = 0
    data.config.ope_resting_priority = [newcomer.name]
    solver.total_agent = [newcomer]
    plan = solver.resting()
    assert plan[newcomer.room][newcomer.index] == newcomer.replacement[0]
    assert newcomer.name in [bed.name for bed in data.dorm]
