"""User-selected ingredients that workshop crafting must preserve."""

PROTECTED_T2_MATERIALS = frozenset({"装置", "固源岩"})


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
