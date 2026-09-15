"""Mastery assistant optimizer regressions."""

from unittest.mock import patch

import pytest

from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    owned as owned,
)
from arknights_mower.tests.mastery_support_fixtures import (
    stat as stat,
)
from arknights_mower.utils import mastery_optimizer as optimizer
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_support_types import StageSpec, TrainingInputs


def test_auto_excludes_dynamic_trainers_but_allows_unskilled_manual(game):
    data, ids = game
    roster = [
        owned(ids[n]) for n in ("能天使", "余", "乌尔比安", "芬", "逻各斯", "艾丽妮")
    ]
    options, _ = support.candidates(
        ids["能天使"], TrainingInputs(roster, data, ({"逻各斯": {"central"}}, 0))
    )
    assert set(options) == {"芬", "艾丽妮"}
    options, _ = support.candidates(
        ids["能天使"],
        TrainingInputs(
            roster, data, ({"能天使": {"dormitory_1"}, "逻各斯": {"central"}}, 0)
        ),
    )
    assert set(options) == {"芬", "艾丽妮"}


def test_continuous_chain_earns_half_but_single_final_stage_does_not(game):
    data, ids = game
    roster = [owned(ids[n]) for n in ("能天使", "假日威龙陈", "W", "艾丽妮", "逻各斯")]
    chain = support.plan_supports(
        ids["能天使"],
        0,
        3,
        inputs=TrainingInputs(roster=roster, metadata=data, schedule=({}, 0)),
    )
    assert not chain["stages"][0]["half_inherited"]
    assert chain["stages"][1]["half_inherited"]
    assert chain["stages"][2]["half_inherited"]
    assert chain["stages"][2]["swap_target"] is None
    for stage in chain["stages"][:-1]:
        assert stage["hours"] - (stage["switch_after"] or 0) >= 310 / 60
    final = support.plan_supports(
        ids["能天使"],
        2,
        3,
        inputs=TrainingInputs(roster=roster, metadata=data, schedule=({}, 0)),
    )
    assert not final["stages"][0]["half_inherited"]
    assert final["stages"][0]["operator"] == "W"
    assert final["hours"] == pytest.approx(24 / 2)


def test_no_reducer_uses_fixed_speed_and_never_schedules_swap(game):
    data, ids = game
    result = support.plan_supports(
        ids["能天使"],
        0,
        3,
        inputs=TrainingInputs(
            roster=[owned(ids[n]) for n in ("能天使", "芬")],
            metadata=data,
            schedule=({}, 5),
        ),
    )
    assert result["hours"] == pytest.approx(48 / 1.1)
    assert all(
        s["swap_target"] is None and not s["half_inherited"] for s in result["stages"]
    )


def test_manual_speed_is_not_an_eligibility_check():
    route = support.stage_route(
        stat("普通教官"),
        stat("速度更快的自选教官", 50),
        StageSpec(2, 16, 0, 10, manual=True),
    )
    assert route["swap_target"] == "速度更快的自选教官"


def test_full_roster_route_search_is_bounded(game):
    data, ids = game
    with patch.object(
        optimizer, "stage_route", wraps=optimizer.stage_route
    ) as calculate:
        support.plan_supports(
            ids["能天使"],
            0,
            3,
            inputs=TrainingInputs(
                roster=[owned(cid) for cid in data], metadata=data, schedule=({}, 5)
            ),
        )
    # Candidate count grows with the roster; route search retains only useful representatives.
    assert 0 < calculate.call_count < 200
