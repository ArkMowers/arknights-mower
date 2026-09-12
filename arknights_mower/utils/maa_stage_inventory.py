"""MAA 刷理智的库存上限与关卡比例选关实际调度逻辑。

前端 ``ui/src/utils/maa_stage_inventory.js`` 保留本模块的即时预览镜像。修改物品
解析、上限回退、比例参与条件或同分选择顺序时，需要同步更新两处实现及对应测试。
"""

import json
import os
import time
from collections.abc import Iterable
from pathlib import Path

from arknights_mower.data import key_mapping, stage_data_full
from arknights_mower.utils.path import get_path
from arknights_mower.utils.weekly_stage import select_latest_activity_stages

UNBOUND_STAGE_IDS = frozenset({"", "Annihilation"})

# 常驻关的常规掉落来自 PRTS「关卡一览 / 资源收集」及其关卡详情页。
# stage_data_full 的 MAIN / DAILY 基线没有 drop，因此在这里保留稳定映射；活动关仍从
# 可热更的 stage_data_full 动态读取 MATERIAL + NORMAL。
DEFAULT_STAGE_DROP_IDS = {
    "1-7": ["30012"],
    "LS-6": ["2004", "2003"],
    "CE-6": ["4001"],
    "AP-5": ["4006"],
    "SK-5": ["3114", "3113", "3401"],
    "CA-5": ["3303", "3302", "3301"],
    "PR-A-1": ["3231", "3261"],
    "PR-A-2": ["3232", "3262"],
    "PR-B-1": ["3241", "3251"],
    "PR-B-2": ["3242", "3252"],
    "PR-C-1": ["3211", "3271"],
    "PR-C-2": ["3212", "3272"],
    "PR-D-1": ["3221", "3281"],
    "PR-D-2": ["3222", "3282"],
}


def _value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _item_info(item_id: str) -> dict:
    info = key_mapping.get(item_id)
    if not isinstance(info, list) or len(info) < 3:
        return {"id": item_id, "name": item_id}
    return {"id": str(info[0]), "name": str(info[2])}


def normal_materials_for_stage(stage: dict | None) -> list[dict]:
    """读取关卡的 MATERIAL + NORMAL 常规掉落并按物品 id 去重。"""
    if not isinstance(stage, dict):
        return []
    result = []
    seen = set()
    for drop in stage.get("drop") or []:
        if not isinstance(drop, dict):
            continue
        if drop.get("type") != "MATERIAL" or drop.get("dropType") != "NORMAL":
            continue
        item_id = str(drop.get("id") or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        result.append(_item_info(item_id))
    return result


def default_materials_for_stage(stage_id: str, stage: dict | None = None) -> list[dict]:
    if stage_id in DEFAULT_STAGE_DROP_IDS:
        return [_item_info(item_id) for item_id in DEFAULT_STAGE_DROP_IDS[stage_id]]
    return normal_materials_for_stage(stage)


def load_inventory_snapshot(
    path: str | os.PathLike | None = None,
) -> tuple[dict, str | None]:
    """读取 cultivate.json，返回物品 id -> 数量及更新时间。"""
    inventory_path = Path(path or get_path("@app/tmp/cultivate.json"))
    if not inventory_path.exists():
        return {}, None
    try:
        data = json.loads(inventory_path.read_text("utf-8"))
        if not isinstance(data, dict):
            return {}, None
        inventory = {}
        payload = data.get("data", {})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if item_id:
                inventory[item_id] = max(0, int(item.get("count", 0) or 0))
        updated_at = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(inventory_path.stat().st_mtime)
        )
        return inventory, updated_at
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}, None


def build_item_options() -> list[dict]:
    """返回资源包中可用于库存规则的全部物品，按 id 去重。"""
    options = {}
    for info in key_mapping.values():
        if not isinstance(info, list) or len(info) < 4:
            continue
        item_id = str(info[0])
        name = str(info[2])
        if not item_id or not name:
            continue
        options.setdefault(
            item_id,
            {
                "value": item_id,
                "label": name,
                "id": item_id,
                "name": name,
                "type": str(info[3]),
            },
        )
    return sorted(options.values(), key=lambda item: (item["label"], item["value"]))


def _iter_plan_stages(weekly_plan: Iterable) -> Iterable[str]:
    for plan in weekly_plan or []:
        for stage in _value(plan, "stage", []) or []:
            if isinstance(stage, str):
                yield stage.strip()


