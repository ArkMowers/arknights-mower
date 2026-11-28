import logging
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, call

import cv2
import numpy as np
import pytest

from arknights_mower import __main__ as main
from arknights_mower.utils import config, email
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.device import DeviceRecoveryError
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import bytes2img, loadres
from arknights_mower.utils.log import should_archive_record
from arknights_mower.utils.recognize import RecognizeError, Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scene_recovery import (
    SceneRecoveryExhausted,
    SceneRestartBudget,
    scene_restart_scope,
)

FIXTURES = Path(__file__).parent / "fixtures" / "login"


@pytest.fixture
def startup_solver(monkeypatch):
    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(main, "base_scheduler", None)
    solver = object.__new__(SceneGraphSolver)
    solver.device = Mock()
    solver.recog = Mock()
    solver.scene = Mock(return_value=Scene.UNKNOWN)
    solver.sleep = Mock()
    solver.back = Mock()
    solver.restart_game = Mock()
    solver.initialize_operators = Mock(return_value="Verify only startup")
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    return solver


@pytest.mark.parametrize(
    "filename",
    ["startup_logo_fading_20261016.jpg", "startup_logo_bright_20261016.jpg"],
)
def test_startup_logo_is_loading(filename):
    device = Mock()
    device.check_current_focus.return_value = False
    recognizer = Recognizer(device, (FIXTURES / filename).read_bytes())

    assert recognizer.get_scene() == Scene.LOADING
    device.check_current_focus.assert_not_called()
    device.exit.assert_not_called()


@pytest.mark.parametrize("brightness", [0.1, 0.25, 0.5])
def test_startup_logo_remains_loading_during_fade(brightness):
    frame = bytes2img((FIXTURES / "startup_logo_bright_20261016.jpg").read_bytes())
    frame = (frame * brightness).astype(np.uint8)
    device = Mock()
    device.check_current_focus.return_value = False
    device.screencap.return_value = (
        None,
        frame,
        cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
    )
    recognizer = Recognizer(device)

    assert recognizer.get_scene() == Scene.LOADING
    device.check_current_focus.assert_called_once_with()


@pytest.mark.parametrize("variant", ["blank", "misplaced", "mirrored"])
def test_loading_notice_requires_text_at_its_original_position(variant):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    notice = loadres("loading7")
    height, width = notice.shape[:2]
    if variant == "misplaced":
        frame[400 : 400 + height, 106 : 106 + width] = notice
    elif variant == "mirrored":
        frame[635 : 635 + height, 106 : 106 + width] = notice[:, ::-1]
    device = Mock()
    device.screencap.return_value = (
        None,
        frame,
        cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
    )

    assert Recognizer(device).find("loading7") is None


def test_navigation_waits_for_startup_without_back_or_restart():
    frame = bytes2img((FIXTURES / "startup_logo_fading_20261016.jpg").read_bytes())
    login_start = np.zeros_like(frame)
    age_rating = loadres("12cadpa")
    height, width = age_rating.shape[:2]
    login_start[21 : 21 + height, 1810 : 1810 + width] = age_rating
    frames = iter([frame] * 4 + [login_start])

    def capture():
        current = next(frames, login_start)
        return None, current, cv2.cvtColor(current, cv2.COLOR_RGB2GRAY)

    solver = object.__new__(SceneGraphSolver)
    solver.device = Mock()
    solver.device.screencap.side_effect = capture
    solver.device.check_current_focus.return_value = False
    solver.recog = Recognizer(solver.device)
    solver.sleep = Mock(side_effect=lambda *_: solver.recog.update())

    solver.scene_graph_navigation(Scene.LOGIN_START)

    assert solver.scene() == Scene.LOGIN_START
    assert solver.device.screencap.call_count == 5
    solver.device.send_keyevent.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.launch.assert_not_called()


