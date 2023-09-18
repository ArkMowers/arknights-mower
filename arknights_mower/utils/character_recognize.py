from __future__ import annotations

import traceback
from copy import deepcopy

import cv2
import numpy as np
from matplotlib import pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from .. import __rootdir__
from ..data import agent_list,ocr_error
from . import segment
from .image import saveimg
from .log import logger
from .recognize import RecognizeError
from ..ocr import ocrhandle


def poly_center(poly):
    return (np.average([x[0] for x in poly]), np.average([x[1] for x in poly]))


def in_poly(poly, p):
    return poly[0, 0] <= p[0] <= poly[2, 0] and poly[0, 1] <= p[1] <= poly[2, 1]


char_map = {}
agent_sorted = sorted(deepcopy(agent_list), key=len)
origin = origin_kp = origin_des = None

FLANN_INDEX_KDTREE = 0
GOOD_DISTANCE_LIMIT = 0.7
SIFT = cv2.SIFT_create()


def agent_sift_init():
    global origin, origin_kp, origin_des
    if origin is None:
        logger.debug('agent_sift_init')

        height = width = 2000
        lnum = 25
        cell = height // lnum

        img = np.zeros((height, width, 3), dtype=np.uint8)
        img = Image.fromarray(img)

        font = ImageFont.truetype(
            f'{__rootdir__}/fonts/SourceHanSansSC-Bold.otf', size=30, encoding='utf-8'
        )
        chars = sorted(list(set(''.join([x for x in agent_list]))))
        assert len(chars) <= (lnum - 2) * (lnum - 2)

        for idx, char in enumerate(chars):
            x, y = idx % (lnum - 2) + 1, idx // (lnum - 2) + 1
            char_map[(x, y)] = char
            ImageDraw.Draw(img).text(
                (x * cell, y * cell), char, (255, 255, 255), font=font
            )

        origin = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        origin_kp, origin_des = SIFT.detectAndCompute(origin, None)


