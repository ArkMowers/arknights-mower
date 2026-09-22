"""候补及以上入住保护，同时保留主力接管普通替班的 #942 行为。"""

from arknights_mower.tests import group_resting_capacity_tests
from arknights_mower.tests.group_resting_capacity_tests import (
    DEEP,
    OTHER_COVERS,
    OTHERS,
    apply_plan,
    shift_off,
)
from arknights_mower.utils.scheduler_task import plan_metadata

solver = group_resting_capacity_tests.solver


def fill_remaining_beds(solver, names):
    plan = {}
    for name, bed in zip(names, [bed for bed in solver.op_data.dorm if not bed.name]):
        room, index = bed.position
        plan.setdefault(room, ["Current"] * 5)[index] = name
    apply_plan(solver, plan)


def try_admit_newcomer(solver):
    data = solver.op_data
    newcomer = data.operators[OTHERS[0]]
    newcomer.mood = 0
    plan = {}
    solver.get_resting_plan([newcomer.name], [], plan, data.active_high_resting_count())
    return newcomer, plan


def test_unlisted_cannot_displace_resting_standby(solver):
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    data = solver.op_data
    before = [(bed.name, bed.time) for bed in data.dorm]
    solver.tasks = plan_metadata(data, [])
    tasks_before = [task.plan for task in solver.tasks]
    # Without an explicit priority override, settled standby occupants stay protected.

    newcomer, plan = try_admit_newcomer(solver)

    assert plan == {}
    assert not newcomer.is_resting()
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert [task.plan for task in solver.tasks] == tasks_before
    assert all(data.operators[name].is_resting() for name in DEEP)


def test_unlisted_cannot_displace_resting_low_main(solver):
    data = solver.op_data
    data.config.ope_resting_priority = []
    for name in DEEP:
        data.operators[name].resting_priority = "low"
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    before = [(bed.name, bed.time) for bed in data.dorm]
    # Unlisted low-main newcomers cannot displace settled low-main occupants.

    newcomer, plan = try_admit_newcomer(solver)

    assert plan == {}
    assert not newcomer.is_resting()
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert all(data.operators[name].is_resting() for name in DEEP)


def test_explicit_priority_can_preempt_unlisted_standby_without_eviction_of_ranked_anchor(
    solver,
):
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    data = solver.op_data
    anchor = DEEP[0]
    assert any(bed.name == anchor for bed in data.dorm)
    data.config.ope_resting_priority.append(OTHERS[0])

    newcomer, plan = try_admit_newcomer(solver)

    assert plan
    assert newcomer.name in [bed.name for bed in data.dorm]
    assert any(bed.name == anchor for bed in data.dorm)


def test_low_main_still_preempts_ordinary_replacement_for_942(solver):
    shift_off(solver)
    fill_remaining_beds(solver, OTHER_COVERS)
    data = solver.op_data
    newcomer = data.operators[OTHERS[0]]
    newcomer.resting_priority = "low"

    newcomer, plan = try_admit_newcomer(solver)

    assert plan[newcomer.room][newcomer.index] == newcomer.replacement[0]
    assert newcomer.name in [bed.name for bed in data.dorm]
    assert sum(bed.name in OTHER_COVERS for bed in data.dorm) == 1
