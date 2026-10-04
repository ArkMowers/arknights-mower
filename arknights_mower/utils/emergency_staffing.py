"""用户救急主表的临时上岗资格检查。"""

from math import isfinite

from arknights_mower.utils.operators import Operator


def worker_block_reason(data, name, mood, reserved, *, allow_zero=True):
    if name in reserved:
        return "已被其他任务预约"
    if name == "菲亚梅塔":
        return "菲亚梅塔保留在充能位置"
    if mood is None or not isfinite(mood) or not 0 <= mood <= 24:
        return "心情读数未知或无效"
    op = data.operators.get(name)
    if op is None:
        op = Operator(name, "")
        data.apply_custom_mood_limits(op)
    if op.current_room == "train":
        return "正在训练室驻守"
    if (
        not allow_zero
        and not data.config.is_workaholic(name)
        and mood <= op.lower_limit
    ):
        return f"心情 {mood:.1f} 已到下限 {op.lower_limit:.1f}，无法替班"
    return None
