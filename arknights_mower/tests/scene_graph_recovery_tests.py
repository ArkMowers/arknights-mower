"""Scene transition failures recover the game without repeating device failures."""

from types import SimpleNamespace
from unittest.mock import Mock

import networkx as nx
import pytest

from arknights_mower.utils import graph
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
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
