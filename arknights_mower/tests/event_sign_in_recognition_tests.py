"""Real card-list themes separate login progress from explicit reward receipts."""

import time
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.event_sign_in_recognition import (
    Progress,
    day_positions,
    detect_progress,
    read_cards,
    supplement_day_numbers,
)
from arknights_mower.utils import rapidocr
from arknights_mower.utils.image import cropimg

FIXTURES = Path(__file__).parent / "fixtures/event_sign_in"


def frame(name):
    suffix = "png" if name.startswith(("seven_day_", "celebration_")) else "jpg"
    image = cv2.cvtColor(
        cv2.imdecode(
            np.fromfile(FIXTURES / f"{name}.{suffix}", np.uint8), cv2.IMREAD_COLOR
        ),
        cv2.COLOR_BGR2RGB,
    )
    if name.startswith(("seven", "celebration_")):
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
    result = supplement_day_numbers(
        image,
        progress,
        result,
        lambda glyph, **options: local_ocr(glyph, use_cls=False, **options)[0],
    )
    assert result is not None
    return progress, read_cards(image, progress, result)


@pytest.mark.parametrize(
    "name,first_day,expected",
    [
        ("before", 1, [(1, False), (2, False), (3, False), (4, False)]),
        ("claimed", 1, [(1, True), (2, False), (3, False), (4, False)]),
        ("middle", 4, [(4, False), (5, False), (6, False)]),
        ("right", 7, [(7, False), (8, False), (9, False), (10, False)]),
        ("right_settled", 7, [(7, False), (8, False), (9, False), (10, False)]),
    ],
)
def test_actual_solver_reads_celebration_pages_captured_on_device(
    name, first_day, expected, local_ocr, monkeypatch
):
    from arknights_mower.solvers.event_sign_in import EventSignInSolver
    from arknights_mower.utils import config

    solver = object.__new__(EventSignInSolver)
    solver.deadline = time.monotonic() + 180
    solver.activity_days = None
    solver.recog = SimpleNamespace(
        img=frame(f"celebration_{name}"), check_announcement=lambda: (1870, 152)
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(rapidocr, "engine", local_ocr)

    page = solver._panel_states()

    assert page is not None
    assert page.progress.total_days == 10
    assert page.progress.unlocked_days == 1
    assert page.first_day == first_day
    assert [(card.day, card.claimed) for card in page.cards] == expected


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
    assert day_positions([(box, "2", float("nan"))], progress) == {}


def glyph_panel(*, light=False):
    background, foreground = (
        ((30, 30, 30), (255, 255, 255)) if light else ((255, 255, 255), (0, 0, 0))
    )
    image = np.full((130, 1100, 3), background, dtype=np.uint8)
    progress = Progress(7, 7, (), ((0, 0), (1100, 130)), ((0, 0), (1100, 130)), 60, 1)
    return image, progress, foreground


@pytest.mark.parametrize("light", [False, True])
def test_complete_light_and_dark_day_glyphs_are_read_without_mutating_the_frame(light):
    image, progress, color = glyph_panel(light=light)
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)
    before = image.copy()
    recognize = Mock(return_value=[["4", 0.99]])

    rows = supplement_day_numbers(image, progress, [], recognize)

    assert day_positions(rows, progress) == {4: (138, 60)}
    assert recognize.call_count == 1
    assert recognize.call_args.kwargs == {"use_det": False}
    np.testing.assert_array_equal(recognize.call_args.args[0][0, 0], image[0, 0])
    np.testing.assert_array_equal(image, before)


@pytest.mark.parametrize("score", [0.89, float("nan"), float("inf")])
def test_supplemental_day_glyphs_require_finite_high_confidence(score):
    image, progress, color = glyph_panel()
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)

    rows = supplement_day_numbers(
        image, progress, [], Mock(return_value=[["4", score]])
    )

    assert day_positions(rows, progress) == {}


