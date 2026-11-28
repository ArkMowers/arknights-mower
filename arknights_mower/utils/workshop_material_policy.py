"""User-selected ingredients that workshop crafting must preserve."""

PROTECTED_T2_MATERIALS = frozenset({"装置", "固源岩"})


def _ingredient_reserves():
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import config

    limits = {1: config.conf.workshop_t1_reserve, 2: config.conf.workshop_t2_reserve}
    return {
        child: limits[recipe["apCost"]]
        for recipe in workshop_formula.values()
        if recipe.get("tab") == "精英材料" and recipe.get("apCost") in limits
        for child in recipe["items"]
    }


def workshop_material_reserves(items):
    """Return T1/T2 ingredient reserves using the workshop's material names."""
    limits = _ingredient_reserves()
    return {
        key: limits[item["name"]]
        for key, item in items.items()
        if item["name"] in limits
    }


def ingredient_reserve(name, lower_limit=0):
    return max(lower_limit, _ingredient_reserves().get(name, 0))


def protected_workshop_materials():
    from arknights_mower.utils import config

    if getattr(config.conf, "workshop_protect_t2_device_rock", False):
        return PROTECTED_T2_MATERIALS
    return frozenset()


def workshop_recipe_allowed(recipe, protected=None):
    if protected is None:
        protected = protected_workshop_materials()
    ingredients = set(recipe.get("items", [])) | set(recipe.get("costs", {}))
    return not protected.intersection(ingredients)
