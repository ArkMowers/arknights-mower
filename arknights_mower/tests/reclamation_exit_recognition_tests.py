from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import Recognizer


@pytest.mark.parametrize(
    ("position", "expected"),
    [((76, 48), ((76, 48), (164, 124))), ((300, 200), None)],
)
def test_battle_exit_uses_only_the_grayscale_search_area(
    monkeypatch, position, expected
):
    frame = np.zeros((1080, 1920), dtype=np.uint8)
    button = loadres("ra/battle_exit", True)
    x, y = position
    h, w = button.shape
    frame[y : y + h, x : x + w] = button
    recognizer = Recognizer(Mock(), cv2.imencode(".png", frame)[1].tobytes())
    convert = Mock(wraps=cv2.cvtColor)
    mask = Mock(wraps=cv2.inRange)
    monkeypatch.setattr(cv2, "cvtColor", convert)
    monkeypatch.setattr(cv2, "inRange", mask)

    assert recognizer.find_ra_battle_exit() == expected
    convert.assert_not_called()
    mask.assert_not_called()