@pytest.mark.parametrize(
    ("initial", "after_back", "after_restart", "returns", "restarts", "continues"),
    [
        (Scene.INDEX, Scene.INDEX, Scene.INDEX, 0, 0, True),
        (Scene.INFRA_MAIN, Scene.INFRA_MAIN, Scene.INDEX, 0, 0, True),
        (Scene.CONNECTING, Scene.CONNECTING, Scene.INDEX, 0, 0, True),
        (Scene.UNKNOWN, Scene.INDEX, Scene.INDEX, 1, 0, True),
        (Scene.UNKNOWN, Scene.UNKNOWN, Scene.INDEX, 3, 1, True),
        (Scene.UNKNOWN, Scene.UNKNOWN, Scene.UNKNOWN, 6, 1, False),
        (Scene.UNKNOWN, Scene.UNKNOWN, Scene.CONNECTING, 3, 1, False),
        (Scene.UNKNOWN, Scene.SSS_DEPLOY, Scene.INDEX, 3, 0, False),
    ],
)
def test_startup_recovers_unknown_scene_at_most_once(
    startup_solver,
    initial,
    after_back,
    after_restart,
    returns,
    restarts,
    continues,
    caplog,
    monkeypatch,
):
    solver = startup_solver
    solver.scene.return_value = initial
    solver.back.side_effect = lambda: setattr(solver.scene, "return_value", after_back)
    solver.restart_game.side_effect = lambda: setattr(
        solver.scene, "return_value", after_restart
    )
    pending = object()
    saved = {"tasks": [pending]}
    config.conf.mail_enable = 1
    config.conf.notification_level = "ERROR"
    mail = Mock()
    make_email = Mock(return_value=mail)
    monkeypatch.setattr(email, "Email", make_email)
    monkeypatch.setattr(
        email,
        "Thread",
        lambda *, target, args: SimpleNamespace(start=lambda: target(*args)),
    )

    main.simulate(saved)

    assert solver.back.call_count == returns
    assert solver.restart_game.call_count == restarts
    assert solver.initialize_operators.call_count == continues
    solver.device.exit.assert_not_called()
    assert saved == {"tasks": [pending]}
    failed_start = [
        record for record in caplog.records if "未能确认游戏首页" in record.getMessage()
    ]
    if continues:
        assert not failed_start
        make_email.assert_not_called()
        mail.send.assert_not_called()
    else:
        assert len(failed_start) == 1
        assert failed_start[0].levelno == logging.ERROR
        assert "本次自动化未启动" in failed_start[0].getMessage()
        assert should_archive_record(failed_start[0])
        make_email.assert_called_once()
        assert make_email.call_args.args[1].endswith("Mower 启动失败")
        mail.send.assert_called_once_with()
    if initial == Scene.UNKNOWN:
        assert solver.sleep.call_args_list[:3] == [call()] * 3


def test_startup_mail_preparation_failure_does_not_restart_again(
    startup_solver, monkeypatch
):
    config.conf.mail_enable = 1
    make_email = Mock(side_effect=ValueError("invalid mail configuration"))
    monkeypatch.setattr(email, "Email", make_email)
    resume = Mock()
    monkeypatch.setattr(main, "_resume_device_dispatch", resume)

    main.simulate(None)

    make_email.assert_called_once()
    startup_solver.restart_game.assert_called_once_with()
    startup_solver.initialize_operators.assert_not_called()
    resume.assert_not_called()


@pytest.mark.parametrize("reconnected_scene", [Scene.UNKNOWN, Scene.CONNECTING])
def test_startup_device_recovery_retains_spent_game_restart_budget(
    startup_solver, monkeypatch, caplog, reconnected_scene
):
    failure = DeviceRecoveryError("lost device while relaunching the game")
    startup_solver.restart_game.side_effect = failure
    resume = Mock(
        side_effect=lambda **_: setattr(
            startup_solver.scene, "return_value", reconnected_scene
        )
    )
    monkeypatch.setattr(main, "_resume_device_dispatch", resume)

    main.simulate(None)

    resume.assert_called_once_with(failure=failure)
    startup_solver.restart_game.assert_called_once_with()
    startup_solver.initialize_operators.assert_not_called()
    assert "未能确认游戏首页" in caplog.text


@pytest.mark.parametrize("finds_home", [False, True])
def test_startup_device_recovery_still_requires_home_confirmation(
    startup_solver, monkeypatch, caplog, finds_home
):
    solver = startup_solver
    failure = DeviceRecoveryError("lost device while leaving the base")

    def back():
        if solver.back.call_count == 1:
            solver.scene.return_value = Scene.INFRA_MAIN
        elif solver.back.call_count == 2:
            raise failure
        else:
            solver.scene.return_value = Scene.INDEX if finds_home else Scene.SSS_DEPLOY

    solver.back.side_effect = back
    resume = Mock()
    monkeypatch.setattr(main, "_resume_device_dispatch", resume)
    pending = object()
    saved = {"tasks": [pending]}

    main.simulate(saved)

    resume.assert_called_once_with(failure=failure)
    assert solver.back.call_count >= 3
    solver.restart_game.assert_not_called()
    assert saved == {"tasks": [pending]}
    assert solver.initialize_operators.call_count == finds_home
    assert ("未能确认游戏首页" in caplog.text) is not finds_home


