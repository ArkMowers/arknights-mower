import os
import cv2
import numpy as np
from functools import lru_cache

from utils.log import logger
from utils.matcher import FlannBasedMatcher


def bytes2img(data):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)


def loadimg(filename):
    return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)


def threshole(img, thresh=254):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


class Status:
    STATUS_UNDEFINED = -1  # 未定义
    STATUS_INDEX = 0  # 首页


class Recognizer():

    def __init__(self, data):
        self.matcher = FlannBasedMatcher(bytes2img(data))
        self.matcher_thres = FlannBasedMatcher(threshole(bytes2img(data)))
        self.status = Status.STATUS_UNDEFINED
        self.items = {}
        self.items['index'] = [x.strip('.png')
                               for x in os.listdir('./resources/index/')]

    @lru_cache(1)
    def is_index(self):
        if self.status != Status.STATUS_UNDEFINED:
            return self.status == Status.STATUS_INDEX
        logger.debug('check index')
        if self.matcher_thres.match(threshole(loadimg('./resources/index/navbutton.png'))):
            self.status = Status.STATUS_INDEX
            return True
        else:
            return False

    def find_index(self, item):
        if self.status == Status.STATUS_INDEX and item in self.items['index']:
            logger.debug(f'find index_{item}')
            return self.matcher.match(loadimg(f'./resources/index/{item}.png'), True)
        else:
            return None
