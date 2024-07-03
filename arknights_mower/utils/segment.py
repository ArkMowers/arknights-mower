from __future__ import annotations

import traceback

import cv2
import numpy as np

from arknights_mower.utils import typealias as tp
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import RecognizeError


class FloodCheckFailed(Exception):
    pass


def get_poly(x1: int, x2: int, y1: int, y2: int) -> tp.Rectangle:
    x1, x2 = int(x1), int(x2)
    y1, y2 = int(y1), int(y2)
    return np.array([[x1, y1], [x1, y2], [x2, y2], [x2, y1]])


def credit(img: tp.Image, draw: bool = False) -> list[tp.Scope]:
    """
    信用交易所特供的图像分割算法
    """
    try:
        height, width, _ = img.shape

        left, right = 0, width
        while np.max(img[:, right - 1]) < 100:
            right -= 1
        while np.max(img[:, left]) < 100:
            left += 1

        def average(i: int) -> int:
            num, sum = 0, 0
            for j in range(left, right):
                if img[i, j, 0] == img[i, j, 1] and img[i, j, 1] == img[i, j, 2]:
                    num += 1
                    sum += img[i, j, 0]
            return sum // num

        def ptp(j: int) -> int:
            maxval = -999999
            minval = 999999
            for i in range(up_1, up_2):
                minval = min(minval, img[i, j, 0])
                maxval = max(maxval, img[i, j, 0])
            return maxval - minval

        up_1 = 0
        flag = False
        while not flag or average(up_1) >= 250:
            flag |= average(up_1) >= 250  # numpy.bool_
            up_1 += 1

        up_2 = up_1
        flag = False
        while not flag or average(up_2) < 220:
            flag |= average(up_2) < 220
            up_2 += 1

        down = height - 1
        while average(down) < 150:
            down -= 1

        right = width - 1
        while ptp(right) < 50:
            right -= 1

        left = 0
        while ptp(left) < 50:
            left += 1

        split_x = [left + (right - left) // 5 * i for i in range(0, 6)]
        split_y = [up_1, (up_1 + down) // 2, down]

        ret = []
        for y1, y2 in zip(split_y[:-1], split_y[1:]):
            for x1, x2 in zip(split_x[:-1], split_x[1:]):
                ret.append(((x1, y1), (x2, y2)))

        if draw:
            for y1, y2 in zip(split_y[:-1], split_y[1:]):
                for x1, x2 in zip(split_x[:-1], split_x[1:]):
                    cv2.polylines(
                        img, [get_poly(x1, x2, y1, y2)], True, 0, 10, cv2.LINE_AA
                    )

            from matplotlib import pyplot as plt

            plt.imshow(img)
            plt.show()

        logger.debug(f"segment.credit: {ret}")
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)


def recruit(img: tp.Image, draw: bool = False) -> list[tp.Scope]:
    """
    公招特供的图像分割算法
    """
    try:
        height, width, _ = img.shape
        left, right = width // 2 - 100, width // 2 - 50

        def adj_x(i: int) -> int:
            if i == 0:
                return 0
            sum = 0
            for j in range(left, right):
                for k in range(3):
                    sum += abs(int(img[i, j, k]) - int(img[i - 1, j, k]))
            return sum // (right - left)

        def adj_y(j: int) -> int:
            if j == 0:
                return 0
            sum = 0
            for i in range(up_2, down_2):
                for k in range(3):
                    sum += abs(int(img[i, j, k]) - int(img[i, j - 1, k]))
            return int(sum / (down_2 - up_2))

        def average(i: int) -> int:
            sum = 0
            for j in range(left, right):
                sum += np.sum(img[i, j, :3])
            return sum // (right - left) // 3

        def minus(i: int) -> int:
            s = 0
            for j in range(left, right):
                s += int(img[i, j, 2]) - int(img[i, j, 0])
            return s // (right - left)

        up = 0
        while minus(up) > -100:
            up += 1
        while not (adj_x(up) > 80 and minus(up) > -10 and average(up) > 210):
            up += 1
        up_2, down_2 = up - 90, up - 40

        left = 0
        while np.max(img[:, left]) < 100:
            left += 1
        left += 1
        while adj_y(left) < 50:
            left += 1

        right = width - 1
        while np.max(img[:, right]) < 100:
            right -= 1
        while adj_y(right) < 50:
            right -= 1

        split_x = [left, (left + right) // 2, right]
        down = height - 1
        split_y = [up, (up + down) // 2, down]

        ret = []
        for y1, y2 in zip(split_y[:-1], split_y[1:]):
            for x1, x2 in zip(split_x[:-1], split_x[1:]):
                ret.append(((x1, y1), (x2, y2)))

        if draw:
            for y1, y2 in zip(split_y[:-1], split_y[1:]):
                for x1, x2 in zip(split_x[:-1], split_x[1:]):
                    cv2.polylines(
                        img, [get_poly(x1, x2, y1, y2)], True, 0, 10, cv2.LINE_AA
                    )

            from matplotlib import pyplot as plt

            plt.imshow(img)
            plt.show()

        logger.debug(f"segment.recruit: {ret}")
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)


def base(
    img: tp.Image, central: tp.Scope, draw: bool = False
) -> dict[str, tp.Rectangle]:
    """
    基建布局的图像分割算法
    """
    try:
        ret = {}

        x1, y1 = central[0]
        x2, y2 = central[1]
        alpha = (y2 - y1) / 160
        x1 -= 170 * alpha
        x2 += 182 * alpha
        y1 -= 67 * alpha
        y2 += 67 * alpha
        central = get_poly(x1, x2, y1, y2)
        ret["central"] = central

        for i in range(1, 5):
            y1 = y2 + 25 * alpha
            y2 = y1 + 134 * alpha
            if i & 1:
                dormitory = get_poly(x1, x2 - 158 * alpha, y1, y2)
            else:
                dormitory = get_poly(x1 + 158 * alpha, x2, y1, y2)
            ret[f"dormitory_{i}"] = dormitory

        x1, y1 = ret["dormitory_1"][0]
        x2, y2 = ret["dormitory_1"][2]

        x1 = x2 + 419 * alpha
        x2 = x1 + 297 * alpha
        factory = get_poly(x1, x2, y1, y2)
        ret["factory"] = factory

        y2 = y1 - 25 * alpha
        y1 = y2 - 134 * alpha
        meeting = get_poly(x1 - 158 * alpha, x2, y1, y2)
        ret["meeting"] = meeting

        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        contact = get_poly(x1, x2, y1, y2)
        ret["contact"] = contact

        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        train = get_poly(x1, x2, y1, y2)
        ret["train"] = train

        for floor in range(1, 4):
            x1, y1 = ret[f"dormitory_{floor}"][0]
            x2, y2 = ret[f"dormitory_{floor}"][2]
            x2 = x1 - 102 * alpha
            x1 = x2 - 295 * alpha
            if floor & 1 == 0:
                x2 = x1 - 24 * alpha
                x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[f"room_{floor}_3"] = room
            x2 = x1 - 24 * alpha
            x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[f"room_{floor}_2"] = room
            x2 = x1 - 24 * alpha
            x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[f"room_{floor}_1"] = room

        if draw:
            polys = list(ret.values())
            cv2.polylines(img, polys, True, (255, 0, 0), 10, cv2.LINE_AA)

            from matplotlib import pyplot as plt

            plt.imshow(img)
            plt.show()

        logger.debug(f"segment.base: {ret}")
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)
