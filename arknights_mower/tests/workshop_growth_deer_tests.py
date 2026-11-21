"""Growth demand feeds Deer before independent fodder without spending reservations."""

from collections import Counter

import pytest

from arknights_mower.tests.growth_crafting_order_tests import order_case as order_case
from arknights_mower.tests.growth_planning_tests import growth_case as growth_case
from arknights_mower.utils import config, workshop_fodder
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.growth_workshop import growth_workshop_config


@pytest.fixture
def deer_case(order_case, monkeypatch):
    case = order_case
    case.plans = [case.plans[0]]
    case.goals = []
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = [
        {"id": "book", "count": 2},
        {"id": "t4", "count": 1},
    ]
    case.stock.update(t3=2, t4=0, book=0)
    case.operators["fodder_operators"] = ["九色鹿", "瑕光", "空爆"]
    case.formulas["fallback"] = {
        "tab": "基建材料",
        "apCost": 4,
        "items": ["raw"],
        "costs": {"raw": 1},
        "output_name": "furniture",
        "output_count": 12,
    }
    monkeypatch.setattr(
        workshop_fodder,
        "deer_fodder_items",
        lambda: [
            {
                "item_names": ["fallback"],
                "children_lower_limit": 20,
                "self_upper_limit": 9999,
            }
        ],
    )
    return case


def generate(case):
    return growth_workshop_config(
        case.box,
        case.skills,
        case.plans,
        case.goals,
        case.stock,
        case.formulas,
        case.operators,
    )


def test_growth_books_feed_deer_before_fallback_and_t4(deer_case):
    result = generate(deer_case)
    deer = result.settings[0]
    assert deer["operator"] == "九色鹿"
    assert [item["item_names"] for item in deer["items"]] == [
        ["book"],
        ["fallback"],
        ["t4"],
    ]
    assert deer["items"][0]["self_upper_limit"] == 2
    assert deer["items"][2]["self_upper_limit"] == 1
    assert deer_case.operators["fodder_operators"] == ["九色鹿", "瑕光", "空爆"]


@pytest.mark.parametrize("cost", [1, 2])
def test_t2_t3_demand_can_feed_deer(cost, deer_case):
    case = deer_case
    case.formulas["t3"]["apCost"] = cost
    case.formulas["t4"].update(items=["other"], costs={"other": 2})
    case.stock.update(t3=0, other=2)
    materials = case.skills["characters"]["char_test"]["skills"][0]["levels"][0][
        "materials"
    ]
    materials[0] = {"id": "t3", "count": 3}
    deer = generate(case).settings[0]
    assert deer["operator"] == "九色鹿"
    assert deer["items"][0] == {
        "item_names": ["t3"],
        "children_lower_limit": 0,
        "self_upper_limit": 3,
    }


def test_deer_can_finish_t4_with_configured_fodder_after_demand_is_satisfied(deer_case):
    deer_case.stock["book"] = 2
    deer = generate(deer_case).settings[0]
    assert deer["operator"] == "九色鹿"
    assert [item["item_names"] for item in deer["items"]] == [["fallback"], ["t4"]]


def test_no_t4_demand_keeps_normal_manual_order(deer_case):
    deer_case.stock["t4"] = 1
    assert all(entry["operator"] != "九色鹿" for entry in generate(deer_case).settings)


def test_unselected_deer_is_not_added(deer_case):
    deer_case.operators["fodder_operators"].remove("九色鹿")
    assert all(entry["operator"] != "九色鹿" for entry in generate(deer_case).settings)


def test_fallback_reserves_ingredients_for_all_admitted_projects(deer_case):
    # Two books consume two raw; fallback must not spend those ingredients.
    deer_case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"][
        0
    ]["count"] = 40
    deer = generate(deer_case).settings[0]
    assert deer["items"][1]["children_lower_limit"] == 40


def test_insufficient_project_emits_no_deer_quota(deer_case):
    deer_case.stock = Counter({"raw": 0, "t3": 0, "4001": 1000})
    assert generate(deer_case).settings == []


def test_manual_t4_fallback_caps_one_extra_output_and_preserves_saved_limits(deer_case):
    case = deer_case
    case.stock["t4"] = 1
    case.stock["t3"] = 3
    manual = RIICPart.WorkShopSetting(
        operator="九色鹿",
        items=[
            WorkShopItem(item_names=["t4"], children_lower_limit=1, self_upper_limit=5),
        ],
    )
    config.conf.workshop_manual_backup = [manual]
    before = manual.model_dump()
    deer = generate(case).settings[0]
    assert deer["operator"] == "九色鹿"
    assert deer["items"][-1] == {
        "item_names": ["t4"],
        "children_lower_limit": 1,
        "self_upper_limit": 2,
    }
    assert manual.model_dump() == before


def test_manual_predecessors_run_before_deer_and_keep_their_material_scope(deer_case):
    case = deer_case
    case.operators["fodder_operators"] = ["瑕光", "九色鹿", "空爆"]
    case.formulas["t3"]["apCost"] = 2
    case.formulas["t4"].update(items=["other"], costs={"other": 2})
    case.stock.update(t3=0, other=2)
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"][0] = {
        "id": "t3",
        "count": 3,
    }
    result = generate(case)
    assert [entry["operator"] for entry in result.settings] == [
        "瑕光",
        "九色鹿",
        "空爆",
    ]
    assert result.settings[0]["items"] == [
        {"item_names": ["t3"], "children_lower_limit": 0, "self_upper_limit": 3}
    ]


@pytest.mark.parametrize("blocked", ["disabled", "upper", "lower", "unknown"])
def test_manual_t4_fallback_obeys_user_switch_limits_and_known_inventory(
    deer_case, blocked
):
    case = deer_case
    case.stock["t4"] = 1
    manual = RIICPart.WorkShopSetting(
        operator="九色鹿",
        items=[
            WorkShopItem(item_names=["t4"], children_lower_limit=0, self_upper_limit=5),
        ],
    )
    config.conf.workshop_manual_backup = [manual]
    if blocked == "disabled":
        manual.enabled = False
    elif blocked == "upper":
        manual.items[0].self_upper_limit = 1
    elif blocked == "lower":
        manual.items[0].children_lower_limit = 2
    else:
        case.stock.pop("t3")
    assert all(entry["operator"] != "九色鹿" for entry in generate(case).settings)
