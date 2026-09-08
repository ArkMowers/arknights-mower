"""Workshop runtime regressions."""

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


@pytest.mark.parametrize("missing_box", [False, True])
def test_t4_scopes_apply_to_old_category_lists_and_keep_deer_building_fodder(
    game, missing_box
):
    meta, ids = game
    names = ["莱伊", "蚀清", "九色鹿"]
    formulas = {
        "糖组": recipe(2),
        "糖聚块": recipe(),
        "双极纳米片": recipe(8),
        "技巧概要·卷3": recipe(2, "技巧概要"),
        "碳素": recipe(2, "基建材料"),
    }
    groups = [
        ("fodder_operators", names, [item("糖组"), item("糖聚块")]),
        ("t5_operators", names, [item("双极纳米片")]),
        ("book_operators", names, [item("技巧概要·卷3")]),
    ]
    with patch.object(
        workshop,
        "available_operators",
        return_value=workshop.available_operators(owned(ids, *names), meta),
        side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
        if missing_box
        else None,
    ):
        result = workshop.allocate_workshop_items(
            groups, formulas=formulas, fodder_items=[item("碳素")]
        )
    assert [entry["operator"] for entry in result] == ["九色鹿", "蚀清", "莱伊"]
    scopes = {
        entry["operator"]: {
            material for task in entry["items"] for material in task["item_names"]
        }
        for entry in result
    }
    assert scopes == {
        "九色鹿": {"糖聚块", "碳素"},
        "蚀清": {"糖聚块"},
        "莱伊": {"糖组", "双极纳米片", "技巧概要·卷3"},
    }


@pytest.mark.parametrize("missing_box", [False, True])
def test_saved_runtime_configs_are_scoped_before_dispatch_without_mutating_them(
    game, missing_box
):
    from types import SimpleNamespace

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import scheduler_task
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    meta, ids = game
    # Stock makes only a forbidden recipe available for each operator.
    names = ["莱伊", "蚀清", "九色鹿"]
    settings = [
        RIICPart.WorkShopSetting(
            operator=name,
            items=[WorkShopItem(**item("糖聚块" if name == "莱伊" else "双极纳米片"))],
        )
        for name in names
    ]
    snapshot = [entry.model_dump() for entry in settings]
    inventory = {
        name: 100 for recipe in workshop_formula.values() for name in recipe["items"]
    }
    inventory.update({"糖聚块": 0, "双极纳米片": 0})
    tasks = []
    with (
        patch.object(config.conf, "workshop_settings", settings),
        patch.object(scheduler_task, "get_inventory_counts", return_value=inventory),
        patch.object(
            workshop,
            "available_operators",
            return_value=workshop.available_operators(owned(ids, *names), meta),
            side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
            if missing_box
            else None,
        ),
    ):
        scheduler_task.try_workshop_tasks(
            SimpleNamespace(
                operators={name: SimpleNamespace(mood=24) for name in names}
            ),
            tasks,
        )
    assert tasks == []
    assert [entry.model_dump() for entry in settings] == snapshot


def test_mixed_saved_recipe_rows_keep_limits_and_only_remove_forbidden_materials():
    original = [{**item("糖聚块"), "item_names": ["糖聚块", "糖组", "双极纳米片"]}]
    result = workshop.scope_workshop_items("蚀清", original)
    assert result == [item("糖聚块")]
    assert original[0]["item_names"] == ["糖聚块", "糖组", "双极纳米片"]
