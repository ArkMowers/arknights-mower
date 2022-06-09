import cv2
import numpy as np

from .. import __rootdir__
from . import typealias as tp
from .image import loadimg
from .log import logger
from .matcher import Matcher


def confirm(img: tp.Image) -> tp.Coordinate:
    """
    检测是否出现确认界面
    """
    height, width, _ = img.shape

    # 4 scan lines: left, right, up, down
    left, right = width // 4 * 3 - 10, width // 4 * 3 + 10
    up, down = height // 2 - 10, height // 2 + 10

    # the R/G/B must be the same for a single pixel in the specified area
    if (img[up:down, left:right, :-1] != img[up:down, left:right, 1:]).any():
        return None

    # the pixel average of the specified area must be in the vicinity of 55
    if abs(np.mean(img[up:down, left:right]) - 55) > 5:
        return None

    # set a new scan line: up
    up = 0
    for i in range(down, height):
        for j in range(left, right):
            if np.ptp(img[i, j]) != 0 or abs(img[i, j, 0] - 13) > 3:
                break
            elif j == right-1:
                up = i
        if up:
            break
    if up == 0:
        return None

    # set a new scan line: down
    down = 0
    for i in range(up, height):
        for j in range(left, right):
            if np.ptp(img[i, j]) != 0 or abs(img[i, j, 0] - 13) > 3:
                down = i
                break
        if down:
            break
    if down == 0:
        return None

    # detect successful
    point = (width // 2, (up + down) // 2)
    logger.debug(f'detector.confirm: {point}')
    return point


def infra_notification(img: tp.Image) -> tp.Coordinate:
    """
    检测基建内是否存在蓝色通知
    前置条件：已经处于基建内
    """
    height, width, _ = img.shape

    # set a new scan line: right
    right = width
    while np.max(img[:, right-1]) < 100:
        right -= 1
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
    logger.debug(f'detector.infra_notification: {point}')
    return point


def announcement_close(img: tp.Image) -> tp.Coordinate:
    """
    检测「关闭公告」按钮
    """
    height, width, _ = img.shape

    # 4 scan lines: left, right, up, down
    up, down = 0, height // 4
    left, right = width // 4 * 3, width

    sumx, sumy, cnt = 0, 0, 0
    for i in range(up, down):
        line_cnt = 0
        for j in range(left, right):
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


def visit_next(img: tp.Image) -> tp.Coordinate:
    """
    检测「访问下位」按钮
    """
    height, width, _ = img.shape

    # set a new scan line: right
    right = width
    while np.max(img[:, right-1]) < 100:
        right -= 1
    right -= 1

    # set a new scan line: up
    up = 0
    for i in range(height):
        if img[i, right, 0] > 150 > img[i, right, 1] > 40 > img[i, right, 2]:
            up = i
            break
    if up == 0:
        return None

    # set a new scan line: down
    down = 0
    for i in range(up, height):
        if not (img[i, right, 0] > 150 > img[i, right, 1] > 40 > img[i, right, 2]):
            down = i
            break
    if down == 0:
        return None

    # detect successful
    point = (right - 10, (up + down) // 2)
    logger.debug(f'detector.visit_next: {point}')
    return point


on_shift = loadimg(f'{__rootdir__}/resources/agent_on_shift.png', True)
distracted = loadimg(f'{__rootdir__}/resources/distracted.png', True)
resting = loadimg(f'{__rootdir__}/resources/agent_resting.png', True)

def is_on_shift(img: tp.Image) -> bool:
    """
    检测干员是否正在工作中
    """
    matcher = Matcher(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
    if matcher.match(on_shift, judge=False) is not None:
        return True
    if matcher.match(resting, judge=False) is not None:
        return True
    if matcher.match(distracted, judge=False) is not None:
        return False
    width = img.shape[1]
    __width = int(width * 0.7)
    left_up = np.count_nonzero(np.all(img[0, :__width] <= 62, axis=1) & np.all(30 <= img[0, :__width], axis=1)) / __width
    logger.debug(f'is_on_shift: {left_up}')
    return left_up > 0.3
