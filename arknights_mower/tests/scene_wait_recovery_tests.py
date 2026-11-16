import threading
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.utils import config
from arknights_mower.utils import recognize as recognize_module
from arknights_mower.utils import solver as solver_module
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.recognize import Recognizer, Scene


@pytest.fixture
def subject(monkeypatch):
    monkeypatch.setattr(config, "conf", Conf(run_order_delay=1))
    monkeypatch.setattr(config, "stop_mower", threading.Event())
    monkeypatch.setattr(recognize_module, "logger", Mock())
    monkeypatch.setattr(solver_module, "logger", Mock())
    monkeypatch.setattr(solver_module, "csleep", Mock())
    device = Mock()
    result = solver_module.BaseSolver(device, Recognizer(device))
    result.sleep = Mock()
    result.check_current_focus = Mock()
    return result


def test_freeze_during_wait_entry_releases_dispatch_with_invalidated_frame(subject):
    subject.recog.scene = Scene.LOADING
    subject.recog.last_scene = Scene.LOADING
    subject.recog.last_scene_time = datetime.now() - timedelta(minutes=10)
    subject.recog._screencap = b"old frame"

    assert subject.waiting_solver() is True

    assert subject.recog.scene == Scene.UNDEFINED
    assert subject.recog._screencap is None
    subject.device.exit.assert_called_once()
    subject.sleep.assert_not_called()
    subject.check_current_focus.assert_not_called()


@pytest.mark.parametrize("scene", [Scene.INDEX, Scene.FACTORY_ROOM])
def test_already_changed_scene_returns_without_waiting_or_restarting(subject, scene):
    subject.recog.scene = scene

    assert subject.waiting_solver() is True

    subject.sleep.assert_not_called()
    subject.device.exit.assert_not_called()


def test_wait_continues_until_scene_changes(subject):
    subject.recog.scene = Scene.UNKNOWN
    subject.sleep.side_effect = lambda _: setattr(subject.recog, "scene", Scene.INDEX)

    assert subject.waiting_solver() is True

    subject.sleep.assert_called_once_with(1)
    subject.device.exit.assert_not_called()


def test_unchanged_wait_keeps_existing_timeout_and_restart(subject):
    subject.recog.scene = Scene.UNKNOWN

    assert subject.waiting_solver() is False

    assert subject.sleep.call_count == 10
    subject.device.exit.assert_called_once()
    subject.check_current_focus.assert_called_once()
