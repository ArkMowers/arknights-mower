from copy import deepcopy
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.tests import base_scheduler_tests
from arknights_mower.tests.workshop_batch_tests import batch as batch
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.scene import Scene

BaseSchedulerSolver = base_scheduler_tests.BaseSchedulerSolver


@pytest.mark.parametrize("factory_plan", [None, []])
@pytest.mark.parametrize("cached", [True, False])
@pytest.mark.parametrize(
    "resident, name_readings",
    [
        ("特克诺", []),
        ("", []),
        ("特克诺", ["", "特克诺"]),
        ("特克诺", ["", "", "特克诺"]),
        ("特克诺", ["", "", ""]),
    ],
)
def test_batch_reads_actual_resident_before_selection_and_restores_positions(
    batch, factory_plan, cached, resident, name_readings
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
    pending_readings = name_readings[:]
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
        operator.need_to_refresh = lambda **kwargs: True
        operator.depletion_rate = 0
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
        if pending_readings:
            return pending_readings.pop(0)
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

    original_positions = {
        name: (operator.current_room, operator.current_index)
        for name, operator in solver.op_data.operators.items()
    }
    original_tasks = solver.tasks[:]
    solver.sleep = MagicMock()

    solver.craft_material()

    if name_readings == ["", "", ""]:
        assert batch.crafts == []
        assert solver.op_data.plan == original_plan
        assert actual_factory == [resident]
        assert {
            name: (operator.current_room, operator.current_index)
            for name, operator in solver.op_data.operators.items()
        } == original_positions
        assert solver.tasks == original_tasks
        solver.choose_agent.assert_not_called()
        solver.tap_confirm.assert_not_called()
        solver.agent_arrange.assert_not_called()
        batch.errors.assert_called_once()
        assert isinstance(batch.errors.call_args.args[0], RecognizeError)
        assert solver.read_screen.call_count == 3
        assert solver.sleep.call_count == 2
        batch.errors.reset_mock()
        solver.craft_material()

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