@pytest.mark.parametrize("kind", ["left", "right", "top", "bottom", "small"])
def test_clipped_and_small_supplemental_glyphs_are_never_recognized(kind):
    image, progress, color = glyph_panel()
    x, y, width, height = 100, 13, 76, 95
    if kind == "left":
        x = 0
    elif kind == "right":
        x = image.shape[1] - width
    elif kind == "top":
        y = 0
    elif kind == "bottom":
        y = image.shape[0] - height
    else:
        height = 48
    image[y : y + height, x : x + width] = color
    recognize = Mock()

    assert supplement_day_numbers(image, progress, [], recognize) == []
    recognize.assert_not_called()


@pytest.mark.parametrize("readings", [("4", "4"), ("5", "4")])
def test_supplemental_duplicate_or_reversed_days_reject_the_page(readings):
    image, progress, color = glyph_panel()
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)
    cv2.rectangle(image, (400, 13), (475, 107), color, -1)
    recognize = Mock(side_effect=[[[text, 0.99]] for text in readings])

    assert supplement_day_numbers(image, progress, [], recognize) is None


def test_supplemental_reading_cannot_replace_an_overlapping_detected_identity():
    image, progress, color = glyph_panel()
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)
    detected = ([[90, 10], [150, 10], [150, 110], [90, 110]], "6", 0.99)

    assert (
        supplement_day_numbers(
            image, progress, [detected], Mock(return_value=[["7", 0.99]])
        )
        is None
    )


def test_supplemental_glyph_count_is_bounded_by_the_detected_activity_days():
    image, progress, color = glyph_panel()
    for x in range(10, 1090, 135):
        cv2.rectangle(image, (x, 13), (x + 50, 107), color, -1)
    recognize = Mock()

    assert supplement_day_numbers(image, progress, [], recognize) is None
    recognize.assert_not_called()


def test_confident_detected_numerals_do_not_receive_another_ocr_request():
    image, progress, color = glyph_panel()
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)
    detected = ([[95, 10], [180, 10], [180, 110], [95, 110]], "6", 0.99)
    recognize = Mock()

    assert supplement_day_numbers(image, progress, [detected], recognize) == [detected]
    recognize.assert_not_called()


def test_adjacent_components_of_a_two_digit_day_are_recognized_together():
    image, _, color = glyph_panel()
    progress = Progress(10, 10, (), ((0, 0), (1100, 130)), ((0, 0), (1100, 130)), 60, 1)
    cv2.rectangle(image, (100, 13), (125, 107), color, -1)
    cv2.rectangle(image, (140, 13), (175, 107), color, -1)
    recognize = Mock(return_value=[["10", 0.99]])

    rows = supplement_day_numbers(image, progress, [], recognize)

    assert day_positions(rows, progress) == {10: (138, 60)}
    assert recognize.call_count == 1


@pytest.mark.parametrize("score,claimed", [(0.89, False), (0.99, True)])
@pytest.mark.parametrize("offset", [-20, -8, 0, 10, 20])
def test_offset_receipt_text_uses_confirmed_card_spacing_without_lowering_confidence(
    score, claimed, offset, monkeypatch
):
    from arknights_mower.solvers import event_sign_in_recognition as vision

    image = frame("ten_receipt_one")
    progress = detect_progress(image)
    x0, _ = progress.day_scope[0]
    rows = []
    for day, x in ((2, 714), (3, 862), (4, 1014)):
        rows.append(
            (
                [
                    [x - x0 - 25, 10],
                    [x - x0 + 25, 10],
                    [x - x0 + 25, 80],
                    [x - x0 - 25, 80],
                ],
                str(day),
                0.99,
            )
        )
    left, right = 34 + offset, 116 + offset
    rows.append(
        ([[left, 156], [right, 156], [right, 182], [left, 182]], "物资已领取", score)
    )
    monkeypatch.setattr(vision, "_receipt_positions", lambda *_: [])

    cards = read_cards(image, progress, rows)

    assert [(card.day, card.claimed) for card in cards] == [
        (1 if claimed else None, claimed),
        (2, False),
        (3, False),
        (4, False),
    ]
    assert [card.position[0] for card in cards] == [564, 714, 862, 1014]


