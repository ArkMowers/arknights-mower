"""宿舍候选、分床和重排共用的排班身份与心情排序。"""

from enum import IntEnum


class RestingTier(IntEnum):
    PRIORITY = 0
    MAIN = 1
    LOW_MAIN = 2
    STANDBY = 3
    REPLACEMENT = 4
    IDLE = 5
    EXCLUDED = 6


def resting_tier(op_data, name):
    op = op_data.operators.get(name)
    if name in op_data.config.free_blacklist or (op is not None and op.workaholic):
        return RestingTier.EXCLUDED
    if name in op_data.config.ope_resting_priority:
        return RestingTier.PRIORITY
    if op is not None:
        if op.is_workshop():
            return RestingTier.IDLE
        if (op.room == "train" and op.index == 0) or (
            op.current_room == "train" and op.current_index == 0
        ):
            return RestingTier.REPLACEMENT
        if op.is_high():
            return {
                "high": RestingTier.MAIN,
                "low": RestingTier.LOW_MAIN,
                "standby": RestingTier.STANDBY,
            }[op.resting_priority]
        if getattr(op, "resting_from_train", False):
            return RestingTier.REPLACEMENT
    # 菲亚梅塔的名单是充能目标，不是普通替班。
    if any(
        name in slot.replacement
        for slots in op_data.plan.values()
        for slot in slots
        if slot.agent != "菲亚梅塔"
    ):
        return RestingTier.REPLACEMENT
    return RestingTier.IDLE


def resting_mood(op, now=None):
    """无有效读数时排在同级末尾，也不能据未知心情踢出休息者。"""
    if op is None or op.time_stamp is None or not 0 <= op.mood <= 24:
        return float("inf")
    mood = op.current_mood(now)
    return mood if 0 <= mood <= 24 else float("inf")


def resting_key(op_data, name, now=None):
    return resting_tier(op_data, name), resting_mood(op_data.operators.get(name), now)


def busy_resting_names():
    """每次候选扫描只读一次专精状态，不为全部干员逐个查询数据库。"""
    from arknights_mower.utils import config

    if not config.conf.enable_mastery:
        return set()
    from arknights_mower.utils.mastery_db import _resolve_char_name, get_active_plan

    active = get_active_plan()
    if active is None:
        return set()
    name = active.get("char_name") or _resolve_char_name(active["char_id"])
    return {name} if name else set()
