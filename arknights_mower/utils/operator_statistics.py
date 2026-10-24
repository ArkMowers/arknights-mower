"""Personal roster statistics derived locally from observed progression."""

from collections import Counter

from arknights_mower.utils.growth import growth_data
from arknights_mower.utils.growth_value import consumed_materials, price_catalog


def personal_statistics(chars, skills, catalog=None):
    """Count obtained operators and reconstruct their completed material costs."""
    data = growth_data(skills)
    definitions = data.get("characters", {})
    catalog = catalog or price_catalog()
    prices = {iid: row["value"] for iid, row in catalog["items"].items()}
    if "2003" in prices:
        prices["growth_exp"] = prices["2003"] / 1000
    names = {iid: row.get("name", iid) for iid, row in catalog["items"].items()}
    names.update(
        {iid: row.get("name", iid) for iid, row in skills.get("items", {}).items()}
    )
    names.update({"growth_exp": "作战记录经验", "4001": "龙门币"})
    rows = {
        str(r): {
            "owned": 0,
            "available": 0,
            "elite2": 0,
            "max_level": 0,
            "module_level": 0,
            "supports_mastery": False,
            "supports_modules": False,
            "max_phase": 0,
            "max_level_limit": 0,
            "skills": {str(i): 0 for i in (1, 2, 3)},
            "modules": {str(i): 0 for i in (1, 2, 3)},
            "sanity": 0,
            "consumed_lmd": 0,
            "consumed_exp": 0,
            "module_blocks": 0,
            "skill_book_equivalent": 0,
            "materials": [],
            "ranking": [],
            "incomplete": [],
            "unpriced": [],
        }
        for r in range(6, 0, -1)
    }
    available = {r: set() for r in rows}
    for cid, definition in definitions.items():
        rarity = str(definition.get("rarity"))
        if rarity in rows:
            available[rarity].add(definition.get("progression_owner", cid))
            row = rows[rarity]
            phases = definition.get("phases", [])
            if phases:
                row["max_phase"] = max(row["max_phase"], len(phases) - 1)
                row["max_level_limit"] = max(
                    row["max_level_limit"], phases[-1]["max_level"]
                )
            row["supports_modules"] |= bool(definition.get("modules"))
            row["supports_mastery"] |= any(
                skill.get("levels")
                for skill in skills.get("characters", {}).get(cid, {}).get("skills", [])
            )
    for rarity in rows:
        rows[rarity]["available"] = len(available[rarity])

    costs = {r: Counter() for r in rows}
    rankings = {r: {} for r in rows}
    owned, counted, seen_chars = set(), set(), set()
    ordered = sorted(
        chars,
        key=lambda c: (
            definitions.get(c["id"], {}).get("progression_owner", c["id"]) != c["id"]
        ),
    )
    for char in ordered:
        cid = char["id"]
        definition = definitions.get(cid, {})
        rarity = str(definition.get("rarity"))
        if rarity not in rows or cid in seen_chars:
            continue
        seen_chars.add(cid)
        owner = definition.get("progression_owner", cid)
        row = rows[rarity]
        if owner not in owned:
            owned.add(owner)
            row["owned"] += 1
            elite2 = char.get("evolvePhase") == 2
            row["elite2"] += elite2
            phases = definition.get("phases", [])
            row["max_level"] += bool(phases) and (
                char.get("evolvePhase") == len(phases) - 1
                and char.get("level", 0) >= phases[-1]["max_level"]
            )
            row["module_level"] += elite2 and char.get("level", 0) >= {
                "6": 60,
                "5": 50,
                "4": 40,
            }.get(rarity, float("inf"))
        for skill in char.get("skills", []):
            level = str(skill.get("level", 0))
            if level in row["skills"]:
                row["skills"][level] += 1
        valid_modules = {m["id"] for m in definition.get("modules", [])}
        modules = {}
        for module in char.get("equips", []):
            if module["id"] in valid_modules:
                modules[module["id"]] = max(
                    modules.get(module["id"], 0), module.get("level", 0)
                )
        for level in modules.values():
            if str(level) in row["modules"]:
                row["modules"][str(level)] += 1

        materials, blocks, incomplete = consumed_materials(
            char, definition, data, skills, shared=owner not in counted
        )
        counted.add(owner)
        costs[rarity].update(materials)
        row["module_blocks"] += blocks
        name = definitions.get(owner, definition).get("name", owner)
        rank = rankings[rarity].setdefault(
            owner,
            {
                "char_id": owner,
                "name": name,
                "rarity": int(rarity),
                "sanity": 0,
                "unpriced": [],
                "incomplete": False,
                "forms": [],
            },
        )
        rank["forms"].append(cid)
        rank["incomplete"] |= incomplete
        if incomplete and name not in row["incomplete"]:
            row["incomplete"].append(name)
        for iid, count in materials.items():
            if iid in prices:
                rank["sanity"] += prices[iid] * count
            elif iid not in rank["unpriced"]:
                rank["unpriced"].append(iid)

    for rarity, row in rows.items():
        for iid, count in costs[rarity].items():
            if count <= 0:
                continue
            price = prices.get(iid)
            value = None if price is None else count * price
            item = {
                "id": iid,
                "name": names.get(iid, iid),
                "count": count,
                "value": price,
                "sanity": None if value is None else round(value, 2),
            }
            row["materials"].append(item)
            if value is None:
                row["unpriced"].append(
                    {"id": iid, "name": names.get(iid, iid), "count": count}
                )
            else:
                row["sanity"] += value
        row["sanity"] = round(row["sanity"], 2)
        row["consumed_lmd"] = costs[rarity]["4001"]
        row["consumed_exp"] = costs[rarity]["growth_exp"]
        row["skill_book_equivalent"] = round(
            costs[rarity]["3301"] / 9
            + costs[rarity]["3302"] / 3
            + costs[rarity]["3303"],
            2,
        )
        row["materials"].sort(
            key=lambda item: (
                item["sanity"] is None,
                -(item["sanity"] or 0),
                item["id"],
            )
        )
        for rank in rankings[rarity].values():
            rank["sanity"] = round(rank["sanity"], 2)
        row["ranking"] = sorted(
            rankings[rarity].values(),
            key=lambda rank: (-rank["sanity"], rank["char_id"]),
        )
    return {"rarities": rows, "source": catalog["_meta"]}
