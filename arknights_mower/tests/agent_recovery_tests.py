"""画面无进展交给有界恢复；用户停止仍立即结束，不重放输入。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin, base_schedule  # noqa: E402
from arknights_mower.solvers.base_mixin import (  # noqa: E402
    AgentSelectionNotReady,
    BaseMixin,
)
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402


def test_unready_verification_does_not_sort_again_on_uncertain_page():
    solver = BaseMixin()
    solver.wait_for_arranged_agents = MagicMock(
        side_effect=AgentSelectionNotReady("移动中")
    )
    solver.switch_arrange_order = MagicMock()
    with pytest.raises(AgentSelectionNotReady):
        solver.verify_agent(["梅尔"], "room_1_1")
    solver.wait_for_arranged_agents.assert_called_once()
    solver.switch_arrange_order.assert_not_called()


@pytest.mark.parametrize("stopped", [False, True])
def test_room_recovery_is_bounded_and_user_stop_is_not_retried(monkeypatch, stopped):
    solver = MagicMock()
    solver.scene.return_value = Scene.INFRA_MAIN
    attempts = [AgentSelectionNotReady("排序未变化")] * 4
    if stopped:
        attempts = [attempts[0], MowerExit()]
    solver.enter_room.side_effect = attempts
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    plan = {"room_1_1": ["梅尔"]}
    error = MowerExit if stopped else AgentSelectionNotReady
    with pytest.raises(error):
        BaseSchedulerSolver.agent_arrange_room(solver, {}, "room_1_1", plan)
    assert solver.enter_room.call_count == (2 if stopped else 4)
    assert plan == {"room_1_1": ["梅尔"]}
    solver.tap_confirm.assert_not_called()
    solver.device.exit.assert_not_called()


def room_solver(monkeypatch, *, enter_on=None, enter_after_reset=False):
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=None)
    state = {"room": "main", "taps": 0}
    solver.find = MagicMock(
        side_effect=lambda name: (
            ((10, 10), (30, 30))
            if name == "control_central" and state["room"] == "main"
            else None
        )
    )
    solver.detect_room = MagicMock(side_effect=lambda: state["room"])
    polygon = np.array([[400, 550], [400, 680], [700, 680], [700, 550]])
    monkeypatch.setattr(base_mixin.segment, "base", lambda *_: {"room_1_1": polygon})
    solver.adjust_room = MagicMock(side_effect=lambda p: p)

    def tap(*args, **kwargs):
        state["taps"] += 1
        if state["taps"] == enter_on or (
            enter_after_reset and solver.back_to_index.called
        ):
            state["room"] = "room_1_1"

    solver.tap = MagicMock(side_effect=tap)
    solver.sleep = MagicMock()
    solver.back_to_index = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    return solver


def test_room_entered_by_final_click_is_not_reported_failed(monkeypatch):
    solver = room_solver(monkeypatch, enter_on=5)
    solver.enter_room("room_1_1")
    assert solver.tap.call_count == 5
    solver.back_to_index.assert_not_called()


def test_unchanged_overview_is_reentered_before_more_room_clicks(monkeypatch):
    solver = room_solver(monkeypatch, enter_after_reset=True)
    solver.enter_room("room_1_1")
    assert solver.tap.call_count == 6
    solver.back_to_index.assert_called_once()
    solver.back_to_infrastructure.assert_called_once()


def test_failed_room_navigation_has_limit_and_identifies_target(monkeypatch):
    solver = room_solver(monkeypatch)
    with pytest.raises(RuntimeError, match="未成功进入房间 room_1_1"):
        solver.enter_room("room_1_1")
    assert solver.tap.call_count == 15
    assert solver.back_to_index.call_count == 2
    assert solver.back_to_infrastructure.call_count == 2


def test_stop_during_room_navigation_does_not_reenter_map(monkeypatch):
    solver = room_solver(monkeypatch)
    solver.tap.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.enter_room("room_1_1")
    solver.tap.assert_called_once()
    solver.back_to_index.assert_not_called()


def test_connection_overlay_does_not_receive_room_taps(monkeypatch):
    solver = room_solver(monkeypatch)
    solver.find.side_effect = lambda name: name == "connecting"
    with pytest.raises(RuntimeError):
        solver.enter_room("room_1_1")
    solver.tap.assert_not_called()
