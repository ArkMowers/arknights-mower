"""Generate the next missing recipe for one operator using shared live stock."""

from collections import Counter
from dataclasses import dataclass, field
from math import ceil

from arknights_mower.utils.mastery_materials import MaterialBudget


def calculate_crafting_materials(budget, materials):
    """Include workshop fees in the same LMD requirement as direct growth costs."""
    materials = list(materials)
    fee = crafting_gold_cost(budget, materials, budget.formulas)
    if fee:
        materials.append({"id": "4001", "count": fee})
    summary = budget.calculate(materials)
    summary["crafting_gold"] = fee
    return summary


def crafting_gold_cost(budget, materials, formulas=None):
    """Charge missing recipe batches once, including their missing ingredients."""
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula
    from arknights_mower.utils import config
    from arknights_mower.utils.workshop_limits import crafting_lmd_cost
    from arknights_mower.utils.workshop_recipes import operator_recipe_allowed

    blemishine = "瑕光" in config.conf.fodder_operators
    fees = {
        recipe.get("output_name", name): crafting_lmd_cost(
            recipe,
            "瑕光" if blemishine and operator_recipe_allowed("瑕光", recipe) else None,
        )
        for name, recipe in formulas.items()
        if recipe.get("tab") in ("精英材料", "技巧概要")
    }
    demand = Counter()
    for material in materials:
        demand[material["id"]] += material["count"]
    direct = demand.copy()
    pending = set(demand)
    total = 0
    while pending:
        iid = max(pending, key=lambda key: (budget.depths.get(key, 0), key))
        pending.remove(iid)
        reserve = (
            max(0, budget.ingredient_reserves.get(iid, 0) - direct[iid])
            if demand[iid] > direct[iid]
            else 0
        )
        shortage = max(0, demand[iid] + reserve - budget.inventory.get(iid, 0))
        if not shortage or iid.startswith("32") or iid not in budget.recipes:
            continue
        costs, output = budget.recipes[iid]
        batches = ceil(shortage / output)
        total += batches * fees.get(budget.items.get(iid, {}).get("name", iid), 0)
        for child, count in costs.items():
            demand[child] += count * batches
            pending.add(child)
    return total


def next_recipe(
    entries, skills, inventory, formulas, blocked=(), *, recipe_filter=None
):
    """Reserve earlier projects, then finish the first outstanding recipe.

    Only a single recipe receives a bounded quota. The caller recalculates after
    confirmed crafting, so consumed intermediate stock cannot refill an old quota.
    """
    budget = MaterialBudget(skills, inventory, formulas, blocked_materials=blocked)
    stock = Counter(inventory)
    recipe_names = {
        skills["items"][iid]["name"]: iid for iid in skills.get("items", {})
    }
    formula_ids = {
        recipe_names[f.get("output_name", name)]: name
        for name, f in formulas.items()
        if f.get("output_name", name) in recipe_names
        and f.get("tab") in ("精英材料", "技巧概要")
    }
    held = Counter()
    for cid, materials in entries:
        direct = Counter()
        for material in materials:
            direct[material["id"]] += material["count"]
        reserved = {iid: min(count, stock[iid]) for iid, count in direct.items()}
        available = stock.copy()
        available.subtract(reserved)
        demand = Counter({iid: count - reserved[iid] for iid, count in direct.items()})
        pending = set(demand)
        crafts = {}
        while pending:
            iid = max(pending, key=lambda key: (budget.depths.get(key, 0), key))
            pending.remove(iid)
            floor = max(
                0, budget.ingredient_reserves.get(iid, 0) - held[iid] - direct[iid]
            )
            used = min(max(0, available[iid] - floor), demand[iid])
            available[iid] -= used
            shortage = demand[iid] - used
            if demand[iid] > direct[iid] - reserved.get(iid, 0):
                shortage += max(0, floor - available[iid])
            if shortage <= 0 or iid not in budget.recipes or iid not in formula_ids:
                continue
            costs, output = budget.recipes[iid]
            batches = ceil(shortage / output)
            crafts[iid] = batches
            for child, count in costs.items():
                demand[child] += count * batches
                pending.add(child)
        if not crafts:
            stock.subtract(reserved)
            held.update(reserved)
            continue
        for iid in sorted(crafts, key=lambda key: (budget.depths.get(key, 0), key)):
            if recipe_filter and not recipe_filter(formulas[formula_ids[iid]]):
                continue
            costs, output = budget.recipes[iid]
            batches = min(
                crafts[iid],
                *(
                    max(
                        0,
                        stock[child]
                        - max(
                            reserved.get(child, 0),
                            max(
                                0,
                                budget.ingredient_reserves.get(child, 0) - held[child],
                            ),
                        ),
                    )
                    // count
                    for child, count in costs.items()
                ),
            )
            if batches:
                return cid, [
                    {
                        "item_names": [formula_ids[iid]],
                        "children_lower_limit": 0,
                        "self_upper_limit": inventory.get(iid, 0) + batches * output,
                    }
                ]
        # Retain this project's ingredients until its outstanding recipe is supplied.
        return cid, []
    return None, []


