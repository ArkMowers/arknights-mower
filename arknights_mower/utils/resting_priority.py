"""宿舍候选、分床和重排共用的排班身份与心情排序。"""

from enum import IntEnum


class RestingTier(IntEnum):
    PRIORITY = 0
    MAIN = 1
    LOW_MAIN = 2
    PRIORITY_REPLACEMENT = 3
    STANDBY = 4
    REPLACEMENT = 5
    IDLE = 6
    EXCLUDED = 7


def _replacement_tier(op_data, name):
    if getattr(op_data, "experimental_dorm_logic", False) and name in getattr(
        op_data.config, "resting_priority_replacement", ()
    ):
        return RestingTier.PRIORITY_REPLACEMENT
    return RestingTier.REPLACEMENT


def resting_tier(op_data, name):
    op = op_data.operators.get(name)
    if name in op_data.config.free_blacklist or (op is not None and op.workaholic):
        return RestingTier.EXCLUDED
    if name in op_data.config.ope_resting_priority:
        return RestingTier.PRIORITY
    if op is not None:
        if (op.room == "train" and op.index == 0) or (
            op.current_room == "train" and op.current_index == 0
        ):
            return _replacement_tier(op_data, name)
        if op.is_high():
            if (
                getattr(op_data, "experimental_dorm_logic", False)
                and op.resting_priority == "standby"
                and getattr(op, "standby_low_priority", False)
            ):
                return RestingTier.LOW_MAIN
            return {
                "high": RestingTier.MAIN,
                "low": RestingTier.LOW_MAIN,
                "standby": RestingTier.STANDBY,
            }[op.resting_priority]
        if getattr(op, "resting_from_train", False):
            return _replacement_tier(op_data, name)
    # 菲亚梅塔的名单是充能目标，不是普通替班。
    if any(
        name in slot.replacement
        for slots in op_data.plan.values()
        for slot in slots
        if slot.agent != "菲亚梅塔"
    ):
        return _replacement_tier(op_data, name)
    return RestingTier.IDLE


def has_resting_mood(op, now=None):
    """是否有可用于恢复计时等操作的真实心情读数。"""
    return (
        op is not None
        and op.time_stamp is not None
        and 0 <= op.mood <= 24
        and 0 <= op.current_mood(now) <= 24
    )


def resting_mood(op, now=None):
    """没有有效缓存时沿用默认 24 心情，读到实际心情后再更新。"""
    return op.current_mood(now) if has_resting_mood(op, now) else 24


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
