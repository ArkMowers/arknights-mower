from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene

FIXTURES = Path(__file__).parent / "fixtures" / "clue"
BOARD_FRAMES = [
    "clue_board_fast_place_enabled.png",
    "clue_board_fast_place_disabled.png",
    "clue_board_blue_background.jpg",
    "clue_live_receive_before.png",
]


def observation(filename):
    return Recognizer(
        SimpleNamespace(check_current_focus=lambda: False),
        (FIXTURES / filename).read_bytes(),
    )


@pytest.mark.parametrize("filename", BOARD_FRAMES)
def test_board_scene_does_not_depend_on_confidential_icon(filename):
    recog = observation(filename)
    # 移除旧的文件图标，页面识别仍须接受橙色和灰色快捷置入按钮。
    recog.img[710:900, 1740:1860] = 0
    recog._gray = cv2.cvtColor(recog.img, cv2.COLOR_RGB2GRAY)

    assert recog.get_scene() == Scene.INFRA_CONFIDENTIAL


@pytest.mark.parametrize("filename", BOARD_FRAMES)
def test_both_fast_place_appearances_are_accepted(filename):
    recog = observation(filename)

    assert recog.find("clue") == ((1656, 940), (1872, 1023))


@pytest.mark.parametrize("filename", BOARD_FRAMES)
def test_badge_does_not_change_board_scene(filename):
    recog = observation(filename)
    # 角标可随可置入数量出现或消失；识别范围不能包含角标。
    recog.img[918:970, 1874:1920] = 0
    recog._gray = cv2.cvtColor(recog.img, cv2.COLOR_RGB2GRAY)

    assert recog.get_scene() == Scene.INFRA_CONFIDENTIAL


@pytest.mark.parametrize(
    "filename,scene",
    [
        ("clue_gift_inventory.jpg", Scene.CLUE_GIVE_AWAY),
        ("clue_live_room_details.png", Scene.INFRA_DETAILS),
        ("clue_live_receive_after.png", Scene.CLUE_RECEIVE),
    ],
)
def test_other_reception_pages_are_not_board(filename, scene):
    recog = observation(filename)

    assert recog.get_scene() == scene
    assert recog.find("clue") is None
