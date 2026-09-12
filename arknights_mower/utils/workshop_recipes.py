"""Match fixed workshop bonuses, material scopes and execution preferences."""

import json
from functools import lru_cache
from pathlib import Path

from arknights_mower.utils.workshop_data import unlocked
from arknights_mower.utils.workshop_material_policy import (
    protected_workshop_materials,
    workshop_recipe_allowed,
)

T4_PREFERRED = ("九色鹿", "蚀清")


def recipe_category(recipe):
    if recipe.get("tab") == "技巧概要":
        return "book_operators"
    if recipe.get("tab") == "精英材料" and recipe.get("apCost", 0) > 0:
        return "t5_operators" if recipe["apCost"] >= 8 else "fodder_operators"
    return None


def operator_recipe_allowed(name, recipe, *, fodder=False):
    """Apply user material scopes using original recipe cost, before reductions."""
    t4 = recipe.get("tab") == "精英材料" and recipe.get("apCost") == 4
    if name in T4_PREFERRED:
        return t4 or (name == "九色鹿" and fodder and recipe.get("tab") == "基建材料")
    return name != "莱伊" or not t4


def scope_workshop_items(name, items, formulas=None):
    """Filter saved tasks too; copy changed items without altering user settings."""
    protected = protected_workshop_materials()
    if not protected and name not in (*T4_PREFERRED, "莱伊"):
        return list(items)
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula
    result = []
    for item in items:
        data = item.model_dump() if hasattr(item, "model_dump") else item
        materials = [
            material
            for material in data["item_names"]
            if operator_recipe_allowed(name, formulas.get(material, {}), fodder=True)
            and workshop_recipe_allowed(formulas.get(material, {}), protected)
        ]
        if materials:
            result.append(
                item.model_copy(update={"item_names": materials})
                if hasattr(item, "model_copy")
                else {**item, "item_names": materials}
            )
    return result


def rule_matches(rule, name, recipe):
    category = {"技巧概要": "book", "精英材料": "material"}.get(recipe.get("tab"))
    return (
        category in rule.get("categories", [])
        and (
            "original_cost" not in rule or rule["original_cost"] == recipe.get("apCost")
        )
        and ("item" not in rule or rule["item"] == name)
        and ("family" not in rule or rule["family"] in name)
    )


def matches_specialty(rules, name, recipe):
    return any(rule_matches(rule, name, recipe) for rule in rules)


def recipe_bonus(effects, name, recipe):
    return sum(
        rule["bonus"]
        for rule in effects
        if rule["kind"] == "byproduct" and rule_matches(rule, name, recipe)
    )


def _specialty_bonus_effects(rule, effects):
    if rule["kind"] != "cost_reduction":
        return effects
    return [
        effect
        for effect in effects
        if not any(key in effect for key in ("item", "family", "original_cost"))
    ]


def specialty_rules(effects):
    """Material/cost conditions whose combined fixed bonus reaches at least 80%."""
    from arknights_mower.data import workshop_formula

    return [
        rule
        for rule in effects
        if rule["kind"] in {"byproduct", "cost_reduction"}
        and any(key in rule for key in ("item", "family", "original_cost"))
        and any(
            recipe.get("tab") == "精英材料"
            and rule_matches(rule, material, recipe)
            and recipe_bonus(_specialty_bonus_effects(rule, effects), material, recipe)
            >= 80
            for material, recipe in workshop_formula.items()
        )
    ]


@lru_cache(maxsize=1)
def _bundled_specialties():
    # Keep manual selections scoped even without BOX or with an older resource pack.
    path = Path(__file__).parents[1] / "data/skill_data.json"
    operators = json.loads(path.read_text(encoding="utf-8"))["workshop"]["operators"]
    result = {}
    for meta in operators.values():
        rules = []
        for group in meta["groups"]:
            for version in group:
                effects = unlocked(
                    meta, {"evolvePhase": version["elite"], "level": version["level"]}
                )
                for rule in specialty_rules(effects):
                    if rule not in rules:
                        rules.append(rule)
        if rules:
            result[meta["name"]] = rules
    return result


def operator_specialties(unlocked_specialties):
    return {
        **_bundled_specialties(),
        **{name: rules for name, rules in unlocked_specialties.items() if rules},
    }


def exclusive_specialists(bonuses, specialists):
    """Reserve a recipe for its specialists only when one reaches the best bonus."""
    return (
        specialists
        if specialists
        and max(bonuses[name] for name in specialists) == max(bonuses.values())
        else set()
    )


def operator_priority(name, bonus, *, t5=False, effects=()):
    # T4 exceptions precede probability; all other preferences only break ties.
    preference = 2
    if bonus == 80:
        if name == "蜜莓":
            preference = 0
        elif name == "缇缇" and t5:
            preference = 1
    return (
        T4_PREFERRED.index(name) if name in T4_PREFERRED else len(T4_PREFERRED),
        -bonus,
        not any(effect["kind"] == "dormitory" for effect in effects),
        preference,
    )
