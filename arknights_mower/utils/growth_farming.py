"""Bind outstanding chip requirements to the selected MAA weekly plan."""

import json
from copy import deepcopy

from arknights_mower import __rootdir__
from arknights_mower.utils.maa_stage_inventory import DEFAULT_STAGE_DROP_IDS

RESOURCE_STAGE_OPEN_DAYS = json.loads(
    (__rootdir__ / "data" / "resource_stage_open_days.json").read_text("utf-8")
)


def chip_farming_plan(plan, inventory_config, summary, *, filter_by_availability=True):
    missing = {row["id"] for row in summary["missing"] if row["count"] > 0}
    needs = {row["id"]: row for row in summary["materials"] if row["id"] in missing}
    rules = []
    for stage, drops in DEFAULT_STAGE_DROP_IDS.items():
        if not stage.startswith("PR-") and stage != "AP-5":
            continue
        items = [
            {
                "item_id": iid,
                "item_name": needs[iid]["name"],
                "limit": needs[iid]["required"],
            }
            for iid in drops
            if iid in needs
        ]
        if items:
            rules.append(
                {"stage": stage, "operator": "and", "enabled": True, "items": items}
            )
    stages = [rule["stage"] for rule in rules]
    config = deepcopy(inventory_config)
    if not stages:
        return deepcopy(plan), config, stages
    # One current requirement rule replaces all old rules for each affected stage;
    # an old OR rule must not stop farming when only the unrelated drop is full.
    config["enabled"] = True
    config["limit_rules"] = [
        rule for rule in config.get("limit_rules", []) if rule["stage"] not in stages
    ] + rules
    for rule in config.get("ratio_rules", []):
        rule["members"] = [
            member
            for member in rule.get("members", [])
            if member.get("stage") not in stages
        ]
    result = deepcopy(plan)
    for day in result:
        weekday = day.get("weekday")
        scheduled = [
            stage
            for stage in stages
            if not filter_by_availability
            or weekday in RESOURCE_STAGE_OPEN_DAYS[stage.rsplit("-", 1)[0]]
        ]
        if not scheduled:
            continue
        existing = day.get("stage", [])
        day["stage"] = (
            (["Annihilation"] if "Annihilation" in existing else [])
            + scheduled
            + [
                stage
                for stage in existing
                if stage not in scheduled and stage != "Annihilation"
            ]
        )
    return result, config, stages
