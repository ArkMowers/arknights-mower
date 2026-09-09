"""Compile fixed workshop bonuses, including material-specific conditions."""

import re


def compile_workshop_buff(buff):
    if buff.get("roomType") == "DORMITORY":
        return [{"kind": "dormitory"}]
    if buff.get("roomType") != "WORKSHOP":
        return []
    text = re.sub(r"<[^>]*>", "", buff["description"])
    if "累积40点因果必定产出一次副产品" in text:
        return [{"kind": "causality"}]
    reduction = re.match(
        r"进驻加工站加工精英材料时，心情消耗为(\d+)的配方全部-(\d+)心情消耗", text
    )
    if reduction:
        return [
            {
                "kind": "cost_reduction",
                "categories": ["material"],
                "original_cost": int(reduction[1]),
                "reduction": int(reduction[2]),
            }
        ]
    return _compile_byproduct(text)


def _compile_byproduct(text):
    # Read the fixed part; dorm/storage-dependent extras remain conditional.
    match = re.match(
        r"进驻加工站加工(?:原始心情消耗为(\d+)的)?"
        r"(.+?)时，副产品的产出概率(?:额外)?提升(\d+)%",
        text,
    )
    if not match:
        return []
    if match[2] in {"基建材料", "芯片"}:
        return []
    return [_byproduct_rule(match)]


def _byproduct_rule(match):
    categories = {
        "任意类材料": ["material", "book"],
        "精英材料": ["material"],
        "技巧概要": ["book"],
    }
    rule = {
        "kind": "byproduct",
        "categories": categories.get(match[2], ["material"]),
        "bonus": int(match[3]),
    }
    if match[1]:
        rule["original_cost"] = int(match[1])
    if match[2] not in categories:
        scope = match[2].removesuffix("材料")
        if scope.endswith("类"):
            family = scope[:-1]
            # 双酮/酮阵列 belong to the 酮凝集 family too.
            rule["family"] = {"酮凝集": "酮"}.get(family, family)
        else:
            rule["item"] = scope
    return rule


def _compile_groups(char, rules):
    groups = []
    for group in char.get("buffChar", []):
        versions = [
            {
                "elite": int(str(ref["cond"]["phase"]).removeprefix("PHASE_")),
                "level": ref["cond"]["level"],
                "effects": rules.get(ref["buffId"], []),
            }
            for ref in group["buffData"]
        ]
        # Empty upgrades replace their predecessor too.
        if any(version["effects"] for version in versions):
            groups.append(versions)
    return groups


def _compile_operators(characters, building, rules):
    operators = {}
    for cid, char in characters.items():
        if not cid.startswith("char_") or char.get("isNotObtainable"):
            continue
        groups = _compile_groups(building.get("chars", {}).get(cid, {}), rules)
        # Dorm skills break workshop ties, but must not add dorm-only operators.
        if any(
            effect["kind"] != "dormitory"
            for group in groups
            for version in group
            for effect in version["effects"]
        ):
            operators[cid] = {"name": char["name"], "groups": groups}
    return operators


def compile_workshop_data(characters, building):
    from arknights_mower.utils.workshop_mood import compile_mood_buff

    rules = {
        key: compile_workshop_buff(buff) for key, buff in building["buffs"].items()
    }
    # Keep ingredient quantities indexed by item ID for automatic material planning.
    recipe_ingredients = {
        formula["itemId"]: {cost["id"]: cost["count"] for cost in formula["costs"]}
        for formula in building.get("workshopFormulas", {}).values()
        if formula["formulaType"] == "F_EVOLVE" and formula["count"] == 1
    }
    return {
        "version": 1,
        "operators": _compile_operators(characters, building, rules),
        "mood_operators": _compile_operators(
            characters,
            building,
            {key: compile_mood_buff(buff) for key, buff in building["buffs"].items()},
        ),
        "recipe_ingredients": recipe_ingredients,
    }
