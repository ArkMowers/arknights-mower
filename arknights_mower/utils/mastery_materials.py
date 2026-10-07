"""Read-only material budgeting for mastery previews; never changes workshop tasks."""

from collections import Counter
from math import ceil


class MaterialBudget:
    def __init__(
        self, skill_data, inventory, workshop_formula=None, *, blocked_materials=()
    ):
        self.items = skill_data.get("items", {})
        self.formulas = workshop_formula
        self.inventory = {key: max(0, int(value)) for key, value in inventory.items()}
        ids = {item["name"]: key for key, item in self.items.items()}
        self.recipes = {}
        for key, recipe in skill_data.get("composite", {}).items():
            costs = Counter()
            for child in recipe.get("pathway", []):
                costs[child["id"]] += child["count"]
            if costs:
                self.recipes[key] = (dict(costs), 1)
        for name, recipe in (workshop_formula or {}).items():
            if recipe.get("tab", "精英材料") not in ("精英材料", "技巧概要"):
                continue
            output = ids.get(recipe.get("output_name", name))
            costs = recipe.get("costs") or dict(Counter(recipe.get("items", [])))
            if output and costs and all(child in ids for child in costs):
                self.recipes[output] = (
                    {ids[child]: count for child, count in costs.items()},
                    max(1, int(recipe.get("output_count", 1))),
                )
        blocked_ids = {ids[name] for name in blocked_materials if name in ids}
        self.recipes = {
            key: recipe
            for key, recipe in self.recipes.items()
            if not blocked_ids.intersection(recipe[0])
        }
        self.depths = {}
        for key in self.recipes:
            self._depth(key, set())

    def _depth(self, key, visiting):
        if key in visiting:
            raise ValueError("材料合成配方存在循环")
        if key not in self.depths:
            children = self.recipes.get(key, ({}, 1))[0]
            self.depths[key] = 1 + max(
                (self._depth(child, visiting | {key}) for child in children), default=-1
            )
        return self.depths[key]

    def _consume(self, key, count, stock, trace=None):
        used = min(stock.get(key, 0), count)
        if trace is not None and used:
            # Show inventory actually spent, not intermediates made during crafting.
            trace[key] += used
        stock[key] = stock.get(key, 0) - used
        count -= used
        if not count:
            return True
        recipe = self.recipes.get(key)
        if not recipe:
            return False
        costs, output = recipe
        batches = ceil(count / output)
        for child, cost in costs.items():
            if not self._consume(child, cost * batches, stock, trace):
                return False
        stock[key] += batches * output - count
        return True

    def _craft_available(self, key, count, stock, trace):
        # Whole batches only. Failed probes must not consume shared ingredients.
        low, high = 0, count
        while low < high:
            middle = (low + high + 1) // 2
            if self._consume(key, middle, dict(stock)):
                low = middle
            else:
                high = middle - 1
        if low:
            self._consume(key, low, stock, trace)
        return low

    def calculate(self, materials):
        direct = Counter()
        for material in materials:
            direct[material["id"]] += material["count"]
        demand = Counter(direct)
        stock = dict(self.inventory)
        reserved = {key: min(count, stock.get(key, 0)) for key, count in direct.items()}
        for key, count in reserved.items():
            stock[key] = stock.get(key, 0) - count
        rows, missing = [], []
        lower_demand = Counter()
        pending = set(demand)
        while pending:
            key = max(pending, key=lambda k: (self.depths.get(k, 0), k))
            pending.remove(key)
            count = demand[key]
            if count <= 0:
                continue
            item = self.items.get(key, {})
            owned = stock.get(key, 0)
            extra_used = min(count - reserved.get(key, 0), owned)
            stock[key] = owned - extra_used
            used = extra_used + reserved.get(key, 0)
            shortage = count - used
            row = {
                "id": key,
                "name": item.get("name", key),
                "rarity": item.get("rarity", 0),
                "required": count,
                "owned": self.inventory.get(key, 0),
                "used": used,
                "direct": direct[key],
                "to_craft": shortage,
            }
            rows.append(row)
            if not shortage:
                continue
            # Stop the shopping list at blue elite materials. Lower-tier stock
            # may still make whole blue materials; books are reported separately.
            blue = item.get("rarity") == 3 and not key.startswith("330")
            book = key.startswith("330")
            recipe = self.recipes.get(key)
            if recipe and not blue and not book:
                costs, output = recipe
                batches = ceil(shortage / output)
                for child, cost in costs.items():
                    demand[child] += cost * batches
                    pending.add(child)
            else:
                crafted = (
                    self._craft_available(key, shortage, stock, lower_demand)
                    if recipe
                    else 0
                )
                row["craftable_count"] = crafted
                if shortage > crafted:
                    missing.append({**row, "count": shortage - crafted, "blue": blue})
        known_rows = {row["id"]: row for row in rows}
        for key, count in lower_demand.items():
            if key in known_rows:
                known_rows[key]["required"] += count
                continue
            item = self.items.get(key, {})
            rows.append(
                {
                    "id": key,
                    "name": item.get("name", key),
                    "rarity": item.get("rarity", 0),
                    "required": count,
                    "owned": self.inventory.get(key, 0),
                    "direct": 0,
                }
            )
        # Propagate unresolved ingredient shortages upward through the shared
        # budget, so unrelated craftable materials remain distinguishable.
        missing_ids = {row["id"] for row in missing}
        supply = {}
        for row in sorted(rows, key=lambda row: self.depths.get(row["id"], 0)):
            key = row["id"]
            needs_crafting = row.get("to_craft", 0) > 0
            row["craftable"] = not needs_crafting or (
                key not in missing_ids
                and all(
                    supply.get(child, True)
                    for child in self.recipes.get(key, ({}, 1))[0]
                )
            )
            supply[key] = row["craftable"]
        direct_rows = [
            {
                "id": key,
                "name": self.items.get(key, {}).get("name", key),
                "required": count,
                "owned": self.inventory.get(key, 0),
                "craftable": supply[key],
            }
            for key, count in direct.items()
            if count > 0
        ]
        return {
            "materials": direct_rows,
            "crafting": [row for row in rows if row["required"] > row["direct"]],
            "missing": missing,
            "available": all(row["owned"] >= row["required"] for row in direct_rows),
            "craftable": not missing,
        }

    def calculate_plan(self, entries):
        """Attribute new elite-material shortages in plan order using shared stock."""
        from arknights_mower.utils.growth_workshop import calculate_crafting_materials

        demand = Counter()
        previous_missing = {}
        missing_skills = []
        summary = calculate_crafting_materials(self, [])
        for key, materials in entries:
            for material in materials:
                demand[material["id"]] += material["count"]
            # Aggregate first: each pass is bounded by material types, not plan length.
            summary = calculate_crafting_materials(
                self, [{"id": item, "count": count} for item, count in demand.items()]
            )
            missing = {
                row["id"]: row["count"]
                for row in summary["missing"]
                if not row["id"].startswith("330")
            }
            if any(
                count > previous_missing.get(item, 0) for item, count in missing.items()
            ):
                missing_skills.append(key)
            previous_missing = missing
        summary["missing_skills"] = missing_skills
        return summary


