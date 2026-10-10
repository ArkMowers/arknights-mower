"""Scene transition failures recover the game without repeating device failures."""

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import networkx as nx
import pytest

from arknights_mower.utils import config, graph
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device import recovery
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.screenshot_backend import ScreenshotFailure
from arknights_mower.utils.device.touch_backend import TouchFailure
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.scene import Scene


@pytest.fixture
def navigation(monkeypatch):
    solver = object.__new__(graph.SceneGraphSolver)
    state = {"scene": Scene.INFRA_MAIN, "attempts": 0}
    solver.scene = lambda: state["scene"]
    solver.sleep = Mock()
    solver.check_current_focus = Mock()
    solver.recog = SimpleNamespace(update=Mock())
    solver.device = SimpleNamespace(reconnect=Mock(), exit=Mock(), launch=Mock())
    routes = nx.DiGraph()
    transition = Mock()
    routes.add_edge(Scene.INFRA_MAIN, Scene.INDEX, transition=transition, weight=1)
    monkeypatch.setattr(graph, "DG", routes)
    monkeypatch.setattr(graph, "logger", Mock())
    monkeypatch.setattr(graph, "csleep", Mock())
    monkeypatch.setattr(recovery, "csleep", Mock())
    monkeypatch.setattr(config, "stop_mower", Event())

    def fail(_):
        state["attempts"] += 1
        if state["attempts"] > 20:
            pytest.fail("Scene transition failures exceeded the navigation limit")
        raise RecognizeError("Game transition failed")

    transition.side_effect = fail
    return solver, state, transition


def test_healthy_transport_still_restarts_a_stuck_game(navigation):
    solver, state, transition = navigation
    solver.device.launch.side_effect = lambda: state.update(scene=Scene.INDEX)

    solver.scene_graph_navigation(Scene.INDEX)

    assert transition.call_count == 7
    solver.device.reconnect.assert_called_once_with()
    solver.device.exit.assert_called_once_with()
    solver.device.launch.assert_called_once_with()
    solver.recog.update.assert_called()


def test_persistent_transition_failure_stops_after_one_game_restart(navigation):
    solver, _, transition = navigation

    with pytest.raises(RecognizeError, match="场景转移.*重启"):
        solver.scene_graph_navigation(Scene.INDEX)

    assert transition.call_count == 14
    solver.device.reconnect.assert_called_once_with()
    solver.device.exit.assert_called_once_with()
    solver.device.launch.assert_called_once_with()


@pytest.mark.parametrize("failure", [MowerExit(), DeviceRecoveryError("exhausted")])
def test_terminal_transition_failure_never_restarts_or_replays(navigation, failure):
    solver, _, transition = navigation
    transition.side_effect = failure

    with pytest.raises(type(failure)) as caught:
        solver.scene_graph_navigation(Scene.INDEX)

    assert caught.value is failure
    transition.assert_called_once_with(solver)
    solver.device.reconnect.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()


def test_failed_device_recovery_does_not_restart_the_game(navigation):
    solver, _, transition = navigation
    failure = DeviceRecoveryError("bound target unavailable")
    solver.device.reconnect.side_effect = failure

    with pytest.raises(DeviceRecoveryError) as caught:
        solver.scene_graph_navigation(Scene.INDEX)

    assert caught.value is failure
    assert transition.call_count == 7
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()


def test_transient_transition_failure_needs_no_game_restart(navigation):
    solver, state, transition = navigation

    def recover(_):
        state["attempts"] += 1
        if state["attempts"] == 1:
            raise RecognizeError("Temporary transition failure")
        state["scene"] = Scene.INDEX

    transition.side_effect = recover
    solver.scene_graph_navigation(Scene.INDEX)

    assert transition.call_count == 2
    solver.device.reconnect.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()


def test_uncertain_navigation_refreshes_scene_without_replaying_old_edge(navigation):
    solver, state, _ = navigation
    state["scene"] = Scene.INDEX
    calls = []

    def index_to_infra(current):
        calls.append("old edge")
        state["scene"] = Scene.NAVIGATION_BAR
        raise TouchFailure(
            Conf().device, "windows", BrokenPipeError("unknown"), delivery_unknown=True
        )

    def nav_index(current):
        calls.append("new edge")
        state["scene"] = Scene.INFRA_MAIN

    graph.DG.add_edge(
        Scene.INDEX, Scene.INFRA_MAIN, transition=index_to_infra, weight=1
    )
    graph.DG.add_edge(
        Scene.NAVIGATION_BAR, Scene.INFRA_MAIN, transition=nav_index, weight=1
    )

    solver.scene_graph_navigation(Scene.INFRA_MAIN)

    assert calls == ["old edge", "new edge"]
    solver.sleep.assert_not_called()
    graph.csleep.assert_called_once_with(30)
    solver.device.reconnect.assert_called_once_with()
    assert solver.recog.update.call_count == 2
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()


def test_uncertain_side_effect_edge_never_enters_navigation_retry(navigation):
    solver, state, _ = navigation
    state["scene"] = Scene.INFRA_ARRANGE_CONFIRM

    def infra_arrange_confirm(current):
        raise TouchFailure(
            Conf().device, "windows", BrokenPipeError("unknown"), delivery_unknown=True
        )

    graph.DG.add_edge(
        Scene.INFRA_ARRANGE_CONFIRM,
        Scene.INFRA_DETAILS,
        transition=infra_arrange_confirm,
        weight=1,
    )
    with pytest.raises(TouchFailure) as caught:
        solver.scene_graph_navigation(Scene.INFRA_DETAILS)

    assert caught.value.reconciliation == "task"
    solver.device.reconnect.assert_not_called()
    solver.device.exit.assert_not_called()


def test_failed_recovery_frame_keeps_original_navigation_stack(navigation):
    solver, state, _ = navigation
    state["scene"] = Scene.INDEX
    calls = []

    def index_to_infra(current):
        calls.append("old edge")
        state["scene"] = Scene.INFRA_MAIN
        raise TouchFailure(
            Conf().device, "windows", BrokenPipeError("unknown"), delivery_unknown=True
        )

    graph.DG.add_edge(
        Scene.INDEX, Scene.INFRA_MAIN, transition=index_to_infra, weight=1
    )
    solver.recog.update.side_effect = [
        ScreenshotFailure(Conf().device, "windows", TimeoutError("fresh frame")),
        None,
    ]

    solver.scene_graph_navigation(Scene.INFRA_MAIN)

    assert calls == ["old edge"]
    assert solver.device.reconnect.call_count == 2
    recovery.csleep.assert_called_once_with(30)
    solver.sleep.assert_not_called()
