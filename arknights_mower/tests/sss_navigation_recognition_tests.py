"""现场行动前调整截图可以交给 MAA 接管，旧版按钮仍然有效。"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


def test_current_preparation_frame_reaches_sss_handoff_without_input():
    path = Path(__file__).parent / "fixtures/sss/action_preparation_20261028.jpg"
    device = MagicMock()
    recog = Recognizer(device, path.read_bytes())
    assert recog.find("sss/deploy_button") is None
    assert recog.get_sss_scene() == Scene.SSS_DEPLOY
    solver = object.__new__(BaseSolver)
    solver.device, solver.recog = device, recog
    assert solver.to_sss(1, 1) is None
    device.tap.assert_not_called()


def test_old_deploy_button_still_recognized():
    recog = Recognizer(MagicMock())
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    button = loadres("sss/deploy_button")
    h, w = button.shape[:2]
    img[620 : 620 + h, 1500 : 1500 + w] = button
    import cv2

    recog._img, recog._gray = img, cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    recog.check_loading_time = MagicMock()
    assert recog.get_sss_scene() == Scene.SSS_DEPLOY


def test_unrelated_frame_is_not_action_preparation():
    recog = Recognizer(MagicMock())
    recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    recog._gray = np.zeros((1080, 1920), dtype=np.uint8)
    assert recog.find("sss/action_preparation") is None