@pytest.mark.parametrize("kind", ["clipped", "duplicate"])
def test_receipt_grid_alignment_rejects_incomplete_or_conflicting_slots(
    kind, monkeypatch
):
    from arknights_mower.solvers import event_sign_in_recognition as vision

    image = frame("ten_receipt_one")
    progress = detect_progress(image)
    x0, _ = progress.day_scope[0]
    rows = []
    for day, x in ((2, 714), (3, 862), (4, 1014)):
        rows.append(
            (
                [
                    [x - x0 - 25, 10],
                    [x - x0 + 25, 10],
                    [x - x0 + 25, 80],
                    [x - x0 - 25, 80],
                ],
                str(day),
                0.99,
            )
        )
    centers = [556] if kind == "clipped" else [542, 586]
    for center in centers:
        left, right = center - x0 - 15, center - x0 + 15
        rows.append(
            ([[left, 156], [right, 156], [right, 182], [left, 182]], "已领取", 0.99)
        )
    if kind == "clipped":
        progress = replace(progress, card_scope=((520, 219), progress.card_scope[1]))
    monkeypatch.setattr(vision, "_receipt_positions", lambda *_: [])

    cards = read_cards(image, progress, rows)

    if kind == "clipped":
        assert [(card.day, card.claimed) for card in cards] == [
            (2, False),
            (3, False),
            (4, False),
        ]
    else:
        assert cards == ()


@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError])
def test_supplemental_ocr_failure_leaves_the_actual_panel_unconfirmed(
    failure, monkeypatch
):
    from arknights_mower.solvers import event_sign_in as sign_in
    from arknights_mower.utils import config

    image, progress, color = glyph_panel()
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)
    solver = object.__new__(sign_in.EventSignInSolver)
    solver.deadline = time.monotonic() + 180
    solver.activity_days = None
    solver.recog = SimpleNamespace(img=image, check_announcement=lambda: (0, 0))
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(sign_in, "detect_progress", lambda _: progress)
    engine = Mock(side_effect=[([], None), failure("supplement failed")])
    monkeypatch.setattr(rapidocr, "engine", engine)

    with pytest.raises(sign_in.RecognizeError, match="supplement failed"):
        solver._panel_states()
    assert [call.kwargs["use_det"] for call in engine.call_args_list] == [True, False]


@pytest.mark.parametrize("failure", ["stop", "deadline"])
def test_supplemental_ocr_stop_and_deadline_propagate_before_a_panel_can_be_used(
    failure, monkeypatch
):
    from arknights_mower.solvers import event_sign_in as sign_in
    from arknights_mower.utils import config

    image, progress, color = glyph_panel()
    cv2.rectangle(image, (100, 13), (175, 107), color, -1)
    solver = object.__new__(sign_in.EventSignInSolver)
    solver.deadline = 180
    solver.activity_days = None
    solver.recog = SimpleNamespace(img=image, check_announcement=lambda: (0, 0))
    stopped = Event()
    now = 0
    monkeypatch.setattr(config, "stop_mower", stopped)
    monkeypatch.setattr(sign_in, "time", SimpleNamespace(monotonic=lambda: now))
    monkeypatch.setattr(sign_in, "detect_progress", lambda _: progress)

    def recognize(image, **options):
        nonlocal now
        if not options["use_det"]:
            if failure == "stop":
                stopped.set()
            else:
                now = 181
            return [["4", 0.99]], None
        return [], None

    engine = Mock(side_effect=recognize)
    monkeypatch.setattr(rapidocr, "engine", engine)

    with pytest.raises(
        sign_in.MowerExit if failure == "stop" else sign_in.RecognizeError
    ):
        solver._panel_states()
    assert [call.kwargs["use_det"] for call in engine.call_args_list] == [True, False]


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


