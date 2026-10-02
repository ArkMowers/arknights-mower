"""救急个人分床沿用共享候选、预约和优先级。"""

from types import SimpleNamespace

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


def prepare(solver, groups, capacity=3):
    data = solver.op_data
    data.global_plan["default_plan"].plan["dormitory_2"] = [
        Room("杜林", "", []),
        Room("安赛尔", "", []),
        *[Room("Free", "", []) for _ in range(3)],
    ]
    data.swap_plan([])
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 24, NOW, 0
        op._current_room, op.current_index = op.room, op.index
    state = {"targets": {name: 16 for name in PRIMARY}}
    solver.emergency_state = state
    data.dorm[:] = data.dorm[:capacity]
    for index, members in enumerate(groups):
        group = f"工作组{index}"
        data.groups[group] = list(members)
        for name in members:
            op = data.operators[name]
            op.group = group
            op._current_room, op.current_index = "", -1
            op.mood, op.time_stamp = 8, NOW
    return data, state


def admissions(plan):
    return {name for row in plan.values() for name in row} - {"Free", "Current"}


def test_admission_excludes_member_already_above_target(solver):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=2)
    data.operators[group[1]].mood = 20
    original_beds = [(bed.name, bed.position) for bed in data.dorm]

    assert admissions(emergency_dorm_plan(data, state)) == {group[0]}
    assert [(bed.name, bed.position) for bed in data.dorm] == original_beds
    assert all(data.operators[name].current_room == "" for name in group)


def test_members_from_multiple_groups_share_capacity(solver):
    data, state = prepare(solver, [PRIMARY[:2], PRIMARY[2:]], capacity=4)

    assert admissions(emergency_dorm_plan(data, state)) == set(PRIMARY)


def test_capacity_shortage_preserves_other_individual_priority(solver):
    rejected = PRIMARY[:3]
    admitted = PRIMARY[3]
    data, state = prepare(solver, [rejected], capacity=2)
    data.operators[admitted]._current_room = ""
    data.operators[admitted].mood = 8

    data.config.ope_resting_priority = [admitted]
    names = admissions(emergency_dorm_plan(data, state))
    assert len(names) == 2
    assert len(set(rejected) & names) == 1
    assert admitted in names


def test_completed_priority_member_does_not_reserve_beds_for_peers(solver):
    first, second = PRIMARY[:2], PRIMARY[2:]
    data, state = prepare(solver, [first, second], capacity=2)
    data.config.ope_resting_priority = [first[1]]
    data.operators[first[1]].mood = 20
    data.operators[first[0]].mood = 6
    data.operators[second[0]].mood = 1

    assert admissions(emergency_dorm_plan(data, state)) == {second[0], first[0]}


@pytest.mark.parametrize("capacity", [1, 2])
def test_released_completed_member_bed_is_available_to_peer(solver, capacity):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=capacity)
    resident, peer = (data.operators[name] for name in group)
    resident.mood = 20
    state["ready_members"] = [resident.name]

    plan = emergency_dorm_plan(data, state)

    assert admissions(plan) == {peer.name}
    assert resident.current_room == ""


def test_completed_member_bed_can_be_taken_without_displacing_unready_peer(solver):
    group = PRIMARY[:2]
    incoming = PRIMARY[2]
    data, state = prepare(solver, [group], capacity=2)
    for bed, name in zip(data.dorm, group):
        op = data.operators[name]
        op._current_room, op.current_index = bed.position
        bed.name = name
    data.operators[group[0]].mood = 20
    data.config.ope_resting_priority = [incoming]
    data.operators[incoming]._current_room = ""
    data.operators[incoming].mood = 0

    plan = emergency_dorm_plan(data, state)
    assert incoming in admissions(plan)
    peer = data.operators[group[1]]
    assert plan[peer.current_room][peer.current_index] == "Current"


@pytest.mark.parametrize("reservation", ["name", "bed", "strict", "product"])
def test_reservation_does_not_block_unreserved_peer(solver, reservation):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=2)
    tasks = []
    if reservation == "name":
        tasks = [SchedulerTask(NOW, {"room_1_1": [group[1]]})]
    elif reservation == "bed":
        room, index = data.dorm[0].position
        row = ["Current"] * 5
        row[index] = "Free"
        tasks = [SchedulerTask(NOW, {room: row})]
    elif reservation == "strict":
        tasks = [
            SimpleNamespace(
                plan={},
                strict_mood_limit=True,
                release_dorm_targets=lambda: {group[1]: ("dormitory_1", 3)},
            )
        ]
    else:
        data.reserved_product_beds[data.dorm[0].position] = PRIMARY[2]

    names = admissions(emergency_dorm_plan(data, state, tasks))
    assert len(names) == 1
    assert names <= set(group)
    if reservation in ("name", "strict"):
        assert names == {group[0]}


