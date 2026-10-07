"""Growth targets share prerequisites and cannot bypass actual training readiness."""

import copy
import json
from collections import Counter

import pytest

from arknights_mower.utils import growth
from arknights_mower.utils.growth_farming import chip_farming_plan
from arknights_mower.utils.growth_workshop import next_recipe


@pytest.fixture
def growth_case():
    definition = {
        "name": "测试干员",
        "rarity": 6,
        "phases": [
            {"max_level": 2, "materials": []},
            {"max_level": 2, "materials": [{"id": "small", "count": 2}]},
            {"max_level": 90, "materials": [{"id": "3213", "count": 4}]},
        ],
        "basic_skills": [[{"id": "book", "count": 1}] for _ in range(6)],
        "modules": [
            {
                "id": "module",
                "name": "测试模组",
                "elite": 2,
                "level": 60,
                "materials": [{"id": "t4", "count": 2}],
                "release_at": 0,
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
        "growth": data,
        "characters": {
            "char_test": {
                "skills": [
                    {
                        "levels": [
                            {"materials": [{"id": "t3", "count": n}]} for n in (1, 2, 4)
                        ]
                    }
                    for _ in range(3)
                ]
            }
        },
    }
    char = {
        "id": "char_test",
        "evolvePhase": 0,
        "level": 1,
        "mainSkillLevel": 4,
        "skills": [{"level": 0}],
        "equips": [],
    }
    return {"characters": [char], "items": []}, skills


def counts(entries):
    result = Counter()
    for _, materials in entries:
        for material in materials:
            result[material["id"]] += material["count"]
    return result


def test_unpromoted_and_locked_skills_share_promotion_and_basic_costs(growth_case):
    box, skills = growth_case
    plans = [
        {"char_id": "char_test", "skill_index": i, "target_level": 2} for i in (0, 2)
    ]
    result = counts(growth.material_entries(box, skills, plans))
    assert result == {
        "small": 2,
        "3213": 4,
        "book": 3,
        "t3": 6,
        "4001": 95,
        "growth_exp": 200,
    }


def test_module_raises_level_target_without_repeating_shared_promotion(growth_case):
    box, skills = growth_case
    plans = [{"char_id": "char_test", "skill_index": 0, "target_level": 1}]
    goals = [{"char_id": "char_test", "module_id": mid} for mid in ("elite2", "module")]
    result = counts(growth.material_entries(box, skills, plans, goals))
    assert result["3213"] == 4
    assert result["t4"] == 2
    assert result["growth_exp"] == 6100
    assert result["book"] == 3


def test_open_module_and_completed_target_have_no_remaining_cost(growth_case):
    box, skills = growth_case
    box["characters"][0].update(
        evolvePhase=2,
        level=90,
        equips=[{"id": "module", "level": 2}],
        skills=[{"level": 2}],
    )
    assert not counts(
        growth.material_entries(
            box,
            skills,
            [{"char_id": "char_test", "skill_index": 0, "target_level": 2}],
            [{"char_id": "char_test", "module_id": "module"}],
        )
    )


def test_paid_training_stage_is_not_counted_twice(growth_case):
    box, skills = growth_case
    box["characters"][0].update(evolvePhase=2, level=90, mainSkillLevel=7)
    plan = {
        "char_id": "char_test",
        "skill_index": 0,
        "target_level": 2,
        "status": "training",
        "support_runtime": {"level": 1},
    }
    assert counts(growth.material_entries(box, skills, [plan])) == {"t3": 2}


@pytest.mark.parametrize("target", [0, 4, True, "2"])
def test_invalid_target_is_rejected(growth_case, target):
    box, skills = growth_case
    with pytest.raises(ValueError, match="目标"):
        growth.material_entries(
            box,
            skills,
            [{"char_id": "char_test", "skill_index": 0, "target_level": target}],
        )


def test_dual_chips_catalysts_and_vouchers_use_existing_stock_once():
    demand = [
        {"id": "3213", "count": 4},
        {"id": "3223", "count": 3},
        {"id": "3212", "count": 1},
    ]
    result = {
        m["id"]: m["count"]
        for m in growth.expand_chip_costs(demand, {"3213": 2, "32001": 3})
    }
    assert result == {
        "3213": 4,
        "3223": 3,
        "3212": 5,
        "3222": 6,
        "32001": 5,
        "4006": 180,
    }
    assert growth.expand_chip_costs([{"id": "3213", "count": 2}], {"3213": 2}) == [
        {"id": "3213", "count": 2}
    ]


def test_chips_and_ap5_bind_only_missing_drops_preserving_other_stages():
    plan = [{"weekday": "周一", "stage": ["1-7", "Annihilation"]}]
    rules = {
        "enabled": False,
        "limit_rules": [
            {"stage": "PR-C-2", "operator": "or", "items": []},
            {"stage": "1-7", "items": []},
        ],
        "ratio_rules": [{"members": [{"stage": "PR-C-2"}, {"stage": "1-7"}]}],
    }
    original = copy.deepcopy((plan, rules))
    summary = {
        "materials": [
            {"id": "3212", "name": "先锋芯片组", "required": 8},
            {"id": "4006", "name": "采购凭证", "required": 360},
        ],
        "missing": [{"id": "3212", "count": 4}, {"id": "4006", "count": 90}],
    }
    updated, config, stages = chip_farming_plan(plan, rules, summary)
    assert stages == ["AP-5", "PR-C-2"]
    assert updated[0]["stage"] == ["Annihilation", "AP-5", "PR-C-2", "1-7"]
    assert config["enabled"]
    assert config["limit_rules"][-1]["items"] == [
        {"item_id": "3212", "item_name": "先锋芯片组", "limit": 8}
    ]
    assert config["limit_rules"][-1]["operator"] == "and"
    assert config["ratio_rules"][0]["members"] == [{"stage": "1-7"}]
    assert (plan, rules) == original
    assert chip_farming_plan(updated, config, summary) == (updated, config, stages)


def recipe_data():
    skills = {
        "items": {
            k: {"name": k, "rarity": int(k[-1])} for k in ("t2", "t3", "t4", "t5")
        },
        "composite": {},
    }
    formulas = {
        f"t{i}": {"tab": "精英材料", "costs": {f"t{i - 1}": 2}, "output_count": 1}
        for i in (3, 4, 5)
    }
    return skills, formulas


def test_crafting_only_missing_recipe_then_recalculates_without_refilling():
    skills, formulas = recipe_data()
    entries = [
        ("first", [{"id": "t5", "count": 1}]),
        ("second", [{"id": "t4", "count": 8}]),
    ]
    stock = {"t4": 1, "t3": 2}
    cid, tasks = next_recipe(entries, skills, stock, formulas)
    assert cid == "first"
    assert tasks == [
        {"item_names": ["t4"], "children_lower_limit": 0, "self_upper_limit": 2}
    ]
    stock = {"t4": 2, "t3": 0}
    assert next_recipe(entries, skills, stock, formulas)[1][0]["item_names"] == ["t5"]
    stock = {"t4": 0, "t3": 0, "t5": 1}
    cid, tasks = next_recipe(entries[:1], skills, stock, formulas)
    assert cid is None and tasks == []


def test_completed_operator_stock_is_reserved_for_later_operators():
    skills, formulas = recipe_data()
    entries = [
        ("first", [{"id": "t3", "count": 3}]),
        ("second", [{"id": "t4", "count": 1}]),
    ]
    assert next_recipe(entries, skills, {"t3": 4}, formulas) == ("second", [])


def test_crafting_is_partial_and_never_uses_chip_conversion():
    skills, formulas = recipe_data()
    assert (
        next_recipe([("a", [{"id": "t4", "count": 5}])], skills, {"t3": 3}, formulas)[
            1
        ][0]["self_upper_limit"]
        == 1
    )
    skills["items"]["3212"] = {"name": "3212"}
    formulas["3212"] = {"tab": "芯片", "costs": {"t3": 1}, "output_count": 1}
    assert next_recipe(
        [("a", [{"id": "3212", "count": 5}])], skills, {"t3": 100}, formulas
    ) == (None, [])


def test_statistics_include_completed_operators_and_ignore_default_equipment(
    growth_case,
):
    box, skills = growth_case
    char = box["characters"][0]
    char.update(
        evolvePhase=2,
        level=90,
        skills=[{"level": 1}, {"level": 2}, {"level": 3}],
        equips=[{"id": "module", "level": 1}, {"id": "default", "level": 1}],
    )
    stats = growth.statistics([char], skills)
    assert {key: stats["6"][key] for key in growth.METRICS} == {
        "max_level": 1,
        "module_level": 1,
        "elite2": 1,
        "modules": 1,
        "masteries": 1,
    }
    assert not any(stats["5"][key] for key in growth.METRICS)


def test_history_records_observed_times_only_and_bounds_retention(
    tmp_path, growth_case
):
    box, skills = growth_case
    path = tmp_path / "history.json"
    growth.save_statistics({"data": box}, path, 100, skills)
    assert [r["time"] for r in json.loads(path.read_text())] == [100]
    growth.save_statistics({"data": box}, path, 100, skills)
    assert len(json.loads(path.read_text())) == 1
    growth.save_statistics({"data": box}, path, 200, skills)
    assert [r["time"] for r in json.loads(path.read_text())] == [100, 200]


def test_goal_selection_persists_atomically_and_validates_module(
    tmp_path, growth_case, monkeypatch
):
    box, skills = growth_case
    path = tmp_path / "goals.json"
    monkeypatch.setattr(growth, "get_path", lambda _: path)
    selected = growth.set_goal("char_test", "module", True, box, skills)
    assert growth.load_goals() == selected
    assert growth.set_goal("char_test", "module", True, box, skills) == selected
    with pytest.raises(ValueError):
        growth.set_goal("char_test", "foreign_module", True, box, skills)
    assert growth.load_goals() == selected
    assert growth.set_goal("char_test", "module", False, box, skills) == []


def test_goal_api_and_ap5_binding_use_saved_goals(tmp_path, growth_case, monkeypatch):
    from unittest.mock import MagicMock

    import server
    from arknights_mower.utils import (
        mastery_db,
        mastery_materials,
        mastery_recommendation,
    )
    from arknights_mower.utils.config import weekly_plan_loader

    box, skills = growth_case
    cultivate = tmp_path / "cultivate.json"
    cultivate.write_text(json.dumps({"data": box}))
    monkeypatch.setattr(server.app, "token", "", raising=False)
    monkeypatch.setattr(server, "get_path", lambda _: cultivate)
    monkeypatch.setattr(growth, "get_path", lambda _: tmp_path / "goals.json")
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: skills)
    client = server.app.test_client()
    goal = {"char_id": "char_test", "module_id": "elite2"}
    assert client.post("/growth-plan", json={**goal, "selected": True}).json == {
        "goals": [goal]
    }
    assert client.get("/growth-plan").json == {"goals": [goal]}
    assert (
        client.post("/growth-plan", json={**goal, "selected": "yes"}).status_code == 400
    )
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: [])
    monkeypatch.setattr(mastery_db, "get_failed_plans", lambda: [])
    summary = MagicMock(
        return_value={
            "missing": [{"id": "4006", "count": 80}],
            "materials": [{"id": "4006", "name": "采购凭证", "required": 180}],
        }
    )
    monkeypatch.setattr(mastery_materials, "plan_material_summary", summary)
    manager = MagicMock()
    manager.get_active_plan_key.return_value = "daily"
    manager.get_plan.return_value = [{"stage": ["1-7"], "weekday": "Monday"}]
    manager.get_inventory_config.return_value = {"enabled": False}
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", lambda: manager)
    response = client.post("/growth-chip-farming", json={"stage": "ignored"})
    assert response.status_code == 200 and response.json["stages"] == ["AP-5"]
    summary.assert_called_once_with([], [goal])
    args, kwargs = manager.create_or_update_plan.call_args
    assert args[0] == "daily" and args[1][0]["stage"] == ["AP-5", "1-7"]
    assert kwargs["inventory_config"]["enabled"]
    assert kwargs["inventory_config"]["limit_rules"][0]["items"][0]["limit"] == 180


