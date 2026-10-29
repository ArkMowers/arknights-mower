from copy import deepcopy
from datetime import datetime
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import base_scheduler_tests
from arknights_mower.tests.workshop_batch_tests import batch as batch
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scene import Scene

BaseSchedulerSolver = base_scheduler_tests.BaseSchedulerSolver


@pytest.mark.parametrize("factory_plan", [None, []])
@pytest.mark.parametrize("cached", [True, False])
@pytest.mark.parametrize("resident", ["特克诺", ""])
@pytest.mark.parametrize("card_only", [False, True])
def test_batch_reads_actual_resident_before_selection_and_restores_positions(
    batch, factory_plan, cached, resident, card_only
):
    solver = batch.solver
    if factory_plan is None:
        del solver.op_data.plan["factory"]
    else:
        solver.op_data.plan["factory"] = factory_plan
    original_plan = deepcopy(solver.op_data.plan)
    previous = solver.op_data.operators["特克诺"]
    if not cached:
        previous.current_room, previous.current_index = "", -1
    actual_factory = [resident]
    arrange = solver.agent_arrange.side_effect
    events = []
    pending_factory = []
    solver.waiting_scene = []
    solver.scene = MagicMock(return_value=Scene.INFRA_DETAILS)
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.recog = MagicMock()
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.op_data.config = SimpleNamespace(free_room=False)
    solver.op_data.run_order_rooms = {}
    solver.op_data.all_dorms = lambda: []
    for name, operator in solver.op_data.operators.items():
        operator.name = name
        operator.room = operator.current_room
        operator.need_to_refresh = lambda **kwargs: True
        operator.depletion_rate = 0
    if card_only:
        solver.op_data.dorm_mood_estimates = {
            name: (24, datetime.now()) for name in ("蜜莓", "年", "空爆")
        }
        for name in solver.op_data.dorm_mood_estimates:
            solver.op_data.operators[name].mood = -1
    craft = solver.generate_product.side_effect

    def craft_with_observed_mood(name, snapshot):
        assert solver.op_data.operators[name].mood == 24
        return craft(name, snapshot)

    solver.generate_product.side_effect = craft_with_observed_mood
    solver.op_data.get_current_room = MethodType(
        Operators.get_current_room, solver.op_data
    )
    solver.op_data.get_refresh_index = MethodType(
        Operators.get_refresh_index, solver.op_data
    )

    def choose(names, room, **kwargs):
        pending_factory[:] = names
        events.append(("choose", names[:]))

    def confirm(room, new_plan):
        actual_factory[:] = pending_factory
        events.append(("confirm", actual_factory[:]))

    def read_name(*args, **kwargs):
        return actual_factory[0]

    def find(name, **kwargs):
        if name == "infra_no_operator":
            events.append(("read", actual_factory[:]))
            return not actual_factory[0]
        return True

    def update_detail(name, mood, room, index, update_time):
        operator = solver.op_data.operators[name]
        operator.current_room, operator.current_index = room, index
        operator.mood = mood
        return None

    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap_confirm = MagicMock(side_effect=confirm)
    solver.find = MagicMock(side_effect=find)
    solver.read_screen = MagicMock(side_effect=read_name)
    solver.read_accurate_mood = MagicMock(return_value=24)
    solver.op_data.update_detail = MagicMock(side_effect=update_detail)
    for name in (
        "back",
        "wait_product_complete",
        "refresh_facility_state",
        "turn_on_room_detail",
        "record_selection_success",
    ):
        setattr(solver, name, MagicMock())
    solver.enter_room.side_effect = lambda *args, **kwargs: setattr(
        solver.scene, "return_value", Scene.INFRA_DETAILS
    )
    solver.back.side_effect = lambda *args, **kwargs: setattr(
        solver.scene, "return_value", Scene.INFRA_MAIN
    )

    def arrange_and_update_actual(plan, get_time=False):
        requested = deepcopy(plan)
        if "factory" in plan:
            BaseSchedulerSolver.agent_arrange_room(
                solver, {}, "factory", plan, get_time=get_time
            )
        return arrange(requested, get_time)

    solver.agent_arrange = MagicMock(side_effect=arrange_and_update_actual)
    solver.get_agent_from_room = MagicMock(
        side_effect=MethodType(BaseSchedulerSolver.get_agent_from_room, solver)
    )

    solver.infra_main()

    assert batch.crafts == ["蜜莓", "年", "空爆"]
    assert solver.op_data.plan == original_plan
    assert events[0] == ("read", [resident])
    assert actual_factory == [resident or "蜜莓"]
    for name, index in (("年", 1), ("空爆", 2)):
        operator = solver.op_data.operators[name]
        assert (operator.current_room, operator.current_index) == ("dormitory_1", index)
    first = solver.op_data.operators["蜜莓"]
    assert (first.current_room, first.current_index) == (
        ("dormitory_1", 0) if resident else ("factory", 0)
    )
    batch.errors.assert_not_called()
    assert solver.tasks == []


