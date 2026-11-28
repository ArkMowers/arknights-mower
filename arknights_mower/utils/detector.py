import numpy as np

from . import typealias as tp
from .log import logger


def infra_notification(img: tp.Image) -> tp.Coordinate:
    """
    检测基建内是否存在蓝色通知
    前置条件：已经处于基建内
    """
    height, width, _ = img.shape

    # set a new scan line: right
    # 场景切换过渡帧可能整屏全暗，right 无下限会越界（减到 -1921）；
    # 加 left 边界，全暗帧直接返回 None（调用方按「无通知」重读跳过）。
    right = width
    while right > 0 and np.max(img[:, right - 1]) < 100:
        right -= 1
    if right == 0:
        return None
    right -= 1

    # set a new scan line: up
    up = 0
    for i in range(height):
        if img[i, right, 0] < 100 < img[i, right, 1] < img[i, right, 2]:
            up = i
            break
    if up == 0:
        return None

    # set a new scan line: down
    down = 0
    for i in range(up, height):
        if not (img[i, right, 0] < 100 < img[i, right, 1] < img[i, right, 2]):
            down = i
            break
    if down == 0:
        return None

    # detect successful
    point = (right - 10, (up + down) // 2)
    logger.debug(f"detector.infra_notification: {point}")
    return point
