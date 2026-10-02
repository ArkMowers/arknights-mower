"""救急开放宿管床位，需求减少后先恢复各宿舍一号再二号宿管。"""

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

RECOVERY_NAMES = [*PRIMARY, *COVERS, "阿米娅", "幽灵鲨"]


def setup_episode(solver, count, *, fiammetta=False):
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
    if fiammetta:
        data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = (
            "",
            -1,
        )
        data.plan["dormitory_1"][0].agent = "菲亚梅塔"
        data.operators["菲亚梅塔"] = Operator(
            "菲亚梅塔",
            "dormitory_1",
            index=0,
            current_room="dormitory_1",
            current_index=0,
            mood=12,
            time_stamp=NOW,
            operator_type="high",
        )
    for name in RECOVERY_NAMES[:count]:
        if name not in data.operators:
            data.operators[name] = Operator(name, "room_3_1", time_stamp=NOW)
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood = 8
    state = {
        "phase": "recovering",
        "targets": {name: 16 for name in RECOVERY_NAMES[:count]},
        "ready_members": [],
        "dorm_layout": {
            room: [slot.agent for slot in row]
            for room, row in data.plan.items()
            if room.startswith("dorm")
        },
    }
    solver.emergency_state = state
    return data, state


def test_high_need_opens_every_slot_and_produces_full_capacity_plan(solver):
    data, state = setup_episode(solver, 10)

    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)

    assert len(data.dorm) == 10
    assert all(
        slot.agent == "Free"
        for room in state["dorm_layout"]
        for slot in data.plan[room]
    )
    task = solver.tasks[0]
    admitted = {name for row in task.plan.values() for name in row} - {"Current"}
    assert admitted == set(RECOVERY_NAMES)
    assert task.type == TaskTypes.FILL_DORM and task.emergency_dorm
    assert data.emergency_dorm_agents == {"冰酿", "闪灵", "杜林", "安赛尔"}


def test_fiammetta_keeps_configured_position_and_is_not_recovery_bed(solver):
    data, state = setup_episode(solver, 10, fiammetta=True)

    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)

    assert len(data.dorm) == 9
    assert ("dormitory_1", 0) not in {bed.position for bed in data.dorm}
    assert data.plan["dormitory_1"][0].agent == "菲亚梅塔"
    assert solver.tasks[0].plan["dormitory_1"][0] == "Current"
    assert data.operators["菲亚梅塔"].current_room == "dormitory_1"


@pytest.mark.parametrize(
    ("need", "restored"),
    [
        (8, {("dormitory_1", 0), ("dormitory_2", 0)}),
        (7, {("dormitory_1", 0), ("dormitory_2", 0), ("dormitory_1", 1)}),
        (
            6,
            {
                (room, index)
                for room in ("dormitory_1", "dormitory_2")
                for index in (0, 1)
            },
        ),
    ],
)
def test_manager_restoration_uses_room_first_then_slot_order(solver, need, restored):
    data, state = setup_episode(solver, 10)
    solver._open_emergency_beds()
    state["ready_members"] = RECOVERY_NAMES[need:]
    for room, row in state["dorm_layout"].items():
        for name in row[:2]:
            data.operators[name]._current_room, data.operators[name].current_index = (
                "",
                -1,
            )

    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)

    actual = {
        (room, index)
        for room, row in state["dorm_layout"].items()
        for index, name in enumerate(row[:2])
        if data.plan[room][index].agent == name
    }
    assert actual == restored
    assert len(data.dorm) == 10 - len(restored)
    task = solver.tasks[0]
    for room, index in restored:
        assert task.plan[room][index] == state["dorm_layout"][room][index]
    assert not set(state["ready_members"]) & {
        name for row in task.plan.values() for name in row
    }


def test_manager_restoration_does_not_evict_unready_recovery_resident(solver):
    data, state = setup_episode(solver, 1)
    resident = data.operators[RECOVERY_NAMES[0]]
    data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = "", -1
    resident._current_room, resident.current_index = "dormitory_1", 0

    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)

    assert data.plan["dormitory_1"][0].agent == "Free"
    assert (
        next(bed for bed in data.dorm if bed.position == ("dormitory_1", 0)).name
        == resident.name
    )
    assert (
        not solver.tasks
        or solver.tasks[0].plan.get("dormitory_1", ["Current"] * 5)[0] == "Current"
    )
    assert resident.current_room == "dormitory_1"


def test_manager_used_in_working_facility_is_not_pulled_back(solver):
    data, state = setup_episode(solver, 0)
    manager = data.operators["冰酿"]
    manager._current_room, manager.current_index = "room_1_1", 0

    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)

    assert data.plan["dormitory_1"][0].agent == "Free"
    assert all(
        manager.name not in row for task in solver.tasks for row in task.plan.values()
    )
    assert manager.current_room == "room_1_1"


def test_reserved_manager_stays_available_to_specialized_task(solver):
    data, state = setup_episode(solver, 0)
    manager = data.operators["冰酿"]
    manager._current_room, manager.current_index = "", -1
    solver.tasks.append(
        SchedulerTask(NOW, {"factory": [manager.name]}, TaskTypes.WORKSHOP)
    )

    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)

    assert data.plan["dormitory_1"][0].agent == "Free"
    assert all(
        manager.name not in row
        for task in solver.tasks
        if getattr(task, "emergency_dorm", False)
        for row in task.plan.values()
    )


def test_rebuilding_capacity_preserves_actual_resident_and_recovery_deadline(solver):
    data, state = setup_episode(solver, 10)
    bed = data.dorm[0]
    resident = data.operators[RECOVERY_NAMES[0]]
    resident._current_room, resident.current_index = bed.position
    bed.name, bed.time = resident.name, NOW

    solver._open_emergency_beds()
    solver._open_emergency_beds()

    refreshed = next(
        candidate for candidate in data.dorm if candidate.position == bed.position
    )
    assert refreshed.name == resident.name and refreshed.time == NOW
    assert len({candidate.position for candidate in data.dorm}) == 10
