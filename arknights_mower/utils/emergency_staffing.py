"""用户救急主表的临时上岗资格检查。"""

from math import isfinite

from arknights_mower.utils.operators import Operator


def eligible_worker(data, name, mood, reserved):
    if name in reserved or name == "菲亚梅塔":
        return False
    if mood is None or not isfinite(mood) or not 0 <= mood <= 24:
        return False
    op = data.operators.get(name)
    if op is None:
        op = Operator(name, "")
        data.apply_custom_mood_limits(op)
    if op.current_room == "train":
        return False
    return mood >= data.resting_mood_threshold(op) + 1
