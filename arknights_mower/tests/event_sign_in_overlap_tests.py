"""Replay archived reward regions through the sign-in paging workflow."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.event_sign_in import EventSignInSolver, Page
from arknights_mower.solvers.event_sign_in_recognition import Card, Progress


@pytest.mark.parametrize(
    "direction,overlap,narrow",
    [(-1, True, False), (1, True, False), (-1, False, False), (-1, False, True)],
)
def test_claimed_card_overlap_survives_receipt_and_numeral_grid_rounding(
    direction, overlap, narrow
):
    fixtures = Path(__file__).parent / "fixtures/event_sign_in"
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
        image[714:898, 661:1806] = cv2.cvtColor(
            cv2.imread(str(fixtures / name)), cv2.COLOR_BGR2RGB
        )
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
