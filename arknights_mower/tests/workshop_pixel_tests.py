"""Real MuMu workshop headers distinguish furniture recipes after scrolling."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import rapidocr
from arknights_mower.utils.workshop_ui import furniture_formula_name

FIXTURES = Path(__file__).parent / "fixtures/workshop"


@pytest.fixture(scope="module")
def ocr():
    return rapidocr.create_engine()


def headers():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[200:1000, 376:1848] = cv2.cvtColor(
        cv2.imread(str(FIXTURES / "furniture_formula_headers.png")), cv2.COLOR_BGR2RGB
    )
    return image


@pytest.mark.parametrize(
    "x,y,expected",
    [
        (1382, 210, "家具零件_碳"),
        (641, 481, "家具零件_碳素"),
        (1382, 481, "家具零件_碳素组"),
        (640, 751, "家具零件_基础加固建材"),
        (1382, 751, "家具零件_进阶加固建材"),
    ],
)
def test_real_furniture_headers_distinguish_mood_and_lmd(
    ocr, monkeypatch, x, y, expected
):
    monkeypatch.setattr(rapidocr, "engine", ocr)
    assert furniture_formula_name(headers(), [[x, y], [x + 135, y + 40]]) == expected


def test_real_formula_list_recognizes_carbon_group_after_scrolling(ocr, monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", ocr)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=headers(), h=1080, w=1920)
    names = [name for name, _, _ in solver.item_list()]
    assert names.count("家具零件_碳素组") == 1
    assert names.count("家具零件_碳") == 1
    assert "家具零件_碳素" in names
