"""Public workshop recommendation and allocation API; manual fallback is explicit."""

from arknights_mower.utils.workshop_allocation import (
    WorkshopAllocation,
    scope_setting,
    setting_priority,
)
from arknights_mower.utils.workshop_data import (
    WorkshopRecommendationError,
    owned_roster,
    scheduled_operators,
    unlocked,
)
from arknights_mower.utils.workshop_recipes import (
    operator_recipe_allowed,
    recipe_bonus,
    recipe_category,
    scope_workshop_items,
)
from arknights_mower.utils.workshop_selection import (
    CATEGORIES,
    WorkshopSelection,
)

__all__ = [
    "CATEGORIES",
    "WorkshopRecommendationError",
    "owned_roster",
    "scheduled_operators",
    "unlocked",
    "operator_recipe_allowed",
    "recipe_bonus",
    "recipe_category",
    "scope_workshop_items",
    "available_operators",
    "recommend_workshop_operators",
    "allocate_workshop_items",
    "prioritize_workshop_settings",
    "validate_min_bonus",
]


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


def _formulas(formulas):
    if formulas is None:
        from arknights_mower.data import workshop_formula

        return workshop_formula
    return formulas


def _manual_available(available):
    """Existing manual settings remain executable when BOX/rules are unavailable."""
    if available is not None:
        return available
    try:
        return available_operators()
    except WorkshopRecommendationError:
        return None


def prioritize_workshop_settings(settings, *, available=None, formulas=None):
    """Scope and order execution copies, preserving saved configurations/limits."""
    available = _manual_available(available) or {}
    formulas = _formulas(formulas)
    scoped = [scope_setting(entry, formulas) for entry in settings]
    return sorted(
        scoped, key=lambda entry: setting_priority(entry, available, formulas)
    )


def recommend_workshop_operators(
    roster=None, metadata=None, formulas=None, *, plan=None, min_bonus=80
):
    min_bonus = validate_min_bonus(min_bonus)
    available = available_operators(roster, metadata)
    blocked = scheduled_operators(plan)
    eligible = {
        name: effects for name, effects in available.items() if name not in blocked
    }
    selection = WorkshopSelection(eligible, _formulas(formulas), min_bonus)
    return {
        "defaults": {
            key: [entry["name"] for entry in values]
            for key, values in selection.select().items()
        },
        "recommendations": selection.select(curated=True),
        "blocked_operators": blocked,
        "nine_colored_deer": {"name": "九色鹿", "owned": "九色鹿" in available},
        "min_bonus": min_bonus,
    }


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
    """Match saved choices to recipes, preserving manual fallback and merged tasks."""
    from arknights_mower.utils import config

    if min_bonus is None:
        min_bonus = getattr(config.conf, "workshop_min_bonus", 80)
    min_bonus = validate_min_bonus(min_bonus)
    formulas = _formulas(formulas)
    available = _manual_available(available)
    allocator = WorkshopAllocation(
        available, formulas, scheduled_operators(plan), min_bonus
    )
    settings = allocator.allocate(groups, fodder_items, specialist_items)
    return prioritize_workshop_settings(
        settings, available=available or {}, formulas=formulas
    )