def test_idle_target_edit_persists_and_rejects_started_plan(tmp_path, monkeypatch):
    from arknights_mower.utils import mastery_db, mastery_recommendation

    path = str(tmp_path / "mastery.db")
    monkeypatch.setattr(
        mastery_recommendation, "get_current_mastery_level", lambda *_: 0
    )
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_requirement_error", lambda *_: "未精二"
    )
    plan_id = mastery_db.insert_plan(
        "char_test", 0, 3, path=path, char_name="测试", skill_name="测试技能"
    )
    mastery_db.change_plan_target(plan_id, 2, path)
    assert mastery_db.get_plan_by_id(plan_id, path)["target_level"] == 2
    with mastery_db._conn(path) as conn:
        conn.execute("UPDATE mastery_plan SET status='training' WHERE id=?", (plan_id,))
        conn.commit()
    with pytest.raises(ValueError, match="已开始"):
        mastery_db.change_plan_target(plan_id, 1, path)
    assert mastery_db.get_plan_by_id(plan_id, path)["target_level"] == 2


@pytest.mark.parametrize("rarity, maximum", [(6, 90), (5, 80), (4, 70)])
def test_max_level_goal_shares_promotion_and_uses_rarity_cap(
    growth_case, rarity, maximum
):
    box, skills = growth_case
    definition = skills["growth"]["characters"]["char_test"]
    definition["rarity"] = rarity
    definition["phases"][2]["max_level"] = maximum
    result = counts(
        growth.material_entries(
            box,
            skills,
            [{"char_id": "char_test", "skill_index": 0, "target_level": 1}],
            [
                {"char_id": "char_test", "module_id": mid}
                for mid in ("elite2", "elite2_max", "module")
            ],
        )
    )
    assert result["growth_exp"] == (maximum + 1) * 100
    assert result["4001"] == (maximum + 1) * 10 + 75
    assert result["3213"] == 4
    assert result["book"] == 3


