from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, call

import numpy as np
import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import graph
from arknights_mower.utils.scene import Scene

NAV_BAR = ((26, 20), (559, 93))
CHECK_IN = ((65, 384), (139, 453))


def returning_solver(frames):
    solver = object.__new__(BaseSchedulerSolver)
    frames = iter(frames)
    current = None

    def scene():
        nonlocal current
        current = next(frames)
        return current

    solver.scene = Mock(side_effect=scene)
    solver.recog = SimpleNamespace(update=Mock())
    solver.detect_room_type = Mock(return_value="贸易站")
    solver.sleep = Mock()
    solver.tap = Mock()
    solver.back = Mock()
    solver.find = Mock(side_effect=lambda key: NAV_BAR if key == "nav_button" else None)
    return solver


def test_trade_exit_ignores_temporary_recognition_and_uses_visible_back():
    solver = returning_solver(
        [
            Scene.ORDER_LIST,
            Scene.FACTORY_ROOM,
            Scene.INFRA_DETAILS,
            Scene.INFRA_DETAILS,
            Scene.INFRA_MAIN,
        ]
    )

    solver.scene_graph_navigation(Scene.INFRA_MAIN)

    assert solver.tap.call_args_list == [call(NAV_BAR, x_rate=0.08, interval=1)] * 2
    assert solver.sleep.call_args_list == [call(0.3)] * 2
    solver.back.assert_not_called()


def test_enter_room_propagates_the_bounded_return_without_retry(monkeypatch):
    scenes = [Scene.ORDER_LIST, Scene.ORDER_LIST]
    scenes += [Scene.INFRA_DETAILS, Scene.INFRA_DETAILS, Scene.ORDER_LIST] * 3
    solver = returning_solver(scenes)
    solver.find = Mock(
        side_effect=lambda key: {
            "order_label": True,
            "nav_button": NAV_BAR,
        }.get(key)
    )
    # The first order label belongs to enter_room. Subsequent frames have
    # matching page labels, including the repeated return to the same order.
    find = solver.find.side_effect
    solver.find.side_effect = lambda key: (
        None if key == "order_label" and solver.scene.call_count >= 3 else find(key)
    )
    warning = Mock()
    monkeypatch.setattr(graph.logger, "warning", warning)

    with pytest.raises(graph.TradeNavigationError, match="贸易站返回未确认"):
        solver.enter_room("room_2_1")

    assert solver.tap.call_count == 6
    solver.back.assert_not_called()
    warning.assert_called_once()
    assert warning.call_args.kwargs["extra"] == {"archive_screenshots": True}


def test_room_return_requires_two_frames_without_order_page():
    solver = returning_solver(
        [
            Scene.ORDER_LIST,
            Scene.INFRA_DETAILS,
            Scene.ORDER_LIST,
            Scene.INFRA_DETAILS,
            Scene.INFRA_DETAILS,
        ]
    )

    solver.scene_graph_navigation(Scene.INFRA_DETAILS)

    assert solver.scene.call_count == 5
    assert solver.tap.call_args_list == [call(NAV_BAR, x_rate=0.08, interval=1)] * 2
    solver.back.assert_not_called()


def test_trade_return_waits_for_arrow_without_spending_an_input_attempt():
    solver = returning_solver([Scene.ORDER_LIST] * 4 + [Scene.INFRA_DETAILS] * 2)
    solver.find.side_effect = lambda key: (
        NAV_BAR if key == "nav_button" and solver.scene.call_count >= 4 else None
    )

    solver.scene_graph_navigation(Scene.INFRA_DETAILS)

    assert solver.scene.call_count == 6
    solver.tap.assert_called_once_with(NAV_BAR, x_rate=0.08, interval=1)
    solver.back.assert_not_called()


def test_trade_return_without_arrow_uses_only_the_observation_limit():
    solver = returning_solver([Scene.ORDER_LIST] * 13)
    solver.find.side_effect = None
    solver.find.return_value = None

    with pytest.raises(graph.TradeNavigationError):
        solver.scene_graph_navigation(Scene.INFRA_MAIN)

    assert solver.scene.call_count == 13
    assert solver.sleep.call_args_list == [call(0.3)] * 12
    solver.tap.assert_not_called()
    solver.back.assert_not_called()


