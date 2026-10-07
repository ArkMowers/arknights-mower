"""Project priorities preserve training reservations and confirmed stock changes."""

import copy
import json
from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.growth_planning_tests import growth_case as growth_case
from arknights_mower.utils import config, growth, growth_order, mastery_db
from arknights_mower.utils.growth_workshop import growth_workshop_config


@pytest.fixture
def order_case(growth_case, monkeypatch):
    from arknights_mower.utils import workshop_recommendation

    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(workshop_recommendation, "available_operators", lambda: None)
    box, skills = growth_case
    char = box["characters"][0]
    char.update(evolvePhase=2, level=90, mainSkillLevel=7)
    box["characters"].append({**copy.deepcopy(char), "id": "char_next"})
    skills["growth"]["characters"]["char_next"] = copy.deepcopy(
        skills["growth"]["characters"]["char_test"]
    )
    skills["characters"]["char_next"] = copy.deepcopy(skills["characters"]["char_test"])
    for level in skills["characters"]["char_test"]["skills"][1]["levels"]:
        level["materials"] = [{"id": "t4", "count": 1}]
    for level in skills["characters"]["char_next"]["skills"][0]["levels"]:
        level["materials"] = [{"id": "other", "count": 1}]
    skills["items"] = {
        key: {"name": key, "rarity": rarity}
        for key, rarity in [
            ("raw", 2),
            ("t3", 3),
            ("t4", 4),
            ("other", 4),
            ("book", 2),
            ("small", 2),
            ("3213", 5),
            ("4001", 0),
            ("growth_exp", 0),
            ("exclusive", 4),
        ]
    }
    formulas = {
        name: {
            "tab": "技巧概要" if name == "book" else "精英材料",
            "apCost": 2 if name in ("t3", "book", "small") else 4,
            "items": list(costs),
            "costs": costs,
            "output_name": name,
            "output_count": 1,
        }
        for name, costs in {
            "t3": {"raw": 2},
            "t4": {"t3": 2},
            "other": {"raw": 3},
            "book": {"raw": 1},
            "small": {"raw": 1},
        }.items()
    }
    plans = [
        {"char_id": cid, "skill_index": index, "target_level": 1, "status": "idle"}
        for cid, index in [("char_test", 0), ("char_next", 0), ("char_test", 1)]
    ]
    goals = [{"char_id": "char_test", "module_id": "module", "target_level": 1}]
    stock = {"raw": 1000, "4001": 10000, "growth_exp": 10000, "3213": 4}
    return SimpleNamespace(
        box=box,
        skills=skills,
        plans=plans,
        goals=goals,
        stock=stock,
        formulas=formulas,
        operators={
            key: ["空爆"]
            for key in ("fodder_operators", "t5_operators", "book_operators")
        },
    )


def projects(case, order=()):
    return growth_order.crafting_projects(
        case.plans, case.goals, order, box=case.box, skills=case.skills
    )


def prepared(case, order=()):
    return growth_order.prepare_project_materials(
        case.box, case.skills, projects(case, order), case.stock, case.formulas
    )


def generated(case, order=()):
    return growth_workshop_config(
        case.box,
        case.skills,
        case.plans,
        case.goals,
        case.stock,
        case.formulas,
        case.operators,
        order=order,
    )


def recipe(settings):
    return settings[0]["items"][0]


def test_default_finishes_next_skill_before_same_operator_later_skill_or_module(
    order_case,
):
    case = order_case
    settings, cid = generated(case)
    assert cid == "char_test"
    assert recipe(settings)["item_names"] == ["t3"]
    assert recipe(settings)["self_upper_limit"] == 1
    case.stock.update(raw=998, t3=1)
    settings, cid = generated(case)
    assert cid == "char_next"
    assert recipe(settings)["item_names"] == ["other"]
    assert recipe(settings)["self_upper_limit"] == 1


def test_custom_order_can_mix_module_skill_and_level_targets(order_case):
    case = order_case
    case.box["characters"][0].update(evolvePhase=1, level=2)
    case.goals.append({"char_id": "char_test", "module_id": "elite2"})
    custom = [
        "goal:char_test:module",
        "skill:char_next:0",
        "goal:char_test:elite2",
        "skill:char_test:1",
        "skill:char_test:0",
    ]
    assert [p["key"] for p in projects(case, custom)] == custom
    settings, cid = generated(case, custom)
    assert cid == "char_test"
    assert recipe(settings)["item_names"] == ["t3"]
    assert recipe(settings)["self_upper_limit"] == 4