def test_level_choices_are_mutually_exclusive_in_persistent_goals(
    tmp_path, growth_case, monkeypatch
):
    box, skills = growth_case
    monkeypatch.setattr(growth, "get_path", lambda _: tmp_path / "goals.json")
    for goal in ("elite2", "elite2_max", "elite2_module"):
        goals = growth.set_goal("char_test", goal, True, box, skills)
        assert goals == [{"char_id": "char_test", "module_id": goal}]
    result = counts(growth.material_entries(box, skills, [], goals))
    assert result["growth_exp"] == 6100
    assert "book" not in result


def test_module_upgrade_targets_charge_only_unfinished_levels(growth_case):
    box, skills = growth_case
    module = skills["growth"]["characters"]["char_test"]["modules"][0]
    module["levels"] = [
        {"level": level, "materials": [{"id": "token", "count": level * 2}]}
        for level in (1, 2, 3)
    ]
    box["characters"][0].update(
        evolvePhase=2, level=60, equips=[{"id": "module", "level": 1}]
    )
    goal = {"char_id": "char_test", "module_id": "module"}
    assert counts(growth.material_entries(box, skills, [], [goal])) == {"token": 10}
    assert counts(
        growth.material_entries(box, skills, [], [{**goal, "target_level": 2}])
    ) == {"token": 4}
    assert (
        counts(growth.material_entries(box, skills, [], [{**goal, "target_level": 1}]))
        == {}
    )
    with pytest.raises(ValueError, match="模组等级"):
        growth.material_entries(box, skills, [], [{**goal, "target_level": 4}])


def test_module_target_update_and_remove_use_goal_identity(
    growth_case, tmp_path, monkeypatch
):
    box, skills = growth_case
    module = skills["growth"]["characters"]["char_test"]["modules"][0]
    module["levels"] = [{"level": level, "materials": []} for level in (1, 2, 3)]
    monkeypatch.setattr(growth, "get_path", lambda _: tmp_path / "goals.json")
    args = ("char_test", "module", True, box, skills)
    assert growth.set_goal(*args)[0]["target_level"] == 3
    assert growth.set_goal(*args, target_level=2) == [
        {"char_id": "char_test", "module_id": "module", "target_level": 2}
    ]
    assert growth.set_goal("char_test", "module", False, box, skills) == []
