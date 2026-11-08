"""Select the current SS activity and preserve plan-switch ownership."""

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

from arknights_mower.data import stage_data_full
from arknights_mower.utils.activity_stage import resolve_activity_stage
from arknights_mower.utils.resource_pkg import resource_pkg_path


class ShopNavigation(BaseModel):
    activity: str = Field(min_length=1, max_length=256)
    activity_id: str = Field(pattern=r"^act\d+(?:side|sre)$")
    entry_names: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        default_factory=list, max_length=16
    )
    chapters: dict[
        Literal["normal", "ex", "s"],
        Annotated[str, Field(min_length=1, max_length=256)],
    ] = Field(default_factory=dict)
    start_ts: StrictInt = Field(ge=1)
    end_ts: StrictInt = Field(ge=1)
    reward_end_ts: StrictInt | None = None
    token_ids: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_]+$")]] = Field(
        default_factory=list, max_length=16
    )

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_ts >= self.end_ts:
            raise ValueError("活动商店结束时间必须晚于开始时间")
        if self.reward_end_ts is not None and self.reward_end_ts < self.end_ts:
            raise ValueError("商店领取截止时间不能早于活动结束时间")
        return self


def activity_shops(now):
    path = resource_pkg_path("arknights_mower/data/event_shop.json")
    resources = json.loads(path.read_text("utf-8")) if path.is_file() else []
    if not isinstance(resources, list) or len(resources) > 128:
        raise ValueError("活动商店资源格式无效")
    entries = []
    for raw in resources:
        if not isinstance(raw, dict):
            raise ValueError("SS 活动信息格式无效")
        if "activity_id" not in raw:
            legacy = set()
            for stage in stage_data_full:
                window = stage.get("endTs")
                match = re.fullmatch(
                    r"(act\d+(?:side|sre))_zone\d+", stage.get("zoneId") or ""
                )
                if (
                    stage.get("zoneNameSecond") == raw.get("activity")
                    and stage.get("stageType") == "ACTIVITY"
                    and match
                    and isinstance(window, dict)
                    and type(window.get("startTs")) is int
                    and type(window.get("endTs")) is int
                ):
                    legacy.add((match[1], window["startTs"], window["endTs"]))
            if len(legacy) != 1:
                continue
            activity_id, start, end = next(iter(legacy))
            if (
                raw.get("start_ts") != start
                or type(raw.get("end_ts")) is not int
                or raw["end_ts"] < end
            ):
                continue
            raw = {
                **raw,
                "activity_id": activity_id,
                "start_ts": start,
                "end_ts": end,
                "reward_end_ts": raw.get("end_ts"),
            }
        entries.append(ShopNavigation.model_validate(raw))
    result = {}
    for item in entries:
        if item.start_ts <= now < item.end_ts:
            if item.activity in result:
                raise ValueError("活动商店资源存在重叠时段")
            result[item.activity] = item.model_dump(exclude_unset=True)
    return list(result.values())


def select_shop(manager, now):
    shops = activity_shops(now)
    if not shops:
        return None
    latest = max(shop["start_ts"] for shop in shops)
    current = [shop for shop in shops if shop["start_ts"] == latest]
    if len(current) != 1 or not weekly_plan_uses_activity(
        manager, current[0]["activity"], shop=current[0]
    ):
        return None
    return current[0]


def weekly_plan_uses_activity(manager, activity, *, shop=None):
    source = manager.get_active_plan_key()
    selected = set(manager._plan_stage_ids(manager.get_plan(source)))

    def shop_for_activity(name):
        if name != activity:
            return {}
        if shop is not None:
            return shop
        return next(
            (
                item
                for item in activity_shops(manager._current_server_timestamp())
                if item["activity"] == name
            ),
            {},
        )

    return any(
        stage.get("stageType") == "ACTIVITY" and stage.get("zoneNameSecond") == activity
        for code in selected
        if (stage := resolve_activity_stage(code, stage_data_full, shop_for_activity))
    )


def shop_params(conf):
    return {
        "task_names": ["SS@Store@Begin"],
        "params": {"event_shop": {"blacklist": conf.blacklist}},
    }


def switch_after_shop(task, conf, manager):
    if (
        not task.get("finite_done")
        or not task.get("completed")
        or task["settings"] != conf.model_dump()
        or not conf.switch_source
        or task["source"] != conf.switch_source
        or not conf.enable
        or manager.get_active_plan_key() != task["source"]
        or manager.get_active_plan_revision() != task["revision"]
        or manager.get_activity_fallbacks().get(task["source"]) != task["target"]
        or not task["target"]
    ):
        return False
    return manager.set_active_plan(task["target"])
