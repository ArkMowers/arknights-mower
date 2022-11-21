from __future__ import annotations

import traceback
from copy import deepcopy

import cv2
import numpy as np
from matplotlib import pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from .. import __rootdir__
from ..data import agent_list, ocr_error
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


def sift_recog(query, resolution, draw=False,reverse = False):
    """
    使用 SIFT 提取特征点识别干员名称
    """
    agent_sift_init()
    query = cv2.cvtColor(np.array(query), cv2.COLOR_RGB2GRAY)
    if reverse :
        # 干员总览界面图像色度反转
        query = 255 -query
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
            img[height - 1, x0 - 1, 0] > img[height - 1, x0, 0] + 10
            and abs(int(img[height - 1, x0, 0]) - int(img[height - 1, x0 + 1, 0])) < 5
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
                    if x[1] in agent_list and x[1] not in ['砾', '陈']:  # ocr 经常会把这两个搞错
                        ret_agent.append(x[1])
                        ret_succ.append(poly)
                        continue
                    res = sift_recog(__img, resolution, draw)
                    if (res is not None) and res in agent_list:
                        ret_agent.append(res)
                        ret_succ.append(poly)
                        continue
                    logger.warning(
                        f'干员名称识别异常：{x[1]} 为不存在的数据，请报告至 https://github.com/Konano/arknights-mower/issues'
                    )
                    saveimg(__img, 'failure_agent')
                    raise Exception("启动 Plan B")
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
                name = segment.read_screen(__img,
                                           langurage="chi_sim",
                                           type="text")
                logger.warning(f'备选方案识别结果： {name}')
                ret_fail.append(poly)
                if name in ocr_error.keys():
                    name = ocr_error[name]
                else:
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


def agent_with_mood(img ,length=5, draw: bool = False) :
    try:
        height, width, _ = img.shape
        result = []
        index = 0
        x0 = int(width*470/1920);y0 = int(height*765/1080);x1 = int(width*590/1920);y1 = int(height*1010/1080);h = int((y1 - y0) / 5)
        a0 = int(width*80/2496); b0 = int(height*1005/1404); a1 = int(width*275/2496); b1 = int(height*1310/1404); ah = int((b1 - b0) / 5)
        while index < length:
            data ={}
            data ["mood"]=segment.read_screen(img[ (y0+h*index):(y0+h*(index+1)), x0:x1 ],type="mood")
            name = ''
                #如果不是没人在基建
            if data["mood"]!=-1:
                __img = img[ (b0 + ah * index):(b0 + ah * (index + 1)), a0:a1 ]
                ocr = ocrhandle.predict(__img)
                if len(ocr) > 0 and ocr[0][1] in agent_list and ocr[0][1] not in ['砾', '陈']: name = ocr[0][1]
                else :
                    res = sift_recog(__img, height, draw,True)
                    if (res is not None) and res in agent_list:
                        name = res
                # 这两个名字太长会被挡住
            data[ "agent" ] = name
            result.append(data)
            index = index + 1
        return result
    except Exception as e:
        logger.debug(traceback.format_exc())
        raise RecognizeError(e)

