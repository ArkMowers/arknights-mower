"""Independent Nine-Colored Deer fodder preferences, never generated or restored."""

from arknights_mower.utils import config


def deer_fodder_materials():
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.workshop_recipes import is_deer_fodder

    return [name for name, recipe in workshop_formula.items() if is_deer_fodder(recipe)]


def deer_fodder_items():
    allowed = set(deer_fodder_materials())
    result = []
    for item in config.conf.workshop_deer_fodder:
        data = item.model_dump()
        names = [name for name in data["item_names"] if name in allowed]
        if names:
            result.append({**data, "item_names": names})
    return result


def deer_manual_t4(inventory, reserved, formulas):
    """Borrow at most one usable T4 from the independent manual Deer form."""
    from arknights_mower.utils.config.conf import WorkShopItem
    from arknights_mower.utils.workshop_config import workshop_state
    from arknights_mower.utils.workshop_limits import (
        batch_limit,
        blocked_workshop_recipes,
    )

    rejected = blocked_workshop_recipes(inventory, readonly=True)
    for entry in workshop_state(config.conf)["workshop_manual_settings"]:
        if entry["operator"] != "九色鹿" or not entry["enabled"]:
            continue
        for item in entry["items"]:
            for name in item["item_names"]:
                recipe = formulas.get(name, {})
                if (
                    recipe.get("tab") != "精英材料"
                    or recipe.get("apCost") != 4
                    or name in rejected
                ):
                    continue
                output = recipe.get("output_name", name)
                setting = WorkShopItem(
                    **{
                        **item,
                        "item_names": [name],
                        "children_lower_limit": max(
                            [
                                item["children_lower_limit"],
                                *(reserved.get(child, 0) for child in recipe["items"]),
                            ]
                        ),
                        "self_upper_limit": min(
                            item["self_upper_limit"], inventory.get(output, 0) + 1
                        ),
                    }
                )
                if batch_limit(name, recipe, setting, inventory, operator="九色鹿"):
                    return [setting.model_dump()]
    return []
