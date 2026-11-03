"""Workshop priority regressions."""

from unittest.mock import patch

import pytest

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.tests.workshop_fixtures import (
    item,
    owned,
    recipe,
)
from arknights_mower.utils import config
from arknights_mower.utils import workshop_recommendation as workshop


def test_recommendations_rank_bonus_but_execution_preserves_manual_t5_order(game):
    meta, ids = game
    roster = owned(ids, "空爆", "缇缇", "蜜莓", "年", "号角")
    recommendations = workshop.recommend_workshop_operators(roster, meta)
    assert recommendations["defaults"]["t5_operators"] == ["年", "蜜莓", "缇缇", "空爆"]
    assert recommendations["defaults"]["fodder_operators"] == ["号角", "蜜莓", "空爆"]
    result = workshop.allocate_workshop_items(
        [("t5_operators", ["空爆", "缇缇", "蜜莓", "年"], [item("双极纳米片")])],
        available=workshop.available_operators(roster, meta),
    )
    assert [entry["operator"] for entry in result] == ["空爆", "缇缇", "蜜莓", "年"]
    # Titi's mood savings do not make ordinary T5 recipes exclusive to her.
    assert all(entry["items"] == [item("双极纳米片")] for entry in result)


def test_unlocked_80_percent_is_required_for_honeyberry_preference(game):
    meta, ids = game
    roster = owned(ids, "蜜莓", elite=0) + owned(ids, "空爆", "缇缇")
    result = workshop.allocate_workshop_items(
        [("t5_operators", ["蜜莓", "空爆", "缇缇"], [item("双极纳米片")])],
        available=workshop.available_operators(roster, meta),
        min_bonus=75,
    )
    assert [entry["operator"] for entry in result] == ["蜜莓", "空爆", "缇缇"]


@pytest.mark.parametrize("nian_mood", [24, 20])
def test_scheduler_uses_saved_order_and_respects_existing_mood_gate(game, nian_mood):
    from types import SimpleNamespace

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import scheduler_task
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    meta, ids = game
    names = ["空爆", "缇缇", "蜜莓", "年"]
    settings = [
        RIICPart.WorkShopSetting(
            operator=name, items=[WorkShopItem(**item("双极纳米片"))]
        )
        for name in names
    ]
    available = workshop.available_operators(owned(ids, *names), meta)
    operators = {
        name: SimpleNamespace(mood=nian_mood if name == "年" else 24) for name in names
    }
    inventory = {
        "双极纳米片": 0,
        **{name: 100 for name in workshop_formula["双极纳米片"]["items"]},
    }
    tasks = []
    with (
        patch.object(config.conf, "workshop_settings", settings),
        patch.object(scheduler_task, "get_inventory_counts", return_value=inventory),
        patch.object(workshop, "available_operators", return_value=available),
    ):
        scheduler_task.try_workshop_tasks(SimpleNamespace(operators=operators), tasks)
    assert [task.meta_data for task in tasks] == ["空爆", "缇缇", "蜜莓"] + (
        ["年"] if nian_mood > 22 else []
    )
    assert [entry.operator for entry in settings] == names
    assert all(
        (later.time - earlier.time).total_seconds() >= 2
        for earlier, later in zip(tasks, tasks[1:])
    )


def test_all_unlocked_dorm_skills_win_ties_but_not_larger_bonuses(game):
    meta, ids = game
    names = ["司霆惊蛰", "炎客", "子月", "赫拉格", "蜜莓", "空爆", "年"]
    available = workshop.available_operators(owned(ids, *names), meta)
    result = workshop.recommend_workshop_operators(owned(ids, *names), meta)
    assert set(result["defaults"]["book_operators"][:2]) == {"子月", "赫拉格"}
    assert result["defaults"]["t5_operators"] == ["年", "蜜莓", "空爆"]
    assert all(
        {"kind": "dormitory"} in available[name] for name in ["子月", "赫拉格", "蜜莓"]
    )
    assert {"kind": "dormitory"} not in workshop.available_operators(
        owned(ids, "蜜莓", elite=1), meta
    )["蜜莓"]


def test_t4_preferences_precede_specialists_without_broadening_other_generalists(game):
    meta, ids = game
    names = ["蜜莓", "号角", "蚀清", "九色鹿"]
    result = workshop.recommend_workshop_operators(
        owned(ids, *names), meta, {"炽合金块": recipe()}
    )
    assert result["defaults"]["fodder_operators"] == ["九色鹿", "蚀清", "号角"]
    allocated = workshop.allocate_workshop_items(
        [("fodder_operators", names, [item("炽合金块")])],
        available=workshop.available_operators(owned(ids, *names), meta),
        min_bonus=90,
    )
    assert [entry["operator"] for entry in allocated if entry["items"]] == [
        "蜜莓",
        "号角",
        "蚀清",
        "九色鹿",
    ]


def test_preferred_operators_cover_every_t4_before_material_specialists(game):
    from arknights_mower.data import workshop_formula
    from arknights_mower.tests.workshop_fixtures import SPECIALISTS

    meta, ids = game
    names = ["九色鹿", "镜匠", "蚀清"] + [name for name, *_ in SPECIALISTS]
    formulas = {
        name: formula
        for name, formula in workshop_formula.items()
        if formula.get("tab") == "精英材料" and formula.get("apCost") == 4
    }
    roster = owned(ids, *names)
    available = workshop.available_operators(roster, meta)
    defaults = workshop.recommend_workshop_operators(roster, meta, formulas)
    assert defaults["defaults"]["fodder_operators"][:3] == ["九色鹿", "镜匠", "蚀清"]
    for material in formulas:
        allocated = workshop.allocate_workshop_items(
            [("fodder_operators", names, [item(material)])],
            available=available,
            formulas=formulas,
        )
        workers = [entry["operator"] for entry in allocated if entry["items"]]
        assert workers[:3] == ["九色鹿", "镜匠", "蚀清"], material