@pytest.mark.parametrize("retry_button_visible", [False, True])
def test_startup_login_cancellation_failure_issues_notification(
    startup_solver, monkeypatch, retry_button_visible
):
    solver = startup_solver
    solver.back.side_effect = lambda: setattr(
        solver.scene, "return_value", Scene.LOGIN_CANCELLED
    )
    solver.find = Mock(return_value=(0, 0) if retry_button_visible else None)
    solver.tap = Mock()
    notify = Mock(wraps=email.send_message)
    monkeypatch.setattr(email, "send_message", notify)
    pending = object()
    saved = {"tasks": [pending]}

    main.simulate(saved)

    assert solver.tap.call_count == (
        config.MAX_RETRYTIME if retry_button_visible else 0
    )
    notify.assert_called_once()
    assert notify.call_args.kwargs["subject"] == "Mower 启动失败"
    assert notify.call_args.kwargs["level"] == "ERROR"
    assert notify.call_args.kwargs["archive_screenshots"] is True
    solver.restart_game.assert_not_called()
    solver.initialize_operators.assert_not_called()
    assert saved == {"tasks": [pending]}


def test_transition_reconnect_failure_does_not_spend_startup_game_restart(
    startup_solver, monkeypatch
):
    solver = startup_solver
    failure = DeviceRecoveryError("lost device before relaunching the game")

    def back():
        if solver.back.call_count == 1:
            solver.scene.return_value = Scene.INFRA_MAIN
        else:
            raise RecognizeError("could not leave the base")

    solver.back.side_effect = back
    solver.device.reconnect.side_effect = [failure, None]
    solver.restart_game.side_effect = lambda: setattr(
        solver.scene, "return_value", Scene.INDEX
    )
    resume = Mock()
    monkeypatch.setattr(main, "_resume_device_dispatch", resume)

    main.simulate(None)

    resume.assert_called_once_with(failure=failure)
    assert solver.device.reconnect.call_count == 2
    assert solver.back.call_count == 15
    solver.restart_game.assert_called_once_with()
    solver.initialize_operators.assert_called_once_with()


def test_normal_scene_navigation_keeps_original_unknown_retry_limit(startup_solver):
    startup_solver.scene_graph_navigation(Scene.INDEX)

    assert startup_solver.back.call_count == 3
    assert startup_solver.sleep.call_args_list == [call()] * 3 + [call(0.5)] * 3
    startup_solver.restart_game.assert_not_called()


def test_startup_cancellation_before_relaunch_does_not_exit_game(startup_solver):
    startup_solver.back.side_effect = [None, None, None]

    def cancel_after_last_back(seconds=1):
        if startup_solver.back.call_count == 3:
            config.stop_mower.set()

    startup_solver.sleep.side_effect = cancel_after_last_back

    main.simulate(None)

    assert startup_solver.back.call_count == 3
    startup_solver.restart_game.assert_not_called()
    startup_solver.initialize_operators.assert_not_called()


def test_same_scene_watchdog_respects_existing_limit_and_restart_budget(startup_solver):
    recognizer = object.__new__(Recognizer)
    recognizer.device = startup_solver.device
    recognizer.scene = recognizer.last_scene = Scene.UNKNOWN
    recognizer.last_scene_time = datetime(2026, 1, 1)
    recognizer.clear = Mock()
    at_limit = recognizer.last_scene_time + timedelta(
        seconds=config.conf.run_order_delay * 90
    )

    with scene_restart_scope(SceneRestartBudget(used=True)):
        recognizer.check_freeze(at_limit)
        with pytest.raises(SceneRecoveryExhausted):
            recognizer.check_freeze(at_limit + timedelta(seconds=1))

    recognizer.device.exit.assert_not_called()


@pytest.mark.parametrize(
    ("recognized", "used", "returns", "restarts"),
    [(True, False, 3, 0), (False, False, 5, 1), (False, True, 5, 0)],
)
def test_base_correction_keeps_five_returns_and_shares_restart_budget(
    startup_solver, recognized, used, returns, restarts
):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    solver = startup_solver
    solver.error = False
    solver.find_next_task = Mock(return_value=object())
    solver.check_current_focus = Mock()
    if recognized:
        solver.scene.side_effect = [Scene.UNKNOWN] * 3 + [Scene.INFRA_MAIN]

    with scene_restart_scope(SceneRestartBudget(used=used)):
        assert BaseSchedulerSolver.handle_error(solver)

    assert solver.back.call_count == returns
    assert solver.device.exit.call_count == restarts
    assert solver.check_current_focus.call_count == restarts
