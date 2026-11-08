"""Resolve activity ownership and chapters from one resource generation."""

import re


def resolve_activity_stage(target, stages, shop_for_activity):
    stages = list(stages)
    exact = next(
        (s for s in stages if target in (s.get("id"), s.get("name"), s.get("code"))),
        None,
    )
    if exact is not None:
        return exact
    match = re.fullmatch(r"([A-Z0-9]+)-(EX|S)-\d+", target)
    if match is None:
        return None
    related = [
        s
        for s in stages
        if s.get("stageType") == "ACTIVITY"
        and (s.get("id") or s.get("code") or "").startswith(match[1] + "-")
    ]
    activities = {s.get("zoneNameSecond") for s in related}
    if len(activities) != 1:
        return None
    activity = next(iter(activities))
    title = shop_for_activity(activity).get("chapters", {}).get(match[2].lower())
    if not title:
        return None
    return {
        "id": target,
        "name": target,
        "stageType": "ACTIVITY",
        "zoneNameSecond": activity,
        "subTitle": title,
        "endTs": related[0].get("endTs"),
    }
