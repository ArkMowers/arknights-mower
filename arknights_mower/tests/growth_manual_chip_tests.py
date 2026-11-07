"""Manual chip readiness shares real stock without generating workshop tasks."""

import copy

import pytest

from arknights_mower.utils.growth import calculate_growth_materials
from arknights_mower.utils.growth_workshop import next_recipe
from arknights_mower.utils.mastery_materials import MaterialBudget


def budget(stock):
    items = {
        iid: {"name": iid}
        for iid in ("3213", "3212", "3223", "3222", "32001", "4006", "other")
    }
    return MaterialBudget({"items": items}, stock, {})


def rows(summary):
    return {row["id"]: row for row in summary["materials"]}


@pytest.mark.parametrize(
    "stock,craftable",
    [
        ({"3212": 8, "32001": 4}, True),
        ({"3212": 8, "32001": 2, "4006": 180}, True),
        ({"3212": 8, "4006": 360}, True),
        ({"3212": 8, "32001": 2, "4006": 179}, False),
        ({"3212": 7, "32001": 4}, False),
        ({"3222": 8, "32001": 4}, False),
        ({"3212": 8}, False),
    ],
)
def test_dual_chip_requires_own_profession_groups_and_whole_catalysts(stock, craftable):
    calculator = budget(stock)
    before = copy.deepcopy(calculator.inventory)
    summary = calculate_growth_materials(calculator, [{"id": "3213", "count": 4}])
    assert summary["craftable"] is craftable
    assert rows(summary)["3213"]["craftable"] is craftable
    assert rows(summary)["3213"]["owned"] == 0
    assert not summary["available"]
    assert summary["manual_chips"]
    assert summary["crafting_gold"] == 0
    assert calculator.inventory == before
    assert not calculator.recipes
    if craftable:
        assert not summary["missing"]


def test_existing_dual_chips_reduce_manual_requirements_and_keep_resource_rows():
    summary = calculate_growth_materials(
        budget({"3213": 2, "3212": 4, "32001": 1, "4006": 90}),
        [{"id": "3213", "count": 4}],
    )
    materials = rows(summary)
    assert summary["craftable"] and not summary["available"]
    assert {iid: row["required"] for iid, row in materials.items()} == {
        "3213": 4,
        "3212": 4,
        "32001": 2,
        "4006": 90,
    }
    assert materials["32001"]["owned"] == 1
    assert materials["32001"]["craftable"]
    assert materials["4006"]["owned"] == 90


@pytest.mark.parametrize(
    "extra", [{"id": "3212", "count": 1}, {"id": "4006", "count": 1}]
)
def test_direct_group_and_voucher_costs_compete_with_manual_conversion(extra):
    summary = calculate_growth_materials(
        budget({"3212": 2, "4006": 90}),
        [{"id": "3213", "count": 1}, extra],
    )
    assert not summary["craftable"]
    assert not rows(summary)["3213"]["craftable"]
    assert any(row["id"] == extra["id"] for row in summary["missing"])


@pytest.mark.parametrize(
    "stock",
    [
        {"3212": 2, "3222": 2, "32001": 1},
        {"3212": 2, "3222": 2, "4006": 90},
    ],
)
def test_two_operators_do_not_reuse_shared_catalysts_or_vouchers(stock):
    summary = budget(stock).calculate_plan(
        [
            ("first", [{"id": "3213", "count": 1}]),
            ("second", [{"id": "3223", "count": 1}]),
        ],
        growth=True,
    )
    assert not summary["craftable"]
    assert summary["missing_skills"] == ["second"]
    assert rows(summary)["32001"]["required"] == 2


def test_mixed_catalyst_and_vouchers_cover_two_operators_once():
    summary = budget({"3212": 2, "3222": 2, "32001": 1, "4006": 90}).calculate_plan(
        [
            ("first", [{"id": "3213", "count": 1}]),
            ("second", [{"id": "3223", "count": 1}]),
        ],
        growth=True,
    )
    assert summary["craftable"] and not summary["available"]
    assert not summary["missing_skills"]
    assert rows(summary)["4006"]["required"] == 90


def test_unrelated_shortage_does_not_hide_craftable_manual_chips():
    summary = calculate_growth_materials(
        budget({"3212": 2, "4006": 90}),
        [{"id": "3213", "count": 1}, {"id": "other", "count": 1}],
    )
    assert not summary["craftable"]
    assert rows(summary)["3213"]["craftable"]
    assert [row["id"] for row in summary["missing"]] == ["other"]


def test_manual_chip_readiness_never_generates_automatic_tasks():
    calculator = budget({"3212": 2, "4006": 90})
    materials = [{"id": "3213", "count": 1}]
    assert calculate_growth_materials(calculator, materials)["craftable"]
    assert next_recipe(
        [("first", materials)], {"items": calculator.items}, calculator.inventory, {}
    ) == (None, [])