def test_crafting_restores_borrowed_operator_through_real_room_arrangement(
    batch, monkeypatch
):
    solver = batch.solver
    task = solver.task
    solver.tasks[:] = [task]
    monkeypatch.setattr(config.conf, "workshop_auto_active", False)
    dorm = "dormitory_2"
    original = {
        "factory": ["特克诺"],
        dorm: ["杜林", "琴柳", "年", "空爆", "蜜莓"],
    }
    physical = deepcopy(original)
    solver.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "factory": [Room("特克诺", "", ["蜜莓"])],
                    dorm: [
                        Room("杜林", "", []),
                        Room("琴柳", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert solver.op_data.init_and_validate() is None
    solver.op_data.current_room_changed_callback = None
    for room, names in original.items():
        for index, name in enumerate(names):
            solver.op_data.add(Operator(name, ""))
            operator = solver.op_data.operators[name]
            operator.current_room, operator.current_index = room, index
            operator.mood = 24
            operator.time_stamp = batch.clock.now()
    for bed in solver.op_data.all_dorms():
        bed.name = original[dorm][bed.position[1]]

    solver.agent_arrange = MethodType(BaseSchedulerSolver.agent_arrange, solver)
    solver.get_agent_from_room = MethodType(
        BaseSchedulerSolver.get_agent_from_room, solver
    )
    solver.waiting_scene = []
    solver.scene = MagicMock(return_value=Scene.INFRA_MAIN)
    solver.recog = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    monkeypatch.setattr(base_scheduler_tests.base_schedule, "cropimg", lambda _, p: p)
    viewed_room = "factory"
    pending = []
    confirmations = []

    def enter(room):
        nonlocal viewed_room
        viewed_room = room

    def choose(names, room, **kwargs):
        pending[:] = names

    def confirm(room, new_plan):
        for names in physical.values():
            for index, name in enumerate(names):
                if name in pending:
                    names[index] = ""
        physical[room][:] = pending
        confirmations.append((room, pending[:]))

    def read_name(scope, **kwargs):
        index = [160, 369, 578, 557, 766].index(scope[0][1])
        return physical[viewed_room][index]

    def find(name, **kwargs):
        if name == "infra_no_operator":
            index = [135, 344, 553, 532, 741].index(kwargs["scope"][0][1])
            return physical[viewed_room][index] == ""
        return True

    def read_mood(scope):
        index = [219, 428, 637, 615, 823].index(scope[0][1])
        name = physical[viewed_room][index]
        return solver.op_data.operators[name].mood

    solver.enter_room = MagicMock(side_effect=enter)
    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap_confirm = MagicMock(side_effect=confirm)
    solver.find = MagicMock(side_effect=find)
    solver.read_screen = MagicMock(side_effect=read_name)
    solver.read_accurate_mood = MagicMock(side_effect=read_mood)
    solver.read_operator_time = MagicMock(return_value=batch.clock.now())
    for name in (
        "back",
        "wait_product_complete",
        "refresh_facility_state",
        "turn_on_room_detail",
        "scroll_room_operators",
        "record_selection_success",
    ):
        setattr(solver, name, MagicMock())

    solver.craft_material()

    assert batch.crafts == ["蜜莓"]
    assert confirmations == [
        ("factory", ["蜜莓"]),
        ("factory", ["特克诺"]),
        (dorm, original[dorm]),
    ]
    assert physical == original
    assert solver.op_data.get_current_room("factory", True) == ["特克诺"]
    assert solver.op_data.get_current_room(dorm, True) == original[dorm]
    borrowed = solver.op_data.operators["蜜莓"]
    assert (borrowed.current_room, borrowed.current_index, borrowed.mood) == (
        dorm,
        4,
        0,
    )
    assert task.plan == {}
    assert solver.tasks == []
    solver._plan_dorm_recovery.assert_called_once_with(scan_moods=False)
    batch.errors.assert_not_called()
