"""Blemishine is an optional T2/T3 worker with free elite-material crafting."""

import pytest

from arknights_mower.data import workshop_formula
from arknights_mower.tests.workshop_fixtures import buff, item, owned
from arknights_mower.tests.workshop_fixtures import empty_schedule as empty_schedule
from arknights_mower.tests.workshop_fixtures import game as game
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import WorkShopItem
from arknights_mower.utils.workshop_limits import batch_delta, batch_limit
from arknights_mower.utils.workshop_recommendation import (
    allocate_workshop_items,
    available_operators,
    recommend_workshop_operators,
    scope_workshop_items,
)
from arknights_mower.utils.workshop_rules import compile_workshop_buff


def test_reference_includes_blemishine_and_caledo_without_forcing_low_bonus_default(
    game,
):
    meta, ids = game
    result = recommend_workshop_operators(owned(ids, "瑕光", "镜匠"), meta)
    references = {
        op["name"]: op for op in result["recommendations"]["fodder_operators"]
    }
    assert references["瑕光"]["material_scope"] == "t2_t3"
    assert references["镜匠"]["material_scope"] == "t4"
    assert set(references["瑕光"]["materials"]) == {
        name
        for name, recipe in workshop_formula.items()
        if recipe["tab"] == "精英材料" and recipe["apCost"] in {1, 2}
    }
    assert "瑕光" not in result["defaults"]["fodder_operators"]


def test_selected_blemishine_stays_first_even_with_higher_bonus_specialists(game):
    meta, ids = game
    names = ["瑕光", "休谟斯", "九色鹿"]
    result = allocate_workshop_items(
        [("fodder_operators", names, [item("糖组"), item("糖聚块")])],
        available=available_operators(owned(ids, *names), meta),
    )
    assert [entry["operator"] for entry in result] == names
    assert result[0]["items"] == [item("糖组")]


def test_old_and_manual_blemishine_rows_only_allow_t2_t3():
    items = [
        item(name)
        for name in ["糖", "糖组", "糖聚块", "双极纳米片", "技巧概要·卷3", "碳素"]
    ]
    scoped = scope_workshop_items("瑕光", items)
    assert [entry["item_names"] for entry in scoped] == [["糖"], ["糖组"]]
    assert len(items) == 6


@pytest.mark.parametrize("name,child,stock", [("糖", "代糖", 109), ("糖组", "糖", 112)])
def test_zero_lmd_allows_blemishine_and_does_not_charge_inventory(
    monkeypatch, name, child, stock
):
    monkeypatch.setattr(config, "conf", config.Conf())
    setting = WorkShopItem(self_upper_limit=3, children_lower_limit=0)
    inventory = {name: 0, child: stock, "龙门币": 0}
    assert (
        batch_limit(name, workshop_formula[name], setting, inventory, operator="瑕光")
        == 3
    )
    assert (
        batch_limit(name, workshop_formula[name], setting, inventory, operator="空爆")
        == 0
    )
    assert batch_delta(name, workshop_formula[name], 3, operator="瑕光") == {
        child: -(stock - 100),
        name: 3,
    }


def test_free_lmd_skill_is_generated_and_shipped_at_elite_zero(game):
    meta, _ = game
    assert compile_workshop_buff(buff("进驻加工站加工精英材料时，减免龙门币消耗")) == [
        {"kind": "free_lmd", "categories": ["material"]}
    ]
    assert meta["char_423_blemsh"]["groups"][0] == [
        {
            "elite": 0,
            "level": 1,
            "effects": [{"kind": "free_lmd", "categories": ["material"]}],
        }
    ]
