import cv2
import numpy as np

from .log import logger


def bytes2img(data, gray=False):
    if gray:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    else:
        return cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def loadimg(filename, gray=True):
    logger.debug(filename)
    if gray:
        return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
    else:
        return cv2.cvtColor(cv2.imread(filename, cv2.IMREAD_GRAYSCALE), cv2.COLOR_BGR2RGB)


def threshole(img, thresh):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


def margin(img, thresh):
    ret = img.copy()
    if len(ret.shape) == 3:
        # ret[rgb2gray(img) <= thresh] = 0
        z0 = ret[:,:,0]
        z1 = ret[:,:,1]
        z2 = ret[:,:,2]
        _ = (z0 <= thresh) | (z1 <= thresh) | (z2 <= thresh)
        z0[_] = 0
        z1[_] = 0
        z2[_] = 0
    else:
        ret[ret <= thresh] = 0
    return ret


def rgb2gray(img):
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
