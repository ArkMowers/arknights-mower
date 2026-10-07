"""Observed growth valuation is independent of stock and future plans."""

import copy

import pytest

from arknights_mower.utils.growth_data import compile_growth_data
from arknights_mower.utils.growth_value import (
    consumed_materials,
    consumed_statistics,
    price_catalog,
)


@pytest.fixture
def valuation_case():
    definition = {
        "name": "测试干员",
        "rarity": 6,
        "phases": [
            {"max_level": 2, "materials": []},
            {"max_level": 2, "materials": [{"id": "chip", "count": 2}]},
            {"max_level": 90, "materials": [{"id": "dual", "count": 4}]},
        ],
        "basic_skills": [[{"id": "3301", "count": 3}]] * 6,
        "modules": [
            {
                "id": "module",
                "levels": [
                    {"level": 1, "materials": [{"id": "mod_unlock_token", "count": 4}]},
                    {
                        "level": 2,
                        "materials": [{"id": "mod_update_token_1", "count": 20}],
                    },
                    {"level": 3, "materials": [{"id": "3303", "count": 9}]},
                ],
            }
        ],
    }
    data = {
        "characters": {"char_test": definition},
        "experience": [[100] * 90] * 3,
        "level_gold": [[10] * 90] * 3,
        "promotion_gold": [[15, 60]] * 6,
    }
    skills = {
        "characters": {
            "char_test": {
                "skills": [
                    {
                        "skillId": "skill",
                        "levels": [
                            {"materials": [{"id": "3303", "count": count}]}
                            for count in (2, 4, 8)
                        ],
                    }
                ]
            }
        },
        "items": {"mod_update_token_1": {"name": "数据增补条"}},
    }
    char = {
        "id": "char_test",
        "evolvePhase": 2,
        "level": 2,
        "mainSkillLevel": 3,
        "skills": [{"id": "skill", "level": 2}],
        "equips": [{"id": "module", "level": 2}, {"id": "module", "level": 1}],
    }
    catalog = {
        "_meta": {"retrieved_at": "2026-10-07"},
        "items": {
            iid: {"value": value}
            for iid, value in {
                "chip": 2,
                "dual": 10,
                "4001": 0.1,
                "2003": 10,
                "3301": 1,
                "3303": 9,
                "mod_unlock_token": 20,
            }.items()
        },
    }
    return char, definition, data, skills, catalog


def test_completed_costs_include_only_paid_stages_and_deduplicate_module(
    valuation_case,
):
    char, definition, data, skills, _ = valuation_case
    costs, blocks, incomplete = consumed_materials(char, definition, data, skills)
    assert costs == {
        "chip": 2,
        "dual": 4,
        "4001": 105,
        "growth_exp": 300,
        "3301": 6,
        "3303": 6,
        "mod_unlock_token": 4,
        "mod_update_token_1": 20,
    }
    assert blocks == 4
    assert incomplete is False


def test_prices_and_unknown_items_are_explicit_and_rarity_scoped(valuation_case):
    char, _, data, skills, catalog = valuation_case
    result = consumed_statistics([char], skills, data, catalog)
    assert result["6"]["sanity_value"] == 197.5
    assert result["6"]["consumed_lmd"] == 105
    assert result["6"]["consumed_exp"] == 300
    assert result["6"]["sanity_unpriced"] == [
        {"id": "mod_update_token_1", "name": "数据增补条", "count": 20}
    ]
    assert result["6"]["skill_book_equivalent"] == 6.67
    assert result["6"]["module_blocks"] == 4
    assert result["5"]["sanity_value"] == 0
    assert result["5"]["sanity_unpriced"] == []


def test_shared_forms_count_level_promotion_basic_once_but_mastery_separately(
    valuation_case,
):
    char, definition, data, skills, catalog = valuation_case
    alternate = copy.deepcopy(char)
    alternate.update(id="char_form", equips=[])
    data["characters"]["char_form"] = {**definition, "progression_owner": "char_test"}
    skills["characters"]["char_form"] = skills["characters"]["char_test"]
    result = consumed_statistics([alternate, char, char], skills, data, catalog)
    assert result["6"]["sanity_value"] == 197.5 + 54
    assert result["6"]["module_blocks"] == 4


def test_missing_level_or_module_cost_reports_partial_coverage(valuation_case):
    char, definition, data, skills, catalog = valuation_case
    char.pop("mainSkillLevel")
    definition["modules"][0]["levels"] = definition["modules"][0]["levels"][:1]
    result = consumed_statistics([char], skills, data, catalog)
    assert result["6"]["sanity_incomplete"] == ["测试干员"]


def test_integrated_strategy_unlocks_do_not_invent_depot_costs(valuation_case):
    char, definition, data, skills, catalog = valuation_case
    definition["integrated_strategy"] = True
    row = consumed_statistics([char], skills, data, catalog)["6"]
    assert row["sanity_value"] == 0
    assert row["skill_book_equivalent"] == 0
    assert row["module_blocks"] == 0
    assert row["sanity_incomplete"] == []


def test_offline_snapshot_has_immutable_source_and_documented_currency_values():
    catalog = price_catalog()
    assert catalog["_meta"]["commit"] in catalog["_meta"]["values_url"]
    values = {iid: row["value"] for iid, row in catalog["items"].items()}
    assert values["4001"] == pytest.approx(36 / 10000)
    assert values["4006"] == pytest.approx(30 * (1 - 12 * values["4001"]) / 21)
    assert values["32001"] == pytest.approx(values["4006"] * 90)
    assert values["mod_unlock_token"] == pytest.approx(values["4006"] * 120)
    assert "mod_update_token_1" not in values


def test_compiler_preserves_all_module_levels_and_shared_progression():
    char = {
        "name": "测试",
        "rarity": "TIER_5",
        "profession": "MEDIC",
        "subProfessionId": "medic",
        "phases": [],
    }
    module = {
        "charId": "char_form",
        "itemCost": {
            "1": [{"id": "a", "count": 1}],
            "2": [{"id": "b", "count": 2}],
            "3": [],
        },
        "uniEquipName": "模组",
        "unlockEvolvePhase": "PHASE_2",
        "unlockLevel": 50,
    }
    result = compile_growth_data(
        {"char_base": char, "char_form": char},
        {"equipDict": {"mod": module}},
        {"characterExpMap": [], "characterUpgradeCostMap": [], "evolveGoldCost": []},
        {"char_base": {"tmplIds": ["char_base", "char_form"]}},
    )
    definition = result["characters"]["char_form"]
    assert definition["progression_owner"] == "char_base"
    assert definition["modules"][0]["levels"][1] == {
        "level": 2,
        "materials": [{"id": "b", "count": 2}],
    }
