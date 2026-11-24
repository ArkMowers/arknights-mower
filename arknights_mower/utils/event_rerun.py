import re

from arknights_mower.data import stage_data_full
from arknights_mower.utils.maa_event_shop import activity_shops

STAGE_SECONDS = 240


def current_rerun():
    from arknights_mower.utils.config.weekly_plan_loader import WeeklyPlanManager

    now = WeeklyPlanManager._current_server_timestamp()
    return select_rerun(activity_shops(now), stage_data_full, now)


def select_rerun(activities, stages, now):
    available = [
        activity
        for activity in activities
        if activity["activity_id"].endswith("sre")
        and activity["start_ts"] <= now < activity["end_ts"]
    ]
    if not available:
        return None
    latest = max(item["start_ts"] for item in available)
    current = [item for item in available if item["start_ts"] == latest]
    if len(current) != 1:
        return None

    activity = current[0]
    activity_id = activity["activity_id"]
    chapters = activity.get("chapters", {})
    normal = {}
    raids = {}
    for stage in stages:
        code = stage.get("id", "")
        window = stage.get("endTs")
        if (
            stage.get("stageType") != "ACTIVITY"
            or not stage.get("zoneId", "").startswith(activity_id + "_")
            or not isinstance(window, dict)
            or not isinstance(window.get("startTs"), int)
            or not isinstance(window.get("endTs"), int)
            or not activity["start_ts"] <= window["startTs"] < window["endTs"]
            or window["endTs"] > activity["end_ts"]
            or not isinstance(stage.get("apCost"), int)
            or stage["apCost"] <= 0
        ):
            continue
        option = {
            "code": code,
            "name": stage.get("name") or code,
            "ap_cost": stage["apCost"],
            "start_ts": window["startTs"],
            "end_ts": window["endTs"],
        }
        if (
            stage.get("subTitle") == chapters.get("normal")
            and stage.get("difficulty") == "NORMAL"
            and re.fullmatch(r"[A-Z0-9]+-\d+", code)
        ):
            normal[code] = option
        elif stage.get("subTitle") == chapters.get("ex") and re.fullmatch(
            r"[A-Z0-9]+-EX-8 突袭", code
        ):
            variants = {code, code.removesuffix(" 突袭"), option["name"]}
            activity_number = activity_id.removeprefix("act").removesuffix("sre")
            for prefix in ("act", "level_act"):
                for kind in ("side", "sre"):
                    for index in ("08", "8"):
                        level = f"{prefix}{activity_number}{kind}_ex{index}"
                        variants.update((level, f"{level}#f#"))
            raids[code] = {**option, "script_stage_names": sorted(variants)}

    return {
        "key": f"{activity_id}:{latest}",
        "activity_id": activity_id,
        "name": activity["activity"],
        "now": now,
        "stages": sorted(
            normal.values(), key=lambda stage: int(stage["code"].rsplit("-", 1)[1])
        ),
        "raid": next(iter(raids.values())) if len(raids) == 1 else None,
    }
