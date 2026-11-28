"""Compile SS chapter and currency navigation data from game tables."""

import json
import math
import re
from pathlib import Path
from time import time

FRAME = (1920, 1080)
LAYOUTS = Path(__file__).resolve().parents[1] / "data/event_shop_layouts.json"


def button_rect(chain):
    """Resolve root-to-button RectTransforms into top-left screen coordinates."""
    if not chain or len(chain) > 64:
        raise ValueError("活动商店按钮层级为空或过深")
    size, pivot, position, scale = list(FRAME), [0, 0], [0, 0], [1, 1]
    for node in chain:
        rotation = node["m_LocalRotation"]
        if any(
            abs(rotation[key]) > 1e-6 for key in ("x", "y", "z")
        ) or not math.isclose(abs(rotation["w"]), 1, abs_tol=1e-6):
            raise ValueError("活动商店按钮存在未支持的旋转，不能生成精确坐标")
        next_size, next_position, next_scale = [], [], []
        for index, axis in enumerate(("x", "y")):
            low = node["m_AnchorMin"][axis]
            high = node["m_AnchorMax"][axis]
            own_pivot = node["m_Pivot"][axis]
            extent = size[index] * (high - low) + node["m_SizeDelta"][axis]
            offset = (
                size[index] * (low + (high - low) * own_pivot - pivot[index])
                + node["m_AnchoredPosition"][axis]
            )
            own_scale = scale[index] * node["m_LocalScale"][axis]
            if not all(math.isfinite(value) for value in (extent, offset, own_scale)):
                raise ValueError("活动商店按钮布局含无效数值")
            if extent <= 0 or own_scale <= 0:
                raise ValueError("活动商店按钮尺寸或缩放无效")
            next_size.append(extent)
            next_position.append(position[index] + offset * scale[index])
            next_scale.append(own_scale)
        size, position, scale = next_size, next_position, next_scale
        pivot = [node["m_Pivot"][axis] for axis in ("x", "y")]
    left = position[0] - pivot[0] * size[0] * scale[0]
    right = left + size[0] * scale[0]
    bottom = FRAME[1] - (position[1] - pivot[1] * size[1] * scale[1])
    top = bottom - size[1] * scale[1]
    if not (0 <= left < right <= FRAME[0] and 0 <= top < bottom <= FRAME[1]):
        raise ValueError("活动商店按钮超出 1920×1080 画面")
    return left, top, right, bottom


def compile_activity_shops(activity_table, *, zones, stages, items=None, now=None):
    """生成已开放和下一期已预载的 SS 导航信息。"""
    basic = activity_table.get("basicInfo")
    if (
        not isinstance(basic, dict)
        or not isinstance(zones, dict)
        or not isinstance(stages, dict)
    ):
        raise ValueError("SS 活动生成输入不完整")
    now = time() if now is None else now
    items = {} if items is None else items
    zone_to_activity = activity_table.get("zoneToActivity", {})
    windows = []
    for activity_id, info in basic.items():
        if not re.fullmatch(r"act\d+(?:side|sre)", activity_id):
            continue
        if not info.get("hasStage") or not info.get("templateShopId"):
            continue
        start, end, reward_end = (
            info["startTime"],
            info["endTime"],
            info["rewardEndTime"],
        )
        if (
            any(type(value) is not int for value in (start, end, reward_end))
            or not 0 < start < end <= reward_end
        ):
            raise ValueError(f"SS 活动开放时间无效：{activity_id}")
        if now < end:
            windows.append((start, end, reward_end, activity_id, info["name"]))

    next_start = min((start for start, *_ in windows if start > now), default=None)
    result = []
    for start, end, reward_end, activity_id, name in windows:
        upcoming = start > now
        if upcoming and start != next_start:
            continue
        zone_ids = {
            key for key, value in zone_to_activity.items() if value == activity_id
        }
        if not zone_ids or any(zone not in zones for zone in zone_ids):
            if upcoming:
                continue
            raise ValueError(f"SS 活动缺少章节信息：{activity_id}")
        related = [
            stage for stage in stages.values() if stage.get("zoneId") in zone_ids
        ]
        if not related:
            if upcoming:
                continue
            raise ValueError(f"SS 活动缺少关卡信息：{activity_id}")
        chapters, tokens = {}, set()
        titles = {
            zone_id: next(
                (
                    zones[zone_id][key]
                    for key in ("zoneNameSecond", "zoneNameFirst", "zoneNameThird")
                    if zones[zone_id].get(key)
                ),
                None,
            )
            for zone_id in zone_ids
        }
        if not all(titles.values()):
            if upcoming:
                continue
            raise ValueError(f"SS 活动章节名称为空：{activity_id}")
        for stage in related:
            title = titles[stage["zoneId"]]
            code = stage.get("code") or ""
            kind = "ex" if "-EX-" in code else "s" if "-S-" in code else "normal"
            chapters.setdefault(kind, set()).add(title)
            tokens.update(
                item["id"]
                for item in (stage.get("stageDropInfo") or {}).get(
                    "displayDetailRewards"
                )
                or []
                if item.get("type") == "ACTIVITY_ITEM"
                and re.fullmatch(r"[A-Za-z0-9_]+", item.get("id", ""))
            )
        for zone_id in sorted(zone_ids - {stage["zoneId"] for stage in related}):
            # 三区式 SS 的后续关卡可能尚未进入关卡表，章节标题已在区域表中。
            suffix = re.fullmatch(re.escape(activity_id) + r"_zone([123])", zone_id)
            if suffix:
                kind = {"1": "normal", "2": "ex", "3": "s"}[suffix[1]]
                chapters.setdefault(kind, set()).add(titles[zone_id])
        if not tokens:
            if upcoming:
                continue
            raise ValueError(f"SS 活动缺少代币信息：{activity_id}")
        icon_ids = {items.get(token, {}).get("iconId") for token in tokens}
        aliases = sorted(
            icon
            for icon in icon_ids - tokens
            if re.fullmatch(r"[A-Za-z0-9_]+", icon or "")
        )
        result.append(
            {
                "activity": name.replace("·复刻", "").strip(),
                "activity_id": activity_id,
                "start_ts": start,
                "end_ts": end,
                "reward_end_ts": reward_end,
                "entry_names": sorted(set(titles.values())),
                "chapters": {
                    key: next(iter(chapters[key]))
                    for key in ("normal", "ex", "s")
                    if key in chapters and len(chapters[key]) == 1
                },
                "token_ids": sorted(tokens),
                **({"token_icon_ids": aliases} if aliases else {}),
            }
        )
    return sorted(result, key=lambda shop: (shop["start_ts"], shop["activity"]))


def write_event_shop_data(
    activity_table,
    output="arknights_mower/data/event_shop.json",
    *,
    zones,
    stages,
    items=None,
    now=None,
):
    shops = compile_activity_shops(
        activity_table, zones=zones, stages=stages, items=items, now=now
    )
    Path(output).write_text(
        json.dumps(shops, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return shops