def test_saved_order_keeps_new_projects_at_tail_without_changing_training_priorities(
    order_case,
):
    case = order_case
    for priority, plan in enumerate(case.plans):
        plan["priority"] = priority
    original = copy.deepcopy((case.plans, case.goals))
    custom = ["goal:char_test:module", "skill:char_next:0"]
    assert [p["key"] for p in projects(case, custom)] == [
        *custom,
        "skill:char_test:0",
        "skill:char_test:1",
    ]
    generated(case, custom)
    assert (case.plans, case.goals) == original


@pytest.mark.parametrize(
    "status", ["training", "arranging", "waiting_collect", "material_waiting"]
)
def test_active_training_is_pinned_and_backend_rejects_moving_it(order_case, status):
    case = order_case
    plan = case.plans[1]
    plan.update(target_level=3, status=status, support_runtime={"level": 1})
    if status == "material_waiting":
        plan.update(status="idle", expires_at="2030-01-01", failed_reason="材料不足")
    custom = [
        "goal:char_test:module",
        "skill:char_test:1",
        "skill:char_test:0",
        "skill:char_next:0",
    ]
    rows = projects(case, custom)
    assert rows[0]["key"] == "skill:char_next:0" and rows[0]["locked"]
    with pytest.raises(ValueError, match="固定"):
        growth_order.validate_order(custom, rows)
    accepted = [p["key"] for p in rows]
    assert growth_order.validate_order(accepted, rows) == accepted
    settings, cid = generated(case, custom)
    assert cid == "char_next" and recipe(settings)["item_names"] == ["other"]


@pytest.mark.parametrize("order", [None, {}, [1], [], ["wrong"]])
def test_stale_or_malformed_order_is_rejected(order_case, order):
    with pytest.raises(ValueError):
        growth_order.validate_order(order, projects(order_case))


def test_shortage_skips_entire_project_without_reserving_its_available_ingredients(
    order_case,
):
    case = order_case
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0][
        "materials"
    ].append({"id": "exclusive", "count": 1})
    case.stock["raw"] = 3
    states, entries = prepared(case)
    assert states[0]["status"] == "waiting" and "跳过" in states[0]["reason"]
    assert states[1]["status"] == "ready"
    assert [key for key, _ in entries] == ["skill:char_next:0"]
    settings, cid = generated(case)
    assert cid == "char_next" and recipe(settings)["item_names"] == ["other"]


def test_active_training_shortage_blocks_later_projects(order_case):
    case = order_case
    case.plans[0].update(
        status="training", target_level=2, support_runtime={"level": 1}
    )
    case.skills["characters"]["char_test"]["skills"][0]["levels"][1][
        "materials"
    ].append({"id": "exclusive", "count": 1})
    states, entries = prepared(case)
    assert states[0]["status"] == "active" and "暂停" in states[0]["reason"]
    assert all(row["status"] == "waiting" for row in states[1:])
    assert entries == []
    assert generated(case) == ([], "char_test")


def test_unmet_prerequisites_prepare_first_and_are_shared_between_skills(order_case):
    case = order_case
    case.box["characters"][0].update(evolvePhase=0, level=1, mainSkillLevel=4)
    case.plans[:] = [case.plans[0], case.plans[2]]
    case.goals.clear()
    states, entries = prepared(case)
    assert all(
        p["status"] == "preparing" and "前置未完成" in p["reason"] for p in states
    )
    assert [key for key, _ in entries] == [
        "skill:char_test:0",
        "skill:char_test:0",
        "skill:char_test:1",
    ]
    before = Counter({m["id"]: m["count"] for m in entries[0][1]})
    assert before == {"book": 3, "small": 2, "3213": 4, "4001": 95, "growth_exp": 200}
    total = Counter()
    for _, costs in entries:
        for material in costs:
            total[material["id"]] += material["count"]
    assert total["book"] == 3 and total["3213"] == 4
    settings, _ = generated(case)
    assert recipe(settings)["item_names"] == ["book"]


def test_confirmed_intermediate_consumption_never_refills_previous_quota(order_case):
    case = order_case
    case.plans.clear()
    settings, _ = generated(case)
    assert recipe(settings)["item_names"] == ["t3"]
    assert recipe(settings)["self_upper_limit"] == 4
    case.stock.update(raw=992, t3=4)
    settings, _ = generated(case)
    assert recipe(settings)["item_names"] == ["t4"]
    assert recipe(settings)["self_upper_limit"] == 2
    case.stock.update(t3=0, t4=2)
    assert generated(case) == ([], None)


