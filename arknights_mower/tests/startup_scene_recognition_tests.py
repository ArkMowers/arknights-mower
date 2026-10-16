from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import bytes2img, loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene

FIXTURES = Path(__file__).parent / "fixtures" / "login"


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
    device.check_current_focus.assert_not_called()


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
