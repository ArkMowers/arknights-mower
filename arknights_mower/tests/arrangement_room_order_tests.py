"""Source workplaces are refilled before cross-facility transfers."""

import json
from copy import deepcopy
from datetime import timedelta
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


@pytest.mark.parametrize(
    "case,fast_first",
    [
        ("positive_floor", True),
        ("missing_model", False),
        ("swapped_seats", True),
        ("workaholic", False),
        ("short_targets", True),
    ],
)
def test_actual_departures_supply_the_room_deadline(staffed_order, case, fast_first):
    from arknights_mower.utils.operators import Operator

    now = staffed_order.clock.now()
    slow_room, fast_room = "room_1_1", "room_3_1"

    def primary(name, room, index, actual, mood, rate):
        return Operator(
            name,
            room,
            index=index,
            current_room=room,
            current_index=actual,
            group="同组",
            operator_type="high",
            mood=mood,
            depletion_rate=rate,
            time_stamp=now,
        )

    slow = primary("鸿雪", slow_room, 0, 0, 1, 4)
    fast = primary("图耶", fast_room, 0, 0, 1, 8)
    other = primary("红", fast_room, 1, 1, 3, 1)
    operators = {op.name: op for op in (slow, fast, other)}
    data = SimpleNamespace(
        operators=operators,
        _projection_now=now,
        mood_calculation_enabled=case == "missing_model",
        calculated_mood_rates=lambda now: {slow.name: 4},
        calculated_mood=lambda name, now: {slow.name: 1}.get(name),
    )
    plan = {slow_room: ["孑"], fast_room: ["锏"], "dormitory_1": [slow.name, fast.name]}
    if case in ("positive_floor", "missing_model"):
        fast.mood = 0
        fast.lower_limit = 4 if case == "positive_floor" else 0
        fast.exhaust_time = now + timedelta(minutes=45)
        if case == "missing_model":
            other.current_room, other.current_index = "", -1
            plan = {
                fast_room: plan[fast_room],
                slow_room: plan[slow_room],
                "dormitory_1": plan["dormitory_1"],
            }
    elif case == "short_targets":
        fast.depletion_rate = 0.5
        other.depletion_rate = 24
        plan["dormitory_1"].append(other.name)
    else:
        plan[fast_room].append("砾")
        if case == "swapped_seats":
            fast.current_index, other.current_index = 1, 0
            fast.depletion_rate = 8
        else:
            fast.depletion_rate = 0.5
            other.mood, other.workaholic = 0, True
    expected = [fast_room, slow_room] if fast_first else [slow_room, fast_room]
    assert staffed_order.base._arrangement_room_order(plan, data, shift_off=True) == [
        *expected,
        "dormitory_1",
    ]


@pytest.mark.parametrize("end", ["open", "fixed", "dormitory"])
def test_generated_handoffs_match_all_feasible_routes(staffed_order, end):
    from arknights_mower.utils.operators import Operator

    base = staffed_order.base
    now = staffed_order.clock.now()
    hours = {
        "room_1_1": 4,
        "factory": 2,
        "room_3_1": 1,
        "contact": 3,
        "room_1_3": 2,
        "meeting": 1,
    }
    entry = {
        "room_1_1": 1,
        "room_3_1": 1,
        "factory": 2,
        "contact": 2,
        "room_1_3": 3,
        "meeting": 4,
    }
    workers = {
        room: Operator(
            room,
            room,
            index=0,
            group="自定组名",
            current_room=room,
            current_index=0,
            mood=hours[room],
            depletion_rate=1,
            time_stamp=now,
            operator_type="high",
        )
        for room in hours
    }
    workers["cover-contact"] = Operator(
        "cover-contact", "", current_room="room_3_1", current_index=1
    )
    data = SimpleNamespace(
        operators=workers, _projection_now=now, mood_calculation_enabled=False
    )

    def drag(a, b):
        right = {"factory", "contact", "meeting"}
        return (
            a in right and b.startswith("room_") and (a, b) != ("meeting", "room_1_3")
        ) or (a.startswith("room_") and b in right)

    def drag_count(route):
        return sum(drag(a, b) for a, b in zip(route, route[1:]))

    def detour_costs(route, original, dorms):
        stops = ["room_2_1", "room_1_3", "meeting", "contact", "central"]
        for count in range(1, min(len(route) + 1, len(route) + len(dorms))):
            done = route[:count]
            pending = [room for room in original if room not in done]
            rest = []
            while pending:
                next_room = next(
                    room
                    for room in pending
                    if room != "contact" or "room_3_1" not in pending
                )
                rest.append(next_room)
                pending.remove(next_room)
            rest.extend(dorms)
            fixed_cost = drag_count(done) + drag_count(rest)
            for first in stops:
                for last in stops:
                    yield fixed_cost + drag(done[-1], first) + drag(last, rest[0])

    feasible = [
        (r, drag_count(r))
        for r in permutations(hours)
        if r.index("room_3_1") < r.index("contact")
    ]
    for original in permutations(hours):
        plan = {room: ["cover-" + room] for room in original}
        plan["room_3_1"].append("second-cover")
        if end == "dormitory":
            plan["dormitory_1"] = list(hours)[:3]
            plan["dormitory_2"] = list(hours)[3:]
        route = base._arrangement_room_order(plan, data, allow_open_end=end == "open")
        work = [room for room in route if room in hours]
        budget = drag_count(work)
        legal = (
            r
            for r, cost in feasible
            if cost <= budget
            and entry[r[0]] == entry[work[0]]
            and (end != "fixed" or r[-1] == work[-1])
        )
        expected = min(
            legal, key=lambda r: tuple((hours[room], work.index(room)) for room in r)
        )
        result = base._arrangement_room_order(
            plan, data, allow_open_end=end == "open", shift_off=True
        )
        dorms = route[len(work) :]
        fits = all(
            new <= old
            for new, old in zip(
                detour_costs(expected, original, dorms),
                detour_costs(work, original, dorms),
            )
        )
        assert result == [*(expected if fits else work), *dorms]


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


