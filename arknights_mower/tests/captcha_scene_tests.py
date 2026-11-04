"""验证码场景须有可用面板，启动背景的零散白点不能用于匹配。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pytest

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.recognize import Recognizer, captcha_panel_scope
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver

FIXTURE = Path(__file__).parent / "fixtures/login/startup_background_20261103.jpg"


def captcha_solver(frame):
    solver = object.__new__(BaseSolver)
    solver.recog = SimpleNamespace(
        img=frame, gray=cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    )
    solver.device = Mock()
    solver.tap = Mock()
    return solver


def panel_frame():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[220:860, 640:1280] = 255
    return frame


@pytest.mark.parametrize("false_feature_match", [False, True])
def test_archived_startup_background_is_not_captcha(false_feature_match):
    device = Mock()
    device.check_current_focus.return_value = False
    recognizer = Recognizer(device, FIXTURE.read_bytes())
    if false_feature_match:
        recognizer.find = Mock(side_effect=lambda name, **_: name == "login_captcha")
        recognizer.detect_index_scene = Mock(return_value=False)
        recognizer.check_announcement = Mock(return_value=False)

    assert recognizer.get_scene() != Scene.LOGIN_CAPTCHA
    device.send_keyevent.assert_not_called()
    device.exit.assert_not_called()


@pytest.mark.parametrize("refresh", [False, True])
def test_archived_background_does_not_match_or_send_captcha_input(refresh):
    frame = cv2.cvtColor(cv2.imread(str(FIXTURE)), cv2.COLOR_BGR2RGB)
    solver = captcha_solver(frame)
    with patch(
        "arknights_mower.utils.solver.cv2.matchTemplate", wraps=cv2.matchTemplate
    ) as match:
        assert solver.solve_captcha(refresh=refresh) is None
    match.assert_not_called()
    solver.tap.assert_not_called()
    solver.device.swipe_ext.assert_not_called()


@pytest.mark.parametrize("variant", ["sparse", "narrow", "tiny"])
def test_invalid_panel_geometry_never_reaches_template_matching(variant):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    if variant == "sparse":
        frame[220, 640] = frame[859, 1279] = 255
    elif variant == "narrow":
        frame[220:860, 640:660] = 255
    else:
        frame[220:240, 640:660] = 255
    solver = captcha_solver(frame)
    with patch(
        "arknights_mower.utils.solver.cv2.matchTemplate", wraps=cv2.matchTemplate
    ) as match:
        assert solver.solve_captcha() is None
    match.assert_not_called()
    solver.device.swipe_ext.assert_not_called()


def test_supported_constructed_panel_retains_existing_matching_path():
    solver = captcha_solver(panel_frame())
    with patch(
        "arknights_mower.utils.solver.cv2.matchTemplate", wraps=cv2.matchTemplate
    ) as match:
        solver.solve_captcha()

    assert match.call_count == 2
    solver.device.swipe_ext.assert_called_once()
    solver.tap.assert_not_called()


def test_supported_constructed_panel_retains_captcha_scene():
    recognizer = object.__new__(Recognizer)
    recognizer.scene = Scene.UNDEFINED
    recognizer._gray = cv2.cvtColor(panel_frame(), cv2.COLOR_RGB2GRAY)
    recognizer.find = Mock(side_effect=lambda name, **_: name == "login_captcha")
    recognizer.detect_index_scene = Mock(return_value=False)
    recognizer.check_announcement = Mock(return_value=False)
    recognizer.check_freeze = Mock()

    assert recognizer.get_scene() == Scene.LOGIN_CAPTCHA


def test_captcha_refresh_rechecks_panel_before_matching():
    solver = captcha_solver(panel_frame())
    solver.tap.side_effect = lambda *_, **__: setattr(
        solver, "recog", captcha_solver(np.zeros((1080, 1920, 3), dtype=np.uint8)).recog
    )
    with patch(
        "arknights_mower.utils.solver.cv2.matchTemplate", wraps=cv2.matchTemplate
    ) as match:
        assert solver.solve_captcha(refresh=True) is None

    solver.tap.assert_called_once()
    match.assert_not_called()
    solver.device.swipe_ext.assert_not_called()


@pytest.mark.parametrize("error", [MowerExit(), DeviceRecoveryError("touch failed")])
def test_supported_captcha_input_failure_propagates(error):
    solver = captcha_solver(panel_frame())
    solver.device.swipe_ext.side_effect = error

    with pytest.raises(type(error)) as caught:
        solver.solve_captcha()

    assert caught.value is error
    solver.device.swipe_ext.assert_called_once()


@pytest.mark.parametrize("error", [MowerExit(), DeviceRecoveryError("capture failed")])
def test_captcha_observation_failure_propagates(error):
    class FailedFrame:
        @property
        def gray(self):
            raise error

    solver = object.__new__(BaseSolver)
    solver.recog = FailedFrame()
    solver.device = Mock()
    with pytest.raises(type(error)) as caught:
        solver.solve_captcha()
    assert caught.value is error
    solver.device.swipe_ext.assert_not_called()


def captcha_login_solver():
    solver = captcha_solver(panel_frame())
    solver.is_login = Mock(side_effect=[False, True, True])
    solver.scene = Mock(
        side_effect=lambda: (
            Scene.LOGIN_CAPTCHA
            if captcha_panel_scope(solver.recog.gray) is not None
            else Scene.INDEX
        )
    )
    solver.find = Mock(side_effect=lambda name, **_: name == "login_captcha")
    solver.sleep = Mock()
    return solver


@pytest.mark.parametrize("disappears_after", ["swipe", "refresh"])
def test_login_returns_to_other_scenes_after_captcha_panel_disappears(
    disappears_after,
):
    solver = captcha_login_solver()
    background = captcha_solver(
        cv2.cvtColor(cv2.imread(str(FIXTURE)), cv2.COLOR_BGR2RGB)
    ).recog
    if disappears_after == "swipe":
        solver.sleep.side_effect = lambda *_: setattr(solver, "recog", background)
    else:
        solver.tap.side_effect = lambda *_, **__: setattr(solver, "recog", background)

    with (
        patch("arknights_mower.solvers.captcha_solver.CaptchaClickSolver"),
        patch("arknights_mower.utils.solver.send_message") as notify,
        patch(
            "arknights_mower.utils.solver.sys.exit",
            side_effect=AssertionError("验证码消失后不能退出实例"),
        ) as exit_process,
    ):
        solver.login()

    solver.device.swipe_ext.assert_called_once()
    assert solver.tap.call_count == (disappears_after == "refresh")
    solver.device.exit.assert_not_called()
    exit_process.assert_not_called()
    notify.assert_not_called()


def test_login_retains_failure_limit_for_a_present_captcha_panel():
    solver = captcha_login_solver()
    with (
        patch("arknights_mower.solvers.captcha_solver.CaptchaClickSolver"),
        patch("arknights_mower.utils.solver.send_message") as notify,
        patch("arknights_mower.utils.solver.sys.exit", side_effect=SystemExit),
        pytest.raises(SystemExit),
    ):
        solver.login()

    assert solver.device.swipe_ext.call_count == 3
    assert solver.tap.call_count == 2
    solver.device.exit.assert_called_once()
    notify.assert_called_once()


@pytest.mark.parametrize("error", [MowerExit(), DeviceRecoveryError("captcha failed")])
@pytest.mark.parametrize("failure_at", ["input", "scene"])
def test_login_captcha_failures_propagate_without_exiting(error, failure_at):
    solver = captcha_login_solver()
    if failure_at == "input":
        solver.device.swipe_ext.side_effect = error
    else:
        solver.scene.side_effect = [Scene.LOGIN_CAPTCHA, Scene.LOGIN_CAPTCHA, error]

    with (
        patch("arknights_mower.solvers.captcha_solver.CaptchaClickSolver"),
        patch("arknights_mower.utils.solver.send_message") as notify,
        pytest.raises(type(error)) as caught,
    ):
        solver.login()

    assert caught.value is error
    solver.device.exit.assert_not_called()
    notify.assert_not_called()
