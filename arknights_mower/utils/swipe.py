"""无惯性手势参数；是否需要重试由调用场景根据实际画面判断。"""

from arknights_mower.utils import typealias as tp

NOINERTIA_OFFSET = 100


def noinertia_path(
    start: tp.Coordinate,
    movement: tp.Coordinate,
    duration: int = 20,
    *,
    retry: bool = False,
) -> tuple[list[tp.Coordinate], list[int]]:
    """duration 为每 100px 的毫秒数；重试只延长主轴拖动，不改变路径。"""
    x, y = start
    dx, dy = movement
    if dx == 0:
        distance = abs(dy)
        points = [
            start,
            (x + NOINERTIA_OFFSET, y),
            (x + NOINERTIA_OFFSET, y + dy),
            (x, y + dy),
        ]
    else:
        distance = abs(dx)
        points = [
            start,
            (x, y + NOINERTIA_OFFSET),
            (x + dx, y + NOINERTIA_OFFSET),
            (x + dx, y),
        ]
    main_duration = distance * duration // 100
    if retry:
        # 短距离复核也需要足够的拖动时间，不能只按距离缩短。
        main_duration = max(main_duration, distance * 80 // 100, 400)
    return points, [200, main_duration, 200]
