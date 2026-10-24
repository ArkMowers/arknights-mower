"""Offline recognition and bounded retries for the captured login cancellation."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import bytes2img, loadres
from arknights_mower.utils.recognize import RecognizeError, Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import StrategyError

# The captured dialog is preserved; the surrounding account UI is masked.
FIXTURE = Path(__file__).parent / "fixtures/login/login_cancelled_20261021.jpg"
LOGIN_CANCELLED = 117


def recognizer(frame=None):
    device = Mock()
    device.check_current_focus.return_value = False
    if frame is None:
        return Recognizer(device, FIXTURE.read_bytes())
    ok, encoded = cv2.imencode(".png", frame)
    assert ok
    return Recognizer(device, encoded.tobytes())


def test_captured_dialog_is_recognized_as_not_logged_in():
    recog = recognizer()
    assert recog.get_scene() == LOGIN_CANCELLED
    solver = object.__new__(SceneGraphSolver)
    solver.recog = recog
    assert solver.is_login() is False


@pytest.mark.parametrize("missing", ["main", "message", "retry_button"])
def test_cancelled_login_requires_dialog_message_and_retry_button(missing):
    frame = cv2.imdecode(np.fromfile(FIXTURE, dtype=np.uint8), cv2.IMREAD_COLOR)
    region = {
        "main": (835, 683, 1082, 800),
        "message": (780, 460, 1140, 510),
        "retry_button": (1164, 712, 1374, 772),
    }[missing]
    left, top, right, bottom = region
    frame[top:bottom, left:right] = 0
    assert recognizer(frame).get_scene() != LOGIN_CANCELLED


@pytest.mark.parametrize(
    ("resource", "position", "expected"),
    [
        ("exit", (940, 464), Scene.EXIT_GAME),
        ("recruit", (981, 464), Scene.REFRESH_TAGS),
        ("network", (708, 435), Scene.NETWORK_CHECK),
    ],
)
def test_other_double_confirm_messages_keep_their_own_scene(
    resource, position, expected
):
    frame = bytes2img(FIXTURE.read_bytes())
    frame[420:650] = 240
    template = loadres(f"double_confirm/{resource}")
    x, y = position
    height, width = template.shape[:2]
    frame[y : y + height, x : x + width] = template
    device = Mock()
    device.check_current_focus.return_value = False
    device.screencap.return_value = (
        None,
        frame,
        cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
    )
    assert Recognizer(device).get_scene() == expected
    device.tap.assert_not_called()


def navigation(scenes):
    state = SimpleNamespace(index=0)
    solver = object.__new__(SceneGraphSolver)
    solver.device = Mock()
    solver.recog = SimpleNamespace(update=Mock())
    solver.find = recognizer().find
    solver.scene = Mock(side_effect=lambda: scenes[min(state.index, len(scenes) - 1)])

    def advance(*_):
        state.index += 1

    solver.sleep = Mock(side_effect=advance)
    solver.waiting_solver = Mock(side_effect=advance)
    return solver


def run_navigation(solver, caller):
    if caller == "login":
        solver.login()
    else:
        solver.scene_graph_navigation(Scene.INDEX)


@pytest.mark.parametrize("caller", ["login", "graph"])
def test_login_retry_clicks_right_button_and_observes_progress(caller):
    solver = navigation([LOGIN_CANCELLED, Scene.LOGIN_LOADING, Scene.INDEX])
    run_navigation(solver, caller)
    assert solver.is_login() is True
    solver.device.tap.assert_called_once()
    x, y = solver.device.tap.call_args.args[0]
    assert 1164 <= x < 1374 and 712 <= y < 772
    solver.waiting_solver.assert_called_once_with()
    solver.device.send_keyevent.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()
    solver.device.reconnect.assert_not_called()


@pytest.mark.parametrize("caller", ["login", "graph"])
@pytest.mark.parametrize("intermediate_loading", [False, True])
def test_repeated_cancellation_exhausts_one_attempt_count(caller, intermediate_loading):
    cycle = (
        [LOGIN_CANCELLED, Scene.LOGIN_LOADING]
        if intermediate_loading
        else [LOGIN_CANCELLED]
    )
    solver = navigation(cycle * (config.MAX_RETRYTIME + 1))
    with pytest.raises(StrategyError, match="登录被取消"):
        run_navigation(solver, caller)
    assert solver.device.tap.call_count == config.MAX_RETRYTIME
    assert solver.is_login() is False
    solver.device.send_keyevent.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()
    solver.device.reconnect.assert_not_called()


@pytest.mark.parametrize("caller", ["login", "graph"])
@pytest.mark.parametrize("failure", [MowerExit(), DeviceRecoveryError("input failed")])
def test_cancelled_login_preserves_cancellation_and_device_failure(caller, failure):
    solver = navigation([LOGIN_CANCELLED])
    solver.device.tap.side_effect = failure
    with pytest.raises(type(failure)) as raised:
        run_navigation(solver, caller)
    assert raised.value is failure
    solver.device.tap.assert_called_once()
    solver.device.send_keyevent.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.reconnect.assert_not_called()


@pytest.mark.parametrize("caller", ["login", "graph"])
def test_changed_retry_button_is_not_clicked_from_a_cached_scene(caller):
    solver = navigation([LOGIN_CANCELLED])
    frame = cv2.imdecode(np.fromfile(FIXTURE, dtype=np.uint8), cv2.IMREAD_COLOR)
    frame[712:772, 1164:1374] = 0
    solver.find = recognizer(frame).find
    with pytest.raises((RecognizeError, StrategyError)):
        run_navigation(solver, caller)
    solver.device.tap.assert_not_called()
    solver.device.send_keyevent.assert_not_called()
    solver.device.reconnect.assert_not_called()
