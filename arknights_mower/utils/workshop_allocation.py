"""Allocate recipe tasks and sort scoped copies of saved workshop settings."""

from arknights_mower.utils.workshop_material_policy import protected_workshop_materials
from arknights_mower.utils.workshop_recipes import (
    T4_PREFERRED,
    exclusive_specialists,
    matches_specialty,
    operator_priority,
    operator_recipe_allowed,
    operator_specialties,
    recipe_bonus,
    recipe_category,
    scope_workshop_items,
    specialty_rules,
)


def setting_priority(entry, available, formulas):
    data = entry.model_dump() if hasattr(entry, "model_dump") else entry
    name = data["operator"]
    if name not in available:
        return operator_priority(name, 0)
    materials = [material for item in data["items"] for material in item["item_names"]]
    effects = available[name]
    bonus = max(
        (
            recipe_bonus(effects, material, formulas.get(material, {}))
            for material in materials
        ),
        default=0,
    )
    t5 = any(
        recipe_category(formulas.get(material, {})) == "t5_operators"
        for material in materials
    )
    return operator_priority(name, bonus, t5=t5, effects=effects)


def scope_setting(entry, formulas):
    name = entry.operator if hasattr(entry, "model_dump") else entry["operator"]
    if not protected_workshop_materials() and name not in (*T4_PREFERRED, "莱伊"):
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

    def retained(self, candidates, material):
        if self.available is None:
            return candidates
        recipe = self.formulas.get(material, {})
        bonuses = {
            name: recipe_bonus(self.available.get(name, []), material, recipe)
            for name in candidates
        }
        highest = max(bonuses.values(), default=0)
        specialists = self.specialists(candidates, material)
        exclusive = exclusive_specialists(
            bonuses, self.specialists(candidates, material, byproduct=True)
        )
        return [
            name
            for name in candidates
            if (not exclusive or name in exclusive or name in T4_PREFERRED)
            and (
                name in T4_PREFERRED
                or name in specialists
                or bonuses[name] >= max(1, self.min_bonus)
                or bonuses[name] == highest
            )
        ]

    def add_items(self, names, items, *, specialist_only=False):
        for item in items:
            for material in item["item_names"]:
                candidates = self.candidates(
                    names, material, specialist_only=specialist_only
                )
                for name in self.retained(candidates, material):
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
