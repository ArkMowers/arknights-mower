from __future__ import annotations

import pickle
import traceback
from typing import Optional, Tuple

import cv2
import numpy as np
import sklearn
from matplotlib import pyplot as plt
from skimage.metrics import structural_similarity as compare_ssim

from .. import __rootdir__
from . import typealias as tp
from .image import cropimg
from .log import logger

MATCHER_DEBUG = False
FLANN_INDEX_KDTREE = 0
GOOD_DISTANCE_LIMIT = 0.7
SIFT = cv2.SIFT_create()
with open(f'{__rootdir__}/models/svm.model', 'rb') as f:
    SVC = pickle.loads(f.read())


def getHash(data: list[float]) -> tp.Hash:
    """ calc image hash """
    avreage = np.mean(data)
    return np.where(data > avreage, 1, 0)


def hammingDistance(hash1: tp.Hash, hash2: tp.Hash) -> int:
    """ calc Hamming distance between two hash """
    return np.count_nonzero(hash1 != hash2)


def aHash(img1: tp.GrayImage, img2: tp.GrayImage) -> int:
    """ calc image hash """
    data1 = cv2.resize(img1, (8, 8)).flatten()
    data2 = cv2.resize(img2, (8, 8)).flatten()
    hash1 = getHash(data1)
    hash2 = getHash(data2)
    return hammingDistance(hash1, hash2)


