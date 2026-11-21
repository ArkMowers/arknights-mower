"""自动救急沿用正常宿舍床位和恢复层级，不修改工作主班。"""

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan


def episode():
    return {"phase": "recovering", "targets": {name: 16 for name in PRIMARY}}


def admissions(plan):
    return {name for row in plan.values() for name in row} - {"Current", "Free", ""}


def test_assistance_keeps_normal_manager_positions_and_bed_capacity(solver):
    data = solver.op_data
    state = episode()
    layout = [slot.agent for slot in data.plan["dormitory_1"]]
    beds = [(bed.position, bed.name) for bed in data.dorm]
    for name in PRIMARY:
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood, op.time_stamp = 8, NOW

    plan = emergency_dorm_plan(data, state)

    assert len(beds) == 3
    assert len(admissions(plan)) == len(beds)
    assert admissions(plan) <= set(PRIMARY)
    assert plan["dormitory_1"][:2] == ["Current", "Current"]
    assert [slot.agent for slot in data.plan["dormitory_1"]] == layout
    assert [(bed.position, bed.name) for bed in data.dorm] == beds
    assert all(data.operators[name].room.startswith("room") for name in PRIMARY)


def test_working_primary_is_not_pulled_into_dormitory(solver):
    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 8

    plan = emergency_dorm_plan(data, episode())

    assert not set(PRIMARY) & admissions(plan)
    assert all(data.operators[name].is_working() for name in PRIMARY)


def test_lower_priority_unfinished_standby_yields_to_required_primary(solver):
    data = solver.op_data
    incoming, standby = PRIMARY[:2]
    data.config.resting_standby = [standby]
    data.operators[standby].resting_priority = "standby"
    for bed, name in zip(data.dorm, [standby, *COVERS[:2]]):
        bed.name = name
        op = data.operators[name]
        op._current_room, op.current_index = bed.position
        op.mood, op.time_stamp = 5, NOW
    data.operators[incoming]._current_room = ""
    data.operators[incoming].mood = 8

    state = episode()
    state["targets"].pop(standby)
    plan = emergency_dorm_plan(data, state)

    assert incoming in admissions(plan)
    assert standby not in admissions(plan)
    assert plan["dormitory_1"][:2] == ["Current", "Current"]


def test_normal_managers_remain_while_required_primary_recovers(solver):
    data = solver.op_data
    op = data.operators[PRIMARY[0]]
    bed = data.dorm[0]
    op._current_room, op.current_index = bed.position
    op.mood = 8
    bed.name = op.name
    managers = [data.get_current_operator("dormitory_1", index) for index in (0, 1)]

    plan = emergency_dorm_plan(data, episode())

    row = plan.get("dormitory_1", ["Current"] * 5)
    assert row[:2] == ["Current", "Current"]
    assert row[op.current_index] == "Current"
    assert bed.name == op.name
    assert [data.get_current_operator("dormitory_1", index) for index in (0, 1)] == (
        managers
    )


def test_same_group_admitted_before_other_group_and_spare_fillers(solver):
    data = solver.op_data
    for index, name in enumerate(PRIMARY):
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood = index * 3
    for name in (PRIMARY[0], PRIMARY[3]):
        data.operators[name].group = "同组"
    data.groups["同组"] = [PRIMARY[0], PRIMARY[3]]
    data.dorm = data.dorm[:2]
    assert admissions(emergency_dorm_plan(data, episode())) == {PRIMARY[0], PRIMARY[3]}


def test_rescue_exit_order_precedes_high_priority_list_and_mood(solver):
    data = solver.op_data
    first, second = PRIMARY[:2]
    for name, mood in [(first, 1), (second, 12)]:
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood = mood
    data.config.ope_resting_priority = [first, second]
    data.dorm = data.dorm[:1]
    plan = emergency_dorm_plan(
        data,
        {"targets": {first: 16, second: 16}},
        members=[first, second],
        recovery_order={first: (1, 10), second: (0, 1)},
    )
    assert admissions(plan) == {second}
    assert data.operators[second].current_room == ""
    assert data.dorm[0].name == ""


def test_rescue_group_continuity_ignores_resting_tiers(solver):
    data = solver.op_data
    first, second, third = PRIMARY[:3]
    for name, mood in [(first, 1), (second, 2), (third, 3)]:
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood = mood
    data.operators[first].group = data.operators[third].group = "同组"
    data.groups["同组"] = [first, third]
    data.config.ope_resting_priority = [first]
    data.dorm = data.dorm[:2]
    order = {first: (0, 3), third: (0, 3), second: (1, 1)}
    plan = emergency_dorm_plan(
        data, episode(), members=[first, second, third], recovery_order=order
    )
    assert admissions(plan) == {first, third}


def test_rescue_exit_order_gets_fast_bed_despite_low_resting_priority(solver):
    data = solver.op_data
    first, second = PRIMARY[:2]
    for name in (first, second):
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood = 8
    data.config.resting_priority = [first]
    data.operators[first].resting_priority = "low"
    data.config.ope_resting_priority = [second]
    order = {first: (0, 1), second: (1, 10)}
    plan = emergency_dorm_plan(
        data, episode(), members=[first, second], recovery_order=order
    )
    assert plan["dormitory_1"][2:4] == [first, second]
