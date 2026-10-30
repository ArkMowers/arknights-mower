"""保全导航不把部署入口误识别为装备确认并点击进入战斗。"""

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


def test_current_preparation_frame_keeps_existing_handoff_without_input():
    path = Path(__file__).parent / "fixtures/sss/action_preparation_20261028.jpg"
    device = MagicMock()
    recog = Recognizer(device, path.read_bytes())
    assert recog.find("sss/deploy_button") is None
    assert recog.get_sss_scene() == Scene.SSS_DEPLOY
    solver = object.__new__(BaseSolver)
    solver.device, solver.recog = device, recog
    assert solver.to_sss(1, 1) is None
    device.tap.assert_not_called()


@pytest.mark.parametrize("seed", range(40))
def test_start_action_is_not_equipment_confirmation(seed):
    cv2.setRNGSeed(seed)
    path = Path(__file__).parent / "fixtures/sss/squad_20261029.jpg"
    recog = Recognizer(MagicMock(), path.read_bytes())
    recog.check_current_focus = MagicMock()
    assert recog.find("sss/device_button") is None
    assert recog.find("sss/next_step_button") is None
    assert recog.get_sss_scene() != Scene.SSS_DEVICE


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
    assert recog.find("sss/action_preparation") is None
    assert recog.get_sss_scene() == Scene.SSS_DEPLOY


@pytest.mark.parametrize(
    "button", ["deploy_button", "redeploy_button", "device_button", "next_step_button"]
)
def test_unrelated_frame_is_not_a_navigation_button(button):
    recog = Recognizer(MagicMock())
    recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    recog._gray = np.zeros((1080, 1920), dtype=np.uint8)
    assert recog.find(f"sss/{button}") is None


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize(
    "frame,scene",
    [
        ("conduction_20261030.jpg", Scene.SSS_EC),
        ("equipment_20261030.jpg", Scene.SSS_DEVICE),
    ],
)
def test_preparation_pages_are_not_the_map_selection_page(seed, frame, scene):
    cv2.setRNGSeed(seed)
    path = Path(__file__).parent / "fixtures/sss" / frame
    recog = Recognizer(MagicMock(), path.read_bytes())
    assert recog.find("sss/main") is None
    assert recog.get_sss_scene() == scene


def test_real_map_selection_page_still_recognized():
    path = Path(__file__).parent / "fixtures/sss/main_20261030.jpg"
    recog = Recognizer(MagicMock(), path.read_bytes())
    assert recog.find("sss/main") is not None
    assert recog.get_sss_scene() == Scene.SSS_MAIN


@pytest.mark.parametrize("seed", range(40))
def test_equipment_navigation_only_confirms_existing_choices(seed):
    cv2.setRNGSeed(seed)
    root = Path(__file__).parent / "fixtures/sss"
    device = MagicMock()
    recog = Recognizer(device, (root / "equipment_20261030.jpg").read_bytes())
    solver = object.__new__(BaseSolver)
    solver.device, solver.recog = device, recog

    def advance_frame(interval=1):
        solver.recog = Recognizer(
            device, (root / "deployment_20261029.jpg").read_bytes()
        )

    solver.sleep = advance_frame
    assert solver.to_sss(2, 1) is None
    device.tap.assert_called_once_with((1824, 1026))
