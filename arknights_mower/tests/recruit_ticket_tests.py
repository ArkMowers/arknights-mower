"""Replay an archived recruitment ticket counter with a split digit contour."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from arknights_mower.solvers.recruit import RecruitSolver


def test_split_digit_fragment_does_not_break_ticket_count():
    crop = cv2.imread(
        str(Path(__file__).parent / "fixtures/recruit_ticket_split_9_20260927.png"),
        cv2.IMREAD_GRAYSCALE,
    )
    assert crop is not None
    frame = np.zeros((54, 149), dtype=np.uint8)
    frame[10:54, 80:149] = crop
    solver = SimpleNamespace(
        recog=SimpleNamespace(gray=frame),
        find=lambda name: (
            ((0, 0), (80, 59)) if name == "recruit/ticket" else ((179, 0), (259, 60))
        ),
    )

    assert RecruitSolver.get_ticket_number(solver) == 39
