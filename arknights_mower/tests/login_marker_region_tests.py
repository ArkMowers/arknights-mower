"""登录页厂商标识允许微小位置差异，仍须与中央 Logo 同时确认。"""

from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene

# 取自 2026-11-06 17:26:14 的标准画面帧，仅保留无账号信息的左下角。
FOOTER = Path(__file__).parent / "fixtures/login/footer_android_20261106.png"


def paste(frame, resource, x, y):
    image = loadres(resource)
    height, width = image.shape[:2]
    frame[y : y + height, x : x + width] = image


def login_frame():
    frame = np.full((1080, 1920, 3), 180, dtype=np.uint8)
    paste(frame, "login_logo", 601, 332)
    paste(frame, "login_awake", 888, 743)
    return frame


def captured_footer_frame():
    frame = login_frame()
    footer = cv2.cvtColor(cv2.imread(str(FOOTER)), cv2.COLOR_BGR2RGB)
    frame[959:1080, :418] = footer
    return frame


def recognizer(frame):
    device = Mock()
    device.check_current_focus.return_value = False
    device.screencap.return_value = (
        None,
        frame,
        cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
    )
    return Recognizer(device)


def test_captured_footer_recognizes_quick_login():
    recog = recognizer(captured_footer_frame())

    assert recog.find("hypergryph") == ((0, 962), (416, 1080))
    assert recog.get_scene() == Scene.LOGIN_QUICKLY
    recog.device.send_keyevent.assert_not_called()
    recog.device.exit.assert_not_called()


@pytest.mark.parametrize("offset", [(0, 0), (0, 1), (2, -2), (2, 1)])
def test_original_and_nearby_marker_positions_remain_supported(offset):
    frame = login_frame()
    x, y = offset[0], 961 + offset[1]
    paste(frame, "hypergryph", x, y)
    recog = recognizer(frame)

    scope = recog.find("hypergryph")
    assert scope is not None
    (left, top), (right, bottom) = scope
    assert 0 <= left <= 2
    assert 959 <= top <= 962
    assert (right - left, bottom - top) == (416, 118)
    if offset == (0, 0):
        assert scope == ((0, 961), (416, 1079))
    assert recog.get_scene() == Scene.LOGIN_QUICKLY


@pytest.mark.parametrize("position", [(6, 961), (0, 955), (20, 961)])
def test_distant_marker_does_not_confirm_login(position):
    frame = login_frame()
    paste(frame, "hypergryph", *position)
    recog = recognizer(frame)

    assert recog.find("hypergryph") is None
    assert recog.get_scene() != Scene.LOGIN_QUICKLY


@pytest.mark.parametrize("missing", ["logo", "marker"])
def test_login_still_requires_both_markers(missing):
    frame = captured_footer_frame()
    if missing == "logo":
        frame[332:652, 601:1301] = 180
    else:
        frame[959:1080, :418] = 180

    assert recognizer(frame).get_scene() != Scene.LOGIN_QUICKLY


@pytest.mark.parametrize("variant", ["mirrored", "different_color"])
def test_nearby_search_preserves_shape_and_color_checks(variant):
    frame = login_frame()
    marker = loadres("hypergryph").copy()
    if variant == "mirrored":
        marker = marker[:, ::-1]
    else:
        marker = np.clip(marker.astype(int) + 30, 0, 255).astype(np.uint8)
    frame[962:1080, :416] = marker

    assert recognizer(frame).find("hypergryph") is None


def test_shifted_footer_navigation_taps_awake_without_back_or_restart():
    solver = object.__new__(SceneGraphSolver)
    solver.recog = recognizer(captured_footer_frame())
    solver.device = solver.recog.device
    solver.tap = Mock(
        side_effect=lambda *_, **__: setattr(solver.recog, "scene", Scene.INDEX)
    )
    solver.recog.update = Mock()
    solver.sleep = Mock(side_effect=AssertionError("登录页不应等待或返回纠正"))

    solver.scene_graph_navigation(Scene.INDEX)

    solver.tap.assert_called_once()
    (left, top), (right, bottom) = solver.tap.call_args.args[0]
    assert 800 <= left < right <= 1115
    assert 719 <= top < bottom <= 822
    solver.device.send_keyevent.assert_not_called()
    solver.device.exit.assert_not_called()


@pytest.mark.parametrize(
    "filename",
    [
        "startup_background_20261103.jpg",
        "startup_logo_bright_20261016.jpg",
        "login_cancelled_20261021.jpg",
    ],
)
def test_other_login_screens_do_not_become_quick_login(filename):
    device = Mock()
    device.check_current_focus.return_value = False
    frame = FOOTER.with_name(filename).read_bytes()

    assert Recognizer(device, frame).get_scene() != Scene.LOGIN_QUICKLY
