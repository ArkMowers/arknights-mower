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


def test_supplied_last_day_highlight_preserves_the_complete_seven_day_row():
    # 2026-10-30 11:39:09 的现场截图裁剪，保留进度行及奖励卡片。
    image = frame("seven_day_seven_unclaimed_right_20261030")

    progress = detect_progress(image)

    assert progress is not None
    assert (progress.total_days, progress.unlocked_days) == (7, 7)
    np.testing.assert_allclose(
        progress.points,
        [(x, 248) for x in (698, 875, 1051, 1228, 1404, 1581, 1757)],
        atol=3,
        rtol=0,
    )


@pytest.mark.parametrize("days", [7, 10])
@pytest.mark.parametrize("jpeg", [False, True], ids=["rgb", "jpeg"])
def test_short_white_prefix_retains_first_day_when_line_edges_change(days, jpeg):
    image = np.zeros((1080, 1920, 3), np.uint8)
    image[222:275, 680:1794] = 80
    centers = [round(x) for x in np.linspace(697, 1757, days)]
    # The reached and unreached strokes have different edges in captured frames.
    cv2.line(image, (centers[1], 248), (1757, 248), (0, 0, 0), 6, cv2.LINE_AA)
    cv2.line(image, (697, 248), (centers[1], 248), (255, 255, 255), 4, cv2.LINE_AA)
    for index, x in enumerate(centers):
        color = (255, 255, 255) if index < 2 else (0, 0, 0)
        cv2.circle(image, (x, 248), 11, color, -1, cv2.LINE_AA)
        if index in (1, 2, 5, days - 1):
            cv2.circle(image, (x, 248), 18, color, 3, cv2.LINE_AA)
    if jpeg:
        encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])[1]
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    progress = detect_progress(image)

    assert progress is not None
    assert (progress.total_days, progress.unlocked_days) == (days, 2)
    np.testing.assert_allclose(
        progress.points, [(x, 248) for x in centers], atol=3, rtol=0
    )


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
