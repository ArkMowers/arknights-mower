"""Compile fixed workshop bonuses, including material-specific conditions."""

import re


def compile_workshop_buff(buff):
    if buff.get("roomType") != "WORKSHOP":
        return []
    text = re.sub(r"<[^>]*>", "", buff["description"])
    if "累积40点因果必定产出一次副产品" in text:
        return [{"kind": "causality"}]
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
    return [rule]


def compile_workshop_data(characters, building):
    rules = {
        key: compile_workshop_buff(buff) for key, buff in building["buffs"].items()
    }
    operators = {}
    for cid, char in characters.items():
        if not cid.startswith("char_") or char.get("isNotObtainable"):
            continue
        groups = []
        for group in building.get("chars", {}).get(cid, {}).get("buffChar", []):
            versions = [
                {
                    "elite": int(str(ref["cond"]["phase"]).removeprefix("PHASE_")),
                    "level": ref["cond"]["level"],
                    "effects": rules.get(ref["buffId"], []),
                }
                for ref in group["buffData"]
            ]
            # Empty upgrades replace their predecessor too.
            if any(v["effects"] for v in versions):
                groups.append(versions)
        if groups:
            operators[cid] = {"name": char["name"], "groups": groups}
    return {"version": 1, "operators": operators}
