"""Select activity-specific shop coordinates and preserve plan-switch ownership."""

import json
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, model_validator

from arknights_mower.data import stage_data_full
from arknights_mower.utils.resource_pkg import resource_pkg_path


class ShopNavigation(BaseModel):
    activity: str = Field(min_length=1, max_length=256)
    start_ts: StrictInt = Field(ge=1)
    end_ts: StrictInt = Field(ge=1)
    x: StrictInt = Field(ge=0, lt=1920)
    y: StrictInt = Field(ge=0, lt=1080)
    confirm_text: Annotated[str, Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_ts >= self.end_ts:
            raise ValueError("活动商店结束时间必须晚于开始时间")
        return self


def activity_shops(now):
    path = resource_pkg_path("arknights_mower/data/event_shop.json")
    resources = json.loads(path.read_text("utf-8")) if path.is_file() else []
    if not isinstance(resources, list) or len(resources) > 128:
        raise ValueError("活动商店资源格式无效")
    entries = [ShopNavigation.model_validate(item) for item in resources]
    result = {}
    for item in entries:
        if item.start_ts <= now < item.end_ts:
            if item.activity in result:
                raise ValueError("活动商店资源存在重叠时段")
            result[item.activity] = item.model_dump()
    for stage in stage_data_full:
        window = stage.get("endTs")
        name = stage.get("zoneNameSecond")
        if (
            stage.get("stageType") == "ACTIVITY"
            and isinstance(name, str)
            and name
            and isinstance(window, dict)
            and isinstance(window.get("startTs"), (int, float))
            and isinstance(window.get("endTs"), (int, float))
            and window["startTs"] <= now < window["endTs"]
            and name not in result
        ):
            result[name] = {
                "activity": name,
                "start_ts": window["startTs"],
                "end_ts": window["endTs"],
                "x": None,
                "y": None,
                "confirm_text": "",
            }
    return list(result.values())


def select_shop(conf, now):
    item = next(
        (item for item in activity_shops(now) if item["activity"] == conf.activity),
        None,
    )
    if item is None:
        return None
    if conf.custom_entry:
        item.update(x=conf.x, y=conf.y, confirm_text=conf.confirm_text)
    return (
        item
        if item["x"] is not None and item["y"] is not None and item["confirm_text"]
        else None
    )


def weekly_plan_uses_activity(manager, activity):
    source = manager.get_active_plan_key()
    selected = set(manager._plan_stage_ids(manager.get_plan(source)))
    return any(
        stage.get("stageType") == "ACTIVITY"
        and stage.get("zoneNameSecond") == activity
        and (stage.get("id") or stage.get("code")) in selected
        for stage in stage_data_full
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
