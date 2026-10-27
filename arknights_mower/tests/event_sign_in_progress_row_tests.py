"""A partial login prefix retains the full connected progress row."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.event_sign_in_recognition import detect_progress

FIXTURES = Path(__file__).parent / "fixtures/event_sign_in"


def frame(name):
    crop = cv2.cvtColor(
        cv2.imdecode(np.fromfile(FIXTURES / f"{name}.png", np.uint8), cv2.IMREAD_COLOR),
        cv2.COLOR_BGR2RGB,
    )
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[205 : 205 + crop.shape[0], 650 : 650 + crop.shape[1]] = crop
    return image


@pytest.mark.parametrize("page", ["left", "right"])
def test_four_white_nodes_and_three_black_nodes_retain_all_seven_days(page):
    image = frame(f"seven_day_four_claimed_{page}")

    progress = detect_progress(image)

    assert progress is not None
    assert (progress.total_days, progress.unlocked_days) == (7, 4)
    assert len(progress.points) == 7
    assert abs(progress.points[0][0] - 697) <= 3
    assert abs(progress.points[-1][0] - 1757) <= 3


@pytest.mark.parametrize(
    "segments",
    [
        [(679, 248, 1080, 248), (1207, 248, 1798, 248)],
        [(679, 244, 1246, 244), (1207, 256, 1798, 256)],
    ],
    ids=["separated-horizontal-spans", "different-rows"],
)
def test_unconnected_line_fragments_do_not_establish_a_complete_progress_row(
    segments, monkeypatch
):
    image = frame("seven_day_four_claimed_left")
    lines = np.asarray(segments, np.int32)
    lines[:, (0, 2)] -= 480
    lines[:, (1, 3)] -= 108
    monkeypatch.setattr(cv2, "HoughLinesP", lambda *args, **kwargs: lines[:, None, :])

    assert detect_progress(image) is None
