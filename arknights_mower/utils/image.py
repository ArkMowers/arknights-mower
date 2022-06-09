from typing import Union

import cv2
import numpy as np

from . import typealias as tp
from .log import logger, save_screenshot


def bytes2img(data: bytes, gray: bool = False) -> Union[tp.Image, tp.GrayImage]:
    """ bytes -> image """
    if gray:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    else:
        return cv2.cvtColor(
            cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR),
            cv2.COLOR_BGR2RGB,
        )


def img2bytes(img) -> bytes:
    """ bytes -> image """
    return cv2.imencode('.png', img)[1]


def loadimg(filename: str, gray: bool = False) -> Union[tp.Image, tp.GrayImage]:
    """ load image from file """
    logger.debug(filename)
    if gray:
        return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
    else:
        return cv2.cvtColor(cv2.imread(filename, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def thres2(img: tp.GrayImage, thresh: int) -> tp.GrayImage:
    """ binarization of images """
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


# def thres0(img: tp.Image, thresh: int) -> tp.Image:
#     """ delete pixel, filter: value > thresh """
#     ret = img.copy()
#     if len(ret.shape) == 3:
#         # ret[rgb2gray(img) <= thresh] = 0
#         z0 = ret[:, :, 0]
#         z1 = ret[:, :, 1]
#         z2 = ret[:, :, 2]
#         _ = (z0 <= thresh) | (z1 <= thresh) | (z2 <= thresh)
#         z0[_] = 0
#         z1[_] = 0
#         z2[_] = 0
#     else:
#         ret[ret <= thresh] = 0
#     return ret


# def thres0(img: tp.Image, thresh: int) -> tp.Image:  # not support multichannel image
#     """ delete pixel which > thresh """
#     _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_TOZERO)
#     return ret


def rgb2gray(img: tp.Image) -> tp.GrayImage:
    """ change image from rgb to gray """
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def scope2slice(scope: tp.Scope) -> tp.Slice:
    """ ((x0, y0), (x1, y1)) -> ((y0, y1), (x0, x1)) """
    if scope is None:
        return slice(None), slice(None)
    return slice(scope[0][1], scope[1][1]), slice(scope[0][0], scope[1][0])


def cropimg(img: tp.Image, scope: tp.Scope) -> tp.Image:
    """ crop image """
    return img[scope2slice(scope)]


def saveimg(img, folder='failure'):
    save_screenshot(
        img2bytes(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)),
        subdir=f'{folder}/{img.shape[0]}x{img.shape[1]}',
    )
