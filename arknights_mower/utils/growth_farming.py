"""Select farming targets for one operator from shared confirmed inventory."""

import json
from collections import Counter
from dataclasses import dataclass

from arknights_mower import __rootdir__
from arknights_mower.utils.growth import expand_chip_costs, material_entries
from arknights_mower.utils.growth_order import crafting_projects
from arknights_mower.utils.maa_stage_inventory import DEFAULT_STAGE_DROP_IDS

RESOURCE_STAGE_OPEN_DAYS = json.loads(
    (__rootdir__ / "data" / "resource_stage_open_days.json").read_text("utf-8")
)
CHIP_STAGE_DROPS = {
    stage: drops
    for stage, drops in DEFAULT_STAGE_DROP_IDS.items()
    if stage == "AP-5" or stage.startswith("PR-")
}
FARMABLE_ITEMS = {item for drops in CHIP_STAGE_DROPS.values() for item in drops}
DUAL_CHIPS = {f"{prefix}3" for prefix in range(321, 329)}
CHIP_COST_ITEMS = FARMABLE_ITEMS | DUAL_CHIPS | {"32001"}


@dataclass(frozen=True)
class ChipFarmingTarget:
    char_id: str
    rules: dict[str, dict]


def next_chip_farming_target(box, skills, plans, goals, order, inventory):
    groups = {}
    for project in crafting_projects(plans, goals, order):
        group = groups.setdefault(project["char_id"], {"plans": [], "goals": []})
        if project["kind"] == "skill":
            group["plans"].append(project["plan"])
        else:
            group["goals"].append(project["goal"])

    chars = {char["id"]: char for char in box["characters"]}
    demand = Counter()
    for char_id, group in groups.items():
        [(_, materials)] = material_entries(
            {"characters": [chars[char_id]]}, skills, **group, crafting_only=True
        )
        for item in materials:
            if item["id"] in CHIP_COST_ITEMS:
                demand[item["id"]] += item["count"]
        if DUAL_CHIPS.intersection(demand) - inventory.keys():
            return None
        expanded = {
            row["id"]: row["count"]
            for row in expand_chip_costs(
                [{"id": item, "count": count} for item, count in demand.items()],
                inventory,
            )
        }
        if expanded.get("32001") and "32001" not in inventory:
            return None
        required = {item: expanded[item] for item in FARMABLE_ITEMS & expanded.keys()}
        if required.keys() - inventory.keys():
            return None
        limits = {
            item: count for item, count in required.items() if inventory[item] < count
        }
        if not limits:
            continue
        rules = {}
        for stage, drops in CHIP_STAGE_DROPS.items():
            items = [
                {
                    "item_id": item,
                    "item_name": skills["items"].get(item, {}).get("name", item),
                    "limit": limits[item],
                }
                for item in drops
                if item in limits
            ]
            if items:
                rules[stage] = {
                    "stage": stage,
                    "operator": "and",
                    "enabled": True,
                    "items": items,
                }
        return ChipFarmingTarget(char_id, rules)
    return None


def active_chip_farming_target(weekday, filter_by_availability):
    if type(filter_by_availability) is not bool:
        return None

    from arknights_mower.utils import config
    from arknights_mower.utils.growth import growth_resources, load_goals
    from arknights_mower.utils.log import logger
    from arknights_mower.utils.maa_stage_inventory import load_inventory_snapshot
    from arknights_mower.utils.mastery_db import get_all_plans
    from arknights_mower.utils.mastery_recommendation import get_skill_data
    from arknights_mower.utils.path import get_path

    try:
        plans, goals = get_all_plans(), load_goals()
        if not plans and not goals:
            return None
        box = json.loads(get_path("@app/tmp/cultivate.json").read_text("utf-8"))["data"]
        inventory, _ = load_inventory_snapshot()
        target = next_chip_farming_target(
            box,
            growth_resources(get_skill_data()),
            plans,
            goals,
            config.conf.growth_crafting_order,
            inventory,
        )
        if target is not None and filter_by_availability:
            return ChipFarmingTarget(
                target.char_id,
                {
                    stage: rule
                    for stage, rule in target.rules.items()
                    if weekday in RESOURCE_STAGE_OPEN_DAYS[stage.rsplit("-", 1)[0]]
                },
            )
        return target
    except (OSError, KeyError, TypeError, ValueError):
        logger.debug(
            "无法读取养成芯片刷取目标",
            exc_info=True,
            extra={"log_group": "growth-planning"},
        )
        return None