def test_module_below_unlock_level_can_prepare_without_leveling_exp_or_gold(order_case):
    case = order_case
    case.plans.clear()
    case.box["characters"][0].update(level=1)
    module = case.skills["growth"]["characters"]["char_test"]["modules"][0]
    module["materials"].append({"id": "4001", "count": 50})
    case.stock.update(raw=8, growth_exp=0)
    case.stock["4001"] = 50
    states, entries = prepared(case)
    assert len(states) == 1
    assert states[0]["status"] == "preparing"
    assert "前置未完成" in states[0]["reason"]
    assert not growth_order.prerequisites_ready(case.box, case.skills, states[0])
    assert entries == [
        (
            "goal:char_test:module",
            [{"id": "t4", "count": 2}, {"id": "4001", "count": 50}],
        )
    ]
    settings, cid = generated(case)
    assert cid == "char_test" and recipe(settings)["item_names"] == ["t3"]
    assert recipe(settings)["self_upper_limit"] == 4
    overview = Counter()
    for _, costs in growth.material_entries(case.box, case.skills, [], case.goals):
        for material in costs:
            overview[material["id"]] += material["count"]
    assert overview["growth_exp"] == 5900
    assert overview["4001"] == 640
    case.stock["4001"] = 49
    states, entries = prepared(case)
    assert states[0]["status"] == "waiting" and entries == []


def test_unpromoted_module_prepares_only_through_elite_two_level_one(order_case):
    case = order_case
    case.plans.clear()
    case.box["characters"][0].update(evolvePhase=0, level=1)
    case.stock.update(raw=10, growth_exp=200)
    case.stock["4001"] = 95
    states, entries = prepared(case)
    assert len(states) == 1 and states[0]["status"] == "preparing"
    assert [key for key, _ in entries] == ["goal:char_test:module"] * 2
    assert Counter({row["id"]: row["count"] for row in entries[0][1]}) == {
        "small": 2,
        "3213": 4,
        "4001": 95,
        "growth_exp": 200,
    }
    assert entries[1][1] == [{"id": "t4", "count": 2}]
    settings, _ = generated(case)
    assert recipe(settings)["item_names"] == ["small"]
    overview = growth.material_entries(case.box, case.skills, [], case.goals)
    assert (
        sum(
            row["count"]
            for _, costs in overview
            for row in costs
            if row["id"] == "growth_exp"
        )
        == 6100
    )


@pytest.mark.parametrize(
    "goal,experience", [("elite2_module", 5900), ("elite2_max", 8900)]
)
def test_same_phase_leveling_stays_in_overview_but_never_in_crafting_queue(
    order_case, goal, experience
):
    case = order_case
    case.plans.clear()
    case.goals[:] = [{"char_id": "char_test", "module_id": goal}]
    case.box["characters"][0].update(level=1)
    case.stock.clear()
    assert projects(case) == []
    assert prepared(case) == ([], [])
    assert generated(case) == ([], None)
    overview = growth.material_entries(case.box, case.skills, [], case.goals)
    assert (
        sum(
            row["count"]
            for _, costs in overview
            for row in costs
            if row["id"] == "growth_exp"
        )
        == experience
    )
    assert (
        sum(
            row["count"]
            for _, costs in overview
            for row in costs
            if row["id"] == "4001"
        )
        == experience // 10
    )


@pytest.fixture
def order_api(order_case, monkeypatch, tmp_path):
    import arknights_mower.data as data
    import server
    from arknights_mower.utils import mastery_recommendation, workshop_automation

    case = order_case
    path = tmp_path / "cultivate.json"
    path.write_text(json.dumps({"data": case.box}))
    monkeypatch.setattr(growth_order, "get_path", lambda _: path)
    monkeypatch.setattr(growth, "load_goals", lambda: case.goals)
    monkeypatch.setattr(growth, "growth_resources", lambda skills: skills)
    monkeypatch.setattr(growth, "inventory_counts", lambda *args, **kwargs: case.stock)
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: case.plans)
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: case.skills)
    monkeypatch.setattr(data, "workshop_formula", case.formulas)
    monkeypatch.setattr(server.app, "token", "test-order-token", raising=False)
    save = MagicMock()
    refresh = MagicMock()
    monkeypatch.setattr(config, "save_conf", save)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_plan_change", refresh
    )
    config.conf.workshop_preset_migrated = True
    return SimpleNamespace(
        client=server.app.test_client(),
        headers={"token": "test-order-token"},
        case=case,
        box_path=path,
        save=save,
        refresh=refresh,
    )


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_order_api_requires_authentication_without_mutation(order_api, method):
    api = order_api
    response = getattr(api.client, method)("/growth-crafting-order", json={"order": []})
    assert response.status_code == 403
    assert config.conf.growth_crafting_order == []
    api.save.assert_not_called()
    api.refresh.assert_not_called()


