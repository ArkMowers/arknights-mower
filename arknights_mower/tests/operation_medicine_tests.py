from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import operation
from arknights_mower.utils.recognize import Scene


@pytest.mark.parametrize(
    "days, marked_pixels, allowed", [(0, 4000, False), (3, 4000, True), (3, 100, False)]
)
def test_native_potion_retains_threshold_and_expiry_recognition(
    monkeypatch, days, marked_pixels, allowed
):
    monkeypatch.setattr(
        operation.config, "conf", SimpleNamespace(medicine_expire_days=days)
    )
    pixels = np.zeros((1080, 1920, 3), dtype=np.uint8)
    count = MagicMock(return_value=marked_pixels)
    monkeypatch.setattr(operation.cv2, "countNonZero", count)
    solver = object.__new__(operation.OperationSolver)
    solver.stage_id = "1-7"
    solver.recog = SimpleNamespace(img=pixels)
    solver.scene = MagicMock(return_value=Scene.OPERATOR_RECOVER_POTION)
    solver.tap = MagicMock()
    solver._finish_batch = MagicMock()
    solver.sanity_drain = False

    solver.transition()

    assert solver.sanity_drain is not allowed
    if allowed:
        solver.tap.assert_called_once_with((1635, 865))
        solver._finish_batch.assert_not_called()
    else:
        solver.tap.assert_not_called()
        solver._finish_batch.assert_called_once_with(False)
    assert count.call_count == (1 if days > 0 else 0)
