"""房间编号读取保留订单页的实际文字位置，缺失数字不确认房间。"""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils.image import loadres

ROOM_TITLES = Path(__file__).parent / "fixtures" / "room_titles"


def solver_with_title(filename):
    title = cv2.cvtColor(cv2.imread(str(ROOM_TITLES / filename)), cv2.COLOR_BGR2RGB)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[18:95, 568:957] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    return solver


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("trade_order_b101_20261027.png", "room_1_1"),
        ("trade_20261013.png", "room_1_1"),
        ("manufacture_20261013.png", "room_2_2"),
        ("power_20261013.png", "room_1_3"),
    ],
)
def test_observed_facility_header_confirms_its_room_number(filename, expected):
    solver = solver_with_title(filename)
    assert solver.detect_room() == expected


@pytest.mark.parametrize("digit", ["floor", "room", "both"])
def test_missing_number_in_confirmed_trade_header_remains_unknown(digit):
    solver = solver_with_title("trade_order_b101_20261027.png")
    if digit in ("floor", "both"):
        solver.recog.img[36:80, 773:807] = 46
    if digit in ("room", "both"):
        solver.recog.img[36:80, 815:849] = 46
    assert solver.detect_room_type() == "贸易站"
    assert solver.detect_room() == ""


@pytest.mark.parametrize("shape", [(30, 21, 3), (42, 33, 3), (0, 0, 3), (8, 6, 3)])
def test_unreadable_digit_never_defaults_to_a_room_number(shape):
    solver = BaseMixin()
    assert solver.detect_room_number(np.full(shape, 46, dtype=np.uint8)) is None


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_recognized_number_preserves_all_existing_digits(number):
    solver = BaseMixin()
    assert solver.detect_room_number(loadres(f"room/{number}")) == number


@pytest.mark.parametrize("number", [None, 1, 2, 3, 4])
def test_dormitory_identity_requires_a_recognized_number(number):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    title = loadres("room/dormitory")
    height, width = title.shape[:2]
    frame[18 : 18 + height, 568 : 568 + width] = title
    if number is not None:
        frame[42:72, 742:763] = loadres(f"room/{number}")
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    assert solver.detect_room_type() == "宿舍"
    assert solver.detect_room() == ("" if number is None else f"dormitory_{number}")
