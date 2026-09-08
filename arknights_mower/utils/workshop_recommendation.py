"""Recommend multiple owned workshop operators and match their recipe bonuses."""

from arknights_mower.utils.mastery_support import (
    SupportPlanError,
    owned_roster,
    unlocked,
)

CATEGORIES = ("fodder_operators", "t5_operators", "book_operators")
PREFERRED = {
    "fodder_operators": "九色鹿",
    "t5_operators": "年",
    "book_operators": "司霆惊蛰",
}


class WorkshopRecommendationError(ValueError):
    pass


def available_operators(roster=None, metadata=None):
    if roster is None:
        try:
            roster = owned_roster()
        except SupportPlanError:
            raise WorkshopRecommendationError(
                "请先同步干员数据，再读取加工站推荐"
            ) from None
    if metadata is None:
        from arknights_mower.utils.mastery_recommendation import get_skill_data

        data = get_skill_data().get("workshop", {})
        if data.get("version") != 1 or not isinstance(data.get("operators"), dict):
            raise WorkshopRecommendationError(
                "当前资源缺少加工站技能规则，请更新资源包"
            )
        metadata = data["operators"]
    return {
        meta["name"]: unlocked(meta, char)
        for char in roster
        if (meta := metadata.get(char["id"])) is not None
    }


def recipe_category(recipe):
    if recipe.get("tab") == "技巧概要":
        return "book_operators"
    if recipe.get("tab") == "精英材料" and recipe.get("apCost", 0) > 0:
        return "t5_operators" if recipe["apCost"] >= 8 else "fodder_operators"
    return None


def recipe_bonus(effects, name, recipe):
    category = "book" if recipe.get("tab") == "技巧概要" else "material"
    return sum(
        rule["bonus"]
        for rule in effects
        if rule["kind"] == "byproduct"
        and category in rule["categories"]
        and (
            "original_cost" not in rule or rule["original_cost"] == recipe.get("apCost")
        )
        and ("item" not in rule or rule["item"] == name)
        and ("family" not in rule or rule["family"] in name)
    )


def has_causality(effects):
    return any(rule["kind"] == "causality" for rule in effects)


def recommend_workshop_operators(roster=None, metadata=None, formulas=None):
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula
    available = available_operators(roster, metadata)
    selected = {category: {} for category in CATEGORIES}
    for material, recipe in sorted(formulas.items()):
        category = recipe_category(recipe)
        if category is None:
            continue
        bonuses = {
            name: recipe_bonus(effects, material, recipe)
            for name, effects in available.items()
        }
        highest = max(bonuses.values(), default=0)
        for name, bonus in bonuses.items():
            deer = (
                category == "fodder_operators"
                and name == "九色鹿"
                and has_causality(available[name])
            )
            if not deer and (bonus <= 0 or bonus != highest):
                continue
            entry = selected[category].setdefault(
                name, {"name": name, "materials": [], "bonuses": {}, "causality": deer}
            )
            entry["materials"].append(material)
            entry["bonuses"][material] = bonus
    recommendations = {}
    for category, entries in selected.items():
        recommendations[category] = sorted(
            entries.values(),
            key=lambda entry: (
                not entry["causality"],
                -max(entry["bonuses"].values(), default=0),
                entry["name"] != PREFERRED[category],
                entry["name"],
            ),
        )
    return {
        "defaults": {
            key: [entry["name"] for entry in values]
            for key, values in recommendations.items()
        },
        "recommendations": recommendations,
        "nine_colored_deer": {
            "name": "九色鹿",
            "owned": "九色鹿" in available,
            "unlocked": has_causality(available.get("九色鹿", [])),
        },
    }


def allocate_workshop_items(groups, *, fodder_items=(), available=None, formulas=None):
    """Keep tied best operators per recipe, plus Nine-Colored Deer's fodder workflow.

    Missing rules/BOX keep legacy manual assignment usable. Duplicate operator
    entries are merged because the workshop executor consumes only its first entry.
    """
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula
    if available is None:
        try:
            available = available_operators()
        except WorkshopRecommendationError:
            available = None
    result = {}
    use_deer_fodder = False
    for category, names, items in groups:
        names = list(dict.fromkeys(names))
        use_deer_fodder |= category == "fodder_operators" and "九色鹿" in names
        for name in names:
            result.setdefault(name, {"operator": name, "enabled": True, "items": []})
        for item in items:
            for material in item["item_names"]:
                recipe = formulas.get(material, {})
                bonuses = (
                    {
                        name: recipe_bonus(available.get(name, []), material, recipe)
                        for name in names
                    }
                    if available is not None
                    else {}
                )
                highest = max(bonuses.values(), default=0)
                for name in names:
                    deer = name == "九色鹿" and category == "fodder_operators"
                    if available is None or deer or bonuses[name] == highest:
                        result[name]["items"].append({**item, "item_names": [material]})
    if use_deer_fodder:
        result["九色鹿"]["items"] = list(fodder_items) + result["九色鹿"]["items"]
    return list(result.values())
