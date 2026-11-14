"""排序局部转换须保留整图判定、房型差异和多箭头优先级。"""

import itertools
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402

ROOMS = ["room_1_1", "meeting", "train", "dormitory_1", "central"]
ARROW = cv2.cvtColor(np.array([[[100, 220, 220]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[
    0, 0
]


def solver_for(image):
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=image)
    return solver


def full_image_reference(solver, room):
    """优化前的整图基准，独立保留原读取坐标与优先级。"""
    hsv = cv2.cvtColor(solver.recog.img, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (95, 100, 100), (105, 255, 255))
    for name, x in solver._arrange_order_x(room).items():
        if np.count_nonzero(mask[70:73, x : x + 5]):
            return name, False
        if np.count_nonzero(mask[80:83, x : x + 5]):
            return name, True


@pytest.mark.parametrize("room", ROOMS)
def test_random_rgb_matches_full_image_reference(room):
    rng = np.random.default_rng(418729)
    for _ in range(3):
        solver = solver_for(rng.integers(0, 256, (1080, 1920, 3), dtype=np.uint8))
        assert solver.detect_arrange_order(room) == full_image_reference(solver, room)


@pytest.mark.parametrize("room", ROOMS)
def test_each_arrow_and_sample_corner_keeps_its_direction(room):
    solver = solver_for(np.zeros((1080, 1920, 3), dtype=np.uint8))
    for name, x in solver._arrange_order_x(room).items():
        for direction, y in [(False, 70), (True, 80)]:
            for offset_x, offset_y in [(0, 0), (4, 2)]:
                solver.recog.img[:] = 0
                solver.recog.img[y + offset_y, x + offset_x] = ARROW
                assert solver.detect_arrange_order(room) == (name, direction)


@pytest.mark.parametrize("room", ROOMS)
def test_earlier_column_lower_arrow_precedes_later_upper_arrow(room):
    solver = solver_for(np.zeros((1080, 1920, 3), dtype=np.uint8))
    first, second = list(solver._arrange_order_x(room).items())[:2]
    solver.recog.img[80, first[1]] = ARROW
    solver.recog.img[70, second[1]] = ARROW
    assert solver.detect_arrange_order(room) == (first[0], True)
    solver.recog.img[70, first[1]] = ARROW
    assert solver.detect_arrange_order(room) == (first[0], False)


@pytest.mark.parametrize("room", ["room_1_1", "dormitory_1"])
def test_threshold_neighborhood_matches_full_image_reference(room):
    solver = solver_for(np.zeros((1080, 1920, 3), dtype=np.uint8))
    columns = list(solver._arrange_order_x(room).values())
    colors = itertools.product(
        [94, 95, 96, 104, 105, 106], [99, 100, 101, 254, 255], [99, 100, 101, 254, 255]
    )
    for index, color in enumerate(colors):
        solver.recog.img[:] = 0
        # 以实际 RGB 输入比较，不能假定 HSV 往返量化后保持原值。
        rgb = cv2.cvtColor(np.array([[color]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        solver.recog.img[70 if index % 2 else 80, columns[index % len(columns)]] = rgb
        assert solver.detect_arrange_order(room) == full_image_reference(solver, room)


def test_central_uses_dormitory_mapping_not_production_mapping():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[70, 1070] = ARROW
    solver = solver_for(image)
    assert solver.detect_arrange_order("room_1_1") == ("效率", False)
    assert solver.detect_arrange_order("central") == ("工作状态", False)
    assert solver.detect_arrange_order("dormitory_1") == ("工作状态", False)


@pytest.mark.parametrize("room", ROOMS)
@pytest.mark.parametrize("shape", [(40, 700, 3), (75, 1100, 3), (82, 1300, 3)])
def test_partial_dimensions_match_full_image_reference(room, shape):
    rng = np.random.default_rng(852017)
    solver = solver_for(rng.integers(0, 256, shape, dtype=np.uint8))
    assert solver.detect_arrange_order(room) == full_image_reference(solver, room)


def test_uses_one_current_image_and_only_converts_arrow_region(monkeypatch):
    class Recognizer:
        reads = 0

        @property
        def img(self):
            self.reads += 1
            image = np.zeros((1080, 1920, 3), dtype=np.uint8)
            image[70, 1210] = ARROW
            return image

    solver = BaseMixin()
    solver.recog = Recognizer()
    convert = cv2.cvtColor
    shapes = []

    def measured_convert(image, conversion):
        shapes.append(image.shape)
        return convert(image, conversion)

    monkeypatch.setattr(cv2, "cvtColor", measured_convert)
    assert solver.detect_arrange_order("room_1_1") == ("技能", False)
    assert solver.recog.reads == 1
    assert shapes == [(13, 560, 3)]
