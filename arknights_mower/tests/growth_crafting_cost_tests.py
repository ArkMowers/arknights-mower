"""Workshop fees follow the remaining shared material tree, not owned stock."""

from arknights_mower.utils.growth_workshop import crafting_gold_cost
from arknights_mower.utils.mastery_materials import MaterialBudget


def test_fee_includes_shared_intermediates_and_batch_output_without_double_count():
    items = {iid: {"name": iid} for iid in ("raw", "middle", "final")}
    formulas = {
        "middle": {
            "tab": "精英材料",
            "costs": {"raw": 2},
            "output_count": 2,
            "goldCost": 100,
        },
        "final": {
            "tab": "精英材料",
            "costs": {"middle": 3},
            "output_count": 1,
            "goldCost": 300,
        },
    }
    budget = MaterialBudget({"items": items}, {"final": 1, "middle": 2}, formulas)
    materials = [{"id": "final", "count": 2}, {"id": "middle", "count": 2}]
    assert crafting_gold_cost(budget, materials, formulas) == 500
    budget.inventory = {"final": 2, "middle": 2}
    assert crafting_gold_cost(budget, materials, formulas) == 0


def test_manual_chip_exchange_does_not_charge_workshop_fee():
    skills = {
        "items": {"3213": {"name": "dual"}, "3212": {"name": "chip"}},
        "composite": {"3213": {"pathway": [{"id": "3212", "count": 2}]}},
    }
    budget = MaterialBudget(skills, {})
    assert crafting_gold_cost(budget, [{"id": "3213", "count": 4}], {}) == 0


def test_real_recipe_fees_use_only_missing_quantities():
    from arknights_mower.data import workshop_formula

    skills = {
        "items": {
            name: {"name": name} for name in ("聚合剂", "提纯源岩", "异铁块", "酮阵列")
        }
    }
    stock = {"聚合剂": 1, "提纯源岩": 1, "异铁块": 1, "酮阵列": 1}
    budget = MaterialBudget(skills, stock, workshop_formula)
    assert crafting_gold_cost(budget, [{"id": "聚合剂", "count": 2}]) == 400


def test_plan_fee_is_recomputed_from_shared_total_and_added_to_direct_gold_once():
    formulas = {
        "middle": {
            "tab": "精英材料",
            "costs": {"raw": 2},
            "output_count": 2,
            "goldCost": 100,
        }
    }
    skills = {"items": {iid: {"name": iid} for iid in ("raw", "middle", "4001")}}
    budget = MaterialBudget(skills, {"raw": 2, "4001": 1050}, formulas)
    summary = budget.calculate_plan(
        [
            ("a", [{"id": "middle", "count": 1}, {"id": "4001", "count": 1000}]),
            ("b", [{"id": "middle", "count": 1}]),
        ]
    )
    assert summary["crafting_gold"] == 100
    gold = next(row for row in summary["materials"] if row["id"] == "4001")
    assert gold["required"] == 1100
    assert next(row for row in summary["missing"] if row["id"] == "4001")["count"] == 50
    assert summary["craftable"] is False


def test_growth_summary_includes_fee_and_available_stock_has_zero_fee():
    from arknights_mower.utils.growth import calculate_growth_materials

    formulas = {
        "middle": {
            "tab": "精英材料",
            "costs": {"raw": 2},
            "output_count": 1,
            "goldCost": 100,
        }
    }
    skills = {"items": {iid: {"name": iid} for iid in ("raw", "middle", "4001")}}
    budget = MaterialBudget(skills, {"raw": 2, "4001": 100}, formulas)
    summary = calculate_growth_materials(budget, [{"id": "middle", "count": 1}])
    assert summary["crafting_gold"] == 100
    assert summary["craftable"] is True
    budget.inventory["middle"] = 1
    summary = calculate_growth_materials(budget, [{"id": "middle", "count": 1}])
    assert summary["crafting_gold"] == 0
    assert summary["available"] is True
    assert all(row["id"] != "4001" for row in summary["materials"])