def sift_recog(query, resolution, draw=False,bigfont = False):
    """
    使用 SIFT 提取特征点识别干员名称
    """
    agent_sift_init()
    # 大号字体修改参数
    if bigfont:
        SIFT = cv2.SIFT_create(
            contrastThreshold=0.1,
            edgeThreshold=20
        )
    else:
        SIFT = cv2.SIFT_create()
    query = cv2.cvtColor(np.array(query), cv2.COLOR_RGB2GRAY)
    # the height & width of query image
    height, width = query.shape

    multi = 2 * (resolution / 1080)
    query = cv2.resize(query, (int(width * multi), int(height * multi)))
    query_kp, query_des = SIFT.detectAndCompute(query, None)

    # build FlannBasedMatcher
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    matches = flann.knnMatch(query_des, origin_des, k=2)

    # store all the good matches as per Lowe's ratio test
    good = []
    for x, y in matches:
        if x.distance < GOOD_DISTANCE_LIMIT * y.distance:
            good.append(x)

    if draw:
        result = cv2.drawMatches(query, query_kp, origin, origin_kp, good, None)
        plt.imshow(result, 'gray')
        plt.show()

    count = {}

    for x in good:
        x, y = origin_kp[x.trainIdx].pt
        c = char_map[(int(x) // 80, int(y) // 80)]
        count[c] = count.get(c, 0) + 1

    best = None
    best_score = 0
    for x in agent_sorted:
        score = 0
        for c in set(x):
            score += count.get(c, -1)
        if score > best_score:
            best = x
            best_score = score

    logger.debug(f'segment.sift_recog: {count}, {best}')

    return best


def agent(img, draw=False):
    """
    识别干员总览界面的干员名称
    """
    try:
        height, width, _ = img.shape
        resolution = height
        left, right = 0, width

        # 异形屏适配
        while np.max(img[:, right - 1]) < 100:
            right -= 1
        while np.max(img[:, left]) < 100:
            left += 1

        # 去除左侧干员详情
        x0 = left + 1
        while not (
            img[height - 10, x0 - 1, 0] > img[height - 10, x0, 0] + 10
            and abs(int(img[height - 10, x0, 0]) - int(img[height - 10, x0 + 1, 0])) < 5
        ):
            x0 += 1

        # 获取分割结果
        ret, ocr = segment.agent(img, draw)

        # 确定位置后开始精确识别
        ret_succ = []
        ret_fail = []
        ret_agent = []
        for poly in ret:
            found_ocr, fx = None, 0
            for x in ocr:
                cx, cy = poly_center(x[2])
                if in_poly(poly, (cx + x0, cy)) and cx > fx:
                    fx = cx
                    found_ocr = x
            __img = img[poly[0, 1]: poly[2, 1], poly[0, 0]: poly[2, 0]]
            try:
                if found_ocr is not None:
                    x = found_ocr
                    if len(x[1]) == 3 and x[1][0] == "休" and x[1][2] == "斯":
                        x[1] = "休谟斯"
                    if x[1] in agent_list and x[1] not in ['砾', '陈']:  # ocr 经常会把这两个搞错
                        ret_agent.append(x[1])
                        ret_succ.append(poly)
                        continue
                    res = sift_recog(__img, resolution, draw)
                    if (res is not None) and res in agent_list:
                        ret_agent.append(res)
                        ret_succ.append(poly)
                        continue
                    logger.debug(
                        f'干员名称识别异常：{x[1]} 为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues'
                    )
                    saveimg(__img, 'failure_agent')
                    raise Exception(x[1])
                else:
                    if 80 <= np.min(__img):
                        continue
                    res = sift_recog(__img, resolution, draw)
                    if res is not None:
                        ret_agent.append(res)
                        ret_succ.append(poly)
                        continue
                    logger.warning(f'干员名称识别异常：区域 {poly.tolist()}')
                    saveimg(__img, 'failure_agent')
                    raise Exception("启动 Plan B")
                ret_fail.append(poly)
                raise Exception("启动 Plan B")
            except Exception as e:
                # 大哥不行了，二哥上！
                _msg = str(e)
                ret_fail.append(poly)
                if "Plan B" not in _msg:
                    if _msg in ocr_error.keys():
                        name = ocr_error[_msg]
                    elif "Off" in _msg:
                        name = 'U-Official'
                    else:
                        continue
                    ret_agent.append(name)
                    ret_succ.append(poly)
                    continue
        if len(ret_fail):
            saveimg(img, 'failure')
            if draw:
                __img = img.copy()
                cv2.polylines(__img, ret_fail, True, (255, 0, 0), 3, cv2.LINE_AA)
                plt.imshow(__img)
                plt.show()

        logger.debug(f'character_recognize.agent: {ret_agent}')
        logger.debug(f'character_recognize.agent: {[x.tolist() for x in ret]}')
        return list(zip(ret_agent, ret_succ))

    except Exception as e:
        logger.debug(traceback.format_exc())
        saveimg(img, 'failure_agent')
        raise RecognizeError(e)

def agent_name(__img, height, draw: bool = False):
    query = cv2.cvtColor(np.array(__img), cv2.COLOR_RGB2GRAY)
    h, w= query.shape
    dim = (w*4, h*4)
    # resize image
    resized = cv2.resize(__img, dim, interpolation=cv2.INTER_AREA)
    ocr = ocrhandle.predict(resized)
    name = ''
    try:
        if len(ocr) > 0 and ocr[0][1] in agent_list and ocr[0][1] not in ['砾', '陈']:
            name = ocr[0][1]
        elif len(ocr) > 0 and ocr[0][1] in ocr_error.keys():
            name = ocr_error[ocr[0][1]]
        else:
            res = sift_recog(__img, height, draw,bigfont=True)
            if (res is not None) and res in agent_list:
                name = res
            else:
                raise Exception(f"识别错误: {res}")
    except Exception as e:
        if len(ocr)>0:
            logger.warning(e)
            logger.warning(ocr[0][1])
            saveimg(__img, 'failure_agent')
    return name
