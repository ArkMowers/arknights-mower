"""MAA 协助的床位开放与恢复层级不修改正常工作站。"""

from arknights_mower.tests.mass_mood_recovery_tests import NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan


def episode(data):
    return {
        "phase": "recovering",
        "dispatch": "completed",
        "dorm_layout": {
            room: [slot.agent for slot in slots]
            for room, slots in data.plan.items()
            if room.startswith("dorm")
        },
        "targets": {name: 16 for name in PRIMARY},
    }


def test_assistance_opens_managers_beds_without_changing_primary_roles(solver):
    data = solver.op_data
    solver.emergency_state = episode(data)
    solver._open_emergency_beds()
    assert len(data.dorm) == 5
    assert all(data.is_effective_free_slot(bed) for bed in data.dorm)
    for name in PRIMARY:
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood, op.time_stamp = 8, NOW
    plan = emergency_dorm_plan(data, solver.emergency_state)
    assert set(PRIMARY) <= {name for names in plan.values() for name in names}
    assert set(plan) == {"dormitory_1"}


def test_working_primary_is_not_pulled_from_maa_roster(solver):
    data = solver.op_data
    solver.emergency_state = episode(data)
    solver._open_emergency_beds()
    for name in PRIMARY:
        data.operators[name].mood = 8
    plan = emergency_dorm_plan(data, solver.emergency_state)
    assert not set(PRIMARY) & {name for names in plan.values() for name in names}


def test_lower_priority_unfinished_standby_yields_to_required_primary(solver):
    data = solver.op_data
    state = episode(data)
    solver.emergency_state = state
    solver._open_emergency_beds()
    incoming, standby = PRIMARY[:2]
    data.config.resting_standby = [standby]
    data.operators[standby].resting_priority = "standby"
    for bed in data.dorm:
        bed.name = standby if bed is data.dorm[0] else "冰酿"
    op = data.operators[standby]
    op._current_room, op.current_index = data.dorm[0].position
    op.mood = 5
    data.operators[incoming]._current_room = ""
    data.operators[incoming].mood = 8
    plan = emergency_dorm_plan(data, state)
    assert incoming in {name for names in plan.values() for name in names}


def test_managers_return_without_kicking_unfinished_required_primary(solver):
    data = solver.op_data
    solver.emergency_state = episode(data)
    solver._open_emergency_beds()
    for name in ["冰酿", "闪灵"]:
        data.operators[name]._current_room, data.operators[name].current_index = "", -1
    op = data.operators[PRIMARY[0]]
    op._current_room, op.current_index, op.mood = "dormitory_1", 0, 8
    data.dorm[0].name = op.name
    plan = emergency_dorm_plan(data, solver.emergency_state)
    assert plan.get("dormitory_1", ["Current"] * 5)[0] == "Current"
    assert plan["dormitory_1"][1] == "闪灵"
