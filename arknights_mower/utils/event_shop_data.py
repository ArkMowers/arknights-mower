"""Compile verified activity UI layouts into resource-only shop navigation data."""

import json
import math
from pathlib import Path

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


def compile_activity_shops(activity_table, layouts):
    result = []
    if not isinstance(layouts, dict) or len(layouts) > 128:
        raise ValueError("活动商店布局格式无效")
    for activity_id, layout in layouts.items():
        info = activity_table.get("basicInfo", {}).get(activity_id)
        if not info:
            raise ValueError(f"活动表缺少已适配活动：{activity_id}")
        if info.get("templateShopId") != layout["shop_id"]:
            raise ValueError(f"活动商店身份不匹配：{activity_id}")
        rects = [button_rect(chain) for chain in layout["chains"]]
        if not rects or any(
            any(abs(a - b) > 1e-3 for a, b in zip(rects[0], rect)) for rect in rects[1:]
        ):
            raise ValueError(f"活动商店多套布局位置不一致：{activity_id}")
        left, top, right, bottom = rects[0]
        title = layout["confirm_text"]
        start, end = info["startTime"], info["rewardEndTime"]
        if not isinstance(title, str) or not title.strip() or len(title) > 128:
            raise ValueError(f"活动商店标题无效：{activity_id}")
        if type(start) is not int or type(end) is not int or not 0 < start < end:
            raise ValueError(f"活动商店开放时间无效：{activity_id}")
        result.append(
            {
                "activity": info["name"],
                "start_ts": start,
                "end_ts": end,
                "x": math.floor((left + right) / 2 + 0.5),
                "y": math.floor((top + bottom) / 2 + 0.5),
                "confirm_text": title,
            }
        )
    return sorted(result, key=lambda shop: (shop["start_ts"], shop["activity"]))


def write_event_shop_data(
    activity_table, output="arknights_mower/data/event_shop.json"
):
    layouts = json.loads(LAYOUTS.read_text("utf-8"))
    shops = compile_activity_shops(activity_table, layouts)
    Path(output).write_text(
        json.dumps(shops, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return shops
