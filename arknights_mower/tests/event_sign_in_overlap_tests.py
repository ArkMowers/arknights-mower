"""Replay archived reward regions through the sign-in paging workflow."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.event_sign_in import EventSignInSolver, Page
from arknights_mower.solvers.event_sign_in_recognition import Card, Progress

FIXTURES = Path(__file__).parent / "fixtures/event_sign_in"


def read_fixture(name):
    image = cv2.imdecode(np.fromfile(FIXTURES / name, np.uint8), cv2.IMREAD_COLOR)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    "direction,overlap,narrow",
    [(-1, True, False), (1, True, False), (-1, False, False), (-1, False, True)],
)
def test_claimed_card_overlap_survives_receipt_and_numeral_grid_rounding(
    direction, overlap, narrow
):
    progress = Progress(
        10, 6, (), ((661, 343), (1806, 718)), ((661, 343), (1806, 918)), 510, 1.0
    )
    pages = []
    for name, first_day, centers, scopes in (
        (
            "overlap_claimed_left_20261106.png",
            1,
            (819, 1098, 1377, 1656),
            ((691, 947), (970, 1226), (1249, 1505), (1528, 1784)),
        ),
        (
            "overlap_claimed_middle_20261106.png",
            4,
            (814, 1094, 1374, 1654),
            ((685, 943), (965, 1223), (1245, 1503), (1525, 1783)),
        ),
    ):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        image[714:898, 661:1806] = read_fixture(name)
        cards = tuple(
            Card(
                None,
                (center, 430),
                first_day + index <= 6,
                ((left, 348), (right, 898)),
            )
            for index, (center, (left, right)) in enumerate(zip(centers, scopes))
        )
        pages.append(Page(progress, cards, image, first_day))
    before, after = pages if direction < 0 else pages[::-1]
    if narrow:
        after = replace(
            after,
            cards=tuple(
                replace(
                    card,
                    scope=((left + 40, top), (right - 40, bottom)),
                )
                for card in after.cards
                for (left, top), (right, bottom) in (card.scope,)
            ),
        )
    elif not overlap:
        after.image[714:898, 685:943] = after.image[714:898, 965:1223]
    solver = object.__new__(EventSignInSolver)
    solver._check_budget = Mock()
    solver.swipe_noinertia = Mock()
    solver._wait_panel = Mock(return_value=after)
    solver.tap = Mock(side_effect=AssertionError("Claimed rewards must not be clicked"))
    solver.attempted_days = set()

    if direction < 0:
        assert solver._collect_activity(before) is overlap
    else:
        moved, changed = solver._move_page(before, direction)
        assert changed is True
        assert moved.first_day == 1
    solver.swipe_noinertia.assert_called_once()
    solver.tap.assert_not_called()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_backward_page_distinguishes_similar_claimed_cards(ambiguous):
    progress = Progress(
        10, 8, (), ((661, 343), (1806, 718)), ((661, 343), (1806, 918)), 510, 1.0
    )
    before_image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    before_image[205:920, 650:1850] = read_fixture(
        "celebration_eight_claimed_right_20261108.png"
    )
    before = Page(
        progress,
        tuple(
            Card(day, (x, 430), day <= 8, ((x - 129, 348), (x + 129, 898)))
            for day, x in enumerate((818, 1098, 1378, 1642), 7)
        ),
        before_image,
        7,
    )
    after_image = np.zeros_like(before_image)
    after_image[348:898, 661:1806] = read_fixture(
        "overlap_claimed_ambiguous_middle_20261108.png"
    )
    if ambiguous:
        after_image[348:898, 963:1219] = after_image[348:898, 1521:1777]
    after = Page(
        progress,
        tuple(
            Card(None, (x, 430), True, ((x - 128, 348), (x + 128, 898)))
            for x in (812, 1091, 1370, 1649)
        ),
        after_image,
    )
    solver = object.__new__(EventSignInSolver)
    solver.swipe_noinertia = Mock()
    solver._wait_panel = Mock(return_value=after)

    result = solver._move_page(before, 1)

    if ambiguous:
        assert result is None
    else:
        assert result is not None
        moved, changed = result
        assert changed is True
        assert moved.first_day == 4
    solver.swipe_noinertia.assert_called_once()
