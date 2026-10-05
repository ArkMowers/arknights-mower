"""救急按个人需求分床，待命主班及仍需恢复的住客不重复占床。"""

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan
from arknights_mower.utils.operators import Dormitory
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


def recovery(data, names=PRIMARY, capacity=3):
    data.dorm[:] = data.dorm[:capacity]
    data.groups["恢复组"] = list(names)
    for index, name in enumerate(names):
        op = data.operators[name]
        op.group = "恢复组"
        op._current_room, op.current_index = "", -1
        op.mood, op.time_stamp = 3 + index, NOW
    return {"targets": {name: 16 for name in names}, "ready_members": []}


def admissions(plan):
    return {name for row in plan.values() for name in row} - {"Current", "Free", ""}


def opened_beds(data):
    for index, slot in enumerate(data.plan["dormitory_1"]):
        if slot.agent == "菲亚梅塔":
            continue
        if slot.agent != "Free":
            data.emergency_dorm_agents.add(slot.agent)
            slot.agent = "Free"
        if not any(bed.position == ("dormitory_1", index) for bed in data.dorm):
            resident = data.get_current_operator("dormitory_1", index)
            data.dorm.append(
                Dormitory(("dormitory_1", index), resident.name if resident else "")
            )


@pytest.mark.parametrize("capacity", [1, 2, 3])
def test_group_can_recover_with_fewer_beds_than_members(solver, capacity):
    data = solver.op_data
    state = recovery(data, capacity=capacity)
    original = [(bed.position, bed.name) for bed in data.dorm]

    plan = emergency_dorm_plan(data, state)

    assert admissions(plan) == set(PRIMARY[:capacity])
    assert [(bed.position, bed.name) for bed in data.dorm] == original
    assert all(data.operators[name].current_room == "" for name in PRIMARY)


def test_requested_members_do_not_expand_to_whole_bound_group(solver):
    data = solver.op_data
    state = recovery(data)

    assert admissions(emergency_dorm_plan(data, state, members=[PRIMARY[1]])) == {
        PRIMARY[1]
    }
    assert emergency_dorm_plan(data, state, members=[]) == {}


def test_working_peer_does_not_block_available_individual(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    peer = data.operators[PRIMARY[1]]
    peer._current_room, peer.current_index = peer.room, peer.index

    assert admissions(emergency_dorm_plan(data, state)) == {PRIMARY[0]}
    assert peer.is_working()


def test_excluded_and_unknown_peers_do_not_block_available_individual(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    data.config.free_blacklist = [PRIMARY[1]]

    assert admissions(
        emergency_dorm_plan(data, state, members=[PRIMARY[0], PRIMARY[1], "未注册成员"])
    ) == {PRIMARY[0]}


def test_shared_priority_is_per_person_not_per_group(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    data.config.ope_resting_priority = [PRIMARY[-1]]

    assert admissions(emergency_dorm_plan(data, state)) == {PRIMARY[-1]}


def test_ready_member_does_not_reenter_from_need_or_ordinary_fill(solver):
    data = solver.op_data
    state = recovery(data)
    state["ready_members"] = [PRIMARY[0]]
    data.operators[PRIMARY[0]].mood = 8

    assert PRIMARY[0] not in admissions(emergency_dorm_plan(data, state))
    assert emergency_dorm_plan(data, state, members=[PRIMARY[0]]) == {}


def test_member_already_at_target_is_not_admitted_for_unready_peer(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    data.operators[PRIMARY[0]].mood = 16

    assert admissions(emergency_dorm_plan(data, state)) == {PRIMARY[1]}


def test_predictions_do_not_confirm_recovery_completion(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    op = data.operators[PRIMARY[0]]
    op.mood, op.mood_is_prediction = 20, True
    data.config.ope_resting_priority = [op.name]

    assert admissions(emergency_dorm_plan(data, state)) == {op.name}


def test_unready_individual_keeps_bed_against_higher_priority_primary(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    resident = data.operators[PRIMARY[0]]
    bed = data.dorm[0]
    bed.name = resident.name
    resident._current_room, resident.current_index = bed.position
    data.config.ope_resting_priority = [PRIMARY[1]]

    assert emergency_dorm_plan(data, state) == {}
    assert bed.name == resident.name


def test_pending_task_reservations_remain_per_person(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    task = SchedulerTask(NOW, {"factory": [PRIMARY[0]]}, TaskTypes.WORKSHOP)

    assert admissions(emergency_dorm_plan(data, state, [task])) == {PRIMARY[1]}


def test_spare_capacity_accepts_partial_bound_replacements(solver):
    data = solver.op_data
    state = {"targets": {}, "ready_members": []}
    recovery(data, COVERS[:2], capacity=1)

    assert admissions(emergency_dorm_plan(data, state)) == {COVERS[0]}


def test_opened_manager_slots_increase_capacity_without_mutating_actual_rooms(solver):
    data = solver.op_data
    state = recovery(data)
    opened_beds(data)

    plan = emergency_dorm_plan(data, state)

    assert len(data.dorm) == 5
    assert admissions(plan) == set(PRIMARY)
    assert any(plan["dormitory_1"][index] in PRIMARY for index in (0, 1))
    assert data.operators["冰酿"].current_room == "dormitory_1"


def test_full_high_priority_manager_yields_when_emergency_slot_is_open(solver):
    data = solver.op_data
    state = recovery(data, capacity=0)
    data.config.ope_resting_priority = ["冰酿"]
    opened_beds(data)
    data.dorm[:] = [bed for bed in data.dorm if bed.position[1] == 0]

    assert admissions(emergency_dorm_plan(data, state)) == {PRIMARY[0]}
    assert data.is_planned_operator("冰酿")


def test_unfinished_manager_does_not_gain_full_mood_eviction_exception(solver):
    data = solver.op_data
    state = recovery(data, capacity=0)
    data.config.ope_resting_priority = ["冰酿"]
    data.operators["冰酿"].mood = 12
    opened_beds(data)
    data.dorm[:] = [bed for bed in data.dorm if bed.position[1] == 0]

    assert emergency_dorm_plan(data, state) == {}


def test_normal_plan_swap_clears_opened_manager_identity(solver):
    data = solver.op_data
    opened_beds(data)

    data.swap_plan([])

    assert data.emergency_dorm_agents == set()
    assert [slot.agent for slot in data.plan["dormitory_1"][:2]] == ["冰酿", "闪灵"]


def test_exit_order_breaks_ties_but_preserves_explicit_priority(solver):
    data = solver.op_data
    state = recovery(data, capacity=1)
    order = {name: (1, 20) for name in PRIMARY}
    order[PRIMARY[-1]] = (0, 1)
    assert admissions(emergency_dorm_plan(data, state, recovery_order=order)) == {
        PRIMARY[-1]
    }
    data.config.ope_resting_priority = [PRIMARY[0]]
    assert admissions(emergency_dorm_plan(data, state, recovery_order=order)) == {
        PRIMARY[0]
    }