def test_working_or_excluded_peer_is_not_pulled_from_work(solver):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group])
    peer = data.operators[group[1]]
    peer._current_room = peer.room
    assert admissions(emergency_dorm_plan(data, state)) == {group[0]}

    peer._current_room = ""
    data.config.free_blacklist = [peer.name]
    assert admissions(emergency_dorm_plan(data, state)) == {group[0]}


def test_ordinary_bound_candidates_can_be_split_without_duplicates(solver):
    group = COVERS[:2]
    data, state = prepare(solver, [group], capacity=1)
    data.config.ope_resting_priority = [group[0]]
    assert admissions(emergency_dorm_plan(data, state)) == {group[0]}

    from arknights_mower.utils.operators import Dormitory

    data.dorm.extend(Dormitory(position=("dormitory_1", index)) for index in (3, 4))
    plan = emergency_dorm_plan(data, state)
    assert set(group) <= admissions(plan)
    assert all(sum(row.count(name) for row in plan.values()) == 1 for name in group)


def test_spare_beds_follow_shared_replacement_priority(solver):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group])
    data.dorm[:] = [bed for bed in data.dorm if bed.position[1] >= 2]
    preferred, other = COVERS[:2]
    for name in (preferred, other):
        data.operators[name].mood = 4
    data.config.resting_priority_replacement = [preferred]

    assert admissions(emergency_dorm_plan(data, state)) == {*group, preferred}


def test_fiammetta_fixed_slot_stays_outside_normal_bed_pool(solver):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=2)
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        time_stamp=NOW,
    )
    plan = emergency_dorm_plan(data, state)
    assert admissions(plan) == set(group)
    assert plan["dormitory_1"][0] == "Current"
    assert data.operators["菲亚梅塔"].current_room == "dormitory_1"


def test_standby_return_reservation_keeps_shared_exception(solver, monkeypatch):
    name = COVERS[0]
    data, state = prepare(solver, [])
    data.dorm[:] = [bed for bed in data.dorm if bed.position[1] >= 2][:1]
    data.operators[name].mood = 8
    monkeypatch.setattr(data, "is_standby", lambda candidate: candidate == name)
    task = SchedulerTask(NOW, {"room_1_1": [name]}, TaskTypes.SHIFT_ON)

    assert name in admissions(emergency_dorm_plan(data, state, [task]))


def test_requested_members_skip_other_targets_fillers_and_manager_return(solver):
    selected, other = PRIMARY[:2], PRIMARY[2:]
    data, state = prepare(solver, [selected, other])
    for name in COVERS:
        data.operators[name].mood = 4
    for name in ("冰酿", "闪灵"):
        data.operators[name]._current_room = ""

    assert admissions(emergency_dorm_plan(data, state, members=selected)) == set(
        selected
    )
    assert emergency_dorm_plan(data, state, members=[]) == {}


@pytest.mark.parametrize("bound", [True, False])
def test_requested_members_use_available_capacity_without_group_expansion(
    solver, bound
):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=1)
    if not bound:
        for name in group:
            data.operators[name].group = ""

    names = admissions(emergency_dorm_plan(data, state, members=group))
    assert len(names) == 1 and names <= set(group)


@pytest.mark.parametrize("reservation", ["name", "bed", "strict", "product"])
def test_requested_members_keep_person_and_slot_reservations(solver, reservation):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=2)
    tasks = []
    if reservation == "name":
        tasks = [SchedulerTask(NOW, {"room_1_1": [group[1]]})]
    elif reservation == "bed":
        room, index = data.dorm[0].position
        row = ["Current"] * 5
        row[index] = "Free"
        tasks = [SchedulerTask(NOW, {room: row})]
    elif reservation == "strict":
        tasks = [
            SimpleNamespace(
                plan={},
                strict_mood_limit=True,
                release_dorm_targets=lambda: {group[1]: ("dormitory_1", 3)},
            )
        ]
    else:
        data.reserved_product_beds[data.dorm[0].position] = PRIMARY[2]

    names = admissions(emergency_dorm_plan(data, state, tasks, members=group))
    assert len(names) == 1 and names <= set(group)
    if reservation in ("name", "strict"):
        assert names == {group[0]}


