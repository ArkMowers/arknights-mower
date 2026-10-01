"""主班保床、候补向更高优让床，同时保留主力接管普通替班的行为。"""

import pytest

from arknights_mower.tests import group_resting_capacity_tests
from arknights_mower.tests.group_resting_capacity_tests import (
    DEEP,
    OTHER_COVERS,
    OTHERS,
    apply_plan,
    shift_off,
)
from arknights_mower.utils.scheduler_task import (
    dorm_residents,
    plan_metadata,
    restore_displaced_resting,
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


@pytest.mark.parametrize("rescue", [False, True])
@pytest.mark.parametrize("low_mood", [False, True])
def test_explicit_priority_displaces_standby_without_recalling_its_group(
    solver, rescue, low_mood
):
    data = solver.op_data
    data.rescue_mode = rescue
    if low_mood:
        for name in DEEP[1:]:
            data.operators[name].standby_low_priority = True
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


def test_explicit_priority_displaces_low_main_and_recalls_whole_group(solver):
    data = solver.op_data
    data.config.ope_resting_priority = []
    for name in DEEP:
        data.operators[name].resting_priority = "low"
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    before = [(bed.name, bed.time) for bed in data.dorm]
    data.config.ope_resting_priority = [OTHERS[0]]

    newcomer, plan = try_admit_newcomer(solver)

    assert plan[newcomer.room][newcomer.index] == newcomer.replacement[0]
    assert set(DEEP) <= {name for names in plan.values() for name in names}
    apply_plan(solver, plan)
    apply_plan(solver, try_reorder(data, plan))
    assert all(
        data.operators[name].current_room == data.operators[name].room for name in DEEP
    )
    assert all(bed.name not in DEEP for bed in data.dorm)
    assert [(bed.name, bed.time) for bed in data.dorm] != before


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


@pytest.mark.parametrize("rescue", [False, True])
def test_idle_fill_priority_replacement_evicts_standby_and_preserves_return(
    solver, rescue
):
    solver.op_data.rescue_mode = rescue
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


@pytest.mark.parametrize("rescue", [False, True])
def test_idle_explicit_priority_recalls_displaced_required_group_and_keeps_newcomer(
    solver, rescue
):
    data = solver.op_data
    data.rescue_mode = rescue
    data.config.free_room = True
    for name in DEEP:
        data.operators[name].resting_priority = "low"
    shift_off(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    newcomer = OTHER_COVERS[0]
    data.config.ope_resting_priority = [newcomer]
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    plan = tasks[0].plan
    assert newcomer in {name for names in plan.values() for name in names}
    assert set(DEEP) <= {name for names in plan.values() for name in names}
    apply_plan(solver, plan)
    assert all(data.operators[name].is_working() for name in DEEP)
    assert data.operators[newcomer].is_resting()


def test_uncached_required_resident_still_gets_explicit_return_compensation(solver):
    shift_off(solver)
    data = solver.op_data
    name = DEEP[0]
    _, bed = data.get_dorm_by_name(name)
    position = bed.position
    bed.name = ""
    previous = dorm_residents(data)
    assert previous[position] == name
    bed.name = OTHERS[0]
    plan = {}
    restore_displaced_resting(data, previous, plan, [])
    assert set(DEEP) <= {name for names in plan.values() for name in names}
    assert bed.name == OTHERS[0]


def test_free_opening_keeps_new_required_anchor_and_does_not_recall_standby(solver):
    shift_off(solver)
    data = solver.op_data
    previous = dorm_residents(data)
    _, anchor_bed = data.get_dorm_by_name(DEEP[0])
    _, standby_bed = data.get_dorm_by_name(DEEP[1])
    previous[anchor_bed.position] = ""
    standby_bed.name = OTHERS[0]
    room, index = anchor_bed.position
    plan = {room: ["Current"] * 5}
    plan[room][index] = "Free"
    restore_displaced_resting(data, previous, plan, [])
    assert all(
        name not in {name for names in plan.values() for name in names} for name in DEEP
    )
    assert anchor_bed.name == DEEP[0]
