"""Batch mood budgets use unlocked fixed costs, without extra screen recognition."""

import json
from pathlib import Path

import pytest

from arknights_mower.utils.workshop_data import unlocked
from arknights_mower.utils.workshop_mood import (
    compile_mood_buff,
    mood_cost,
    operator_mood_rules,
)


@pytest.mark.parametrize(
    "operator,elite,name,tab,original,expected",
    [
        ("缇缇", 0, "聚合剂", "精英材料", 8, 8),
        ("缇缇", 2, "聚合剂", "精英材料", 8, 4),
        ("缇缇", 2, "切削原液", "精英材料", 4, 4),
        ("年", 0, "聚合剂", "精英材料", 8, 10),
        ("年", 0, "技巧概要·卷3", "技巧概要", 2, 2),
        ("泥岩", 0, "提纯源岩", "精英材料", 4, 2),
        ("泥岩", 0, "固源岩", "精英材料", 1, 2),
        ("止颂", 0, "糖组", "精英材料", 2, 4),
        ("止颂", 2, "糖组", "精英材料", 2, 3),
        ("特克诺", 2, "晶体电路", "精英材料", 4, 3),
        ("特克诺", 2, "异铁块", "精英材料", 4, 4),
    ],
)
def test_bundled_costs_and_exact_unlock_phase(
    operator, elite, name, tab, original, expected
):
    data = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())
    meta = next(
        m for m in data["workshop"]["mood_operators"].values() if m["name"] == operator
    )
    effects = unlocked(meta, {"evolvePhase": elite, "level": 1})
    assert mood_cost(name, {"tab": tab, "apCost": original}, effects) == expected


@pytest.mark.parametrize(
    "name,expected",
    [("固源岩", 1), ("固源岩组", 2), ("提纯源岩", 4), ("聚合剂", 8)],
)
def test_default_t2_through_t5_costs_from_recipe_data(name, expected):
    recipes = json.loads(
        (Path(__file__).parents[1] / "data/workshop_formula.json").read_text()
    )
    assert mood_cost(name, recipes[name], []) == expected


@pytest.mark.parametrize(
    "description,name,tab,original,expected",
    [
        (
            "进驻加工站加工任意类材料时，心情消耗为4以上的配方全部除以4心情消耗",
            "聚合剂",
            "精英材料",
            8,
            2,
        ),
        (
            "进驻加工站加工精英材料时，副产品的产出概率提升80%，同时心情消耗为4以上的配方全部-2心情消耗",
            "聚合剂",
            "精英材料",
            8,
            6,
        ),
        (
            "进驻加工站加工技巧概要时，心情消耗为2的配方全部-1心情消耗",
            "技巧概要·卷3",
            "技巧概要",
            2,
            1,
        ),
        (
            "进驻加工站加工异铁组材料时，心情消耗为2的配方全部-1心情消耗",
            "异铁组",
            "精英材料",
            2,
            1,
        ),
        (
            "进驻加工站加工异铁组材料时，心情消耗为2的配方全部-1心情消耗",
            "糖组",
            "精英材料",
            2,
            2,
        ),
    ],
)
def test_cost_rule_generation(description, name, tab, original, expected):
    effects = compile_mood_buff({"roomType": "WORKSHOP", "description": description})
    assert mood_cost(name, {"tab": tab, "apCost": original}, effects) == expected


def test_conditional_refunds_are_not_assumed_in_budget():
    for text in [
        "进驻加工站加工任意类材料时，每2次加工没有产出副产品，则恢复自身一次心情",
        "进驻加工站加工精英材料时，宿舍内每有10名心情12以下的干员时，心情消耗为4的配方心情消耗全部-1",
    ]:
        assert compile_mood_buff({"roomType": "WORKSHOP", "description": text}) == []


def test_missing_box_does_not_assume_reduction(monkeypatch):
    from arknights_mower.utils import workshop_data

    monkeypatch.setattr(workshop_data, "owned_roster", lambda: [])
    rules, known = operator_mood_rules("缇缇")
    assert not known
    assert mood_cost("聚合剂", {"tab": "精英材料", "apCost": 8}, rules, known) == 8
    rules, known = operator_mood_rules("年")
    assert mood_cost("聚合剂", {"tab": "精英材料", "apCost": 8}, rules, known) == 10