def test_requested_members_keep_existing_resident_without_relocating_it(solver):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group], capacity=2)
    bed = data.dorm[0]
    resident = data.operators[group[0]]
    resident._current_room, resident.current_index = bed.position
    resident.mood = 24
    bed.name = resident.name

    plan = emergency_dorm_plan(data, state, members=group)
    assert admissions(plan) == {group[1]}
    assert set(group) <= admissions(plan) | {bed.name for bed in data.dorm}


def test_requested_members_skip_working_or_unknown_peers_independently(solver):
    group = PRIMARY[:2]
    data, state = prepare(solver, [group])
    data.operators[group[1]]._current_room = data.operators[group[1]].room

    assert admissions(emergency_dorm_plan(data, state, members=group)) == {group[0]}
    assert admissions(
        emergency_dorm_plan(data, state, members=[group[0], "未注册成员"])
    ) == {group[0]}


@pytest.mark.parametrize("selected_only", [False, True])
def test_planner_does_not_open_closed_manager_slots(solver, selected_only):
    incoming = PRIMARY[0]
    data, state = prepare(solver, [], capacity=1)
    manager = data.operators["冰酿"]
    manager.group = "已回班组"
    data.groups[manager.group] = [manager.name, PRIMARY[1]]
    data.operators[PRIMARY[1]].group = manager.group
    data.config.ope_resting_priority = [manager.name]
    data.operators[incoming]._current_room = ""
    data.operators[incoming].mood = 8

    plan = emergency_dorm_plan(
        data, state, members=[incoming] if selected_only else None
    )
    assert admissions(plan) == {incoming}
    assert plan["dormitory_1"][:2] == ["Current", "Current"]
    assert manager.current_room == "dormitory_1" and manager.current_index == 0
    assert all(bed.position[1] >= 2 for bed in data.all_dorms())
    assert not data.emergency_dorm_agents


@pytest.mark.parametrize("completed", [True, False, "predicted"])
def test_ordinary_bound_residents_yield_individually_to_higher_priority(
    solver, completed
):
    ordinary = COVERS[:2]
    incoming = PRIMARY[:2]
    data, state = prepare(solver, [ordinary, incoming])
    data.dorm[:] = [bed for bed in data.dorm if bed.position[1] >= 2][:2]
    for name, bed in zip(ordinary, data.dorm):
        op = data.operators[name]
        op._current_room, op.current_index = bed.position
        op.mood = 24
        bed.name = name
    if completed is False:
        data.operators[ordinary[1]].mood = 8
    elif completed == "predicted":
        data.operators[ordinary[1]].mood_is_prediction = True

    plan = emergency_dorm_plan(data, state, members=incoming)
    assert admissions(plan) == set(incoming)


def test_explicit_free_group_member_opens_only_its_normal_dynamic_bed(solver):
    selected = PRIMARY[:2]
    data, state = prepare(solver, [])
    default = data.global_plan["default_plan"].plan
    for name in selected:
        op = data.operators[name]
        default[op.room][op.index].group = "临时床组"
    default["dormitory_1"][0].group = "临时床组"
    default["dormitory_1"][0].replacement = ["Free"]
    data.swap_plan([])
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 24, NOW, 0
        op._current_room, op.current_index = op.room, op.index
    for name in selected:
        data.operators[name]._current_room, data.operators[name].current_index = "", -1
        data.operators[name].mood = 8
    data.dorm[:] = [
        bed
        for bed in data.all_dorms()
        if bed.position in (("dormitory_1", 0), ("dormitory_1", 2))
    ]
    group = data.groups["临时床组"]
    before = [(bed.name, bed.position) for bed in data.all_dorms()]

    plan = emergency_dorm_plan(data, state, members=group)
    assert admissions(plan) == set(selected)
    assert plan["dormitory_1"][1] == "Current"
    assert "冰酿" not in admissions(plan)
    assert [(bed.name, bed.position) for bed in data.all_dorms()] == before
    projected = data.project_arrangements([plan])
    assert all(projected.operators[name].is_resting() for name in selected)
    assert projected.operators["冰酿"].current_room == ""
