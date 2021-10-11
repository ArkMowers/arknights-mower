import cv2
import traceback
import numpy as np
from matplotlib import pyplot as plt

from .recognize import RecognizeError
from .log import logger


def credit(im, draw=False):
    """
    信用交易所特供的图像分割算法
    """
    try:
        x, y, z = im.shape

        def average(i):
            n, s = 0, 0
            for j in range(y):
                if im[i, j, 0] == im[i, j, 1] and im[i, j, 0] == im[i, j, 2]:
                    n += 1
                    s += im[i, j, 0]
            return int(s / n)

        def ptp(j):
            mx = -999999
            mn = 999999
            for i in range(up, up2):
                mn = min(mn, im[i, j, 0])
                mx = max(mx, im[i, j, 0])
            return mx - mn

        up = 0
        fg = False
        while fg == False or average(up) >= 250:
            fg |= average(up) >= 250
            up += 1

        up2 = up
        fg = False
        while fg == False or average(up2) < 220:
            fg |= average(up2) < 220
            up2 += 1

        down = x - 1
        while average(down) < 180:
            down -= 1

        right = y - 1
        while ptp(right) < 50:
            right -= 1

        left = 0
        while ptp(left) < 50:
            left += 1

        split_x = [up, (up + down) // 2, down]
        split_y = [left] + [left + (right - left) //
                            5 * i for i in range(1, 5)] + [right]

        ret = []
        for x1, x2 in zip(split_x[:-1], split_x[1:]):
            for y1, y2 in zip(split_y[:-1], split_y[1:]):
                ret.append(((y1, x1), (y2, x2)))

        if draw:
            for x1, x2 in zip(split_x[:-1], split_x[1:]):
                for y1, y2 in zip(split_y[:-1], split_y[1:]):
                    cv2.polylines(im, [np.array([[y1, x1], [y1, x2], [y2, x2], [y2, x1]])],
                                  True, 0, 10, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.credit: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError


def recruit(im, draw=False):
    """
    公招特供的图像分割算法
    """
    try:
        x, y, z = im.shape
        u, d = 0, x
        l, r = y//2-100, y//2-50

        def adj_x(i):
            if i == 0:
                return 0
            s = 0
            for j in range(l, r):
                for k in range(3):
                    s += abs(int(im[i, j, k]) - int(im[i-1, j, k]))
            return int(s / (r-l))

        def adj_y(j):
            if j == 0:
                return 0
            s = 0
            for i in range(u, d):
                for k in range(3):
                    s += abs(int(im[i, j, k]) - int(im[i, j-1, k]))
            return int(s / (d-u))

        def average(i):
            s = 0
            for j in range(l, r):
                s += np.sum(im[i, j, :3])
            return int(s / (r-l) / 3)

        def minus(i):
            s = 0
            for j in range(l, r):
                s += int(im[i, j, 2]) - int(im[i, j, 0])
            return int(s / (r-l))

        up = 0
        while minus(up) > -210:
            up += 1
        while not (adj_x(up) > 80 and minus(up) > -10 and average(up) > 210):
            up += 1
        u, d = up-90, up-40

        down = x - 2
        while adj_x(down+1) < 100:
            down -= 1

        left = 0
        while adj_y(left) < 50:
            left += 1

        right = y - 1
        while adj_y(right) < 50:
            right -= 1

        split_x = [up, (up + down) // 2, down]
        split_y = [left, (left + right) // 2, right]

        ret = []
        for x1, x2 in zip(split_x[:-1], split_x[1:]):
            for y1, y2 in zip(split_y[:-1], split_y[1:]):
                ret.append(((y1, x1), (y2, x2)))

        if draw:
            for x1, x2 in zip(split_x[:-1], split_x[1:]):
                for y1, y2 in zip(split_y[:-1], split_y[1:]):
                    cv2.polylines(im, [np.array(
                        [[y1, x1], [y1, x2], [y2, x2], [y2, x1]])], True, 0, 10, cv2.LINE_AA)
            plt.imshow(im)
            plt.show()

        logger.debug(f'segment.recruit: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError
