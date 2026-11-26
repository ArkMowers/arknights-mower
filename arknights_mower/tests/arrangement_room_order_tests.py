"""Source workplaces are refilled before cross-facility transfers."""

import json
from copy import deepcopy
from itertools import permutations
from pathlib import Path
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


ROUTES = json.loads(
    (Path(__file__).parent / "fixtures/arrangement_room_routes.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", ROUTES, ids=[case["case"] for case in ROUTES])
def test_facility_map_route(staffed_order, case):
    plan = {room: case.get("targets", {}).get(room, [room]) for room in case["rooms"]}
    original = deepcopy(plan)
    data = SimpleNamespace(
        operators={
            name: SimpleNamespace(current_room=room)
            for name, room in case.get("positions", {}).items()
        }
    )
    assert staffed_order.base._arrangement_room_order(plan, data) == case["expected"]
    assert plan == original


@pytest.mark.parametrize("open_end", [False, True])
def test_route_matches_exhaustive_search_from_every_endpoint(staffed_order, open_end):
    base = staffed_order.base
    rooms = (
        "room_2_1",
        "factory",
        "room_1_3",
        "room_3_3" if open_end else "central",
        "contact",
        "meeting",
    )
    # B103 接走加工站的驻员，会客室再接走 B103 的驻员。
    positions = {"room_1_3": "factory", "meeting": "room_1_3"}
    data = SimpleNamespace(
        operators={
            name: SimpleNamespace(current_room=source)
            for name, source in positions.items()
        }
    )

    def drags(route):
        return sum(base._needs_map_drag(a, b) for a, b in zip(route, route[1:]))

    for original in permutations(rooms):
        plan = {room: [room] for room in original}
        stable = base._arrangement_room_order(plan, data, prefer_visible=False)
        possible = (
            [(stable[0], *tail) for tail in permutations(stable[1:])]
            if open_end
            else [
                (stable[0], *middle, stable[-1])
                for middle in permutations(stable[1:-1])
            ]
        )
        legal = [
            route
            for route in possible
            if all(
                route.index(source) < route.index(dest)
                for dest, source in positions.items()
            )
        ]
        result = base._arrangement_room_order(plan, data, allow_open_end=open_end)
        assert tuple(result) in legal
        assert drags(result) == min(map(drags, legal))
        if drags(result) == drags(stable):
            assert result == stable


@pytest.mark.parametrize("target", ["Current", "Free", "_", ""])
def test_route_does_not_cross_a_room_that_resolves_its_occupants_at_execution(
    staffed_order, target
):
    plan = {"room_2_1": ["A"], "factory": [target], "room_2_2": ["B"], "contact": ["C"]}
    assert staffed_order.base._arrangement_room_order(
        plan, SimpleNamespace(operators={})
    ) == list(plan)


@pytest.fixture
def four_workplaces(staffed_order):
    from arknights_mower.utils.plan import Room

    ui = staffed_order
    data = ui.solver.op_data
    targets = {
        "room_1_1": ["鸿雪"],
        "factory": ["孑"],
        "room_2_2": ["图耶"],
        "contact": ["锏"],
    }
    for room in ("factory", "contact"):
        data.plan[room] = [Room(targets[room][0], "", [])]
        ui.occupants[room] = [""]
        ui.durations[room] = 20
    task = ui.task(
        time=ui.clock.now(),
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan=deepcopy(targets),
    )
    ui.solver.task = task
    ui.solver.tasks.append(task)
    return ui, targets, task


@pytest.mark.parametrize("retained", [False, True])
def test_real_arrangement_confirms_the_same_rosters_and_keeps_a_retained_route(
    four_workplaces, retained
):
    ui, targets, task = four_workplaces
    task.execution_retained = retained
    start = task.time

    assert ui.solver.agent_arrange(task.plan) is not False
    assert [r for event, r, _ in ui.events if event == "staffed"] == (
        list(targets) if retained else ["room_1_1", "room_2_2", "factory", "contact"]
    )
    assert {room: ui.occupants[room] for room in targets} == targets
    assert task.time == start and task.plan == {}


@pytest.mark.parametrize("read_orders", [False, True])
def test_three_workplaces_leave_the_last_stop_open_only_without_order_reads(
    four_workplaces, read_orders
):
    ui, targets, task = four_workplaces
    del task.plan["contact"]
    if not read_orders:
        ui.solver.op_data.run_order_rooms.clear()
    original = list(task.plan)

    assert ui.solver.agent_arrange(task.plan) is not False
    assert [r for event, r, _ in ui.events if event == "staffed"] == (
        original if read_orders else ["room_1_1", "room_2_2", "factory"]
    )
    assert all(ui.occupants[room] == targets[room] for room in original)


def test_urgent_order_interrupts_the_shorter_route_and_resumes_remaining_rooms(
    four_workplaces,
):
    ui, targets, task = four_workplaces
    start = task.time
    confirm = ui.solver.tap_confirm.side_effect
    order = ui.task(
        time=start,
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )

    def confirm_then_queue_order(room, new_plan):
        confirm(room, new_plan)
        if room == "room_2_2":
            ui.solver.tasks.append(order)

    ui.solver.tap_confirm.side_effect = confirm_then_queue_order
    for _ in range(2):
        assert ui.solver.agent_arrange(task.plan) is False
        assert task.time == start and task in ui.solver.tasks
        assert task.plan == {
            "factory": targets["factory"],
            "contact": targets["contact"],
        }
        assert [r for event, r, _ in ui.events if event == "staffed"] == [
            "room_1_1",
            "room_2_2",
        ]
    ui.solver.tasks.remove(order)
    assert ui.solver.agent_arrange(task.plan) is not False
    assert [r for event, r, _ in ui.events if event == "staffed"] == [
        "room_1_1",
        "room_2_2",
        "factory",
        "contact",
    ]
    assert {room: ui.occupants[room] for room in targets} == targets
    assert task.time == start and task.plan == {}
