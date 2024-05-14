import lzma
import pickle

import cv2
import numpy as np
from matplotlib import pyplot as plt

from arknights_mower import __rootdir__
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger

kernel = np.ones((10, 10), np.uint8)

with lzma.open(f"{__rootdir__}/models/operator_select.model", "rb") as f:
    OP_SELECT = pickle.loads(f.read())


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
        op_name.append(best_operator)

    logger.debug(op_name)

    if draw:
        display = img.copy()
        for p in name_p:
            cv2.rectangle(display, p[0], p[1], (255, 0, 0), 3)
        plt.imshow(display)
        plt.show()

    return tuple(zip(op_name, name_p))
