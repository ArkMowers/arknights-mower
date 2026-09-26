"""主班保床、候补向更高优让床，同时保留主力接管普通替班的行为。"""

from arknights_mower.tests import group_resting_capacity_tests
from arknights_mower.tests.group_resting_capacity_tests import (
    DEEP,
    OTHER_COVERS,
    OTHERS,
    apply_plan,
    shift_off,
)
from arknights_mower.utils.scheduler_task import (
    plan_metadata,
    try_add_release_dorm,
    try_reorder,
)

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


def test_explicit_priority_displaces_standby_without_recalling_its_group(solver):
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    data = solver.op_data
    solver.tasks = plan_metadata(data, [])
    data.config.ope_resting_priority.append(OTHERS[0])

    newcomer, plan = try_admit_newcomer(solver)

    assert plan[newcomer.room][newcomer.index] == newcomer.replacement[0]
    beds = try_reorder(data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    evicted = [name for name in DEEP[1:] if not data.operators[name].is_resting()]
    assert len(evicted) == 1
    assert data.is_standby(evicted[0])
    assert data.operators[DEEP[0]].is_resting()
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not {name for slots in correction.values() for name in slots} & set(DEEP)
    tasks = plan_metadata(data, [])
    assert any(
        evicted[0] in [name for slots in task.plan.values() for name in slots]
        for task in tasks
    )


def test_explicit_priority_cannot_displace_resting_low_main(solver):
    data = solver.op_data
    data.config.ope_resting_priority = []
    for name in DEEP:
        data.operators[name].resting_priority = "low"
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    before = [(bed.name, bed.time) for bed in data.dorm]
    data.config.ope_resting_priority = [OTHERS[0]]

    newcomer, plan = try_admit_newcomer(solver)

    assert plan == {}
    assert not newcomer.is_resting()
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert all(data.operators[name].is_resting() for name in DEEP)


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


def test_idle_fill_priority_replacement_evicts_standby_and_preserves_return(solver):
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    data = solver.op_data
    data.config.free_room = True
    newcomer = OTHER_COVERS[0]
    data.config.resting_priority_replacement = [newcomer]
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    assert newcomer in [name for names in tasks[0].plan.values() for name in names]
    apply_plan(solver, tasks[0].plan)
    evicted = [name for name in DEEP[1:] if not data.operators[name].is_resting()]
    assert len(evicted) == 1
    assert data.is_standby(evicted[0])
    assert data.operators[DEEP[0]].is_resting()
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not {name for slots in correction.values() for name in slots} & set(DEEP)
    tasks = plan_metadata(data, [])
    assert any(
        evicted[0] in [name for slots in task.plan.values() for name in slots]
        for task in tasks
    )


def test_free_selection_can_replace_standby_with_priority_replacement(solver):
    shift_off(solver)
    data = solver.op_data
    newcomer = OTHER_COVERS[0]
    data.config.resting_priority_replacement = [newcomer]
    _, bed = data.get_dorm_by_name(DEEP[1])
    room, index = bed.position
    plan = ["Current"] * 5
    plan[index] = "Free"
    solver.task = None
    solver.preserve_resting_crafters(plan, room)
    assert plan[index] == newcomer


def test_priority_replacement_fills_empty_bed_before_displacing_standby(solver):
    shift_off(solver)
    data = solver.op_data
    data.config.free_room = True
    newcomer = OTHER_COVERS[0]
    data.config.resting_priority_replacement = [newcomer]
    for name in OTHER_COVERS[1:]:
        data.operators[name].mood = 24
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    apply_plan(solver, tasks[0].plan)
    assert data.operators[newcomer].is_resting()
    assert all(data.operators[name].is_resting() for name in DEEP)


def test_unknown_priority_replacement_does_not_evict_standby(solver):
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    data = solver.op_data
    data.config.free_room = True
    newcomer = OTHER_COVERS[0]
    data.config.resting_priority_replacement = [newcomer]
    data.operators[newcomer].time_stamp = None
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []
    assert all(data.operators[name].is_resting() for name in DEEP)
