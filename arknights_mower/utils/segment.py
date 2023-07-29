from __future__ import annotations

import traceback

import cv2
import numpy as np
from matplotlib import pyplot as plt
from ..data import agent_list
from ..ocr import ocrhandle
from . import detector
from . import typealias as tp
from .log import logger
from .recognize import RecognizeError


class FloodCheckFailed(Exception):
    pass


def get_poly(x1: int, x2: int, y1: int, y2: int) -> tp.Rectangle:
    x1, x2 = int(x1), int(x2)
    y1, y2 = int(y1), int(y2)
    return np.array([ [ x1, y1 ], [ x1, y2 ], [ x2, y2 ], [ x2, y1 ] ])


def credit(img: tp.Image, draw: bool = False) -> list[ tp.Scope ]:
    """
    信用交易所特供的图像分割算法
    """
    try:
        height, width, _ = img.shape

        left, right = 0, width
        while np.max(img[ :, right - 1 ]) < 100:
            right -= 1
        while np.max(img[ :, left ]) < 100:
            left += 1

        def average(i: int) -> int:
            num, sum = 0, 0
            for j in range(left, right):
                if img[ i, j, 0 ] == img[ i, j, 1 ] and img[ i, j, 1 ] == img[ i, j, 2 ]:
                    num += 1
                    sum += img[ i, j, 0 ]
            return sum // num

        def ptp(j: int) -> int:
            maxval = -999999
            minval = 999999
            for i in range(up_1, up_2):
                minval = min(minval, img[ i, j, 0 ])
                maxval = max(maxval, img[ i, j, 0 ])
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
        while average(down) < 180:
            down -= 1

        right = width - 1
        while ptp(right) < 50:
            right -= 1

        left = 0
        while ptp(left) < 50:
            left += 1

        split_x = [ left + (right - left) // 5 * i for i in range(0, 6) ]
        split_y = [ up_1, (up_1 + down) // 2, down ]

        ret = [ ]
        for y1, y2 in zip(split_y[ :-1 ], split_y[ 1: ]):
            for x1, x2 in zip(split_x[ :-1 ], split_x[ 1: ]):
                ret.append(((x1, y1), (x2, y2)))

        if draw:
            for y1, y2 in zip(split_y[ :-1 ], split_y[ 1: ]):
                for x1, x2 in zip(split_x[ :-1 ], split_x[ 1: ]):
                    cv2.polylines(img, [ get_poly(x1, x2, y1, y2) ],
                                  True, 0, 10, cv2.LINE_AA)
            plt.imshow(img)
            plt.show()

        logger.debug(f'segment.credit: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)


def recruit(img: tp.Image, draw: bool = False) -> list[ tp.Scope ]:
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
                    sum += abs(int(img[ i, j, k ]) - int(img[ i - 1, j, k ]))
            return sum // (right - left)

        def adj_y(j: int) -> int:
            if j == 0:
                return 0
            sum = 0
            for i in range(up_2, down_2):
                for k in range(3):
                    sum += abs(int(img[ i, j, k ]) - int(img[ i, j - 1, k ]))
            return int(sum / (down_2 - up_2))

        def average(i: int) -> int:
            sum = 0
            for j in range(left, right):
                sum += np.sum(img[ i, j, :3 ])
            return sum // (right - left) // 3

        def minus(i: int) -> int:
            s = 0
            for j in range(left, right):
                s += int(img[ i, j, 2 ]) - int(img[ i, j, 0 ])
            return s // (right - left)

        up = 0
        while minus(up) > -100:
            up += 1
        while not (adj_x(up) > 80 and minus(up) > -10 and average(up) > 210):
            up += 1
        up_2, down_2 = up - 90, up - 40

        left = 0
        while np.max(img[ :, left ]) < 100:
            left += 1
        left += 1
        while adj_y(left) < 50:
            left += 1

        right = width - 1
        while np.max(img[ :, right ]) < 100:
            right -= 1
        while adj_y(right) < 50:
            right -= 1

        split_x = [ left, (left + right) // 2, right ]
        down = height - 1
        split_y = [ up, (up + down) // 2, down ]

        ret = [ ]
        for y1, y2 in zip(split_y[ :-1 ], split_y[ 1: ]):
            for x1, x2 in zip(split_x[ :-1 ], split_x[ 1: ]):
                ret.append(((x1, y1), (x2, y2)))

        if draw:
            for y1, y2 in zip(split_y[ :-1 ], split_y[ 1: ]):
                for x1, x2 in zip(split_x[ :-1 ], split_x[ 1: ]):
                    cv2.polylines(img, [ get_poly(x1, x2, y1, y2) ],
                                  True, 0, 10, cv2.LINE_AA)
            plt.imshow(img)
            plt.show()

        logger.debug(f'segment.recruit: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)


def base(img: tp.Image, central: tp.Scope, draw: bool = False) -> dict[ str, tp.Rectangle ]:
    """
    基建布局的图像分割算法
    """
    try:
        ret = {}

        x1, y1 = central[ 0 ]
        x2, y2 = central[ 1 ]
        alpha = (y2 - y1) / 160
        x1 -= 170 * alpha
        x2 += 182 * alpha
        y1 -= 67 * alpha
        y2 += 67 * alpha
        central = get_poly(x1, x2, y1, y2)
        ret[ 'central' ] = central

        for i in range(1, 5):
            y1 = y2 + 25 * alpha
            y2 = y1 + 134 * alpha
            if i & 1:
                dormitory = get_poly(x1, x2 - 158 * alpha, y1, y2)
            else:
                dormitory = get_poly(x1 + 158 * alpha, x2, y1, y2)
            ret[ f'dormitory_{i}' ] = dormitory

        x1, y1 = ret[ 'dormitory_1' ][ 0 ]
        x2, y2 = ret[ 'dormitory_1' ][ 2 ]

        x1 = x2 + 419 * alpha
        x2 = x1 + 297 * alpha
        factory = get_poly(x1, x2, y1, y2)
        ret[ f'factory' ] = factory

        y2 = y1 - 25 * alpha
        y1 = y2 - 134 * alpha
        meeting = get_poly(x1 - 158 * alpha, x2, y1, y2)
        ret[ f'meeting' ] = meeting

        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        contact = get_poly(x1, x2, y1, y2)
        ret[ f'contact' ] = contact

        y1 = y2 + 25 * alpha
        y2 = y1 + 134 * alpha
        train = get_poly(x1, x2, y1, y2)
        ret[ f'train' ] = train

        for floor in range(1, 4):
            x1, y1 = ret[ f'dormitory_{floor}' ][ 0 ]
            x2, y2 = ret[ f'dormitory_{floor}' ][ 2 ]
            x2 = x1 - 102 * alpha
            x1 = x2 - 295 * alpha
            if floor & 1 == 0:
                x2 = x1 - 24 * alpha
                x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[ f'room_{floor}_3' ] = room
            x2 = x1 - 24 * alpha
            x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[ f'room_{floor}_2' ] = room
            x2 = x1 - 24 * alpha
            x1 = x2 - 295 * alpha
            room = get_poly(x1, x2, y1, y2)
            ret[ f'room_{floor}_1' ] = room

        if draw:
            polys = list(ret.values())
            cv2.polylines(img, polys, True, (255, 0, 0), 10, cv2.LINE_AA)
            plt.imshow(img)
            plt.show()

        logger.debug(f'segment.base: {ret}')
        return ret

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)

def worker(img: tp.Image, draw: bool = False) -> tuple[ list[ tp.Rectangle ], tp.Rectangle, bool ]:
    """
    进驻总览的图像分割算法
    """
    try:
        height, width, _ = img.shape

        left, right = 0, width
        while np.max(img[ :, right - 1 ]) < 100:
            right -= 1
        while np.max(img[ :, left ]) < 100:
            left += 1

        x0 = right - 1
        while np.average(img[ :, x0, 1 ]) >= 100:
            x0 -= 1
        x0 -= 2

        seg = [ ]
        remove_mode = False
        pre, st = int(img[ 0, x0, 1 ]), 0
        for y in range(1, height):
            remove_mode |= int(img[ y, x0, 0 ]) - int(img[ y, x0, 1 ]) > 40
            if np.ptp(img[ y, x0 ]) <= 1 or int(img[ y, x0, 0 ]) - int(img[ y, x0, 1 ]) > 40:
                now = int(img[ y, x0, 1 ])
                if abs(now - pre) > 20:
                    if now < pre and st == 0:
                        st = y
                    elif now > pre and st != 0:
                        seg.append((st, y))
                        st = 0
                pre = now
            elif st != 0:
                seg.append((st, y))
                st = 0
        # if st != 0:
        #     seg.append((st, height))
        logger.debug(f'segment.worker: seg {seg}')

        remove_button = get_poly(x0 - 10, x0, seg[ 0 ][ 0 ], seg[ 0 ][ 1 ])
        seg = seg[ 1: ]

        for i in range(1, len(seg)):
            if seg[ i ][ 1 ] - seg[ i ][ 0 ] > 9:
                x1 = x0
                while img[ seg[ i ][ 1 ] - 3, x1 - 1, 2 ] < 100:
                    x1 -= 1
                break

        ret = [ ]
        for i in range(len(seg)):
            if seg[ i ][ 1 ] - seg[ i ][ 0 ] > 9:
                ret.append(get_poly(x1, x0, seg[ i ][ 0 ], seg[ i ][ 1 ]))

        if draw:
            cv2.polylines(img, ret, True, (255, 0, 0), 10, cv2.LINE_AA)
            plt.imshow(img)
            plt.show()

        logger.debug(f'segment.worker: {[ x.tolist() for x in ret ]}')
        return ret, remove_button, remove_mode

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)


def agent(img, draw=False):
    """
    干员总览的图像分割算法
    """
    try:
        height, width, _ = img.shape
        resolution = height
        left, right = 0, width

        # 异形屏适配
        while np.max(img[ :, right - 1 ]) < 100:
            right -= 1
        while np.max(img[ :, left ]) < 100:
            left += 1

        # 去除左侧干员详情
        x0 = left + 1
        while not (img[ height - 10, x0 - 1, 0 ] > img[ height - 10, x0, 0 ] + 10 and abs(
                int(img[ height - 10, x0, 0 ]) - int(img[ height - 10, x0 + 1, 0 ])) < 5):
            x0 += 1

        # ocr 初步识别干员名称
        ocr = ocrhandle.predict(img[ :, x0:right ])

        # 收集成功识别出来的干员名称识别结果，提取 y 范围，并将重叠的范围进行合并
        segs = [ (min(x[ 2 ][ 0 ][ 1 ], x[ 2 ][ 1 ][ 1 ]), max(x[ 2 ][ 2 ][ 1 ], x[ 2 ][ 3 ][ 1 ]))
                 for x in ocr if x[ 1 ] in agent_list ]
        while True:
            _a, _b = None, None
            for i in range(len(segs)):
                for j in range(len(segs)):
                    if i != j and (
                            segs[ i ][ 0 ] <= segs[ j ][ 0 ] <= segs[ i ][ 1 ] or segs[ i ][ 0 ] <= segs[ j ][ 1 ] <=
                            segs[ i ][ 1 ]):
                        _a, _b = segs[ i ], segs[ j ]
                        break
                if _b is not None:
                    break
            if _b is not None:
                segs.remove(_a)
                segs.remove(_b)
                segs.append((min(_a[ 0 ], _b[ 0 ]), max(_a[ 1 ], _b[ 1 ])))
            else:
                break
        segs = sorted(segs)

        # 计算纵向的四个高度，[y0, y1] 是第一行干员名称的纵向坐标范围，[y2, y3] 是第二行干员名称的纵向坐标范围
        y0 = y1 = y2 = y3 = None
        for x in segs:
            if x[ 1 ] < height // 2:
                y0, y1 = x
            else:
                y2, y3 = x
        if y0 is None or y2 is None:
            raise RecognizeError
        hpx = y1 - y0  # 卡片上干员名称的高度
        logger.debug((segs, [ y0, y1, y2, y3 ]))

        # 预计算：横向坐标范围集合
        x_set = set()
        for x in ocr:
            if x[ 1 ] in agent_list and (y0 <= x[ 2 ][ 0 ][ 1 ] <= y1 or y2 <= x[ 2 ][ 0 ][ 1 ] <= y3):
                # 只考虑矩形右边端点
                x_set.add(x[ 2 ][ 1 ][ 0 ])
                x_set.add(x[ 2 ][ 2 ][ 0 ])
        x_set = sorted(x_set)
        logger.debug(x_set)

        # 排除掉一些重叠的范围，获得最终的横向坐标范围
        gap = 160 * (resolution / 1080)  # 卡片宽度下限
        x_set = [ x_set[ 0 ] ] + \
                [ y for x, y in zip(x_set[ :-1 ], x_set[ 1: ]) if y - x > gap ]
        gap = [ y - x for x, y in zip(x_set[ :-1 ], x_set[ 1: ]) ]
        logger.debug(sorted(gap))
        gap = int(np.median(gap))  # 干员卡片宽度
        for x, y in zip(x_set[ :-1 ], x_set[ 1: ]):
            if y - x > gap:
                gap_num = round((y - x) / gap)
                for i in range(1, gap_num):
                    x_set.append(int(x + (y - x) / gap_num * i))
        x_set = sorted(x_set)
        if x_set[ -1 ] - x_set[ -2 ] < gap:
            # 如果最后一个间隔不足宽度则丢弃，避免出现「梅尔」只露出一半识别成「梅」算作成功识别的情况
            x_set = x_set[ :-1 ]
        while np.min(x_set) > 0:
            x_set.append(np.min(x_set) - gap)
        while np.max(x_set) < right - x0:
            x_set.append(np.max(x_set) + gap)
        x_set = sorted(x_set)
        logger.debug(x_set)

        # 获得所有的干员名称对应位置
        ret = [ ]
        for x1, x2 in zip(x_set[ :-1 ], x_set[ 1: ]):
            if 0 <= x1 + hpx and x0 + x2 + 5 <= right:
                ret += [ get_poly(x0 + x1 + hpx, x0 + x2 + 5, y0, y1),
                         get_poly(x0 + x1 + hpx, x0 + x2 + 5, y2, y3) ]

        # draw for debug
        if draw:
            __img = img.copy()
            cv2.polylines(__img, ret, True, (255, 0, 0), 3, cv2.LINE_AA)
            plt.imshow(__img)
            plt.show()

        logger.debug(f'segment.agent: {[ x.tolist() for x in ret ]}')
        return ret, ocr

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)


def free_agent(img, draw=False):
    """
    识别未在工作中的干员
    """
    try:
        height, width, _ = img.shape
        resolution = height
        left, right = 0, width

        # 异形屏适配
        while np.max(img[ :, right - 1 ]) < 100:
            right -= 1
        while np.max(img[ :, left ]) < 100:
            left += 1

        # 去除左侧干员详情
        x0 = left + 1
        while not (img[ height - 10, x0 - 1, 0 ] > img[ height - 10, x0, 0 ] + 10 and abs(
                int(img[ height - 10, x0, 0 ]) - int(img[ height - 10, x0 + 1, 0 ])) < 5):
            x0 += 1

        # 获取分割结果
        ret = agent(img, draw)
        st = ret[ -2 ][ 2 ]  # 起点
        ed = ret[ 0 ][ 1 ]  # 终点

        # 收集 y 坐标并初步筛选
        y_set = set()
        __ret = [ ]
        for poly in ret:
            __img = img[ poly[ 0, 1 ]:poly[ 2, 1 ], poly[ 0, 0 ]:poly[ 2, 0 ] ]
            y_set.add(poly[ 0, 1 ])
            y_set.add(poly[ 2, 1 ])
            # 去除空白的干员框
            if 80 <= np.min(__img):
                logger.debug(f'drop(empty): {poly.tolist()}')
                continue
            # 去除被选中的蓝框
            elif np.count_nonzero(__img[ :, :, 0 ] >= 224) == 0 or np.count_nonzero(__img[ :, :, 0 ] == 0) > 0:
                logger.debug(f'drop(selected): {poly.tolist()}')
                continue
            __ret.append(poly)
        ret = __ret

        y1, y2, y4, y5 = sorted(list(y_set))
        y0 = height - y5
        y3 = y0 - y2 + y5

        ret_free = [ ]
        for poly in ret:
            poly[ :, 1 ][ poly[ :, 1 ] == y1 ] = y0
            poly[ :, 1 ][ poly[ :, 1 ] == y4 ] = y3
            __img = img[ poly[ 0, 1 ]:poly[ 2, 1 ], poly[ 0, 0 ]:poly[ 2, 0 ] ]
            if not detector.is_on_shift(__img):
                ret_free.append(poly)

        if draw:
            __img = img.copy()
            cv2.polylines(__img, ret_free, True, (255, 0, 0), 3, cv2.LINE_AA)
            plt.imshow(__img)
            plt.show()

        logger.debug(f'segment.free_agent: {[ x.tolist() for x in ret_free ]}')
        return ret_free, st, ed

    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)
