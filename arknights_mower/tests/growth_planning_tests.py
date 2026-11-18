"""Growth targets share prerequisites and cannot bypass actual training readiness."""

import copy
import json
from collections import Counter
from threading import Event

import pytest

from arknights_mower.utils import growth
from arknights_mower.utils.growth_farming import next_chip_farming_target
from arknights_mower.utils.growth_workshop import next_recipe

pytestmark = pytest.mark.usefixtures("income_db")


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


def test_goal_write_uses_current_instance_config(growth_case, tmp_path, monkeypatch):
    from arknights_mower.utils import path

    monkeypatch.setattr(path, "_data_dir", tmp_path)
    monkeypatch.setattr(path, "global_space", "first")
    box, skills = growth_case
    growth.set_goal("char_test", "elite1", True, box, skills)
    target = tmp_path / "first/config/growth_plan.json"
    assert json.loads(target.read_text()) == [
        {"char_id": "char_test", "module_id": "elite1"}
    ]
    assert not (tmp_path / "first/tmp/growth_plan.json").exists()
    monkeypatch.setattr(path, "global_space", "second")
    assert growth.load_goals() == []
    assert not (tmp_path / "second/config/growth_plan.json").exists()


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


@pytest.fixture
def chip_farming_case(growth_case):
    box, skills = growth_case
    for char_id, item_id in (("char_peer", "3273"), ("char_same", "3213")):
        box["characters"].append({**box["characters"][0], "id": char_id})
        definition = copy.deepcopy(skills["growth"]["characters"]["char_test"])
        definition["phases"][2]["materials"] = [{"id": item_id, "count": 1}]
        skills["growth"]["characters"][char_id] = definition
    goals = [
        {"char_id": char_id, "module_id": "elite2"}
        for char_id in ("char_peer", "char_same", "char_test")
    ]
    order = ["goal:char_test:elite2", "goal:char_peer:elite2", "goal:char_same:elite2"]
    inventory = dict.fromkeys(("3213", "3273", "3212", "3272", "4006", "32001"), 0)
    return box, growth.growth_resources(skills), goals, order, inventory


def test_chip_farming_uses_saved_order_and_credits_both_professions(chip_farming_case):
    box, skills, goals, order, inventory = chip_farming_case

    def target():
        choice = next_chip_farming_target(box, skills, [], goals, order, inventory)
        if choice is None:
            return None
        return choice.char_id, {
            stage: [(item["item_id"], item["limit"]) for item in rule["items"]]
            for stage, rule in choice.rules.items()
        }

    assert target() == ("char_test", {"AP-5": [("4006", 360)], "PR-C-2": [("3212", 8)]})
    inventory.update({"3212": 7, "3272": 2, "4006": 360})
    assert target() == ("char_test", {"PR-C-2": [("3212", 8)]})
    inventory["3212"] = 8
    assert target() == ("char_peer", {"AP-5": [("4006", 450)]})
    inventory["4006"] = 450
    assert target() == (
        "char_same",
        {"AP-5": [("4006", 540)], "PR-C-2": [("3212", 10)]},
    )
    inventory.update({"3212": 10, "4006": 540})
    assert target() is None
    assert target() is None


def test_chip_farming_never_advances_on_unknown_stock(chip_farming_case):
    box, skills, goals, order, inventory = chip_farming_case
    inventory["3212"] = 8
    inventory["3272"] = 2
    del inventory["4006"]
    assert next_chip_farming_target(box, skills, [], goals, order, inventory) is None
    inventory.update({"4006": 360, "3213": 4})
    inventory.pop("32001")
    assert next_chip_farming_target(box, skills, [], goals, order, inventory) is None
    inventory.update({"32001": 1, "3212": 1})
    assert (
        next_chip_farming_target(box, skills, [], goals, order, inventory).char_id
        == "char_same"
    )