def build_stage_options(
    weekly_plan: Iterable = (),
    limit_rules: Iterable = (),
    ratio_rules: Iterable = (),
    now: int | None = None,
) -> tuple[list[dict], dict | None]:
    """构造可绑定关卡，并给出当前活动的关卡-物品绑定关系。"""
    stages = list(stage_data_full)
    stage_by_id = {str(stage.get("id")): stage for stage in stages if stage.get("id")}
    activity_entries = select_latest_activity_stages(
        stages, key_mapping, int(time.time()) if now is None else now
    )
    activity_codes = [entry["code"] for entry in activity_entries]
    activity_materials = {
        entry["code"]: list(entry.get("materials") or []) for entry in activity_entries
    }

    requested = []
    requested.extend(activity_codes)
    requested.extend(DEFAULT_STAGE_DROP_IDS)
    requested.extend(_iter_plan_stages(weekly_plan))
    requested.extend(
        str(_value(rule, "stage", "") or "").strip() for rule in limit_rules or []
    )
    for rule in ratio_rules or []:
        requested.extend(
            str(_value(member, "stage", "") or "").strip()
            for member in (_value(rule, "members", []) or [])
        )

    options = []
    seen = set()
    for stage_id in requested:
        if not stage_id or stage_id in UNBOUND_STAGE_IDS or stage_id in seen:
            continue
        seen.add(stage_id)
        stage = stage_by_id.get(stage_id)
        materials = (
            activity_materials[stage_id]
            if stage_id in activity_materials
            else default_materials_for_stage(stage_id, stage)
        )
        material_names = "、".join(item["name"] for item in materials)
        options.append(
            {
                "value": stage_id,
                "label": f"{stage_id}：{material_names}"
                if material_names
                else stage_id,
                "code": stage_id,
                "activity": stage_id in activity_codes,
                "materials": materials,
            }
        )

    suggestion_members = []
    used_items = set()
    option_by_stage = {option["value"]: option for option in options}
    for stage_id in activity_codes:
        option = option_by_stage.get(stage_id)
        if not option or not option["materials"]:
            continue
        material = next(
            (item for item in option["materials"] if item["id"] not in used_items),
            None,
        )
        if material is None:
            continue
        used_items.add(material["id"])
        suggestion_members.append(
            {
                "stage": stage_id,
                "item_id": material["id"],
                "item_name": material["name"],
                "ratio": 0,
            }
        )
    suggestion = None
    if len(suggestion_members) >= 2:
        suggestion = {
            "name": "当前活动绑定",
            "enabled": True,
            "members": suggestion_members,
        }
    return options, suggestion


def _rule_item_count(item, inventory: dict) -> int:
    item_id = str(_value(item, "item_id", "") or "").strip()
    item_name = str(_value(item, "item_name", "") or "").strip()
    candidates = [item_id]
    for key in (item_id, item_name):
        info = key_mapping.get(key)
        if isinstance(info, list) and info:
            candidates.append(str(info[0]))
    return max(
        (
            int(inventory.get(candidate, 0) or 0)
            for candidate in candidates
            if candidate
        ),
        default=0,
    )


def _stage_limit_reached(stage: str, limit_rules: Iterable, inventory: dict) -> bool:
    for rule in limit_rules or []:
        if not _value(rule, "enabled", True):
            continue
        if str(_value(rule, "stage", "") or "").strip() != stage:
            continue
        active_items = []
        for item in _value(rule, "items", []) or []:
            limit = int(_value(item, "limit", 0) or 0)
            if limit > 0 and (
                _value(item, "item_id", "") or _value(item, "item_name", "")
            ):
                active_items.append(_rule_item_count(item, inventory) >= limit)
        if not active_items:
            continue
        operator = str(_value(rule, "operator", "and") or "and").lower()
        if any(active_items) if operator == "or" else all(active_items):
            return True
    return False


def _apply_ratio_rules(stages: list[str], ratio_rules: Iterable, inventory: dict):
    kept = list(stages)
    decisions = []
    claimed_stages = set()
    stage_positions = {stage: index for index, stage in enumerate(stages)}

    for rule in ratio_rules or []:
        if not _value(rule, "enabled", True):
            continue
        candidates = []
        seen = set()
        for member in _value(rule, "members", []) or []:
            stage = str(_value(member, "stage", "") or "").strip()
            ratio = float(_value(member, "ratio", 0) or 0)
            if (
                not stage
                or stage in seen
                or stage in claimed_stages
                or stage not in kept
                or ratio <= 0
            ):
                continue
            seen.add(stage)
            count = _rule_item_count(member, inventory)
            candidates.append(
                {
                    "stage": stage,
                    "count": count,
                    "ratio": ratio,
                    "score": count / ratio,
                }
            )
        if len(candidates) < 2:
            continue
        selected = min(
            candidates,
            key=lambda item: (item["score"], stage_positions.get(item["stage"], 10**9)),
        )
        candidate_stages = {item["stage"] for item in candidates}
        kept = [
            stage
            for stage in kept
            if stage not in candidate_stages or stage == selected["stage"]
        ]
        claimed_stages.update(candidate_stages)
        decisions.append(
            {
                "name": str(_value(rule, "name", "") or ""),
                "selected": selected["stage"],
                "candidates": candidates,
            }
        )
    return kept, decisions


def select_stages_by_inventory(
    stages: Iterable[str],
    limit_rules: Iterable = (),
    ratio_rules: Iterable = (),
    inventory: dict | None = None,
) -> dict:
    """先执行物品上限，再对剩余关卡执行比例选择。"""
    original = list(stages)
    inventory = inventory or {}
    kept = []
    limit_skipped = []
    for stage in original:
        if stage in UNBOUND_STAGE_IDS or not _stage_limit_reached(
            stage, limit_rules, inventory
        ):
            kept.append(stage)
        else:
            limit_skipped.append(stage)

    # 所有候选都达到上限时，按用户约定忽略整次跳过设置，避免当天完全无关可刷。
    if original and not kept and limit_skipped:
        return {
            "stages": original,
            "limit_skipped": [],
            "limit_fallback": True,
            "ratio_decisions": [],
        }

    selected, ratio_decisions = _apply_ratio_rules(kept, ratio_rules, inventory)
    return {
        "stages": selected,
        "limit_skipped": limit_skipped,
        "limit_fallback": False,
        "ratio_decisions": ratio_decisions,
    }
