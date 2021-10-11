import cv2
import numpy as np

from .log import logger


def bytes2img(data, gray=False):
    if gray:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    else:
        return cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def loadimg(filename):
    logger.debug(filename)
    return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)


def threshole(img, thresh):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret
