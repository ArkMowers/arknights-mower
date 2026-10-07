"""Low-rarity goals follow resource phases without inventing mastery or modules."""

import json

import pytest

from arknights_mower.tests.growth_planning_tests import (
    counts,
)
from arknights_mower.tests.growth_planning_tests import (
    growth_case as growth_case,
)
from arknights_mower.utils import growth, mastery_recommendation
from arknights_mower.utils.operator_statistics import personal_statistics


@pytest.fixture
def low_case(growth_case):
    box, skills = growth_case
    definition = skills["growth"]["characters"]["char_test"]
    definition.update(rarity=3, modules=[])
    definition["phases"] = definition["phases"][:2]
    definition["phases"][1]["max_level"] = 55
    definition["basic_skill_requirements"] = [{"elite": 1, "level": 1}] * 6
    skills["characters"] = {}
    return box, skills


def test_three_star_skill_seven_promotes_only_to_elite_one(low_case):
    box, skills = low_case
    goals = [{"char_id": "char_test", "module_id": "skill7"}]
    assert counts(growth.material_entries(box, skills, [], goals)) == {
        "book": 3,
        "small": 2,
        "4001": 25,
        "growth_exp": 100,
    }
    goals.append({"char_id": "char_test", "module_id": "elite1"})
    assert counts(growth.material_entries(box, skills, [], goals))["4001"] == 25
    goals[-1]["module_id"] = "level_max"
    total = counts(growth.material_entries(box, skills, [], goals))
    assert total == {"book": 3, "small": 2, "4001": 565, "growth_exp": 5500}
    assert "3213" not in total


@pytest.mark.parametrize("rarity", [1, 2])
def test_one_two_star_level_max_requires_only_level_resources(low_case, rarity):
    box, skills = low_case
    definition = skills["growth"]["characters"]["char_test"]
    definition.update(rarity=rarity, basic_skills=[], basic_skill_requirements=[])
    definition["phases"] = [{"max_level": 30, "materials": []}]
    goals = [{"char_id": "char_test", "module_id": "level_max"}]
    assert counts(growth.material_entries(box, skills, [], goals)) == {
        "4001": 290,
        "growth_exp": 2900,
    }
    with pytest.raises(ValueError, match="不支持基础技能"):
        growth.material_entries(
            box, skills, [], [{"char_id": "char_test", "module_id": "skill7"}]
        )


def test_low_star_goal_validation_and_level_exclusivity(
    low_case, tmp_path, monkeypatch
):
    box, skills = low_case
    monkeypatch.setattr(growth, "get_path", lambda _: tmp_path / "goals.json")
    for invalid in ["elite2", "elite2_max", "elite2_module", "module"]:
        with pytest.raises(ValueError):
            growth.set_goal("char_test", invalid, True, box, skills)
    growth.set_goal("char_test", "elite1", True, box, skills)
    growth.set_goal("char_test", "skill7", True, box, skills)
    goals = growth.set_goal("char_test", "level_max", True, box, skills)
    assert {g["module_id"] for g in goals} == {"level_max", "skill7"}


def test_standalone_basic_skill_and_mastery_count_shared_cost_once(growth_case):
    box, skills = growth_case
    plans = [{"char_id": "char_test", "skill_index": 0, "target_level": 1}]
    goals = [{"char_id": "char_test", "module_id": "skill7"}]
    assert counts(growth.material_entries(box, skills, plans, goals)) == counts(
        growth.material_entries(box, skills, plans)
    )


def test_low_rarity_recommendation_lists_real_goals_without_mastery(
    low_case, tmp_path, monkeypatch
):
    box, skills = low_case
    path = tmp_path / "cultivate.json"
    path.write_text(json.dumps({"data": box}))
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: path)
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: skills)
    monkeypatch.setattr(growth, "inventory_counts", lambda *a, **k: {})
    monkeypatch.setattr(growth, "load_goals", lambda: [])
    monkeypatch.setattr(growth, "statistics_history", lambda: [])
    op = mastery_recommendation.get_mastery_recommendations()["operators"][0]
    assert op["recommendations"] == op["modules"] == []
    assert op["mastery_error"] is None
    assert op["max_phase"] == 1 and op["max_level"] == 55
    assert [(g["id"], g["elite"], g["level"]) for g in op["level_goals"]] == [
        ("elite1", 1, 1),
        ("level_max", 1, 55),
    ]
    assert op["supports_basic_skill7"]
    assert op["basic_skill_prerequisite"] == {"elite": 1, "level": 1}
    assert op["basic_skill_summary"] is not None
    box["characters"][0]["skills"] = [{}]
    path.write_text(json.dumps({"data": box}))
    assert mastery_recommendation.get_mastery_recommendations()["operators"][0][
        "skill_levels"
    ] == [None]


@pytest.mark.parametrize("rarity,phase,maximum", [(1, 0, 30), (2, 0, 30), (3, 1, 55)])
def test_statistics_include_real_low_star_maxima_and_costs(
    low_case, rarity, phase, maximum
):
    box, skills = low_case
    char = box["characters"][0]
    definition = skills["growth"]["characters"][char["id"]]
    definition["rarity"] = rarity
    definition["phases"] = definition["phases"][: phase + 1]
    definition["phases"][-1]["max_level"] = maximum
    if rarity < 3:
        definition["basic_skills"] = []
    char.update(evolvePhase=phase, level=maximum, mainSkillLevel=1, skills=[])
    row = personal_statistics([char], skills)["rarities"][str(rarity)]
    assert row["owned"] == row["available"] == row["max_level"] == 1
    assert row["elite2"] == row["module_level"] == 0
    assert row["max_phase"] == phase and row["max_level_limit"] == maximum
    assert not row["supports_mastery"] and not row["supports_modules"]
    assert row["consumed_exp"] > 0 and row["consumed_lmd"] > 0
    assert row["ranking"][0]["sanity"] == row["sanity"] > 0
    assert not row["incomplete"]
    cached = growth.statistics([char], skills)[str(rarity)]
    assert cached["max_level"] == 1 and cached["consumed_exp"] == row["consumed_exp"]
