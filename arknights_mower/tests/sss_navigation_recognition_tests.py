"""保全导航在开始部署页交接，不点击进入战斗。"""

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


@pytest.mark.parametrize("seed", range(40))
def test_deployment_frame_reaches_sss_handoff_without_input(seed):
    cv2.setRNGSeed(seed)
    path = Path(__file__).parent / "fixtures/sss/deployment_20261029.jpg"
    device = MagicMock()
    recog = Recognizer(device, path.read_bytes())
    assert recog.find("sss/next_step_button") is None
    assert recog.find("sss/deploy_button") is not None
    assert recog.get_sss_scene() == Scene.SSS_DEPLOY
    solver = object.__new__(BaseSolver)
    solver.device, solver.recog = device, recog
    assert solver.to_sss(1, 1) is None
    device.tap.assert_not_called()


@pytest.mark.parametrize("seed", range(10))
def test_battle_preparation_is_not_a_deployment_handoff(seed):
    cv2.setRNGSeed(seed)
    path = Path(__file__).parent / "fixtures/sss/action_preparation_20261028.jpg"
    recog = Recognizer(MagicMock(), path.read_bytes())
    recog.check_current_focus = MagicMock()
    assert recog.get_sss_scene() == Scene.UNKNOWN
    solver = object.__new__(BaseSolver)
    solver.device, solver.recog = recog.device, recog
    for _ in range(2):
        assert solver.to_sss(1, 1) == (
            "保全已进入战斗内的行动前调整，请返回开始部署页后重新执行"
        )
    recog.device.tap.assert_not_called()


def test_current_squad_returns_to_deployment_without_starting_battle():
    root = Path(__file__).parent / "fixtures/sss"
    device = MagicMock()
    recog = Recognizer(device, (root / "squad_20261029.jpg").read_bytes())
    assert recog.find("sss/next_step_button") is None
    assert recog.get_sss_scene() == Scene.SSS_SQUAD
    solver = object.__new__(BaseSolver)
    solver.device, solver.recog = device, recog

    def back():
        recog.start((root / "deployment_20261029.jpg").read_bytes())
        recog.scene = Scene.UNDEFINED
        recog._matcher = None

    solver.back = MagicMock(side_effect=back)
    assert solver.to_sss(1, 1) is None
    solver.back.assert_called_once()
    device.tap.assert_not_called()


def test_old_deploy_button_still_recognized():
    path = Path(__file__).parent / "fixtures/sss/action_preparation_20261028.jpg"
    recog = Recognizer(MagicMock(), path.read_bytes())
    img = recog.img.copy()
    # 保留完整场景背景，遮去新版标记后仅用旧版按钮验证兼容识别。
    img[652:706, 1080:1340] = 0
    button = loadres("sss/deploy_button")
    h, w = button.shape[:2]
    img[971 : 971 + h, 1645 : 1645 + w] = button
    recog._img, recog._gray = img, cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    recog.check_loading_time = MagicMock()
    assert recog.get_sss_scene() == Scene.SSS_DEPLOY


@pytest.mark.parametrize(
    "button", ["deploy_button", "redeploy_button", "start_action", "next_step_button"]
)
def test_unrelated_frame_is_not_a_navigation_button(button):
    recog = Recognizer(MagicMock())
    recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    recog._gray = np.zeros((1080, 1920), dtype=np.uint8)
    assert recog.find(f"sss/{button}") is None
