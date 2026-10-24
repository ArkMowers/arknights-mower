"""Personal statistics distinguish observed ownership, catalog size and costs."""

import copy

from arknights_mower.tests.growth_value_tests import valuation_case as valuation_case
from arknights_mower.utils.operator_statistics import personal_statistics


def test_observed_levels_are_exclusive_and_default_modules_do_not_count(valuation_case):
    char, _, data, skills, catalog = valuation_case
    skills["growth"] = data
    char["skills"] = [{"id": "skill", "level": 3}, {"level": 1}, {"level": 0}]
    char["equips"].append({"id": "uniequip_001_test", "level": 1})
    row = personal_statistics([char], skills, catalog)["rarities"]["6"]
    assert row["owned"] == row["available"] == row["elite2"] == 1
    assert row["skills"] == {"1": 1, "2": 0, "3": 1}
    assert row["modules"] == {"1": 0, "2": 1, "3": 0}
    assert row["max_level"] == row["module_level"] == 0


def test_catalog_denominator_is_independent_of_ownership_and_includes_low_rarity(
    valuation_case,
):
    char, definition, data, skills, catalog = valuation_case
    skills["growth"] = data
    data["characters"]["char_unowned"] = copy.deepcopy(definition)
    data["characters"]["char_three"] = {**definition, "rarity": 3}
    third = {**char, "id": "char_three"}
    result = personal_statistics([char, third], skills, catalog)
    assert set(result["rarities"]) == {"6", "5", "4", "3", "2", "1"}
    assert result["rarities"]["6"]["owned"] == 1
    assert result["rarities"]["6"]["available"] == 2
    assert result["rarities"]["3"]["owned"] == 1
    assert result["rarities"]["3"]["available"] == 1


def test_shared_forms_merge_ranking_and_owned_but_preserve_independent_skills(
    valuation_case,
):
    char, definition, data, skills, catalog = valuation_case
    skills["growth"] = data
    alternate = copy.deepcopy(char)
    alternate.update(id="char_form", equips=[])
    data["characters"]["char_form"] = {**definition, "progression_owner": "char_test"}
    skills["characters"]["char_form"] = skills["characters"]["char_test"]
    row = personal_statistics([alternate, char, char], skills, catalog)["rarities"]["6"]
    assert row["owned"] == row["available"] == row["elite2"] == 1
    assert row["skills"]["2"] == 2
    assert len(row["ranking"]) == 1
    assert row["ranking"][0]["forms"] == ["char_test", "char_form"]
    assert row["ranking"][0]["sanity"] == row["sanity"] == 251.5
    assert row["consumed_lmd"] == 105
    assert row["consumed_exp"] == 300
    assert row["module_blocks"] == 4


def test_material_totals_and_ranking_exclude_unknown_prices_but_report_them(
    valuation_case,
):
    char, _, data, skills, catalog = valuation_case
    skills["growth"] = data
    row = personal_statistics([char], skills, catalog)["rarities"]["6"]
    assert row["sanity"] == row["ranking"][0]["sanity"] == 197.5
    assert row["skill_book_equivalent"] == 6.67
    unknown = next(
        item for item in row["materials"] if item["id"] == "mod_update_token_1"
    )
    assert unknown == {
        "id": "mod_update_token_1",
        "name": "数据增补条",
        "count": 20,
        "value": None,
        "sanity": None,
    }
    assert row["ranking"][0]["unpriced"] == ["mod_update_token_1"]
    assert row["unpriced"] == [
        {"id": "mod_update_token_1", "name": "数据增补条", "count": 20}
    ]


def test_empty_roster_preserves_catalog_but_has_no_invented_consumption(valuation_case):
    _, _, data, skills, catalog = valuation_case
    skills["growth"] = data
    row = personal_statistics([], skills, catalog)["rarities"]["6"]
    assert row["available"] == 1
    assert row["owned"] == row["sanity"] == 0
    assert row["materials"] == row["ranking"] == []
