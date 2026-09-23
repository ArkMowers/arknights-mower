"""Independent Nine-Colored Deer fodder preferences, never generated or restored."""

from arknights_mower.utils import config


def deer_fodder_materials():
    from arknights_mower.data import workshop_formula

    return [
        name
        for name, recipe in workshop_formula.items()
        if recipe.get("tab") == "基建材料"
        or recipe.get("tab") == "技巧概要"
        or (recipe.get("tab") == "精英材料" and recipe.get("apCost") == 1)
    ]


def deer_fodder_items():
    allowed = set(deer_fodder_materials())
    result = []
    for item in config.conf.workshop_deer_fodder:
        data = item.model_dump()
        names = [name for name in data["item_names"] if name in allowed]
        if names:
            result.append({**data, "item_names": names})
    return result
