"""加工站共用的归一化页签与导航坐标；坐标以完整游戏画面为基准。"""

FORMULA_TABS = {
    "基建材料": (0.1, 0.18),
    "精英材料": (0.1, 0.31),
    "技巧概要": (0.1, 0.45),
    "芯片": (0.1, 0.57),
    "家具": (0.1, 0.71),
}
CONFIRM_OPERATOR = (0.25, 0.95)
OPEN_FORMULA = (0.45, 0.65)
OPEN_WORKSHOP = (0.1, 0.95)


def scale_point(recognizer, point):
    return point[0] * recognizer.w, point[1] * recognizer.h
