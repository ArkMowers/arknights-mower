"""Build owned default lists and curated recommendations from the same recipes."""

from arknights_mower.utils.workshop_recipes import (
    T4_PREFERRED,
    exclusive_specialists,
    matches_specialty,
    operator_priority,
    operator_recipe_allowed,
    operator_specialties,
    recipe_bonus,
    recipe_category,
    specialty_rules,
)

CATEGORIES = ("fodder_operators", "t5_operators", "book_operators")
ASSIGNMENT_ORDER = ("t5_operators", "book_operators", "fodder_operators")
PREFERRED = {
    "fodder_operators": "九色鹿",
    "t5_operators": "年",
    "book_operators": "司霆惊蛰",
}


class WorkshopSelection:
    def __init__(self, eligible, formulas, min_bonus):
        self.eligible = eligible
        self.min_bonus = min_bonus
        self.unlocked = {
            name: specialty_rules(effects) for name, effects in eligible.items()
        }
        # Keep material assignments separate from current skill eligibility.
        self.material_scopes = operator_specialties(self.unlocked)
        self.recipes = {category: [] for category in CATEGORIES}
        for material, recipe in sorted(formulas.items()):
            category = recipe_category(recipe)
            if category is not None:
                self.recipes[category].append((material, recipe))

    def bonus(self, name, material, recipe):
        if not operator_recipe_allowed(name, recipe):
            return None
        if name in self.material_scopes and not matches_specialty(
            self.material_scopes[name], material, recipe
        ):
            return None
        return recipe_bonus(self.eligible[name], material, recipe)

    def qualifying_bonuses(self, pool, material, recipe, *, threshold):
        bonuses = {}
        for name in pool:
            bonus = self.bonus(name, material, recipe)
            if bonus is None:
                continue
            exception = name == "九色鹿" or (name == "蚀清" and bonus >= 80)
            if exception or bonus >= max(1, threshold):
                bonuses[name] = bonus
        return bonuses

    def exclusive(self, bonuses, material, recipe):
        specialists = {
            name
            for name, bonus in bonuses.items()
            if bonus >= 80
            and matches_specialty(
                [rule for rule in self.unlocked[name] if rule["kind"] == "byproduct"],
                material,
                recipe,
            )
        }
        return exclusive_specialists(bonuses, specialists)

    def add_material(self, entries, bonuses, material, recipe, *, curated=False):
        exclusive = set() if curated else self.exclusive(bonuses, material, recipe)
        for name, bonus in bonuses.items():
            if exclusive and name not in exclusive and name not in T4_PREFERRED:
                continue
            entry = entries.setdefault(
                name,
                {
                    "name": name,
                    "materials": [],
                    "bonuses": {},
                    "causality": name == "九色鹿",
                },
            )
            if matches_specialty(self.unlocked[name], material, recipe) and bonus >= 80:
                entry["specialist"] = True
            if name == "蚀清":
                entry["material_scope"] = "t4"
            entry["materials"].append(material)
            entry["bonuses"][material] = bonus

    def category_entries(self, category, assigned, *, curated):
        threshold = (
            (80 if category == "book_operators" else 90) if curated else self.min_bonus
        )
        if category == "book_operators":
            threshold = min(threshold, 80)
        pool = [
            name
            for name in self.eligible
            if name not in assigned and (name != "年" or category == "t5_operators")
        ]
        entries = {}
        for material, recipe in self.recipes[category]:
            bonuses = self.qualifying_bonuses(
                pool, material, recipe, threshold=threshold
            )
            self.add_material(entries, bonuses, material, recipe, curated=curated)
        return entries

    def priority(self, entry, category):
        name = entry["name"]
        return (
            *operator_priority(
                name,
                max(entry["bonuses"].values(), default=0),
                t5=category == "t5_operators",
                effects=self.eligible[name],
            ),
            name != PREFERRED[category],
            name,
        )

    def select(self, *, curated=False):
        selected = {}
        assigned = set()
        for category in ASSIGNMENT_ORDER:
            entries = self.category_entries(category, assigned, curated=curated)
            # Only operators with exactly 80% bonuses may cross categories.
            assigned.update(
                name
                for name, entry in entries.items()
                if not curated and set(entry["bonuses"].values()) != {80}
            )
            selected[category] = sorted(
                entries.values(), key=lambda entry: self.priority(entry, category)
            )
        return {category: selected[category] for category in CATEGORIES}