def test_order_api_get_put_delete_and_stale_settings_roundtrip(order_api):
    api = order_api
    response = api.client.get("/growth-crafting-order", headers=api.headers)
    assert response.status_code == 200 and not response.json["custom"]
    keys = [row["key"] for row in response.json["items"]]
    custom = list(reversed(keys))
    old_conf = config.conf.model_dump()
    response = api.client.put(
        "/growth-crafting-order", headers=api.headers, json={"order": custom}
    )
    assert response.status_code == 200 and response.json["custom"]
    assert [row["key"] for row in response.json["items"]] == custom
    assert config.conf.growth_crafting_order == custom
    api.save.assert_called_once()
    api.refresh.assert_called_once()
    response = api.client.post("/conf", headers=api.headers, json=old_conf)
    assert response.status_code == 200
    assert config.conf.growth_crafting_order == custom
    response = api.client.delete("/growth-crafting-order", headers=api.headers)
    assert response.status_code == 200 and not response.json["custom"]
    assert [row["key"] for row in response.json["items"]] == keys
    assert config.conf.growth_crafting_order == []


def test_order_api_save_failure_leaves_runtime_order_unchanged(order_api):
    api = order_api
    previous = config.conf
    api.save.side_effect = OSError("storage unavailable")
    custom = list(reversed([row["key"] for row in projects(api.case)]))
    response = api.client.put(
        "/growth-crafting-order", headers=api.headers, json={"order": custom}
    )
    assert response.status_code == 400
    assert config.conf is previous and config.conf.growth_crafting_order == []
    api.refresh.assert_not_called()


def test_order_api_rejects_moving_locked_plan(order_api):
    api = order_api
    api.case.plans[1].update(status="arranging")
    keys = [row["key"] for row in projects(api.case)]
    response = api.client.put(
        "/growth-crafting-order",
        headers=api.headers,
        json={"order": list(reversed(keys))},
    )
    assert response.status_code == 400 and "固定" in response.json["error"]
    api.save.assert_not_called()
    api.refresh.assert_not_called()


@pytest.mark.parametrize(
    "body", [[], {}, {"order": []}, {"order": ["removed-project"]}]
)
def test_order_api_rejects_malformed_or_stale_project_lists(order_api, body):
    api = order_api
    response = api.client.put("/growth-crafting-order", headers=api.headers, json=body)
    assert response.status_code == 400
    assert config.conf.growth_crafting_order == []
    api.save.assert_not_called()
    api.refresh.assert_not_called()


def test_order_api_omits_same_phase_leveling_and_implicit_prerequisite_projects(
    order_api,
):
    api = order_api
    api.case.plans.clear()
    api.case.goals.append({"char_id": "char_test", "module_id": "elite2_max"})
    api.case.box["characters"][0].update(level=1)
    api.box_path.write_text(json.dumps({"data": api.case.box}))
    response = api.client.get("/growth-crafting-order", headers=api.headers)
    assert response.status_code == 200
    assert [row["key"] for row in response.json["items"]] == ["goal:char_test:module"]
    assert response.json["items"][0]["status"] == "preparing"
    api.case.goals[:] = [api.case.goals[1]]
    response = api.client.get("/growth-crafting-order", headers=api.headers)
    assert response.status_code == 200 and response.json["items"] == []
    api.save.assert_not_called()


def reminders(case):
    states, entries = prepared(case)
    return growth_order.prepared_project_reminders(
        case.box, case.skills, states, entries, case.goals, case.stock, case.formulas
    )


def test_duplicate_idle_row_cannot_hide_confirmed_training_waiting_for_materials(
    order_case,
):
    case = order_case
    waiting = {
        **case.plans[0],
        "id": 2,
        "expires_at": "2030-01-01",
        "failed_reason": "材料不足",
    }
    case.plans.insert(1, waiting)
    rows = projects(case, ["skill:char_next:0", "skill:char_test:0"])
    assert rows[0]["key"] == "skill:char_test:0"
    assert rows[0]["locked"] and rows[0]["plan"] is waiting
    with pytest.raises(ValueError, match="固定"):
        growth_order.validate_order(
            [row["key"] for row in rows[1:]] + [rows[0]["key"]], rows
        )


