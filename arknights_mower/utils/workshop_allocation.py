"""Allocate permitted recipes in the user-selected operator order."""

from arknights_mower.utils.workshop_material_policy import protected_workshop_materials
from arknights_mower.utils.workshop_recipes import (
    SCOPED_OPERATORS,
    matches_specialty,
    operator_priority,
    operator_recipe_allowed,
    operator_specialties,
    recipe_bonus,
    recipe_category,
    scope_workshop_items,
    specialty_rules,
)


def setting_recipe_bonus(entry, available, formulas):
    """按当前配方取最高已解锁副产品加成；缺少配方或练度时不比较。"""
    data = entry.model_dump() if hasattr(entry, "model_dump") else entry
    if data["operator"] not in available:
        return None
    return max(
        (
            recipe_bonus(available[data["operator"]], material, formulas[material])
            for item in data["items"]
            for material in item["item_names"]
            if material in formulas
        ),
        default=None,
    )


def setting_priority(entry, available, formulas, *, prefer_t4=True):
    data = entry.model_dump() if hasattr(entry, "model_dump") else entry
    name = data["operator"]
    if name not in available:
        return operator_priority(name, 0, prefer_t4=prefer_t4)
    materials = [material for item in data["items"] for material in item["item_names"]]
    effects = available[name]
    bonus = setting_recipe_bonus(entry, available, formulas) or 0
    t5 = any(
        recipe_category(formulas.get(material, {})) == "t5_operators"
        for material in materials
    )
    return operator_priority(name, bonus, t5=t5, effects=effects, prefer_t4=prefer_t4)


def scope_setting(entry, formulas):
    name = entry.operator if hasattr(entry, "model_dump") else entry["operator"]
    if not protected_workshop_materials() and name not in SCOPED_OPERATORS:
        return entry
    items = scope_workshop_items(
        name, entry.items if hasattr(entry, "model_dump") else entry["items"], formulas
    )
    return (
        entry.model_copy(update={"items": items})
        if hasattr(entry, "model_copy")
        else {**entry, "items": items}
    )


class WorkshopAllocation:
    def __init__(self, available, formulas, min_bonus):
        self.available = available
        self.formulas = formulas
        self.min_bonus = min_bonus
        self.unlocked = {
            name: specialty_rules(effects)
            for name, effects in (available or {}).items()
        }
        self.specialties = operator_specialties(self.unlocked)
        self.result = {}

    def specialists(self, names, material, *, byproduct=False):
        recipe = self.formulas.get(material, {})
        return {
            name
            for name in names
            if recipe_bonus((self.available or {}).get(name, []), material, recipe)
            >= 80
            and matches_specialty(
                [
                    rule
                    for rule in self.unlocked.get(name, [])
                    if not byproduct or rule["kind"] == "byproduct"
                ],
                material,
                recipe,
            )
        }

    def candidates(self, names, material, *, specialist_only):
        recipe = self.formulas.get(material, {})
        specialists = self.specialists(names, material)
        return [
            name
            for name in names
            if operator_recipe_allowed(name, recipe)
            and (
                name not in self.specialties
                or matches_specialty(self.specialties[name], material, recipe)
            )
            and (not specialist_only or name in specialists)
        ]

    def add_items(self, names, items, *, specialist_only=False):
        for item in items:
            for material in item["item_names"]:
                candidates = self.candidates(
                    names, material, specialist_only=specialist_only
                )
                for name in candidates:
                    self.result[name]["items"].append(
                        {**item, "item_names": [material]}
                    )

    def allocate(self, groups, fodder_items, specialist_items):
        use_deer_fodder = False
        for category, names, items in groups:
            names = [
                name
                for name in dict.fromkeys(names)
                if name != "年" or category == "t5_operators"
            ]
            for name in names:
                self.result.setdefault(
                    name, {"operator": name, "enabled": True, "items": []}
                )
            self.add_items(names, items)
            if category == "fodder_operators":
                use_deer_fodder |= "九色鹿" in names
                self.add_items(names, specialist_items, specialist_only=True)
        if use_deer_fodder:
            self.result["九色鹿"]["items"] = (
                list(fodder_items) + self.result["九色鹿"]["items"]
            )
        return self.result.values()