def test_other_facility_keeps_normal_back_action():
    solver = returning_solver([Scene.INFRA_DETAILS, Scene.INFRA_MAIN])
    solver.detect_room_type.return_value = "制造站"

    solver.scene_graph_navigation(Scene.INFRA_MAIN)

    solver.tap.assert_not_called()
    solver.back.assert_called_once_with()


def test_trade_return_budget_is_not_renewed_when_home_navigation_reenters_trade():
    scenes = [
        Scene.ORDER_LIST,
        Scene.INFRA_DETAILS,
        Scene.INFRA_DETAILS,
        Scene.INFRA_MAIN,
    ]
    solver = returning_solver(scenes * 3 + [Scene.ORDER_LIST])

    with pytest.raises(graph.TradeNavigationError):
        solver.scene_graph_navigation(Scene.INDEX)

    assert solver.tap.call_args_list == [call(NAV_BAR, x_rate=0.08, interval=1)] * 6
    assert solver.back.call_count == 3


def test_unexpected_room_view_does_not_complete_trade_return():
    solver = returning_solver([Scene.ORDER_LIST] + [Scene.INFRA_DETAILS] * 12)
    solver.detect_room_type.return_value = "制造站"

    with pytest.raises(graph.TradeNavigationError):
        solver.scene_graph_navigation(Scene.INFRA_DETAILS)

    solver.tap.assert_called_once_with(NAV_BAR, x_rate=0.08, interval=1)
    solver.back.assert_not_called()


@pytest.mark.parametrize("room", ["room_1_1", "room_2_1"])
@pytest.mark.parametrize("recovers", [True, False])
def test_open_trade_mood_recovers_order_page_once(room, recovers):
    solver = returning_solver([])
    phase = "room"
    presses = 0

    def find(key):
        if key == "order_label" and phase == "order":
            return True
        if key == "arrange_check_in" and phase == "room":
            return CHECK_IN
        if key == "room_detail" and phase == "mood":
            return True

    def click(*args, **kwargs):
        nonlocal phase, presses
        presses += 1
        phase = "mood" if presses == 2 and recovers else "order"

    def return_to_room(_target):
        nonlocal phase
        phase = "room"

    solver.scene = Mock(return_value=Scene.INFRA_DETAILS)
    solver.find = Mock(side_effect=find)
    solver.tap.side_effect = click
    solver.scene_graph_navigation = Mock(side_effect=return_to_room)
    solver.detect_room = Mock(return_value=room)
    solver.get_color = Mock(return_value=np.array([255, 255, 255]))

    if recovers:
        solver.turn_on_room_detail(room)
        assert phase == "mood"
    else:
        with pytest.raises(graph.TradeNavigationError, match="再次回到订单页"):
            solver.turn_on_room_detail(room)

    solver.scene_graph_navigation.assert_called_once_with(Scene.INFRA_DETAILS)
    assert solver.tap.call_args_list == [call(CHECK_IN, interval=0.2)] * 2
    solver.back.assert_not_called()


def test_startup_exhaustion_preserves_existing_reservation_and_stops_scan():
    from arknights_mower.solvers import base_schedule

    task = SimpleNamespace(
        type=base_schedule.TaskTypes.RE_ORDER, time=datetime(2026, 11, 23, 23)
    )
    solver = object.__new__(BaseSchedulerSolver)
    solver.tasks = [task]
    solver.op_data = SimpleNamespace(run_order_rooms=["room_1_1", "room_2_1"])
    solver._startup_run_order_check_pending = True
    solver._sync_run_order_tasks = Mock()
    solver._startup_order_check_fits = Mock(return_value=True)
    solver._emergency_run_order_available = Mock(return_value=True)
    solver.find_next_task = Mock(return_value=None)
    solver.get_run_order_time = Mock(
        side_effect=graph.TradeNavigationError("not observed")
    )
    solver.back_to_infrastructure = Mock()

    solver._check_startup_run_orders()
    solver._check_startup_run_orders()

    solver.get_run_order_time.assert_called_once_with("room_1_1", read_mood=True)
    solver.back_to_infrastructure.assert_not_called()
    assert solver.tasks == [task] and solver.tasks[0] is task
    assert task.time == datetime(2026, 11, 23, 23)
