"""Workshop defaults share eligible workers with bonuses at or below 80%."""

import pytest

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.tests.workshop_fixtures import owned, recipe
from arknights_mower.utils import workshop_recommendation as workshop


@pytest.mark.parametrize(
    "name,minimum,books",
    [("安赛尔", 75, []), ("凯尔希", 70, ["凯尔希"]), ("巡林者", 60, ["巡林者"])],
)
def test_owned_low_bonus_workers_fill_every_matching_category(
    game, name, minimum, books
):
    metadata, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, name), metadata, min_bonus=minimum
    )
    assert result["defaults"] == {
        "fodder_operators": [name],
        "t5_operators": [name],
        "book_operators": books,
    }


@pytest.mark.parametrize("minimum", [76, 80])
def test_cross_category_selection_still_requires_the_category_threshold(game, minimum):
    metadata, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, "安赛尔"), metadata, min_bonus=minimum
    )
    assert result["defaults"] == {
        "fodder_operators": [],
        "t5_operators": [],
        "book_operators": [],
    }


@pytest.mark.parametrize(
    "bonus,non_t5,books",
    [
        (1, True, True),
        (50, True, True),
        (75, True, True),
        (80, True, True),
        (81, False, False),
        (90, False, False),
    ],
)
def test_cross_category_bonus_boundary(bonus, non_t5, books):
    name = "测试加工干员"
    metadata = {
        "test_operator": {
            "name": name,
            "groups": [
                [
                    {
                        "elite": 0,
                        "level": 1,
                        "effects": [
                            {
                                "kind": "byproduct",
                                "categories": ["material", "book"],
                                "bonus": bonus,
                            }
                        ],
                    }
                ]
            ],
        }
    }
    result = workshop.recommend_workshop_operators(
        [{"id": "test_operator", "evolvePhase": 0, "level": 1}],
        metadata,
        {
            "聚酸酯块": recipe(4),
            "双极纳米片": recipe(8),
            "技巧概要·卷3": recipe(2, "技巧概要"),
        },
        plan={},
        min_bonus=bonus,
    )
    assert result["defaults"] == {
        "fodder_operators": [name] if non_t5 else [],
        "t5_operators": [name],
        "book_operators": [name] if books else [],
    }


@pytest.mark.parametrize("name,elite", [("莱伊", 0), ("缇缇", 1)])
def test_low_bonus_workers_keep_their_material_scope(game, name, elite):
    metadata, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, name, elite=elite),
        metadata,
        {"聚酸酯块": recipe(4), "双极纳米片": recipe(8)},
        min_bonus=75,
    )
    assert result["defaults"] == {
        "fodder_operators": [],
        "t5_operators": [name],
        "book_operators": [],
    }