def test_maa_and_local_use_confirmed_stock_to_advance_or_fall_back(
    tmp_path, monkeypatch, chip_farming_case
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils import (
        maa_stage_inventory,
        mastery_db,
        mastery_recommendation,
        path,
    )
    from arknights_mower.utils.config import weekly_plan_loader

    box, skills, goals, order, inventory = chip_farming_case
    box_path = tmp_path / "cultivate.json"
    box_path.write_text(json.dumps({"data": box}))
    monkeypatch.setattr(path, "get_path", lambda _: box_path)
    monkeypatch.setattr(growth, "load_goals", lambda: goals)
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: [])
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: skills)
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: (dict(inventory), None)
    )
    weekly = [
        SimpleNamespace(weekday=weekday, stage=["Annihilation", "1-7"], medicine=0)
        for weekday in ("周一", "周四")
    ]
    conf = base_schedule.config.conf.model_copy(deep=True)
    conf.growth_crafting_order = order
    conf.maa_stage_inventory_enable = False
    conf.maa_weekly_plan = weekly
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = MagicMock()
    solver.MAA.append_task.side_effect = iter(range(1, 25))
    solver.maa_drop_inventory = MagicMock()
    solver.maa_drop_inventory.accumulated.return_value = {"3212": 8, "3272": 2}
    solver.stages = []
    active_plan = "daily"
    growth_settings = {"growth": True}
    manager = SimpleNamespace(
        maybe_switch_expired_activity_plan=MagicMock(),
        get_active_plan_key=lambda: active_plan,
        get_growth_chip_farming=lambda: growth_settings,
    )
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", lambda: manager)

    def assert_fight(day, stages):
        monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: day)
        solver.MAA.append_task.reset_mock()
        solver.append_maa_task("Fight")
        assert [
            (call.args[1]["stage"], call.args[1].get("drops"))
            for call in solver.MAA.append_task.call_args_list
        ] == stages
        local_stages, local_target = solver.mower_stage_plan()
        assert local_stages == [stage for stage, _ in stages]
        return local_target

    assert_fight(0, [("Annihilation", None), ("1-7", None)])
    active_plan = "growth"
    inventory.pop("3212")
    assert_fight(0, [("Annihilation", None), ("1-7", None)])
    inventory["3212"] = 0
    assert_fight(0, [("Annihilation", None), ("AP-5", {"4006": 360})])
    inventory["4006"] = 360
    for _ in range(2):
        assert_fight(0, [("Annihilation", None), ("1-7", None)])
    growth_settings["growth"] = False
    assert_fight(0, [("Annihilation", None), ("PR-C-2", {"3212": 8})])
    growth_settings["growth"] = True
    first = assert_fight(1, [("Annihilation", None), ("PR-C-2", {"3212": 8})])
    last_chip_task = next(reversed(solver.maa_inventory_tasks))

    inventory.update({"3212": 8, "3272": 2})
    solver.refresh_maa_inventory_targets()
    assert any(
        call.args[0] == last_chip_task and call.args[1]["times"] == 0
        for call in solver.MAA.set_task_params.call_args_list
    )
    assert_fight(1, [("Annihilation", None), ("AP-5", {"4006": 90})])
    inventory["4006"] = 540
    third = assert_fight(1, [("Annihilation", None), ("PR-C-2", {"3212": 2})])
    assert first.char_id != third.char_id
    local_stages, _ = solver.mower_stage_plan(
        excluded_stages={"Annihilation"},
        attempted_growth={(first.char_id, "PR-C-2")},
    )
    assert local_stages == ["PR-C-2"]
    local_stages, _ = solver.mower_stage_plan(
        excluded_stages={"Annihilation"},
        attempted_growth={(third.char_id, "PR-C-2")},
    )
    assert local_stages == ["1-7"]
    inventory["3212"] = 10
    assert_fight(1, [("Annihilation", None), ("1-7", None)])
    assert all(day.stage == ["Annihilation", "1-7"] for day in weekly)


def test_local_operation_stops_at_growth_cap_with_manual_limits_disabled(monkeypatch):
    from arknights_mower.solvers import operation

    conf = operation.config.conf.model_copy(deep=True)
    conf.maa_stage_inventory_enable = False
    monkeypatch.setattr(operation.config, "conf", conf)
    monkeypatch.setattr(
        operation, "load_inventory_snapshot", lambda: ({"3212": 8, "3272": 0}, None)
    )
    solver = object.__new__(operation.OperationSolver)
    result = solver.run(
        stage_id="PR-C-2",
        stage_duration_seconds=60,
        inventory_limit_rules=[
            {"stage": "PR-C-2", "items": [{"item_id": "3212", "limit": 8}]}
        ],
    )
    assert result["stopped_by_inventory"]
    assert result["executed_runs"] == 0


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


def test_growth_goal_api_persists_only_valid_goals(tmp_path, growth_case, monkeypatch):
    import server
    from arknights_mower.utils import mastery_recommendation

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


@pytest.mark.parametrize("filter_by_availability", [True, False])
def test_configure_chip_farming_requires_an_explicit_existing_plan(
    tmp_path, monkeypatch, filter_by_availability
):
    from unittest.mock import MagicMock

    import yaml

    import server
    from arknights_mower.utils.config import weekly_plan_loader

    monkeypatch.setattr(server.app, "token", "growth-test-token", raising=False)
    client = server.app.test_client()
    headers = {"token": "growth-test-token"}
    manager = object.__new__(weekly_plan_loader.WeeklyPlanManager)
    path = tmp_path / "weekly_plans.yml"
    plans = {
        "daily": [{"weekday": "周一", "stage": ["CE-6"], "medicine": 2}],
        "growth": [{"weekday": "周一", "stage": ["1-7"]}],
    }
    path.write_text(yaml.safe_dump({"plans": plans}))
    original = path.read_bytes()
    monkeypatch.setattr(manager, "WEEKLY_PLANS_FILE", path)
    monkeypatch.setattr(manager, "_read_state", lambda: {"active_weekly_plan": "daily"})
    write_state = MagicMock()
    monkeypatch.setattr(manager, "_write_state", write_state)
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", lambda: manager)
    payload = {
        "plan_key": "growth",
        "filter_stage_by_availability": filter_by_availability,
    }

    for unauthorized in ({}, {"token": "wrong"}):
        assert (
            client.post(
                "/growth-chip-farming", json=payload, headers=unauthorized
            ).status_code
            == 403
        )
        assert client.get("/weekly-plans", headers=unauthorized).status_code == 403
    for invalid, status in (
        ({}, 400),
        ({"plan_key": "deleted"}, 404),
        ({**payload, "filter_stage_by_availability": "false"}, 400),
        ({**payload, "enabled": "false"}, 400),
    ):
        assert (
            client.post(
                "/growth-chip-farming", json=invalid, headers=headers
            ).status_code
            == status
        )
    assert path.read_bytes() == original

    response = client.post("/growth-chip-farming", json=payload, headers=headers)
    assert response.json == {"plan_key": "growth", "enabled": True}
    assert client.get("/weekly-plans", headers=headers).json["growth_chip_farming"] == {
        "growth": filter_by_availability
    }
    assert {key: manager.get_plan(key) for key in plans} == plans
    assert manager.get_active_plan_key() == "daily"
    assert not manager.get_inventory_config("growth")["enabled"]
    write_state.assert_not_called()

    response = client.post(
        "/growth-chip-farming", json={**payload, "enabled": False}, headers=headers
    )
    assert response.json == {"plan_key": "growth", "enabled": False}
    assert manager.get_growth_chip_farming() == {}
    assert (
        client.post("/growth-chip-farming", json=payload, headers=headers).status_code
        == 200
    )
    assert manager.delete_plan("growth")
    assert manager.get_growth_chip_farming() == {}
    assert "growth_chip_farming" not in yaml.safe_load(path.read_text())


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
    for goal in ("elite1", "elite2", "elite2_max", "elite2_module"):
        goals = growth.set_goal("char_test", goal, True, box, skills)
        assert goals == [{"char_id": "char_test", "module_id": goal}]
    result = counts(growth.material_entries(box, skills, [], goals))
    assert result["growth_exp"] == 6100
    assert "book" not in result


def test_elite_one_goal_for_mastery_capable_operator_stops_before_elite_two(
    tmp_path, growth_case, monkeypatch
):
    box, skills = growth_case
    monkeypatch.setattr(growth, "get_path", lambda _: tmp_path / "goals.json")
    goals = growth.set_goal("char_test", "elite1", True, box, skills)
    assert growth.load_goals() == goals
    assert counts(growth.material_entries(box, skills, [], goals)) == {
        "small": 2,
        "4001": 25,
        "growth_exp": 100,
    }


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


