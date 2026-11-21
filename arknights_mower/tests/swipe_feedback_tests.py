"""快速手势兼容，慢速参数只作用于显式重试。"""

import pytest

from arknights_mower.utils.swipe import noinertia_path


@pytest.mark.parametrize(
    "movement,expected",
    [
        ((-860, 0), [(1490, 488), (1490, 588), (630, 588), (630, 488)]),
        ((0, -860), [(1490, 488), (1590, 488), (1590, -372), (1490, -372)]),
    ],
)
def test_fast_gesture_keeps_1050_path_and_timing(movement, expected):
    points, durations = noinertia_path((1490, 488), movement)
    assert points == expected
    assert durations == [200, 172, 200]


def test_short_retry_is_slower_than_initial_full_page_without_changing_path():
    _, fast = noinertia_path((1490, 488), (-860, 0))
    points, _ = noinertia_path((1490, 488), (-215, 0))
    retry_points, slow = noinertia_path((1490, 488), (-215, 0), retry=True)
    assert retry_points == points
    assert slow == [200, 400, 200]
    assert slow[1] > fast[1]
    assert noinertia_path((1490, 488), (-860, 0))[1] == fast


def test_retry_preserves_explicit_longer_duration():
    assert noinertia_path((100, 100), (1000, 0), 200, retry=True)[1] == [200, 2000, 200]


def test_explicit_normal_duration_is_not_replaced_by_retry_minimum():
    assert noinertia_path((100, 100), (100, 0), 50)[1] == [200, 50, 200]
