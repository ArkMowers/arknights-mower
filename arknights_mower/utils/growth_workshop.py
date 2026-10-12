"""Generate the next missing recipe for one operator using shared live stock."""

from collections import Counter
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
    fees = {
        recipe.get("output_name", name): int(recipe.get("goldCost") or 0)
        for name, recipe in formulas.items()
        if recipe.get("tab") in ("精英材料", "技巧概要")
    }
    demand = Counter()
    for material in materials:
        demand[material["id"]] += material["count"]
    pending = set(demand)
    total = 0
    while pending:
        iid = max(pending, key=lambda key: (budget.depths.get(key, 0), key))
        pending.remove(iid)
        shortage = max(0, demand[iid] - budget.inventory.get(iid, 0))
        if not shortage or iid.startswith("32") or iid not in budget.recipes:
            continue
        costs, output = budget.recipes[iid]
        batches = ceil(shortage / output)
        total += batches * fees.get(budget.items.get(iid, {}).get("name", iid), 0)
        for child, count in costs.items():
            demand[child] += count * batches
            pending.add(child)
    return total


def next_recipe(entries, skills, inventory, formulas, blocked=()):
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
            used = min(available[iid], demand[iid])
            available[iid] -= used
            shortage = demand[iid] - used
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
            continue
        for iid in sorted(crafts, key=lambda key: (budget.depths.get(key, 0), key)):
            costs, output = budget.recipes[iid]
            batches = min(
                crafts[iid],
                *(
                    max(0, stock[child] - reserved.get(child, 0)) // count
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


def growth_workshop_config(
    box, skills, plans, goals, inventory, formulas, operators, blocked=(), order=()
):
    from arknights_mower.utils.growth_order import (
        crafting_projects,
        prepare_project_materials,
    )
    from arknights_mower.utils.workshop_recipes import recipe_category
    from arknights_mower.utils.workshop_recommendation import allocate_workshop_items

    projects = crafting_projects(plans, goals, order, box=box, skills=skills)
    states, entries = prepare_project_materials(
        box, skills, projects, inventory, formulas, blocked
    )
    key, items = next_recipe(entries, skills, inventory, formulas, blocked)
    focus = next((p for p in projects if p["key"] == key), None)
    if focus is None:
        focus = next(
            (
                p
                for p in states
                if p["status"] == "waiting" or (p["locked"] and p["reason"])
            ),
            None,
        )
    cid = focus["char_id"] if focus else None
    if not items:
        return [], cid
    category = recipe_category(formulas[items[0]["item_names"][0]])
    # Missing-only preparation cannot add unrelated fodder to build causality.
    names = [name for name in operators[category] if name != "九色鹿"]
    groups = [(category, names, items)]
    return allocate_workshop_items(groups, formulas=formulas), cid
