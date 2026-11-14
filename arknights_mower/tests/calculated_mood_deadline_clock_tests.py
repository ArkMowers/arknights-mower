"""期限缓存区分预测起点，同刻的干员与排班查询仍共用结果。"""

from datetime import timedelta
from unittest.mock import patch

import pytest

from arknights_mower.tests.calculated_mood_facility_levels_tests import NOW
from arknights_mower.tests.calculated_mood_facility_levels_tests import owner as owner


def test_future_start_can_reach_target_after_earlier_short_horizon_cached_none(owner):
    projected = owner().project_arrangements([], now=NOW)
    future = NOW + timedelta(hours=1)

    assert projected.calculated_mood_deadline("芬", 24, NOW, max_hours=1) is None
    assert projected.calculated_mood_deadline(
        "芬", 24, future, max_hours=1
    ) == NOW + timedelta(hours=2)
    assert projected.calculated_mood_deadline("芬", 24, NOW, max_hours=1) is None


@pytest.mark.parametrize("operator_first", [False, True])
def test_owner_and_operator_share_only_same_time_deadline_results(
    owner, operator_first
):
    source = owner()
    source.operators["芬"].current_room = "room_1_1"
    source.operators["芬"].current_index = 0
    projected = source.project_arrangements([], now=NOW)
    operator = projected.operators["芬"]
    deadline = NOW + timedelta(hours=20)

    def query_owner(when):
        assert projected.calculated_mood_deadline("芬", 0, when) == deadline

    def query_operator(when):
        assert operator.predict_exhaust(when) == deadline - timedelta(minutes=30)

    first, second = (
        (query_operator, query_owner)
        if operator_first
        else (query_owner, query_operator)
    )
    with patch.object(
        projected.mood_model, "deadline", wraps=projected.mood_model.deadline
    ) as calculate:
        first(NOW)
        second(NOW)
        assert calculate.call_count == 1

        future = NOW + timedelta(hours=1)
        second(future)
        assert calculate.call_count == 2
        first(future)
        assert calculate.call_count == 2

        first(NOW)
        assert calculate.call_count == 2