@dataclass
class GrowthWorkshopPlan:
    settings: list = field(default_factory=list)
    focus: dict | None = None
    recipe: str | None = None


def growth_workshop_config(
    box, skills, plans, goals, inventory, formulas, operators, blocked=(), order=()
):
    from arknights_mower.utils.growth_order import (
        crafting_projects,
        describe_projects,
        prepare_project_materials,
    )
    from arknights_mower.utils.workshop_recipes import recipe_category
    from arknights_mower.utils.workshop_recommendation import allocate_workshop_items

    projects = crafting_projects(plans, goals, order, box=box, skills=skills)
    states, entries = prepare_project_materials(
        box, skills, projects, inventory, formulas, blocked
    )
    key, items = next_recipe(entries, skills, inventory, formulas, blocked)
    focus = next((p for p in states if p["key"] == key), None)
    if focus is None:
        focus = next(
            (
                p
                for p in states
                if p["status"] == "waiting" or (p["locked"] and p["reason"])
            ),
            None,
        )
    if focus:
        focus = {
            **focus,
            "char_name": describe_projects([focus], skills)[0]["char_name"],
        }
    result = GrowthWorkshopPlan(focus=focus)
    if not items:
        return result
    category = recipe_category(formulas[items[0]["item_names"][0]])
    names = [name for name in operators[category] if name != "九色鹿"]
    groups = [(category, names, items)]
    result.settings = allocate_workshop_items(groups, formulas=formulas)
    if "九色鹿" in operators["fodder_operators"]:
        from arknights_mower.utils.workshop_recipes import is_deer_fodder

        # Use only admitted demand; aggregate it once so shared ingredients and
        # direct reservations bound both the fodder and the T4 quota.
        demand = Counter()
        for _, materials in entries:
            for material in materials:
                demand[material["id"]] += material["count"]
        combined = [(key, [{"id": iid, "count": n} for iid, n in demand.items()])]
        _, fodder = next_recipe(
            combined, skills, inventory, formulas, blocked, recipe_filter=is_deer_fodder
        )
        _, elite = next_recipe(
            combined,
            skills,
            inventory,
            formulas,
            blocked,
            recipe_filter=lambda recipe: (
                recipe.get("tab") == "精英材料" and recipe.get("apCost") == 4
            ),
        )
        planned_elite = elite
        if fodder or elite:
            from arknights_mower.utils.workshop_fodder import (
                deer_fodder_items,
                deer_manual_t4,
            )

            budget = MaterialBudget(
                skills, inventory, formulas, blocked_materials=blocked
            )
            stock, reserved = dict(inventory), Counter()
            for iid, count in demand.items():
                budget._consume(iid, count, stock, reserved)
            reserved_names = {
                skills["items"][iid]["name"]: count for iid, count in reserved.items()
            }
            named_inventory = {
                skills["items"].get(iid, {}).get("name", iid): count
                for iid, count in inventory.items()
            }
            if not elite:
                elite = deer_manual_t4(named_inventory, reserved_names, formulas)
            if not elite:
                result.recipe = items[0]["item_names"][0]
                return result
            fallback = [
                {
                    **item,
                    "children_lower_limit": max(
                        [
                            item["children_lower_limit"],
                            *(
                                reserved_names.get(child, 0)
                                for name in item["item_names"]
                                for child in formulas.get(name, {}).get("items", [])
                            ),
                        ]
                    ),
                }
                for item in deer_fodder_items()
            ]
            before_deer = operators["fodder_operators"][
                : operators["fodder_operators"].index("九色鹿")
            ]
            preceding = allocate_workshop_items(
                [("fodder_operators", before_deer, fodder + planned_elite)],
                formulas=formulas,
            )
            preceding_names = {entry["operator"] for entry in preceding}
            result.settings = (
                preceding
                + [
                    {
                        "operator": "九色鹿",
                        "enabled": True,
                        "items": fodder + fallback + elite,
                    }
                ]
                + [
                    entry
                    for entry in result.settings
                    if entry["operator"] not in preceding_names
                ]
            )
    result.recipe = items[0]["item_names"][0]
    return result
