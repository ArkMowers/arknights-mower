"""New operator skills reach the packaged shared mood runtime."""

import pytest

from arknights_mower.utils.calculated_mood import shared_rates


def test_tocka_and_existing_group_recovery_share_one_maximum():
    result = shared_rates(
        {
            "moods": {"冻河": 24, "波卜": 10, "芬": 10},
            "rooms": {"dormitory_1": {"roster": ["冻河", "波卜", "芬"], "level": 5}},
        }
    )
    assert result["rates"]["芬"] == pytest.approx(-4.22)
    assert result["unquantified"] == []


def test_dminon_recycling_reduces_only_personal_mood_cost():
    result = shared_rates(
        {
            "moods": {"国度": 24, "行铃": 24},
            "rooms": {"recycle": {"roster": ["国度", "行铃"], "level": 3}},
            "stages": {"国度": [2, 90], "行铃": [2, 70]},
        }
    )
    assert result["rates"] == pytest.approx({"国度": 0.9, "行铃": 1})
    assert result["unquantified"] == []
