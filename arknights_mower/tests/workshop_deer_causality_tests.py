"""Regression samples for Nine-Colored Deer causality template matching."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from arknights_mower.utils.digit_reader import DigitReader

FIXTURES = Path(__file__).parent / "fixtures" / "workshop"


@pytest.mark.parametrize(
    "filename,expected",
    [("deer_causality_1.png", 1), ("deer_causality_37.png", 37)],
)
def test_deer_causality_from_real_counter_crops(filename, expected):
    counter = cv2.imread(str(FIXTURES / filename), cv2.IMREAD_GRAYSCALE)
    assert counter is not None and counter.shape == (45, 105)
    screenshot = np.zeros((1080, 1920), dtype=np.uint8)
    screenshot[290:335, 95:200] = counter

    assert DigitReader().get_deer_causality(screenshot) == expected


def test_deer_causality_rejects_unreadable_counter():
    screenshot = np.zeros((1080, 1920), dtype=np.uint8)
    assert DigitReader().get_deer_causality(screenshot) is None
