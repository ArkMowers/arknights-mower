from copy import deepcopy
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.tests import base_scheduler_tests
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

BaseSchedulerSolver = base_scheduler_tests.BaseSchedulerSolver


@pytest.fixture(params=[None, [], ["年"], ["年", "空爆"]])
def schedule(request):
    return (
        {}
        if request.param is None
        else {"factory": [SimpleNamespace(agent=name) for name in request.param]}
    )


def make_operators(schedule, occupant=""):
    data = object.__new__(Operators)
    data.plan = deepcopy(schedule)
    data.config = SimpleNamespace(free_room=False)
    data.operators = (
        {
            occupant: SimpleNamespace(
                name=occupant, current_room="factory", current_index=0
            )
        }
        if occupant
        else {}
    )
    return data


@pytest.mark.parametrize("occupant", ["", "九色鹿"])
def test_cached_workshop_has_one_physical_slot_without_plan_mutation(
    schedule, occupant
):
    data = make_operators(schedule, occupant)
    assert data.get_current_room("factory", True) == [occupant]
    assert data.get_current_room("factory") == ([occupant] if occupant else None)
    assert data.get_current_room("factory", current_index=[]) == [occupant]
    assert data.plan == schedule


@pytest.mark.parametrize("empty", [False, True])
def test_workshop_mood_reader_reads_physical_slot_without_static_staff(schedule, empty):
    solver = MagicMock()
    solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="九色鹿")
    solver.tasks = [solver.task]
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.find.return_value = empty
    solver.read_screen.return_value = "九色鹿"
    solver.read_accurate_mood.return_value = 20
    solver.op_data.plan = deepcopy(schedule)
    solver.op_data.config.free_room = False
    operator = MagicMock()
    operator.current_room = "factory"
    operator.current_index = 0
    operator.need_to_refresh.return_value = True
    operator.depletion_rate = 1
    solver.op_data.operators = {"九色鹿": operator}
    solver.op_data.update_detail.return_value = None

    result = BaseSchedulerSolver.get_agent_from_room(solver, "factory")

    assert len(result) == 1
    assert result[0]["agent"] == ("" if empty else "九色鹿")
    assert solver.read_screen.call_count == (0 if empty else 1)
    assert solver.read_accurate_mood.call_count == (0 if empty else 1)
    assert solver.op_data.plan == schedule
    solver.scroll_room_operators.assert_not_called()


def test_ordinary_rooms_keep_schedule_capacity():
    data = make_operators({"central": [SimpleNamespace(agent="阿米娅")]})
    assert data.get_current_room("central", True) == [""]
    with pytest.raises(KeyError):
        data.get_current_room("unconfigured", True)


def test_training_room_keeps_two_physical_slots():
    assert make_operators({}).get_current_room("train", True) == ["", ""]


@pytest.mark.parametrize("occupant", ["", "空爆"])
def test_actual_workshop_arrangement_confirms_staff_without_plan_entry(
    schedule, occupant, monkeypatch
):
    solver = MagicMock()
    solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="九色鹿")
    solver.tasks = [solver.task]
    solver.waiting_scene = []
    solver.scene.return_value = Scene.INFRA_DETAILS
    solver.ensure_dorm_recovery_order.return_value = False
    solver._can_refresh_idle_dorm_search.return_value = False
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)
    solver.op_data.plan = deepcopy(schedule)
    solver.op_data.run_order_rooms = {}
    solver.op_data.config.free_room = False
    operator = MagicMock()
    operator.name = "九色鹿"
    operator.current_room = ""
    operator.current_index = -1
    operator.need_to_refresh.return_value = True
    operator.depletion_rate = 1
    solver.op_data.operators = {"九色鹿": operator}
    if occupant:
        previous = MagicMock()
        previous.name = occupant
        previous.current_room = "factory"
        previous.current_index = 0
        solver.op_data.operators[occupant] = previous
    solver.op_data.get_current_room.side_effect = MethodType(
        Operators.get_current_room, solver.op_data
    )
    solver.get_agent_from_room.side_effect = MethodType(
        BaseSchedulerSolver.get_agent_from_room, solver
    )
    solver.find.side_effect = lambda name, **kwargs: name != "infra_no_operator"
    solver.read_screen.return_value = "九色鹿"
    solver.read_accurate_mood.return_value = 20

    def update_detail(name, mood, room, index, update_time):
        current = solver.op_data.operators[name]
        current.current_room, current.current_index = room, index
        return None

    solver.op_data.update_detail.side_effect = update_detail
    errors = MagicMock()
    monkeypatch.setattr(base_scheduler_tests.base_schedule, "save_exception", errors)
    plan = {"factory": ["九色鹿"]}

    assert BaseSchedulerSolver.agent_arrange_room(solver, {}, "factory", plan) == {}

    solver.choose_agent.assert_called_once()
    assert solver.choose_agent.call_args.args == (["九色鹿"], "factory")
    solver.tap_confirm.assert_called_once_with("factory", {})
    assert solver.get_agent_from_room.call_count == 1
    assert (operator.current_room, operator.current_index) == ("factory", 0)
    if occupant:
        assert previous.current_room == ""
    assert solver.op_data.plan == schedule
    assert plan == {}
    errors.assert_not_called()
