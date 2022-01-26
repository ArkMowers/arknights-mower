import numpy as np
from typing import Optional

from . import typealias as tp
from .log import logger


def confirm(img: tp.Image) -> Optional(tp.Coordinate):
    """
    检测是否出现确认界面
    """
    h, w, _ = img.shape

    # 4 scan lines: left, right, up, down
    l, r = w // 4 * 3 - 10, w // 4 * 3 + 10
    u, d = h // 2 - 10, h // 2 + 10

    # the R/G/B must be the same for a single pixel in the specified area
    if (img[u:d, l:r, :-1] != img[u:d, l:r, 1:]).any():
        return None

    # the pixel average of the specified area must be in the vicinity of 55
    if abs(np.mean(img[u:d, l:r]) - 55) > 5:
        return None

    # set a new scan line: up
    u = 0
    for i in range(d, h):
        for j in range(l, r):
            if np.ptp(img[i, j]) != 0 or abs(img[i, j, 0] - 13) > 3:
                break
            elif j == r-1:
                u = i
        if u:
            break
    if u == 0:
        return None

    # set a new scan line: down
    d = 0
    for i in range(u, h):
        for j in range(l, r):
            if np.ptp(img[i, j]) != 0 or abs(img[i, j, 0] - 13) > 3:
                d = i
                break
        if d:
            break
    if d == 0:
        return None

    # detect successful
    point = (w // 2, (u + d) // 2)
    logger.debug(f'detector.confirm: {point}')
    return point


def infra_notification(img: tp.Image) -> Optional(tp.Coordinate):
    """
    检测基建内是否存在蓝色通知
    前置条件：已经处于基建内
    """
    h, w, _ = img.shape

    # set a new scan line: right
    r = w
    while np.max(img[:, r-1]) < 100:
        r -= 1
    r -= 1

    # set a new scan line: up
    u = 0
    for i in range(h):
        if img[i, r, 0] < 100 < img[i, r, 1] < img[i, r, 2]:
            u = i
            break
    if u == 0:
        return None

    # set a new scan line: down
    d = 0
    for i in range(u, h):
        if not (img[i, r, 0] < 100 < img[i, r, 1] < img[i, r, 2]):
            d = i
            break
    if d == 0:
        return None

    # detect successful
    point = (r - 10, (u + d) // 2)
    logger.debug(f'detector.infra_notification: {point}')
    return point


def announcement_close(img: tp.Image) -> Optional(tp.Coordinate):
    """
    检测「关闭公告」按钮
    """
    h, w, _ = img.shape

    # 4 scan lines: left, right, up, down
    u, d = 0, h // 4
    l, r = w // 4 * 3, w

    sumx, sumy, cnt = 0, 0, 0
    for i in range(u, d):
        line_cnt = 0
        for j in range(l, r):
            if np.ptp(img[i, j]) == 0 and abs(img[i, j, 0] - 89) < 3:  # condition
                sumx += i
                sumy += j
                cnt += 1
                line_cnt += 1

                # the number of pixels meeting the condition in one line reaches 100
                if line_cnt >= 100:
                    return None

                # the number of pixels meeting the condition reaches 2000
                if cnt >= 2000:
                    # detect successful
                    point = (sumy // cnt, sumx // cnt)
                    logger.debug(f'detector.announcement_close: {point}')
                    return point

    return None


def visit_next(im):
    """
    检测「访问下位」按钮
    """
    h, w, _ = im.shape

    # set a new scan line: right
    r = w
    while np.max(im[:, r-1]) < 100:
        r -= 1
    r -= 1

    # set a new scan line: up
    u = 0
    for i in range(h):
        if im[i, r, 0] > 150 > im[i, r, 1] > 40 > im[i, r, 2]:
            u = i
            break
    if u == 0:
        return None

    # set a new scan line: down
    d = 0
    for i in range(u, h):
        if not (im[i, r, 0] > 150 > im[i, r, 1] > 40 > im[i, r, 2]):
            d = i
            break
    if d == 0:
        return None

    # detect successful
    point = (r - 10, (u + d) // 2)
    logger.debug(f'detector.visit_next: {point}')
    return point