@pytest.mark.parametrize("goal", ["module", "elite2", "skill7"])
def test_prepared_manual_targets_remind_until_actual_goal_is_complete(order_case, goal):
    case = order_case
    case.plans.clear()
    case.goals[:] = [{"char_id": "char_test", "module_id": goal, "target_level": 1}]
    char = case.box["characters"][0]
    case.stock.update(t4=2, book=1)
    if goal == "elite2":
        char.update(evolvePhase=1, level=2)
    elif goal == "skill7":
        char["mainSkillLevel"] = 6
    states, _ = prepared(case)
    assert states[0]["materials_prepared"]
    ready = reminders(case)
    assert len(ready) == 1 and ready[0]["key"] == f"goal:char_test:{goal}"
    if goal == "module":
        char["equips"] = [{"id": "module", "level": 1}]
    elif goal == "elite2":
        char.update(evolvePhase=2, level=1)
    else:
        char["mainSkillLevel"] = 7
    assert reminders(case) == []


def test_prepared_module_upgrade_reminds_until_selected_module_level(order_case):
    case = order_case
    case.plans.clear()
    module = case.skills["growth"]["characters"]["char_test"]["modules"][0]
    module["levels"] = [
        {"level": level, "materials": [{"id": "t4", "count": level}]}
        for level in (1, 2, 3)
    ]
    case.goals[0]["target_level"] = 2
    case.box["characters"][0]["equips"] = [{"id": "module", "level": 1}]
    case.stock["t4"] = 2
    assert [row["key"] for row in reminders(case)] == ["goal:char_test:module"]
    case.box["characters"][0]["equips"][0]["level"] = 2
    assert reminders(case) == []


def test_prepared_skill_only_reminds_when_actual_prerequisites_are_unfinished(
    order_case,
):
    case = order_case
    case.plans[:] = [case.plans[0]]
    case.goals.clear()
    case.stock.update(t3=1, book=1)
    assert prepared(case)[0][0]["materials_prepared"]
    assert reminders(case) == []
    case.box["characters"][0]["mainSkillLevel"] = 6
    assert [row["key"] for row in reminders(case)] == ["skill:char_test:0"]
    case.box["characters"][0]["skills"][0]["level"] = 1
    assert reminders(case) == []


@pytest.mark.parametrize(
    "status", ["training", "arranging", "waiting_collect", "material_waiting"]
)
def test_protected_training_never_emits_manual_prepared_reminder(order_case, status):
    case = order_case
    case.plans[:] = [case.plans[0]]
    case.goals.clear()
    case.plans[0].update(status=status, target_level=2, support_runtime={"level": 1})
    if status == "material_waiting":
        case.plans[0].update(
            status="idle", expires_at="2030-01-01", failed_reason="材料不足"
        )
    case.box["characters"][0]["mainSkillLevel"] = 6
    case.stock.update(t3=20, book=1)
    assert prepared(case)[0][0]["materials_prepared"]
    assert reminders(case) == []


def test_only_craftable_module_does_not_claim_its_materials_are_prepared(order_case):
    case = order_case
    case.plans.clear()
    states, _ = prepared(case)
    assert states[0]["status"] == "ready" and not states[0]["materials_prepared"]
    assert reminders(case) == []
    case.stock["t4"] = 2
    assert prepared(case)[0][0]["materials_prepared"]
    assert len(reminders(case)) == 1


def test_manual_chip_conversion_is_not_counted_as_prepared_final_material(order_case):
    case = order_case
    case.plans.clear()
    case.goals[:] = [{"char_id": "char_test", "module_id": "elite2"}]
    case.box["characters"][0].update(evolvePhase=1, level=2)
    case.stock.update({"3213": 0, "3212": 8, "32001": 4})
    states, _ = prepared(case)
    assert states[0]["status"] == "ready" and not states[0]["materials_prepared"]
    assert reminders(case) == []
    case.stock["3213"] = 4
    assert len(reminders(case)) == 1


def test_two_modules_cannot_both_claim_the_same_prepared_materials(order_case):
    case = order_case
    case.plans.clear()
    case.goals.append(
        {"char_id": "char_next", "module_id": "module", "target_level": 1}
    )
    case.stock.update(raw=0, t4=2)
    states, _ = prepared(case)
    assert [row["materials_prepared"] for row in states] == [True, False]
    assert [row["key"] for row in reminders(case)] == ["goal:char_test:module"]


