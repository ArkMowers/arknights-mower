"""确认按钮不应因半透明栏后面的游戏背景不同而失去识别。"""

from datetime import datetime
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.image import cmatch, loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene


def recognizer(image):
    result = object.__new__(Recognizer)
    result._img = image
    result._gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    result.scene = Scene.UNDEFINED
    result.last_scene = None
    result.last_scene_time = datetime.now()
    return result


def sample(background=(120, 75, 30)):
    image = np.empty((1080, 1920, 3), dtype=np.uint8)
    image[:] = background
    reference = loadres("confirm")
    image[708:772, 928:992] = reference[25:89, 928:992]
    return image


def test_changed_backdrop_preserves_confirm_recognition():
    image = sample()
    assert not cmatch(image[683:797], loadres("confirm"))
    result = recognizer(image)
    assert result.find("confirm") == ((928, 708), (992, 772))
    actual_find = result.find
    result.find = lambda name, **kwargs: (
        actual_find(name, **kwargs) if name == "confirm" else None
    )
    assert result.get_scene() == Scene.CONFIRM


def test_existing_full_bar_keeps_original_scope():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[683:797] = loadres("confirm")
    assert recognizer(image).find("confirm") == ((0, 683), (1920, 797))


@pytest.mark.parametrize("kind", ["empty", "white", "circle", "shifted", "inverted"])
def test_no_click_for_missing_or_different_icon(kind):
    image = sample()
    if kind == "shifted":
        image[708:772, 1040:1104] = image[708:772, 928:992]
    if kind == "inverted":
        image[708:772, 928:992] = 255 - image[708:772, 928:992]
    else:
        image[708:772, 928:992] = 255 if kind == "white" else 0
        if kind == "circle":
            cv2.circle(image, (960, 738), 29, (255, 255, 255), -1)
    assert recognizer(image).find("confirm") is None


def test_confirmation_uses_existing_navigation_without_game_exit():
    from arknights_mower.utils.graph import confirm

    solver = Mock()
    confirm(solver)
    solver.tap_element.assert_called_once_with("confirm")
    solver.device.exit.assert_not_called()


def test_small_frame_does_not_raise():
    assert (
        recognizer(np.zeros((100, 100, 3), dtype=np.uint8)).find_confirm_button()
        is None
    )