@pytest.mark.parametrize(
    "fast_rate, evidence, fast_first",
    [
        (2, "measured", True),
        (0.5, "measured", False),
        (1, "equal", False),
        (0, "unknown", False),
        (2, "retained", False),
        (2, "special_departure", False),
        (2, "card_only_at_limit", False),
        (2, "displayed_zero_with_countdown", False),
    ],
)
def test_generated_shift_keeps_assignments_and_only_reorders_confirmations(
    staffed_order, fast_rate, evidence, fast_first
):
    ui = staffed_order
    solver = ui.solver
    data = solver.op_data
    slow, fast = (data.operators[name] for name in ("鸿雪", "图耶"))
    fast.room = "room_3_1"
    data.plan[fast.room] = data.plan.pop("room_2_2")
    data.run_order_rooms.clear()
    slow.replacement, fast.replacement = ["孑"], ["锏"]
    for op in data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, ui.clock.now()
    slow.mood, slow.lower_limit, slow.depletion_rate = 6, 4, 0.5
    fast.mood, fast.lower_limit, fast.depletion_rate = 4, 0, fast_rate
    ui.config.conf.rescue_threshold = 0
    ui.states[fast.room] = "active"
    ui.durations[fast.room] = 20
    for room in (slow.room, fast.room, "dormitory_1"):
        ui.occupants[room] = data.get_current_room(room, bypass=True)

    solver._plan_primary_recovery(scan_moods=False)
    task = next(task for task in solver.tasks if task.type == ui.task_type.SHIFT_OFF)
    solver.task = task
    task.execution_retained = evidence == "retained"
    if evidence == "special_departure":
        task.ordinary_coordination = False
    if evidence == "card_only_at_limit":
        fast.time_stamp = None
        data.dorm_mood_estimates[fast.name] = (0, ui.clock.now())
    elif evidence == "displayed_zero_with_countdown":
        slow.depletion_rate = 8
        fast.mood = 0
        fast.exhaust_time = ui.clock.now() + timedelta(minutes=30)
    plan, scheduled = deepcopy(task.plan), task.time
    assert [room for room in plan if not room.startswith("dorm")] == [
        slow.room,
        fast.room,
    ]
    assert (plan[slow.room], plan[fast.room]) == (["孑"], ["锏"])
    assert set(plan["dormitory_1"]) >= {slow.name, fast.name}

    assert solver.agent_arrange(task.plan) is not False
    order = [room for event, room, _ in ui.events if event == "staffed"]
    work = [fast.room, slow.room] if fast_first else [slow.room, fast.room]
    assert order == [*work, "dormitory_1"]
    assert (
        ui.occupants[slow.room] == plan[slow.room]
        and ui.occupants[fast.room] == plan[fast.room]
    )
    for name in (slow.name, fast.name):
        index = plan["dormitory_1"].index(name)
        assert ui.occupants["dormitory_1"][index] == name
    assert task.plan == {} and task.time == scheduled


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


@pytest.mark.parametrize("ordinary", [False, True])
def test_priority_visit_after_first_handoff_keeps_the_two_drag_route(
    staffed_order, ordinary
):
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.plan import RIGHT_SIDE_ROOM_CAPACITY, Room

    ui = staffed_order
    solver, data = ui.solver, ui.solver.op_data
    rooms = ["contact", "room_1_3", "recycle", "meeting"]
    primaries = ["白面鸮", "鸿雪", "红", "图耶"]
    replacements = ["孑", "但书", "龙舌兰", "锏"]
    plan = {}
    for room, name, cover, hours in zip(rooms, primaries, replacements, [3, 1, 2, 4]):
        data.plan[room] = [Room(name, "", [cover])]
        data.operators[name] = Operator(
            name,
            room,
            index=0,
            current_room=room,
            current_index=0,
            operator_type="high",
            mood=hours,
            depletion_rate=1,
            time_stamp=ui.clock.now(),
        )
        ui.occupants[room] = [name] + [""] * (RIGHT_SIDE_ROOM_CAPACITY.get(room, 1) - 1)
        ui.durations[room] = 20
        plan[room] = [cover]
    plan["dormitory_1"] = primaries + ["Free"]
    data.run_order_rooms.clear()
    task = ui.task(
        time=ui.clock.now(), task_type=ui.task_type.SHIFT_OFF, task_plan=plan
    )
    task.ordinary_coordination = ordinary
    solver.task = task
    solver.tasks.append(task)
    order = ui.task(
        time=task.time, task_type=ui.task_type.RUN_ORDER, meta_data="room_2_1"
    )
    confirm = solver.tap_confirm.side_effect
    visits = []

    def confirm_then_queue(room, new_plan):
        confirm(room, new_plan)
        ui.occupants[room].extend(
            [""] * (RIGHT_SIDE_ROOM_CAPACITY.get(room, 1) - len(ui.occupants[room]))
        )
        visits.append(room)
        if len(visits) == 1:
            solver.tasks.append(order)

    solver.tap_confirm.side_effect = confirm_then_queue
    start = task.time
    assert solver.agent_arrange(task.plan) is False
    assert task.retains_execution
    visits.append(order.meta_data)
    solver.tasks.remove(order)
    assert solver.agent_arrange(task.plan) is not False
    assert visits == [rooms[0], order.meta_data, *rooms[1:], "dormitory_1"]
    assert sum(ui.base._needs_map_drag(a, b) for a, b in zip(visits, visits[1:])) == 2
    assert task.time == start and task.plan == {}
