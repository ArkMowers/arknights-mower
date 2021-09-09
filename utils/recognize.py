import os
import cv2
import numpy as np

from utils.log import logger
from utils.matcher import FlannBasedMatcher


def bytes2img(data, grey=False):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE if grey else cv2.IMREAD_COLOR)


def loadimg(filename):
    return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)


def threshole(img, thresh=250):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


class Status:
    UNDEFINED = -1  # 未定义
    INDEX = 0  # 首页


class Recognizer():

    def __init__(self, adb, cut=None):
        self.adb = adb
        self.update(cut)

    def update(self, cut=None):
        self.screencap = self.adb.screencap()
        data = bytes2img(self.screencap, True)
        if cut is not None:
            x1, x2 = cut[0]
            y1, y2 = cut[1]
            h, w = data.shape
            if type(x1).__name__ == 'float':
                x1 = int(x1 * w)
            if type(x2).__name__ == 'float':
                x2 = int(x2 * w)
            if type(y1).__name__ == 'float':
                y1 = int(y1 * h)
            if type(y2).__name__ == 'float':
                y2 = int(y2 * h)
            logger.debug(f'cut from ({x1}, {y1}) to ({x2}, {y2})')
            data = data[y1:y2, x1:x2]
            self.offset = (x1, y1)
        else:
            self.offset = (0, 0)
        self.matcher = FlannBasedMatcher(data)
        self.matcher_thres = FlannBasedMatcher(threshole(data))
        self.status = Status.UNDEFINED

    def color(self, x, y):
        return bytes2img(self.screencap)[y][x]

    def is_index(self):
        if self.status != Status.UNDEFINED:
            return self.status == Status.INDEX
        logger.debug('check index')
        if self.matcher_thres.match(threshole(loadimg('./resources/index_nav.png')), False):
            self.status = Status.INDEX
            return True
        else:
            return False

    def find(self, item, draw=False):
        logger.debug(f'find {item}')
        ret = self.matcher.match(loadimg(f'./resources/{item}.png'), draw=draw)
        if ret is None:
            return None
        return [[x[i] + self.offset[i] for i in range(2)] for x in ret]

    def find_thres(self, item, draw=False):
        logger.debug(f'find {item}')
        ret = self.matcher_thres.match(
            threshole(loadimg(f'./resources/{item}.png')), draw=draw)
        if ret is None:
            return None
        return [[x[i] + self.offset[i] for i in range(2)] for x in ret]

    def find_friend_visit(self, draw=False):
        return self.find('friend_visit', draw)

    def find_friend_next(self, draw=False):
        return self.find('friend_next', draw)
