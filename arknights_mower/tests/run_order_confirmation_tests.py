"""跑单提交后仍显示选人页时，核验实际驻员并完成订单与原班恢复。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.run_order_restoration_tests import (
    ORIGINAL,
    ROOM,
    prepare_order,
)
from arknights_mower.tests.run_order_restoration_tests import offline as offline
from arknights_mower.tests.run_order_restoration_tests import solver as solver
from arknights_mower.utils.scheduler_task import SchedulerTask


def test_retained_selection_after_submission_completes_order_and_restoration(
    solver, monkeypatch
):
    task, place = prepare_order(solver, monkeypatch, adjusted=False)
    target = task.plan[ROOM].copy()
    state = {"page": "details", "selected": None}
    confirmations = []
    observed = []

    def find(name, *args, **kwargs):
        visible = {
            "connecting": "connecting",
            "confirm_blue": "selection",
            "room_detail": "details",
        }
        return (1768, 1015) if visible.get(name) == state["page"] else None

    def choose(names, room, **kwargs):
        assert room == ROOM
        assert state["page"] == "selection"
        state["selected"] = names.copy()

    def tap(*args, **kwargs):
        if state["page"] == "details":
            state["page"] = "selection"
            return
        assert state["page"] == "selection"
        confirmations.append(state["selected"].copy())
        place(state["selected"])
        state["page"] = "connecting"

    def finish_submission():
        assert state["page"] == "connecting"
        state["page"] = "selection"
        return True

    read = solver.get_agent_from_room.side_effect

    def observe(*args, **kwargs):
        assert state["page"] == "details"
        result = read(*args, **kwargs)
        observed.append([slot["agent"] for slot in result])
        return result

    solver.find = MagicMock(side_effect=find)
    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap = MagicMock(side_effect=tap)
    solver.back.side_effect = lambda *args, **kwargs: state.update(page="details")
    solver.waiting_solver = MagicMock(side_effect=finish_submission)
    solver.tap_confirm = base_schedule.BaseSchedulerSolver.tap_confirm.__get__(solver)
    solver.get_agent_from_room.side_effect = observe

    solver.agent_arrange(task.plan)

    assert confirmations == [target, ORIGINAL]
    assert observed[0] == observed[-1] == ORIGINAL
    assert observed[1:-1] and all(row == target for row in observed[1:-1])
    solver.accept_order.assert_called_once_with()
    solver.drone.assert_not_called()
    solver.record_selection_failure.assert_not_called()
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert task.plan == {}
    assert not hasattr(task, "run_order_restore_pending")
    assert not hasattr(task, "run_order_original_roster")


def test_submission_feedback_preserves_a_new_secondary_confirmation():
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.task = SchedulerTask()
    solver.op_data = SimpleNamespace(mood_calculation_enabled=False)
    solver.recog = SimpleNamespace(w=1920, h=1080, update=MagicMock())
    state = {"page": "selection"}
    confirmed = []

    def find(name, **kwargs):
        visible = {
            "confirm_blue": "selection",
            "connecting": "connecting",
            "arrange_confirm": "secondary",
            "room_detail": "details",
        }
        return (1768, 1015) if visible.get(name) == state["page"] else None

    def tap(*args, **kwargs):
        confirmed.append(state["page"])
        state["page"] = "connecting" if state["page"] == "selection" else "details"

    solver.find = MagicMock(side_effect=find)
    solver.tap = MagicMock(side_effect=tap)
    solver.sleep = MagicMock()
    solver.back = MagicMock()
    solver.waiting_solver = MagicMock(
        side_effect=lambda: state.update(page="secondary") or True
    )

    solver.tap_confirm(ROOM)

    assert confirmed == ["selection", "secondary"]
    assert state["page"] == "details"
    solver.back.assert_not_called()
