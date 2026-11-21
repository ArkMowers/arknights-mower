"""Source workplaces are refilled before cross-facility transfers."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from arknights_mower.tests import run_order_staffing_admission_tests as admission

staffed_order = admission.staffed_order


@pytest.mark.parametrize(
    "plan,positions,expected",
    [
        (
            {"meeting": ["A"], "room_2_3": ["N"]},
            {"A": "room_2_3", "N": "dormitory_1"},
            ["room_2_3", "meeting"],
        ),
        (
            {"meeting": ["A"], "room_1_1": ["B"], "room_3_1": ["N"]},
            {"A": "room_1_1", "B": "room_3_1", "N": ""},
            ["room_3_1", "room_1_1", "meeting"],
        ),
        (
            {"meeting": ["B"], "room_1_1": ["A"]},
            {"A": "meeting", "B": "room_1_1"},
            ["meeting", "room_1_1"],
        ),
        (
            {
                "dormitory_4": ["A"],
                "meeting": ["N", "Current"],
                "dormitory_1": ["B"],
                "room_1_1": ["Free"],
            },
            {"N": "room_3_1"},
            ["meeting", "room_1_1", "dormitory_1", "dormitory_4"],
        ),
    ],
)
def test_stable_dependencies_do_not_mutate_plan(
    staffed_order, plan, positions, expected
):
    original = deepcopy(plan)
    data = SimpleNamespace(
        operators={
            name: SimpleNamespace(current_room=room) for name, room in positions.items()
        }
    )
    assert staffed_order.base._arrangement_room_order(plan, data) == expected
    assert plan == original


def test_real_arrangement_refills_source_before_taking_its_operator(staffed_order):
    ui = staffed_order
    ui.occupants["room_1_1"] = [""]
    ui.occupants["room_2_2"] = ["鸿雪"]
    for name, room in [("鸿雪", "room_2_2"), ("图耶", "")]:
        ui.solver.op_data.operators[name].current_room = room
        ui.solver.op_data.operators[name].current_index = 0 if room else -1
    task = admission.correction(ui, {"room_1_1", "room_2_2"})
    original_time = task.time
    confirm = ui.solver.tap_confirm.side_effect
    confirmed = []

    def observe(room, new_plan):
        if room == "room_1_1":
            assert ui.occupants["room_2_2"] == ["图耶"]
        confirm(room, new_plan)
        confirmed.append(room)

    ui.solver.tap_confirm.side_effect = observe
    assert ui.solver.agent_arrange(task.plan) is not False
    assert confirmed == ["room_2_2", "room_1_1"]
    assert task.time == original_time and task.plan == {}
