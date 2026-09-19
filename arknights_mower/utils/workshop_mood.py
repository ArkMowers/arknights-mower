"""Fixed workshop mood costs, using existing operator mood and unlocked skills."""

import json
import re
from functools import lru_cache
from pathlib import Path


def compile_mood_buff(buff):
    if buff.get("roomType") != "WORKSHOP":
        return []
    text = re.sub(r"<[^>]*>", "", buff.get("description", ""))
    scope = re.match(r"进驻加工站加工(.+?)时，", text)
    if not scope or "宿舍内" in text or "每" in text:
        return []  # Conditional reductions/refunds are not needed for a safe budget.
    tabs = {
        "任意类材料": [],
        "精英材料": ["精英材料"],
        "基建材料": ["基建材料"],
        "技巧概要": ["技巧概要"],
        "芯片": ["芯片"],
    }
    rule = {"kind": "mood_cost", "tabs": tabs.get(scope[1], ["精英材料"])}
    if scope[1] not in tabs:
        material = scope[1].removesuffix("材料")
        rule["family" if material.endswith("类") else "item"] = material.removesuffix(
            "类"
        )
    if match := re.search(r"心情消耗恒定为(\d+)", text):
        rule.update(mode="fixed", value=int(match[1]))
    elif match := re.search(r"相应配方全部\+(\d+)心情消耗", text):
        rule.update(mode="add", value=int(match[1]))
    elif match := re.search(
        r"心情消耗为(\d+)(以上)?的配方全部(除以|-)(\d+)心情消耗", text
    ):
        rule["min_cost" if match[2] else "original_cost"] = int(match[1])
        rule.update(
            mode="divide" if match[3] == "除以" else "subtract", value=int(match[4])
        )
    elif match := re.search(r"全部心情消耗-(\d+)", text):
        rule.update(mode="subtract", value=int(match[1]))
    else:
        return []
    return [rule]


@lru_cache(maxsize=1)
def _bundled_moods():
    return json.loads(
        (Path(__file__).parents[1] / "data/skill_data.json").read_text("utf-8")
    )["workshop"].get("mood_operators", {})


def operator_mood_rules(name):
    from arknights_mower.utils.mastery_recommendation import get_skill_data
    from arknights_mower.utils.workshop_data import (
        WorkshopRecommendationError,
        owned_roster,
        unlocked,
    )

    metadata = (
        get_skill_data().get("workshop", {}).get("mood_operators", _bundled_moods())
    )
    entry = next(
        ((cid, meta) for cid, meta in metadata.items() if meta["name"] == name), None
    )
    if entry is None:
        return [], True
    cid, meta = entry
    try:
        character = next((char for char in owned_roster() if char["id"] == cid), None)
    except WorkshopRecommendationError:
        character = None
    if character is not None:
        return unlocked(meta, character), True
    # Manual selections without BOX must not assume an unlocked reduction.
    return [
        effect
        for group in meta["groups"]
        for version in group
        for effect in version["effects"]
    ], False


def mood_cost(name, recipe, rules, known=True):
    original = recipe["apCost"]
    cost = original
    for rule in rules:
        if (
            (rule["tabs"] and recipe["tab"] not in rule["tabs"])
            or ("item" in rule and rule["item"] != name)
            or ("family" in rule and rule["family"] not in name)
            or ("original_cost" in rule and rule["original_cost"] != original)
            or ("min_cost" in rule and rule["min_cost"] > original)
        ):
            continue
        mode, value = rule["mode"], rule["value"]
        if mode == "fixed":
            cost = value if known else max(cost, value)
        elif mode == "add":
            cost = cost + value if known else max(cost, original + value)
        elif known and mode == "subtract":
            cost -= value
        elif known and mode == "divide":
            cost /= value
    return max(1, cost)