@pytest.mark.parametrize(
    "module_id,target_level,progress,completed",
    [
        ("elite1", None, {"evolvePhase": 1, "level": 1}, True),
        ("elite2", None, {"evolvePhase": 1, "level": 80}, False),
        ("elite2", None, {"evolvePhase": 2, "level": 1}, True),
        ("elite2_module", None, {"evolvePhase": 2, "level": 59}, False),
        ("elite2_module", None, {"evolvePhase": 2, "level": 60}, True),
        ("elite2_max", None, {"evolvePhase": 2, "level": 89}, False),
        ("elite2_max", None, {"evolvePhase": 2, "level": 90}, True),
        ("skill7", None, {"mainSkillLevel": 6}, False),
        ("skill7", None, {"mainSkillLevel": 7}, True),
        ("module", 2, {"equips": [{"id": "module", "level": 1}]}, False),
        ("module", 2, {"equips": [{"id": "module", "level": 2}]}, True),
        ("module", None, {"equips": [{"id": "module", "level": 2}]}, False),
        ("module", None, {"equips": [{"id": "module", "level": 3}]}, True),
        ("unknown", None, {"evolvePhase": 2, "level": 90}, False),
        ("elite1", None, {"evolvePhase": 1, "level": None}, False),
        ("skill7", None, {"mainSkillLevel": None}, False),
        ("module", 2, {"equips": None}, False),
    ],
)
def test_completed_manual_goal_cleanup_preserves_unfinished_and_unknown_targets(
    growth_case, tmp_path, monkeypatch, module_id, target_level, progress, completed
):
    from arknights_mower.solvers import record

    changed = Event()
    monkeypatch.setattr(record, "workshop_inventory_changed", changed)
    box, skills = growth_case
    module = skills["growth"]["characters"]["char_test"]["modules"][0]
    module["levels"] = [{"level": level} for level in (1, 2, 3)]
    box["characters"][0].update(progress)
    goal = {"char_id": "char_test", "module_id": module_id}
    if target_level is not None:
        goal["target_level"] = target_level
    missing = {"char_id": "char_missing", "module_id": "skill7"}
    path = tmp_path / "goals.json"
    path.write_text(json.dumps([goal, missing]))
    monkeypatch.setattr(growth, "get_path", lambda _: path)
    growth.remove_completed_goals(box, skills)
    expected = [missing] if completed else [goal, missing]
    assert growth.load_goals() == expected
    assert changed.is_set() is completed
    changed.clear()
    with monkeypatch.context() as context:
        context.setattr(
            growth,
            "atomic_write",
            lambda *args: pytest.fail("unchanged goals were rewritten"),
        )
        growth.remove_completed_goals(box, skills)
    assert growth.load_goals() == expected
    assert not changed.is_set()


@pytest.mark.parametrize("phase,maximum", [(0, 30), (1, 55)])
def test_low_rarity_level_goal_clears_only_at_maximum(
    growth_case, tmp_path, monkeypatch, phase, maximum
):
    box, skills = growth_case
    definition = skills["growth"]["characters"]["char_test"]
    definition["phases"] = definition["phases"][: phase + 1]
    definition["phases"][phase]["max_level"] = maximum
    char = box["characters"][0]
    char.update(evolvePhase=phase, level=maximum - 1)
    goal = {"char_id": "char_test", "module_id": "level_max"}
    path = tmp_path / "goals.json"
    path.write_text(json.dumps([goal]))
    monkeypatch.setattr(growth, "get_path", lambda _: path)
    growth.remove_completed_goals(box, skills)
    assert growth.load_goals() == [goal]
    char["level"] = maximum
    growth.remove_completed_goals(box, skills)
    assert growth.load_goals() == []


def test_completed_goal_write_failure_keeps_saved_plan(
    growth_case, tmp_path, monkeypatch
):
    from arknights_mower.solvers import record

    changed = Event()
    monkeypatch.setattr(record, "workshop_inventory_changed", changed)
    box, skills = growth_case
    box["characters"][0]["mainSkillLevel"] = 7
    path = tmp_path / "goals.json"
    path.write_text('[{"char_id": "char_test", "module_id": "skill7"}]')
    previous = path.read_bytes()
    monkeypatch.setattr(growth, "get_path", lambda _: path)
    from arknights_mower.utils import config

    def fail_replace(*args):
        raise OSError("write failed")

    monkeypatch.setattr(config.os, "replace", fail_replace)
    with pytest.raises(OSError, match="write failed"):
        growth.remove_completed_goals(box, skills)
    assert path.read_bytes() == previous
    assert not changed.is_set()


@pytest.mark.parametrize("module_id", ["elite2", "module"])
def test_missing_target_resources_never_confirm_goal_completion(
    growth_case, tmp_path, monkeypatch, module_id
):
    box, skills = growth_case
    box["characters"][0].update(
        evolvePhase=2, level=90, equips=[{"id": "module", "level": 3}]
    )
    definition = skills["growth"]["characters"]["char_test"]
    if module_id == "elite2":
        definition["phases"] = []
    else:
        definition["modules"] = [{"id": "module"}]
    goal = {"char_id": "char_test", "module_id": module_id}
    path = tmp_path / "goals.json"
    path.write_text(json.dumps([goal]))
    monkeypatch.setattr(growth, "get_path", lambda _: path)
    growth.remove_completed_goals(box, skills)
    assert growth.load_goals() == [goal]