def test_actual_solver_confirms_the_supplied_panel_with_day_seven_unclaimed(
    local_ocr, monkeypatch
):
    from arknights_mower.solvers.event_sign_in import EventSignInSolver
    from arknights_mower.utils import config

    solver = object.__new__(EventSignInSolver)
    solver.deadline = time.monotonic() + 180
    solver.activity_days = None
    solver.sleep = Mock()
    solver.recog = SimpleNamespace(
        img=frame("seven_day_seven_unclaimed_right_20261030"),
        check_announcement=lambda: (1875, 152),
        update=Mock(),
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(rapidocr, "engine", local_ocr)

    page = solver._wait_panel()

    assert page is not None
    assert (page.progress.total_days, page.progress.unlocked_days) == (7, 7)
    assert page.first_day == 4
    assert [(card.day, card.claimed) for card in page.cards] == [
        (4, True),
        (5, True),
        (6, True),
        (7, False),
    ]
    assert solver.recog.update.call_count == 2


def test_real_claimed_four_day_prefix_can_be_rechecked_without_reward_clicks(
    local_ocr, monkeypatch
):
    from arknights_mower.solvers.event_sign_in import EventSignInSolver
    from arknights_mower.utils import config

    solver = object.__new__(EventSignInSolver)
    solver.deadline = time.monotonic() + 180
    solver.activity_days = 7
    solver.claimed_days = set()
    solver.attempted_days = set()
    solver.swipe_noinertia = Mock()
    solver.tap = Mock()
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(rapidocr, "engine", local_ocr)
    pages = []
    for side in ("right", "left"):
        solver.recog = SimpleNamespace(
            img=frame(f"seven_day_four_claimed_{side}"),
            check_announcement=lambda: (1800, 150),
        )
        page = solver._panel_states()
        assert page is not None
        assert (page.progress.total_days, page.progress.unlocked_days) == (7, 4)
        pages.append(page)
    before, after = pages
    assert before.first_day == 4
    assert [(card.day, card.claimed) for card in before.cards] == [
        (4, True),
        (5, False),
        (6, False),
        (7, False),
    ]
    assert after.first_day is None
    assert len(after.cards) == 4
    assert all(card.day is None and card.claimed for card in after.cards)
    solver._wait_panel = Mock(return_value=after)

    assert solver._collect_activity(before) is True

    assert solver.swipe_noinertia.call_count == 1
    solver.tap.assert_not_called()
    assert solver.claimed_days == set()
    assert solver.attempted_days == set()


def test_real_claimed_six_day_prefix_keeps_overlap_despite_card_crop_rounding(
    local_ocr, monkeypatch
):
    from arknights_mower.solvers import event_sign_in as sign_in
    from arknights_mower.utils import config

    solver = object.__new__(sign_in.EventSignInSolver)
    solver.deadline = time.monotonic() + 180
    solver.activity_days = 7
    solver.claimed_days = set()
    solver.attempted_days = set()
    solver.swipe_noinertia = Mock()
    solver.tap = Mock()
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(rapidocr, "engine", local_ocr)
    # 回放 2026-10-29 15:04:40、15:04:43 的奖励卡片；日志已确认七日进度。
    # 归档 JPEG 的进度圆点不能稳定重放，本测试只隔离该输入，保留真实 OCR 和翻页判断。
    progress = Progress(
        7,
        6,
        tuple((x, 248) for x in (696, 874, 1050, 1226, 1404, 1580, 1756)),
        ((661, 343), (1806, 718)),
        ((661, 343), (1806, 918)),
        510,
        1.0,
    )
    monkeypatch.setattr(sign_in, "detect_progress", lambda _: progress)
    pages = []
    for side in ("right", "left"):
        crop = cv2.cvtColor(
            cv2.imdecode(
                np.fromfile(
                    FIXTURES / f"seven_day_six_claimed_{side}_20261029.png", np.uint8
                ),
                cv2.IMREAD_COLOR,
            ),
            cv2.COLOR_BGR2RGB,
        )
        image = np.zeros((1080, 1920, 3), np.uint8)
        image[343:918, 661:1806] = crop
        solver.recog = SimpleNamespace(
            img=image, check_announcement=lambda: (1875, 152)
        )
        page = solver._panel_states()
        assert page is not None
        pages.append(page)
    before, after = pages
    assert before.first_day == 4
    assert [(card.day, card.claimed) for card in before.cards] == [
        (4, True),
        (5, True),
        (6, True),
        (7, False),
    ]
    assert after.first_day is None
    assert len(after.cards) == 4
    assert all(card.day is None and card.claimed for card in after.cards)
    solver._wait_panel = Mock(side_effect=[after, before])

    assert solver._collect_activity(before) is True

    assert solver.swipe_noinertia.call_count == 2
    solver.tap.assert_not_called()
    assert solver.claimed_days == set()
    assert solver.attempted_days == set()
