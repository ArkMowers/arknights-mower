"""Uncraftable skills wait without starting partial automatic preparation."""

import copy
import json

from arknights_mower.tests.workshop_plan_fixtures import book_limit
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils import mastery_recommendation as rec
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils.config.conf import RIICPart


def set_stock(fixture, stock):
    fixture.cultivate.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [],
                    "items": [
                        {"id": key, "count": value} for key, value in stock.items()
                    ],
                }
            }
        )
    )


def test_books_short_after_crafting_wait_then_resume_without_changing_plan(next_skill):
    plans = copy.deepcopy(next_skill.plans)
    set_stock(next_skill, {"3302": 20})  # Six books can be made; the head needs seven.
    assert rec.compute_workshop_config([], [], ["赫拉格"]) == []
    assert rec.auto_schedule_mastery_tasks()["scheduled"] == []
    assert next_skill.plans == plans
    set_stock(next_skill, {"3302": 21})
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 7
    assert rec.auto_schedule_mastery_tasks()["scheduled"] == []  # Not crafted yet.
    set_stock(next_skill, {"3303": 7})
    assert any(
        item["char_id"] == "char_b"
        for item in rec.auto_schedule_mastery_tasks()["scheduled"]
    )
    assert next_skill.plans == plans


def test_elite_shortage_stops_all_preparation_including_other_available_materials(
    next_skill, monkeypatch
):
    data = rec.get_mastery_recommendations()
    data["operators"][1]["recommendations"][0]["chain_needed_materials"].append(
        {"name": "糖聚块", "count": 1}
    )
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    set_stock(next_skill, {"3302": 300})
    assert rec.compute_workshop_config(["空爆"], [], ["赫拉格"]) == []
    assert rec.auto_schedule_mastery_tasks()["scheduled"] == []


def test_protected_ingredients_do_not_unlock_automatic_preparation(
    next_skill, monkeypatch
):
    data = rec.get_mastery_recommendations()
    data["operators"][1]["recommendations"][0]["chain_needed_materials"] = [
        {"name": "提纯源岩", "count": 1}
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    set_stock(next_skill, {"30012": 20})
    assert any(item["items"] for item in rec.compute_workshop_config(["空爆"], [], []))
    config.conf.workshop_protect_t2_device_rock = True
    assert rec.compute_workshop_config(["空爆"], [], []) == []
    set_stock(next_skill, {"30013": 4})
    assert any(item["items"] for item in rec.compute_workshop_config(["空爆"], [], []))


def test_new_shortage_invalidates_old_automatic_tasks_but_keeps_backup_and_plan(
    next_skill,
):
    manual = RIICPart.WorkShopSetting(operator="空爆")
    config.conf.workshop_settings = [manual]
    auto.update_workshop_config()
    generation = config.conf.workshop_generation
    plans = copy.deepcopy(next_skill.plans)
    set_stock(next_skill, {})
    result = auto.update_workshop_config()
    assert result["workshop_settings"] == []
    assert config.conf.workshop_auto_active
    assert config.conf.workshop_generation > generation
    assert config.conf.workshop_manual_backup == [manual]
    assert next_skill.plans == plans
    set_stock(next_skill, {"3302": 21})
    assert book_limit(auto.update_workshop_config()["workshop_settings"]) == 7


def test_readiness_uses_target_level_for_both_crafting_and_training(
    next_skill, monkeypatch
):
    next_skill.plans[1]["target_level"] = 1
    data = rec.get_mastery_recommendations()
    data["operators"][1]["recommendations"][0]["stages"] = [
        {
            "to_level": level + 7,
            "needed_materials": [{"name": "技巧概要·卷3", "count": count}],
        }
        for level, count in [(1, 1), (2, 2), (3, 4)]
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    set_stock(next_skill, {"3302": 3})
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 1
    set_stock(next_skill, {"3303": 1})
    assert [
        item["char_id"] for item in rec.auto_schedule_mastery_tasks()["scheduled"]
    ] == ["char_b"]


def test_lookahead_checks_current_remaining_costs_as_well_as_next_skill(
    next_skill, monkeypatch
):
    next_skill.plans[1].update(status="training", expires_at="2999-01-01 00:00:00")
    data = rec.get_mastery_recommendations()
    data["operators"][1]["recommendations"][0]["stages"] = [
        {
            "to_level": level + 7,
            "needed_materials": [{"name": "技巧概要·卷3", "count": count}],
        }
        for level, count in [(1, 1), (2, 2), (3, 4)]
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    set_stock(next_skill, {"3302": 15})  # Enough for next skill, not current + next.
    assert rec.compute_workshop_config([], [], ["赫拉格"]) == []
    set_stock(next_skill, {"3302": 33})
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 11


def test_training_start_sums_repeated_materials_across_remaining_levels(
    next_skill, monkeypatch
):
    next_skill.plans[1]["target_level"] = 2
    data = rec.get_mastery_recommendations()
    skill = data["operators"][1]["recommendations"][0]
    skill["stages"] = [
        {
            "to_level": level + 7,
            "needed_materials": [{"name": "技巧概要·卷3", "count": 1}],
        }
        for level in (1, 2, 3)
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    set_stock(next_skill, {"3303": 1})
    assert rec.auto_schedule_mastery_tasks()["scheduled"] == []
    set_stock(next_skill, {"3303": 2})
    assert [
        item["char_id"] for item in rec.auto_schedule_mastery_tasks()["scheduled"]
    ] == ["char_b"]
    skill["current_level"] = 2
    assert rec.auto_schedule_mastery_tasks()["scheduled"] == []