class Matcher(object):
    """ image matching module """

    def __init__(self, origin: tp.GrayImage) -> None:
        logger.debug(f'Matcher init: shape ({origin.shape})')
        self.origin = origin
        self.init_sift()

    def init_sift(self) -> None:
        """ get SIFT feature points """
        self.kp, self.des = SIFT.detectAndCompute(self.origin, None)

    def match(self, query: tp.GrayImage, draw: bool = False, scope: tp.Scope = None, judge: bool = True,prescore = 0.0) -> Optional(tp.Scope):
        """ check if the image can be matched """
        rect_score = self.score(query, draw, scope)  # get matching score
        if rect_score is None:
            return None  # failed in matching
        else:
            rect, score = rect_score

        if prescore != 0.0 and score[3] >= prescore:
            logger.debug(f'match success: {score}')
            return rect
        # use SVC to determine if the score falls within the legal range
        if judge and not SVC.predict([score])[0]:  # numpy.bool_
            logger.debug(f'match fail: {score}')
            return None  # failed in matching
        else:
            if prescore>0 and score[3]<prescore:
                logger.debug(f'score is not greater than {prescore}: {score}')
                return None
            logger.debug(f'match success: {score}')
            return rect  # success in matching

    def score(self, query: tp.GrayImage, draw: bool = False, scope: tp.Scope = None, only_score: bool = False) -> Optional(Tuple[tp.Scope, tp.Score]):
        """ scoring of image matching """
        try:
            # if feature points is empty
            if self.des is None:
                logger.debug('feature points is None')
                return None

            # specify the crop scope
            if scope is not None:
                ori_kp, ori_des = [], []
                for _kp, _des in zip(self.kp, self.des):
                    if scope[0][0] <= _kp.pt[0] and scope[0][1] <= _kp.pt[1] and _kp.pt[0] <= scope[1][0] and _kp.pt[1] <= scope[1][1]:
                        ori_kp.append(_kp)
                        ori_des.append(_des)
                logger.debug(
                    f'match crop: {scope}, {len(self.kp)} -> {len(ori_kp)}')
                ori_kp, ori_des = np.array(ori_kp), np.array(ori_des)
            else:
                ori_kp, ori_des = self.kp, self.des

            # if feature points is less than 2
            if len(ori_kp) < 2:
                logger.debug('feature points is less than 2')
                return None

            # the height & width of query image
            h, w = query.shape

            # the feature point of query image
            qry_kp, qry_des = SIFT.detectAndCompute(query, None)

            # build FlannBasedMatcher
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            flann = cv2.FlannBasedMatcher(index_params, search_params)
            matches = flann.knnMatch(qry_des, ori_des, k=2)

            # store all the good matches as per Lowe's ratio test
            good = []
            for x, y in matches:
                if x.distance < GOOD_DISTANCE_LIMIT * y.distance:
                    good.append(x)
            good_matches_rate = len(good) / len(qry_des)

            # draw all the good matches, for debug
            if draw:
                result = cv2.drawMatches(
                    query, qry_kp, self.origin, ori_kp, good, None)
                plt.imshow(result, 'gray')
                plt.show()

            # if the number of good matches no more than 4
            if len(good) <= 4:
                logger.debug(
                    f'not enough good matches are found: {len(good)} / {len(qry_des)}')
                return None

            # get the coordinates of good matches
            qry_pts = np.float32(
                [qry_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            ori_pts = np.float32(
                [ori_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            # calculated transformation matrix and the mask
            M, mask = cv2.findHomography(qry_pts, ori_pts, cv2.RANSAC, 5.0)
            matchesMask = mask.ravel().tolist()

            # if transformation matrix is None
            if M is None:
                logger.debug('calculated transformation matrix failed')
                return None

            # calc the location of the query image
            quad = np.float32([[[0, 0]], [[0, h-1]], [[w-1, h-1]], [[w-1, 0]]])
            quad = cv2.perspectiveTransform(quad, M)  # quadrangle
            quad_points = qp = np.int32(quad).reshape(4, 2).tolist()

            # draw the result, for debug
            if draw or MATCHER_DEBUG:
                cv2.polylines(self.origin, [np.int32(quad)],
                              True, 0, 2, cv2.LINE_AA)
                draw_params = dict(matchColor=(0, 255, 0), singlePointColor=None,
                                   matchesMask=matchesMask, flags=2)
                result = cv2.drawMatches(query, qry_kp, self.origin, ori_kp,
                                         good, None, **draw_params)
                plt.imshow(result, 'gray')
                plt.show()

            # if quadrangle is not rectangle
            if max(abs(qp[0][0] - qp[1][0]), abs(qp[2][0] - qp[3][0]), abs(qp[0][1] - qp[3][1]), abs(qp[1][1] - qp[2][1])) > 30:
                logger.debug(f'square is not rectangle: {qp}')
                return None

            # make quadrangle rectangle
            rect = [(np.min(quad[:, 0, 0]), np.min(quad[:, 0, 1])),
                    (np.max(quad[:, 0, 0]), np.max(quad[:, 0, 1]))]

            # if rectangle is too small
            if rect[1][0] - rect[0][0] < 10 or rect[1][1] - rect[0][1] < 10:
                logger.debug(f'rectangle is too small: {rect}')
                return None

            # measure the rate of good match within the rectangle (x-axis)
            better = filter(
                lambda m:
                    rect[0][0] < ori_kp[m.trainIdx].pt[0] < rect[1][0] and rect[0][1] < ori_kp[m.trainIdx].pt[1] < rect[1][1], good)
            better_kp_x = [qry_kp[m.queryIdx].pt[0] for m in better]
            if len(better_kp_x):
                good_area_rate = np.ptp(better_kp_x) / w
            else:
                good_area_rate = 0

            # rectangle: float -> int
            rect = np.array(rect, dtype=int).tolist()
            rect_img = cropimg(self.origin, rect)

            # if rect_img is too small
            if np.min(rect_img.shape) < 10:
                logger.debug(f'rect_img is too small: {rect_img.shape}')
                return None

            # transpose rect_img
            rect_img = cv2.resize(rect_img, query.shape[::-1])

            # draw the result
            if draw or MATCHER_DEBUG:
                plt.subplot(1, 2, 1)
                plt.imshow(query, 'gray')
                plt.subplot(1, 2, 2)
                plt.imshow(rect_img, 'gray')
                plt.show()

            # calc aHash between query image and rect_img
            hash = 1 - (aHash(query, rect_img) / 32)

            # calc ssim between query image and rect_img
            ssim = compare_ssim(query, rect_img, multichannel=True)

            # return final rectangle and four dimensions of scoring
            if only_score:
                return (good_matches_rate, good_area_rate, hash, ssim)
            else:
                return rect, (good_matches_rate, good_area_rate, hash, ssim)

        except Exception as e:
            logger.error(e)
            logger.debug(traceback.format_exc())