def plan_material_summary(planned_keys, goals=(), targets=None):
    if not planned_keys and not goals:
        return MaterialBudget({}, {}).calculate_plan([])
    import json

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.growth import (
        expand_chip_costs,
        growth_resources,
        inventory_counts,
        material_entries,
    )
    from arknights_mower.utils.mastery_db import get_all_plans, get_failed_plans
    from arknights_mower.utils.mastery_recommendation import get_skill_data
    from arknights_mower.utils.path import get_path
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    with open(get_path("@app/tmp/cultivate.json"), encoding="utf-8") as stream:
        box = json.load(stream)["data"]
    skills = growth_resources(get_skill_data())
    saved = {
        f"{p['char_id']}_{p['skill_index']}": p
        for p in get_all_plans() + get_failed_plans()
    }
    plans = []
    for key in dict.fromkeys(planned_keys):
        cid, index = key.rsplit("_", 1)
        plan = {
            "char_id": cid,
            "skill_index": int(index),
            "target_level": 3,
            **saved.get(key, {}),
        }
        if key in (targets or {}):
            plan["target_level"] = targets[key]
        plans.append(plan)
    entries = material_entries(box, skills, plans, goals)
    stock = inventory_counts(box, skills, local=True)
    cumulative, previous, expanded = [], Counter(), []
    for cid, materials in entries:
        cumulative.extend(materials)
        costs = Counter(
            {m["id"]: m["count"] for m in expand_chip_costs(cumulative, stock)}
        )
        expanded.append(
            (
                cid,
                [
                    {"id": iid, "count": count}
                    for iid, count in (costs - previous).items()
                ],
            )
        )
        previous = costs
    summary = MaterialBudget(
        skills,
        stock,
        workshop_formula,
        blocked_materials=protected_workshop_materials(),
    ).calculate_plan(expanded)
    summary["manual_chips"] = any(
        row["id"].startswith("32") for row in summary["materials"]
    )
    missing_operators = set(summary["missing_skills"])
    summary["missing_skills"] = [
        key for key in planned_keys if key.rsplit("_", 1)[0] in missing_operators
    ]
    summary["missing_operators"] = list(missing_operators)
    return summary
