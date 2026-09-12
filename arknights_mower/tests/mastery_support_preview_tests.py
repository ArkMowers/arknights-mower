"""Mastery assistant preview regressions."""

import pytest

from arknights_mower.tests.mastery_support_fixtures import (
    facility as facility,
)
from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    owned as owned,
)
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_support_types import TrainingInputs


@pytest.mark.parametrize("elite,expected", [(0, []), (1, ["杜宾"] * 3)])
def test_profession_defaults_require_unlocked_training_skill(game, elite, expected):
    data, ids = game
    result = support.profession_training_routes(
        {"WARRIOR": "近卫"},
        inputs=TrainingInputs(
            roster=[
                owned(ids["杜宾"], elite),
                owned(ids["阿斯卡纶"]),
                owned(ids["芬"]),
            ],
            metadata=data,
            schedule=({}, 0),
        ),
    )["defaults"]["近卫"]
    assert [s["name"] for s in result["supports"]] == expected
    assert not result["half_off"]
    assert all(not s["swap"] for s in result["supports"])


def test_profession_defaults_exclude_dynamic_skills_and_scheduled_trainers(game):
    data, ids = game
    names = ["余", "乌尔比安", "赤冬", "燧石", "百炼嘉维尔", "杜宾"]
    context = support.schedule_context(
        {
            "plan1": {"room_1_1": facility("赤冬", ["百炼嘉维尔"])},
            "backup_plans": [{"plan": {"dormitory_1": facility("", ["燧石"])}}],
        }
    )
    result = support.profession_training_routes(
        {"WARRIOR": "近卫"},
        inputs=TrainingInputs(
            roster=[owned(ids[n]) for n in names], metadata=data, schedule=context
        ),
    )["defaults"]["近卫"]
    assert [s["name"] for s in result["supports"]] == ["杜宾"] * 3


@pytest.mark.parametrize(
    "name,profession",
    [("仇白", "WARRIOR"), ("提丰", "SNIPER"), ("纯烬艾雅法拉", "MEDIC")],
)
def test_profession_defaults_keep_base_bonus_without_branch_extra(
    game, name, profession
):
    data, ids = game
    result = support.profession_training_routes(
        {profession: "职业"},
        inputs=TrainingInputs(
            roster=[owned(ids[name])], metadata=data, schedule=({}, 5)
        ),
    )["defaults"]["职业"]
    assert [s["efficiency"] for s in result["supports"]] == [30] * 3
    assert all(s["name"] == name and not s["swap"] for s in result["supports"])


def test_profession_defaults_preserve_halving_route(game):
    data, ids = game
    result = support.profession_training_routes(
        {"WARRIOR": "近卫"},
        inputs=TrainingInputs(
            roster=[owned(ids[n]) for n in ["赤冬", "燧石", "百炼嘉维尔", "艾丽妮"]],
            metadata=data,
            schedule=({}, 5),
        ),
    )["defaults"]["近卫"]
    assert result["half_off"]
    assert any(s["swap_name"] == "艾丽妮" for s in result["supports"])
    assert not result["supports"][-1]["swap"]


def test_reference_trainers_keep_original_defaults_and_mark_ownership(game):
    from arknights_mower.solvers.mastery import DEFAULT_ROUTES, PROF_MAP

    data, ids = game
    result = support.profession_reference_trainers(
        DEFAULT_ROUTES,
        PROF_MAP,
        roster=[owned(ids["赤冬"], 1), owned(ids["燧石"])],
        metadata=data,
    )
    for label, stages in result.items():
        for level, trainer in stages.items():
            original = DEFAULT_ROUTES[label][f"level_{level}"]
            assert (trainer["name"], trainer["efficiency"]) == (
                original["operator"],
                original["efficiency"],
            )
    assert result["近卫"][1]["owned"] is True
    assert result["近卫"][1]["unlocked"] is False  # E1 only has the base +30%.
    assert result["近卫"][2]["unlocked"] is True
    assert result["近卫"][3]["owned"] is False


def test_reference_trainers_do_not_infer_unowned_from_missing_roster(game):
    from arknights_mower.solvers.mastery import DEFAULT_ROUTES, PROF_MAP

    data, _ = game
    result = support.profession_reference_trainers(
        DEFAULT_ROUTES, PROF_MAP, roster=None, metadata=data
    )
    assert len(result) == 8
    assert all(
        t["owned"] is None and t["unlocked"] is None
        for stages in result.values()
        for t in stages.values()
    )
