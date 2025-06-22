import lzma
import pickle
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger

kernel = np.ones((10, 10), np.uint8)

with lzma.open(f"{__rootdir__}/models/operator_select.model", "rb") as f:
    OP_SELECT = pickle.loads(f.read())

with lzma.open(f"{__rootdir__}/models/operator_train.model", "rb") as f:
    OP_TRAIN = pickle.loads(f.read())


def operator_list(img, draw=False, full_scan=True):
    name_y = ((488, 520), (909, 941))
    line1 = cropimg(img, tuple(zip((600, 1860 if not full_scan else 1920), name_y[0])))
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

    def process_name_region(p):
        im = cropimg(gray, p)
        im = thres2(im, 140)
        im = cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(im, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = map(lambda c: cv2.boundingRect(c), contours)
        x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
        im = im[y : y + h, x : x + w]
        tpl = np.zeros((42, 200), dtype=np.uint8)
        tpl[: im.shape[0], : im.shape[1]] = im
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        max_score = 0
        best_operator = None
        for operator, template in OP_SELECT.items():
            result = cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val > max_score:
                max_score = max_val
                best_operator = operator
        if max_score > 0.6:
            return best_operator
        return ""

    with ThreadPoolExecutor() as executor:
        op_name = list(executor.map(process_name_region, name_p))
        logger.debug(op_name)

    if draw:
        display = img.copy()
        for p in name_p:
            cv2.rectangle(display, p[0], p[1], (255, 0, 0), 3)
        display = cv2.cvtColor(display, cv2.COLOR_RGB2BGR)
        cv2.imshow("Image", display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return tuple(zip(op_name, name_p))


def operator_list_train(img, draw=False, full_scan=True):
    name_y = ((479, 506), (895, 922))
    name_p_row = [[], []]
    for yi in range(2):
        line1 = cropimg(img, tuple(zip((545, 1920), name_y[yi])))
        hsv = cv2.cvtColor(line1, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (98, 140, 200), (102, 255, 255))
        line1 = cv2.cvtColor(line1, cv2.COLOR_RGB2GRAY)
        line1[mask > 0] = (255,)
        line1 = thres2(line1, 85)

        last_line = line1[0]
        prev = last_line[0]
        front_edge = None
        back_edge = None
        name_x = []
        def color_streak_right(start, length, color):
            """检查从 start 位置开始，向右长度为 length 的像素是否全为color，包括start"""
            end = min(start+length, len(last_line))
            return all(last_line[j] == color for j in range(start, end))

        def color_streak_left(start, length, color):
            """检查从 start 位置开始，向左长度为 length 的像素是否全为color，不包括start"""
            start_idx = max(0, start - length)
            return all(last_line[j] == color for j in range(start_idx, start))
        
        for i in range(1, line1.shape[1]):
            curr = last_line[i]
            # 当从白色像素变为黑色像素时
            if prev == 255 and curr == 0:
                if color_streak_right(i, 20, 0) and color_streak_left(i,10,255):
                    # 若前边缘未记录或当前位置与前边缘距离超过 200 像素，则更新前边缘
                    should_update_front_edge = front_edge is None or i - front_edge > 200
                    if should_update_front_edge:
                        front_edge = i
            # 当从黑色像素变为白色像素时
            elif prev == 0 and curr == 255:
                if color_streak_right(i,10,255) and color_streak_left(i,10,0):
                    # 检查前边缘是否已记录且当前位置与前边缘距离超过 160 像素
                    front_edge_valid = front_edge is not None and 160 < i - front_edge < 200
                    # 检查后边缘是否未记录或当前位置与后边缘距离超过 200 像素
                    should_update_back_edge = back_edge is None or i - back_edge > 200

                    if front_edge_valid and should_update_back_edge:
                        back_edge = i
                        # 记录检测到的名称区域
                        name_x.append((back_edge + 543 -175, back_edge + 543))
            prev = curr

        for x in name_x:
            name_p_row[yi].append(tuple(zip(x, name_y[yi])))

    name_p = []
    max_length = max(len(row) for row in name_p_row)
    for col_index in range(max_length):
        for row in name_p_row:
            if col_index < len(row):
                name_p.append(row[col_index])
    logger.debug(name_p)

    op_name = []
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    def process_name_region(p):
        im = cropimg(gray, p)
        im = thres2(im, 140)
        im = cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(im, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = map(lambda c: cv2.boundingRect(c), contours)
        rect_list = list(rect)
        filtered_rects = [rect for rect in rect_list if len(rect) >= 3 and rect[2] > 30]
        if filtered_rects:
            # 取第一个元素最大的元组
            x, y, w, h = max(filtered_rects, key=lambda rect: rect[0])
        else:
            # 处理没有符合条件元素的情况
            x, y, w, h = 0, 0, 0, 0
        h = h if h <= 42 else 42
        w = w if w <= 200 else 200
        im = im[y : y + h, x : x + w]
        tpl = np.zeros((42, 200), dtype=np.uint8)
        tpl[: im.shape[0], : im.shape[1]] = im
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        '''cv2.imshow("tpl", tpl)
        cv2.waitKey(0)
        cv2.destroyAllWindows()'''
        max_score = 0
        best_operator = ""
        for operator, template in OP_TRAIN.items():
            result = cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val > max_score:
                max_score = max_val
                best_operator = operator
        logger.debug(f"{best_operator}:{max_score}")
        if max_score > 0.6:
            return best_operator
        return ""

    with ThreadPoolExecutor() as executor:
        op_name = list(executor.map(process_name_region, name_p))
    logger.debug(op_name)
    '''for p in name_p:
        op_name.append(process_name_region(p))
    logger.debug(op_name)'''
    if draw:
        display = img.copy()
        for p in name_p:
            cv2.rectangle(display, p[0], p[1], (255, 0, 0), 3)
        display = cv2.cvtColor(display, cv2.COLOR_RGB2BGR)
        cv2.imwrite("train.png", display)
        scale_percent = 66.67  # 缩放比例
        width = int(display.shape[1] * scale_percent / 100)
        height = int(display.shape[0] * scale_percent / 100)
        dim = (width, height)
        display = cv2.resize(display, dim, interpolation=cv2.INTER_AREA)
        cv2.imshow("Image", display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    logger.debug(tuple(zip(op_name, name_p)))
    return tuple(zip(op_name, name_p))