def test_pure_level_targets_reserve_experience_and_gold_only_once(order_case):
    case = order_case
    case.plans.clear()
    case.goals[:] = [
        {"char_id": cid, "module_id": "elite2_max"}
        for cid in ("char_test", "char_next")
    ]
    for char in case.box["characters"]:
        char["level"] = 1
    case.stock.update({"growth_exp": 8900, "4001": 890})
    assert projects(case) == []
    assert [row["key"] for row in reminders(case)] == ["goal:char_test:elite2_max"]
    case.box["characters"][0]["level"] = 90
    assert [row["key"] for row in reminders(case)] == ["goal:char_next:elite2_max"]


@pytest.mark.parametrize("gold", [1029, 1030])
def test_level_reminder_waits_for_accepted_module_crafting_to_finish(order_case, gold):
    case = order_case
    case.plans.clear()
    case.box["characters"][0]["level"] = 1
    case.goals.append({"char_id": "char_test", "module_id": "elite2_max"})
    module = case.skills["growth"]["characters"]["char_test"]["modules"][0]
    module["materials"].append({"id": "4001", "count": 100})
    case.formulas["t3"]["goldCost"] = 5
    case.formulas["t4"]["goldCost"] = 10
    case.stock.update(raw=8, growth_exp=8900)
    case.stock["4001"] = gold
    states, _ = prepared(case)
    assert states[0]["status"] == "preparing" and not states[0]["materials_prepared"]
    assert reminders(case) == []


@pytest.mark.parametrize("gold,level_ready", [(989, False), (990, True)])
def test_level_reminder_reserves_already_prepared_module_gold(
    order_case, gold, level_ready
):
    case = order_case
    case.plans.clear()
    case.box["characters"][0]["level"] = 1
    case.goals.append({"char_id": "char_test", "module_id": "elite2_max"})
    module = case.skills["growth"]["characters"]["char_test"]["modules"][0]
    module["materials"].append({"id": "4001", "count": 100})
    case.stock.update(t4=2, growth_exp=8900)
    case.stock["4001"] = gold
    expected = ["goal:char_test:module"]
    if level_ready:
        expected.append("goal:char_test:elite2_max")
    assert [row["key"] for row in reminders(case)] == expected


def test_order_api_exposes_prepared_reminders_without_adding_them_to_sortable_projects(
    order_api,
):
    api = order_api
    api.case.plans.clear()
    api.case.goals[:] = [{"char_id": "char_test", "module_id": "elite2_max"}]
    api.case.box["characters"][0]["level"] = 1
    api.box_path.write_text(json.dumps({"data": api.case.box}))
    response = api.client.get("/growth-crafting-order", headers=api.headers)
    assert response.status_code == 200 and response.json["items"] == []
    assert [row["key"] for row in response.json["prepared_items"]] == [
        "goal:char_test:elite2_max"
    ]
    api.save.assert_not_called()


def test_prepared_module_waiting_for_manual_leveling_does_not_block_next_project(
    order_case,
):
    case = order_case
    case.plans[:] = [case.plans[1]]
    case.box["characters"][0]["level"] = 1
    case.stock.update(raw=3, t4=2)
    order = ["goal:char_test:module", "skill:char_next:0"]
    states, _ = prepared(case, order)
    assert states[0]["materials_prepared"] and states[0]["status"] == "preparing"
    settings, cid = generated(case, order)
    assert cid == "char_next" and recipe(settings)["item_names"] == ["other"]


def test_legacy_module_goal_without_target_reminds_until_maximum_module_level(
    order_case,
):
    case = order_case
    case.plans.clear()
    case.goals[0].pop("target_level")
    module = case.skills["growth"]["characters"]["char_test"]["modules"][0]
    module["levels"] = [
        {"level": level, "materials": [{"id": "t4", "count": level}]}
        for level in (1, 2, 3)
    ]
    char = case.box["characters"][0]
    char["equips"] = [{"id": "module", "level": 1}]
    case.stock["t4"] = 5
    states, entries = prepared(case)
    assert states[0]["materials_prepared"]
    assert entries == [("goal:char_test:module", [{"id": "t4", "count": 5}])]
    ready = reminders(case)
    assert len(ready) == 1
    assert "待升级模组" in ready[0]["reason"]
    assert ready[0]["label"].endswith("模组 3 级")
    assert growth_order.describe_projects(states, case.skills)[0]["label"].endswith(
        "模组 3 级"
    )
    char["equips"][0]["level"] = 3
    assert reminders(case) == []
