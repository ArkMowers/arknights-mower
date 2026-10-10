"""Value observed growth costs using a pinned, offline Yituliu price snapshot."""

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def price_catalog():
    return json.loads(
        (Path(__file__).parents[1] / "data/growth_values.json").read_text("utf-8")
    )


def consumed_materials(char, definition, data, skills, *, shared=True):
    """Reconstruct completed upgrades, without subtracting current inventory."""
    from arknights_mower.utils.growth import promotion_materials

    materials = Counter()
    incomplete = False
    module_blocks = 0
    # Integrated-strategy progression uses its own unlock system, not depot costs.
    if definition.get("integrated_strategy"):
        return materials, module_blocks, incomplete

    def add(rows):
        for row in rows:
            materials[row["id"]] += row["count"]

    if shared:
        phase, level = char.get("evolvePhase"), char.get("level")
        phases = definition.get("phases", [])
        if (
            type(phase) is int
            and type(level) is int
            and 0 <= phase < len(phases)
            and 1 <= level <= phases[phase]["max_level"]
            and all(
                key in data for key in ("experience", "level_gold", "promotion_gold")
            )
        ):
            add(promotion_materials({}, definition, data, (phase, level)))
        else:
            incomplete = True
        basic = char.get("mainSkillLevel")
        levels = definition.get("basic_skills", [])
        if type(basic) is int and 1 <= basic <= 7 and len(levels) >= basic - 1:
            for rows in levels[: basic - 1]:
                add(rows)
        else:
            incomplete = True

    definitions = skills.get("characters", {}).get(char["id"], {}).get("skills", [])
    by_id = {skill.get("skillId"): skill for skill in definitions}
    for index, skill in enumerate(char.get("skills", [])):
        level = skill.get("level", 0)
        if not level:
            continue
        skill_definition = by_id.get(skill.get("id"))
        if skill_definition is None and index < len(definitions):
            skill_definition = definitions[index]
        levels = (skill_definition or {}).get("levels", [])
        if type(level) is not int or not 0 <= level <= 3 or len(levels) < level:
            incomplete = True
            continue
        for stage in levels[:level]:
            add(stage.get("materials", []))

    modules = {module["id"]: module for module in definition.get("modules", [])}
    owned = {}
    for equip in char.get("equips", []):
        level = equip.get("level", 0)
        if type(level) is int and level > 0:
            owned[equip["id"]] = max(owned.get(equip["id"], 0), level)
    for mid, level in owned.items():
        if mid not in modules:
            # Default equipment is not an unlocked module.
            if not mid.startswith("uniequip_001_"):
                incomplete = True
            continue
        module = modules[mid]
        levels = module.get("levels") or [
            {"level": 1, "materials": module.get("materials", [])}
        ]
        stages = {stage["level"]: stage["materials"] for stage in levels}
        for stage in range(1, level + 1):
            if stage not in stages:
                incomplete = True
                continue
            add(stages[stage])
            module_blocks += sum(
                row["count"] for row in stages[stage] if row["id"] == "mod_unlock_token"
            )
    return materials, module_blocks, incomplete


def consumed_statistics(chars, skills, data, catalog=None):
    """Return rarity totals and explicit coverage limits for each observed roster."""
    catalog = catalog or price_catalog()
    prices = {iid: row["value"] for iid, row in catalog["items"].items()}
    if "2003" in prices:
        prices["growth_exp"] = prices["2003"] / 1000
    result = {
        str(r): {
            "sanity_value": 0,
            "module_blocks": 0,
            "consumed_lmd": 0,
            "consumed_exp": 0,
            "skill_book_equivalent": 0,
            "sanity_unpriced": [],
            "sanity_incomplete": [],
            "sanity_source": catalog["_meta"],
        }
        for r in range(6, 0, -1)
    }
    unknown = {r: Counter() for r in result}
    definitions = data.get("characters", {})
    seen_chars, seen_progression = set(), set()
    # Shared progression belongs to the original form when it is present.
    chars = sorted(
        chars,
        key=lambda c: (
            definitions.get(c["id"], {}).get("progression_owner", c["id"]) != c["id"]
        ),
    )
    for char in chars:
        cid = char["id"]
        definition = definitions.get(cid, {})
        rarity = str(definition.get("rarity"))
        if rarity not in result or cid in seen_chars:
            continue
        seen_chars.add(cid)
        owner = definition.get("progression_owner", cid)
        materials, blocks, incomplete = consumed_materials(
            char, definition, data, skills, shared=owner not in seen_progression
        )
        seen_progression.add(owner)
        row = result[rarity]
        row["module_blocks"] += blocks
        row["consumed_lmd"] += materials["4001"]
        row["consumed_exp"] += materials["growth_exp"]
        row["skill_book_equivalent"] += (
            materials["3301"] / 9 + materials["3302"] / 3 + materials["3303"]
        )
        if incomplete:
            row["sanity_incomplete"].append(definition.get("name", cid))
        for iid, count in materials.items():
            if iid in prices:
                row["sanity_value"] += count * prices[iid]
            else:
                unknown[rarity][iid] += count
    for rarity, row in result.items():
        row["sanity_value"] = round(row["sanity_value"], 2)
        row["skill_book_equivalent"] = round(row["skill_book_equivalent"], 2)
        row["sanity_unpriced"] = [
            {
                "id": iid,
                "name": skills.get("items", {}).get(iid, {}).get("name", iid),
                "count": count,
            }
            for iid, count in sorted(unknown[rarity].items())
        ]
    return result
