"""Batch budgets and inventory accounting shared by all workshop operators."""

import json
from functools import lru_cache
from pathlib import Path

from arknights_mower.utils.workshop_material_policy import workshop_recipe_allowed


@lru_cache(maxsize=1)
def _bundled_recipes():
    return json.loads(
        (Path(__file__).parents[1] / "data/workshop_formula.json").read_text("utf-8")
    )


def recipe_quantities(name, metadata):
    """Old resource packs may omit quantities; use a matching bundled recipe."""
    recipe = metadata
    if "costs" not in recipe or "output_count" not in recipe:
        recipe = _bundled_recipes().get(name, {})
        if any(recipe.get(key) != metadata.get(key) for key in ("items", "apCost")):
            return None
    costs = recipe.get("costs", {})
    count = recipe.get("output_count")
    if (
        not costs
        or set(costs) != set(metadata["items"])
        or not isinstance(count, int)
        or count <= 0
        or any(not isinstance(n, int) or n <= 0 for n in costs.values())
    ):
        return None
    return recipe["output_name"], count, costs


def batch_limit(name, metadata, setting, inventory):
    if not workshop_recipe_allowed(metadata):
        return 0
    quantities = recipe_quantities(name, metadata)
    if quantities is None:
        return 0
    output, count, costs = quantities
    if any(name not in inventory for name in (output, *costs)):
        return 0  # Unknown stock must be read from the depot before spending it.
    return max(
        0,
        min(
            99,
            (setting.self_upper_limit - inventory[output]) // count,
            *(
                (inventory[child] - setting.children_lower_limit) // required
                for child, required in costs.items()
            ),
        ),
    )


def deer_batch_limit(gap, ap_cost):
    """Stop fodder before the guaranteed byproduct, then craft one T4 item."""
    if gap <= 0 or ap_cost <= 0:
        raise ValueError("九色鹿因果或配方心情消耗无效")
    return max(1, (gap - 1) // ap_cost)


def batch_delta(name, metadata, batches):
    """Account only for guaranteed main outputs; ignore all random byproducts."""
    output, count, costs = recipe_quantities(name, metadata)
    if not isinstance(batches, int) or batches <= 0:
        raise ValueError("加工次数无效")
    delta = {child: -amount * batches for child, amount in costs.items()}
    delta[output] = delta.get(output, 0) + count * batches
    return delta
