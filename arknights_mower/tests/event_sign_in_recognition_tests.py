"""Real card-list themes separate login progress from explicit reward receipts."""

import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.event_sign_in_recognition import (
    day_positions,
    detect_progress,
    read_cards,
)
from arknights_mower.utils import rapidocr
from arknights_mower.utils.image import cropimg

FIXTURES = Path(__file__).parent / "fixtures/event_sign_in"


def frame(name):
    image = cv2.cvtColor(
        cv2.imdecode(np.fromfile(FIXTURES / f"{name}.jpg", np.uint8), cv2.IMREAD_COLOR),
        cv2.COLOR_BGR2RGB,
    )
    if name.startswith("seven"):
        height, width, x, y = 1080, 1920, 650, 205
    elif name.endswith("video_border"):
        height, width, x, y = 716, 1272, 475, 180
    else:
        height, width, x, y = 640, 1280, 480, 140
    canvas = np.zeros((height, width, 3), np.uint8)
    canvas[y : y + image.shape[0], x : x + image.shape[1]] = image
    return canvas


@pytest.fixture(scope="module")
def local_ocr():
    return rapidocr.create_engine(threads=2)


def observe(image, local_ocr):
    progress = detect_progress(image)
    assert progress is not None
    result, _ = local_ocr(cropimg(image, progress.day_scope), use_cls=False)
    return progress, read_cards(image, progress, result)


@pytest.mark.parametrize(
    "name,total,unlocked",
    [
        ("seven_receipt_before", 7, 2),
        ("seven_receipt_after", 7, 2),
        ("seven_receipt_right", 7, 2),
        ("ten_receipt_before", 10, 10),
        ("ten_receipt_one", 10, 10),
        ("ten_receipt_two", 10, 10),
        ("ten_receipt_scrolled", 10, 10),
        ("ten_receipt_anonymous", 10, 10),
        ("ten_receipt_video_border", 10, 10),
    ],
)
def test_real_progress_counts_differently_sized_nodes_at_their_actual_positions(
    name, total, unlocked
):
    progress = detect_progress(frame(name))
    assert progress is not None
    assert progress.total_days == total
    assert progress.unlocked_days == unlocked
    assert len(progress.points) == total
    if total == 10:
        assert progress.points[0][0] < 520


@pytest.mark.parametrize(
    "name,expected",
    [
        ("seven_receipt_before", [(1, True), (2, False), (3, False), (4, False)]),
        ("seven_receipt_after", [(1, True), (2, True), (3, False), (4, False)]),
        ("seven_receipt_right", [(4, False), (5, False), (6, False), (7, False)]),
        ("ten_receipt_before", [(1, False), (2, False), (3, False), (4, False)]),
        ("ten_receipt_one", [(1, True), (2, False), (3, False), (4, False)]),
        ("ten_receipt_two", [(1, True), (2, True), (3, False), (4, False)]),
        ("ten_receipt_scrolled", [(2, True), (3, True), (4, True)]),
        ("ten_receipt_video_border", [(1, False), (2, False), (3, False), (4, False)]),
    ],
)
def test_real_card_receipts_not_brightness_or_white_progress_decide_claimed_state(
    name, expected, local_ocr
):
    _, cards = observe(frame(name), local_ocr)
    assert [(card.day, card.claimed) for card in cards] == expected


def test_all_visible_receipt_marks_remain_valid_when_the_day_numerals_are_covered(
    local_ocr,
):
    progress, cards = observe(frame("ten_receipt_anonymous"), local_ocr)
    assert progress.unlocked_days == 10
    assert len(cards) >= 3
    assert all(card.claimed for card in cards)
    assert all(card.day is None for card in cards)


@pytest.mark.parametrize("scale", [0.75, 1.0, 1.5])
def test_ten_day_theme_scales_from_panel_geometry_not_seven_day_coordinates(
    scale, local_ocr
):
    original = frame("ten_receipt_two")
    image = cv2.resize(original, None, fx=scale, fy=scale)
    progress, cards = observe(image, local_ocr)
    assert (progress.total_days, progress.unlocked_days) == (10, 10)
    assert [(card.day, card.claimed) for card in cards] == [
        (1, True),
        (2, True),
        (3, False),
        (4, False),
    ]


def test_standard_canvas_letterboxing_does_not_move_the_progress_to_old_coordinates(
    local_ocr,
):
    image = cv2.resize(frame("ten_receipt_two"), (1920, 960))
    image = cv2.copyMakeBorder(image, 60, 60, 0, 0, cv2.BORDER_CONSTANT)
    progress, cards = observe(image, local_ocr)
    assert progress.points[0][1] > 300
    assert (progress.total_days, progress.unlocked_days) == (10, 10)
    assert [(card.day, card.claimed) for card in cards] == [
        (1, True),
        (2, True),
        (3, False),
        (4, False),
    ]


def test_a_missed_middle_numeral_retains_an_unconfirmed_card_instead_of_hiding_it(
    local_ocr,
):
    image = frame("ten_receipt_before")
    progress = detect_progress(image)
    result, _ = local_ocr(cropimg(image, progress.day_scope), use_cls=False)
    result = [entry for entry in result if entry[1].strip() != "2"]
    cards = read_cards(image, progress, result)
    assert [(card.day, card.claimed) for card in cards] == [
        (1, False),
        (None, False),
        (3, False),
        (4, False),
    ]


def test_low_confidence_and_out_of_range_numbers_do_not_provide_claim_positions():
    progress = detect_progress(frame("ten_receipt_before"))
    box = [[10, 10], [40, 10], [40, 70], [10, 70]]
    assert day_positions([(box, "2", 0.89)], progress) == {}
    assert day_positions([(box, "11", 0.99)], progress) == {}
    assert day_positions([(box, "2O", 0.99)], progress) == {}


def test_the_distinct_login_activity_is_not_a_card_list_progress_row():
    image = np.zeros((1080, 1920, 3), np.uint8)
    crop = cv2.cvtColor(
        cv2.imdecode(np.fromfile(FIXTURES / "login_progress_region.png", np.uint8), 1),
        cv2.COLOR_BGR2RGB,
    )
    image[205:290, 670:1800] = crop
    assert detect_progress(image) is None


@pytest.mark.parametrize("missing", [(0,), (3,), (9,), (0, 1, 2)])
def test_missing_progress_nodes_cannot_renumber_a_ten_day_activity(missing):
    image = frame("ten_receipt_before")
    progress = detect_progress(image)
    for index in missing:
        x, y = progress.points[index]
        image[y - 18 : y + 19, x - 18 : x + 19] = (35, 40, 65)
    assert detect_progress(image) is None


@pytest.mark.parametrize(
    "name,expected",
    [
        ("seven_receipt_before", [(1, True), (2, False), (3, False), (4, False)]),
        ("ten_receipt_before", [(1, False), (2, False), (3, False), (4, False)]),
    ],
)
def test_actual_solver_assembles_real_panel_geometry_and_receipts(
    name, expected, local_ocr, monkeypatch
):
    from arknights_mower.solvers.event_sign_in import EventSignInSolver
    from arknights_mower.utils import config

    solver = object.__new__(EventSignInSolver)
    solver.deadline = time.monotonic() + 180
    solver.activity_days = None
    solver.recog = SimpleNamespace(
        img=frame(name), check_announcement=lambda: (1800, 150)
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(rapidocr, "engine", local_ocr)

    page = solver._panel_states()

    assert page is not None
    assert page.first_day == 1
    assert [(card.day, card.claimed) for card in page.cards] == expected
