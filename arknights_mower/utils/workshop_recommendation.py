"""Recommend multiple owned workshop operators and match their recipe bonuses."""

import json
from functools import lru_cache
from pathlib import Path

CATEGORIES = ("fodder_operators", "t5_operators", "book_operators")
ASSIGNMENT_ORDER = ("t5_operators", "book_operators", "fodder_operators")
PREFERRED = {
    "fodder_operators": "九色鹿",
    "t5_operators": "年",
    "book_operators": "司霆惊蛰",
}
T4_PREFERRED = ("九色鹿", "蚀清")


class WorkshopRecommendationError(ValueError):
    pass


@lru_cache(maxsize=2)
def _read_roster(path, mtime, size):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("data", {}).get("characters", [])


def owned_roster():
    from arknights_mower.utils.path import get_path

    path = get_path("@app/tmp/cultivate.json")
    try:
        stat = path.stat()
        return _read_roster(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        raise WorkshopRecommendationError(
            "请先同步干员数据，再读取加工站推荐"
        ) from None


def unlocked(meta, char):
    progress = (char.get("evolvePhase", 0), char.get("level", 1))
    effects = []
    for group in meta.get("groups", []):
        versions = [v for v in group if (v["elite"], v["level"]) <= progress]
        if versions:
            effects.extend(
                max(versions, key=lambda v: (v["elite"], v["level"]))["effects"]
            )
    return effects


def scheduled_operators(plan=None):
    """Block primary/replacement staff in every plan, except dorms and workshop."""
    if plan is None:
        from arknights_mower.utils import config

        plan = getattr(config, "plan", {})
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump(exclude_none=True)
    base = plan.get(plan.get("default", "plan1"), {})
    blocked = {}
    for table in [base, *(p.get("plan", {}) for p in plan.get("backup_plans", []))]:
        for room, facility in table.items():
            if room == "factory" or room.startswith("dormitory_") or not facility:
                continue
            for slot in facility.get("plans", []):
                for name in [slot.get("agent", ""), *slot.get("replacement", [])]:
                    if name and name not in {"Free", "Current"}:
                        blocked.setdefault(name, set()).add(room)
    return {name: sorted(rooms) for name, rooms in blocked.items()}


def available_operators(roster=None, metadata=None):
    if roster is None:
        roster = owned_roster()
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


def operator_recipe_allowed(name, recipe, *, fodder=False):
    """Apply user material scopes using original recipe cost, before reductions."""
    t4 = recipe.get("tab") == "精英材料" and recipe.get("apCost") == 4
    if name in T4_PREFERRED:
        return t4 or (name == "九色鹿" and fodder and recipe.get("tab") == "基建材料")
    return name != "莱伊" or not t4


def scope_workshop_items(name, items, formulas=None):
    """Filter saved tasks too; copy changed items without altering user settings."""
    if name not in (*T4_PREFERRED, "莱伊"):
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
            and recipe_bonus(
                [
                    r
                    for r in effects
                    if not any(key in r for key in ("item", "family", "original_cost"))
                ]
                if rule["kind"] == "cost_reduction"
                else effects,
                material,
                recipe,
            )
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


def prioritize_workshop_settings(settings, *, available=None, formulas=None):
    """Scope and order execution copies, preserving saved configurations/limits."""
    if available is None:
        try:
            available = available_operators()
        except WorkshopRecommendationError:
            available = {}
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula

    def priority(entry):
        entry = entry.model_dump() if hasattr(entry, "model_dump") else entry
        name = entry["operator"]
        if name not in available:
            return operator_priority(name, 0)
        bonus = max(
            (
                recipe_bonus(
                    available.get(name, []), material, formulas.get(material, {})
                )
                for item in entry["items"]
                for material in item["item_names"]
            ),
            default=0,
        )
        t5 = any(
            recipe_category(formulas.get(material, {})) == "t5_operators"
            for item in entry["items"]
            for material in item["item_names"]
        )
        return operator_priority(name, bonus, t5=t5, effects=available.get(name, []))

    scoped = []
    for entry in settings:
        name = entry.operator if hasattr(entry, "model_dump") else entry["operator"]
        if name not in (*T4_PREFERRED, "莱伊"):
            scoped.append(entry)
            continue
        items = scope_workshop_items(
            name,
            entry.items if hasattr(entry, "model_dump") else entry["items"],
            formulas,
        )
        scoped.append(
            entry.model_copy(update={"items": items})
            if hasattr(entry, "model_copy")
            else {**entry, "items": items}
        )
    return sorted(scoped, key=priority)


def recommend_workshop_operators(
    roster=None, metadata=None, formulas=None, *, plan=None, min_bonus=80
):
    min_bonus = validate_min_bonus(min_bonus)
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula
    available = available_operators(roster, metadata)
    blocked = scheduled_operators(plan)
    eligible = {
        name: effects for name, effects in available.items() if name not in blocked
    }
    unlocked_specialties = {
        name: specialty_rules(effects) for name, effects in eligible.items()
    }
    specialties = operator_specialties(unlocked_specialties)
    recipes = {category: [] for category in CATEGORIES}
    for material, recipe in sorted(formulas.items()):
        category = recipe_category(recipe)
        if category is not None:
            recipes[category].append((material, recipe))

    def select(*, curated=False):
        selected = {category: {} for category in CATEGORIES}
        assigned = set()
        for category in ASSIGNMENT_ORDER:
            threshold = (
                (80 if category == "book_operators" else 90) if curated else min_bonus
            )
            pool = {
                name: effects
                for name, effects in eligible.items()
                if name not in assigned and (name != "年" or category == "t5_operators")
            }
            for material, recipe in recipes[category]:
                bonuses = {}
                for name, effects in pool.items():
                    if not operator_recipe_allowed(name, recipe):
                        continue
                    bonus = recipe_bonus(effects, material, recipe)
                    if name in specialties and (
                        not matches_specialty(
                            unlocked_specialties[name], material, recipe
                        )
                        or bonus < 80
                    ):
                        continue
                    exception = name == "九色鹿" or (
                        curated and name == "蚀清" and bonus >= 80
                    )
                    if not exception and (bonus <= 0 or bonus < threshold):
                        continue
                    bonuses[name] = bonus
                matching_specialists = {
                    name
                    for name, bonus in bonuses.items()
                    if matches_specialty(
                        [
                            r
                            for r in unlocked_specialties[name]
                            if r["kind"] == "byproduct"
                        ],
                        material,
                        recipe,
                    )
                    and bonus >= 80
                }
                exclusive = exclusive_specialists(bonuses, matching_specialists)
                for name, bonus in bonuses.items():
                    # The requested T4 priorities also precede material specialists.
                    if exclusive and name not in exclusive and name not in T4_PREFERRED:
                        continue
                    entry = selected[category].setdefault(
                        name,
                        {
                            "name": name,
                            "materials": [],
                            "bonuses": {},
                            "causality": name == "九色鹿",
                        },
                    )
                    if (
                        matches_specialty(unlocked_specialties[name], material, recipe)
                        and bonus >= 80
                    ):
                        entry["specialist"] = True
                    if name == "蚀清":
                        entry["material_scope"] = "t4"
                    entry["materials"].append(material)
                    entry["bonuses"][material] = bonus
            # 80% operators may serve multiple categories within their valid scopes.
            assigned.update(
                name
                for name, entry in selected[category].items()
                if set(entry["bonuses"].values()) != {80}
            )
        return {
            category: sorted(
                entries.values(),
                key=lambda entry: (
                    *operator_priority(
                        entry["name"],
                        max(entry["bonuses"].values(), default=0),
                        t5=category == "t5_operators",
                        effects=eligible[entry["name"]],
                    ),
                    entry["name"] != PREFERRED[category],
                    entry["name"],
                ),
            )
            for category, entries in selected.items()
        }

    return {
        "defaults": {
            key: [entry["name"] for entry in values] for key, values in select().items()
        },
        "recommendations": select(curated=True),
        "blocked_operators": blocked,
        "nine_colored_deer": {
            "name": "九色鹿",
            "owned": "九色鹿" in available,
        },
        "min_bonus": min_bonus,
    }


def validate_min_bonus(value):
    try:
        number = int(value)
        if isinstance(value, (bool, float)) or not 0 <= number <= 1000:
            raise ValueError
        return number
    except (ValueError, TypeError, OverflowError):
        raise WorkshopRecommendationError(
            "副产品概率加成下限须为 0～1000 的整数"
        ) from None


def allocate_workshop_items(
    groups,
    *,
    fodder_items=(),
    specialist_items=(),
    available=None,
    formulas=None,
    plan=None,
    min_bonus=None,
):
    """Reserve specialist recipes, then prioritize retained candidates by bonus.

    Specialist-only low-tier recipes require an owned, unlocked specialist.
    Missing rules/BOX keep legacy manual assignment usable within known specialties.
    Duplicate entries are merged because the executor consumes only its first entry.
    """
    if formulas is None:
        from arknights_mower.data import workshop_formula

        formulas = workshop_formula
    if min_bonus is None:
        from arknights_mower.utils import config

        min_bonus = getattr(config.conf, "workshop_min_bonus", 80)
    min_bonus = validate_min_bonus(min_bonus)
    if available is None:
        try:
            available = available_operators()
        except WorkshopRecommendationError:
            available = None
    blocked = scheduled_operators(plan)
    unlocked_specialties = {
        name: specialty_rules(effects) for name, effects in (available or {}).items()
    }
    specialties = operator_specialties(unlocked_specialties)
    result = {}
    use_deer_fodder = False
    for category, names, items in groups:
        # Reserve Nian for T5 even when an older saved list includes her elsewhere.
        names = [
            name
            for name in dict.fromkeys(names)
            if name not in blocked and (name != "年" or category == "t5_operators")
        ]
        use_deer_fodder |= category == "fodder_operators" and "九色鹿" in names
        for name in names:
            result.setdefault(name, {"operator": name, "enabled": True, "items": []})
        tasks = [(item, False) for item in items]
        if category == "fodder_operators":
            tasks.extend((item, True) for item in specialist_items)
        for item, specialist_only in tasks:
            for material in item["item_names"]:
                recipe = formulas.get(material, {})
                matching_specialists = {
                    name
                    for name in names
                    if matches_specialty(
                        unlocked_specialties.get(name, []), material, recipe
                    )
                    and recipe_bonus(available.get(name, []), material, recipe) >= 80
                }
                candidates = [
                    name
                    for name in names
                    if operator_recipe_allowed(name, recipe)
                    and (
                        name not in specialties
                        or matches_specialty(specialties[name], material, recipe)
                    )
                    and (not specialist_only or name in matching_specialists)
                ]
                bonuses = (
                    {
                        name: recipe_bonus(available.get(name, []), material, recipe)
                        for name in candidates
                    }
                    if available is not None
                    else {}
                )
                highest = max(bonuses.values(), default=0)
                # Cost savings alone (e.g. Titi's T5 skill) do not reserve materials.
                exclusive = exclusive_specialists(
                    bonuses,
                    {
                        name
                        for name in matching_specialists
                        if matches_specialty(
                            [
                                r
                                for r in unlocked_specialties[name]
                                if r["kind"] == "byproduct"
                            ],
                            material,
                            recipe,
                        )
                    },
                )
                for name in candidates:
                    if exclusive and name not in exclusive and name not in T4_PREFERRED:
                        continue
                    if (
                        available is None
                        or name in T4_PREFERRED
                        or name in matching_specialists
                        or bonuses.get(name, 0) >= max(1, min_bonus)
                        or bonuses[name] == highest
                    ):
                        result[name]["items"].append({**item, "item_names": [material]})
    if use_deer_fodder:
        result["九色鹿"]["items"] = list(fodder_items) + result["九色鹿"]["items"]
    return prioritize_workshop_settings(
        result.values(), available=available or {}, formulas=formulas
    )
