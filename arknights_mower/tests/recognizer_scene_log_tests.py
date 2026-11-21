"""同一场景在静默期内重复识别只记 DEBUG，场景变化或超过静默期才记 INFO。"""

import logging
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import recognize
from arknights_mower.utils.recognize import SCENE_LOG_QUIET_PERIOD, Recognizer
from arknights_mower.utils.scene import Scene, SceneComment


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(recognize.time, "monotonic", lambda: now[0])
    return now


def recognizer(visible):
    result = Recognizer.__new__(Recognizer)
    result.scene = Scene.UNDEFINED
    result.find = MagicMock(side_effect=lambda name, **_: name in visible)
    result.detect_index_scene = MagicMock(return_value=False)
    result.detect_ra_adventure = MagicMock(return_value=False)
    result.find_ra_battle_exit = MagicMock(return_value=False)
    result.check_current_focus = MagicMock()
    result.check_freeze = MagicMock()
    result.check_loading_time = MagicMock()
    return result


def observer(clock, method, visible):
    recog = recognizer(visible)

    def observe(elapsed, *names):
        clock[0] += elapsed
        visible.clear()
        visible.update(names)
        recog.scene = Scene.UNDEFINED
        return getattr(recog, method)()

    return observe


def scene_records(caplog):
    return [
        (record.levelno, record.getMessage(), record.funcName)
        for record in caplog.records
        if record.getMessage().startswith("Scene")
    ]


def test_get_scene_reports_repeats_at_debug_until_quiet_period_ends(caplog, clock):
    caplog.set_level(logging.DEBUG)
    observe = observer(clock, "get_scene", set())

    observe(0, "connecting")
    observe(1, "connecting")
    observe(SCENE_LOG_QUIET_PERIOD - 2, "connecting")
    observe(1, "connecting")
    observe(1, "nav_bar")
    observe(1, "connecting")

    connecting = f"Scene {Scene.CONNECTING}: {SceneComment[Scene.CONNECTING]}"
    nav_bar = f"Scene {Scene.NAVIGATION_BAR}: {SceneComment[Scene.NAVIGATION_BAR]}"
    assert scene_records(caplog) == [
        (logging.INFO, connecting, "get_scene"),
        (logging.DEBUG, connecting, "get_scene"),
        (logging.DEBUG, connecting, "get_scene"),
        (logging.INFO, connecting, "get_scene"),
        (logging.INFO, nav_bar, "get_scene"),
        (logging.INFO, connecting, "get_scene"),
    ]


@pytest.mark.parametrize("method", ["get_ra_scene", "get_sf_scene"])
def test_unknown_frames_do_not_count_as_scene_change(caplog, clock, method):
    caplog.set_level(logging.DEBUG)
    observe = observer(clock, method, set())

    observe(0, "connecting")
    observe(1)
    observe(1, "connecting")
    observe(SCENE_LOG_QUIET_PERIOD, "connecting")

    connecting = f"Scene: {Scene.CONNECTING}: {SceneComment[Scene.CONNECTING]}"
    unknown = f"Scene: {Scene.UNKNOWN}: {SceneComment[Scene.UNKNOWN]}"
    assert scene_records(caplog) == [
        (logging.INFO, connecting, method),
        (logging.DEBUG, unknown, method),
        (logging.DEBUG, connecting, method),
        (logging.INFO, connecting, method),
    ]


@pytest.mark.parametrize(
    "method", ["get_sss_scene", "get_train_scene", "get_factory_scene"]
)
def test_specialized_getters_report_every_recognition_at_info(caplog, method):
    caplog.set_level(logging.DEBUG)
    recog = recognizer({"connecting"})
    for _ in range(2):
        recog.scene = Scene.UNDEFINED
        getattr(recog, method)()

    message = f"Scene: {Scene.CONNECTING}: {SceneComment[Scene.CONNECTING]}"
    assert scene_records(caplog) == [(logging.INFO, message, method)] * 2
