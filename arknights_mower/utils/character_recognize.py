from __future__ import annotations

import lzma
import pickle
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

from arknights_mower.utils import rapidocr
from arknights_mower.utils.image import thres2, cropimg


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

mh = 42
mw = 200

kernel = np.ones((10, 10), np.uint8)

with lzma.open(f"{__rootdir__}/models/operator_select.model", "rb") as f:
    OP_SELECT = pickle.loads(f.read())


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
            f'{__rootdir__}/fonts/SourceHanSansCN-Medium.otf', size=30, encoding='utf-8'
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


def paddle_guess_agent(guess):
    best = None
    best_score = 0
    count = 0
    # “森蚺”可能识别成“森”，“孑”可能识别成“子”（子月）
    # 以单字猜测双字干员不可靠
    # 以“白面鹃”或“白面”匹配“白面鸮”没问题
    # 注意避免“白面”匹配到“白雪”
    # “屯艾雅法拉”既能匹配“纯烬艾雅法拉”，又能匹配“艾雅法拉”，应交给 SIFT
    for x in agent_sorted:
        score = -abs(len(x) - len(guess))
        for c in set(x):
            score += 3 if c in guess else 0
        if score > best_score:
            count = 1
            best = x
            best_score = score
        elif score == best_score:
            count += 1
    if best and best_score > len(best) and count == 1:
        logger.debug(f"{guess} --?--> {best}")
        return best
    else:
        return None


def paddle_recog(__img):
    if len(res := rapidocr.engine(__img, use_det=False, use_cls=False, use_rec=True)[0]) > 0:
        logger.debug(res)
        for r in res:
            if r[0] in agent_list:
                op_name = r[0]
                return op_name
        for r in res:
            if r[0] in ocr_error:
                op_name = ocr_error[r[0]]
                logger.debug(f"{r[0]} =====> {op_name}")
                return op_name
    return None


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
                    if op_name := paddle_recog(__img):
                        ret_agent.append(op_name)
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
                    if op_name := paddle_recog(__img):
                        ret_agent.append(op_name)
                        ret_succ.append(poly)
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

def operator_list(img, draw=False):
    name_y = ((488, 520), (909, 941))
    line1 = cropimg(img, tuple(zip((600, 1920), name_y[0])))
    hsv = cv2.cvtColor(line1, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (98, 140, 200), (102, 255, 255))
    line1 = cv2.cvtColor(line1, cv2.COLOR_RGB2GRAY)
    line1[mask > 0] = (255,)
    line1 = thres2(line1, 140)

    last_line = line1[-1]
    prev = last_line[0]
    start = None
    name_x = []
    for i in range(1, line1.shape[1]):
        curr = last_line[i]
        if prev == 0 and curr == 255 and start and i - start > 186:
            name_x.append((start + 600, i + 598))
        elif prev == 255 and curr == 0:
            start = i
        prev = curr

    name_p = []
    for x in name_x:
        for y in name_y:
            name_p.append(tuple(zip(x, y)))

    logger.debug(name_p)

    op_name = []
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    for p in name_p:
        im = cropimg(gray, p)
        im = thres2(im, 140)
        im = cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(im, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = map(lambda c: cv2.boundingRect(c), contours)
        x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
        im = im[y : y + h, x : x + w]
        tpl = np.zeros((mh, mw))
        tpl[: im.shape[0], : im.shape[1]] = im
        tpl /= 255
        tpl = tpl.reshape(mh * mw)
        op_name.append(agent_list[OP_SELECT.predict([tpl])[0]])

    logger.debug(op_name)

    if draw:
        display = img.copy()
        for p in name_p:
            cv2.rectangle(display, p[0], p[1], (255, 0, 0), 3)
        plt.imshow(display)
        plt.show()

    return tuple(zip(op_name, name_p))
