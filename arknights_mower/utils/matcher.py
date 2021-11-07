import cv2
import pickle
import sklearn
import traceback
import numpy as np
from matplotlib import pyplot as plt
from skimage.metrics import structural_similarity as compare_ssim

from ..__init__ import __rootdir__
from .log import logger

MATCHER_DEBUG = False
FLANN_INDEX_KDTREE = 0
GOOD_DISTANCE_LIMIT = 0.7
SIFT = cv2.SIFT_create()
with open(f'{__rootdir__}/models/svm.model', 'rb') as f:
    SVC = pickle.loads(f.read())


def getHash(image):
    avreage = np.mean(image)
    hash = []
    for i in range(image.shape[0]):
        for j in range(image.shape[1]):
            if image[i, j] > avreage:
                hash.append(1)
            else:
                hash.append(0)
    return hash


def HammingDistance(hash1, hash2):
    num = 0
    for index in range(len(hash1)):
        if hash1[index] != hash2[index]:
            num += 1
    return num


def aHash(image1, image2):
    image1 = cv2.resize(image1, (8, 8))
    image2 = cv2.resize(image2, (8, 8))
    hash1 = getHash(image1)
    hash2 = getHash(image2)
    return HammingDistance(hash1, hash2)


class Matcher():

    def __init__(self, origin):
        self.origin = origin  # need to be gray
        self.kp, self.des = SIFT.detectAndCompute(origin, None)
        logger.debug(f'Matcher init: shape ({origin.shape})')

    def match(self, query, draw=False, scope=None, judge=True):
        score = self.score(query, draw, scope)
        if score is None:
            return None
        elif judge and SVC.predict([score[1:]])[0] == False:
            logger.debug(f'match fail: {score[1:]}')
            return None
        else:
            logger.debug(f'match success: {score[1:]}')
            return score[0]

    def score(self, query, draw=False, scope=None):
        try:
            if self.des is None:
                logger.debug('feature points is None')
                return None
            if scope is not None:
                logger.debug(f'before: {len(self.kp)}')
                logger.debug(f'scope: {scope}')
                kp0, des0 = [], []
                for kp, des in zip(self.kp, self.des):
                    if scope[0][0] <= kp.pt[0] and scope[0][1] <= kp.pt[1] and kp.pt[0] <= scope[1][0] and kp.pt[1] <= scope[1][1]:
                        kp0.append(kp)
                        des0.append(des)
                logger.debug(f'after: {len(kp0)}')
                kp0, des0 = np.array(kp0), np.array(des0)
            else:
                kp0, des0 = self.kp, self.des
            if len(kp0) < 2:
                logger.debug('feature points is None')
                return None

            h, w = query.shape
            kp, des = SIFT.detectAndCompute(query, None)

            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            flann = cv2.FlannBasedMatcher(index_params, search_params)
            matches = flann.knnMatch(des, des0, k=2)

            """store all the good matches as per Lowe's ratio test."""
            good = []
            for x, y in matches:
                if x.distance < GOOD_DISTANCE_LIMIT * y.distance:
                    good.append(x)

            """draw the result"""
            if draw:
                result = cv2.drawMatches(
                    query, kp, self.origin, kp0, good, None)
                plt.imshow(result, 'gray')
                plt.show()

            good_match_rate = len(good) / len(des)
            if len(good) <= 4:
                logger.debug(
                    f'not enough good matches are found: {len(good)} / {len(des)} / {good_match_rate}')
                return None

            """get the coordinates of good matches"""
            src_pts = np.float32(
                [kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32(
                [kp0[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            """calculated transformation matrix and the mask"""
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            matchesMask = mask.ravel().tolist()

            if M is None:
                logger.debug('calculated transformation matrix failed')
                return None

            pts = np.float32([[0, 0], [0, h-1], [w-1, h-1],
                              [w-1, 0]]).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, M)
            dst_list = np.int32(dst).reshape(4, 2).tolist()

            """draw the result"""
            if draw or MATCHER_DEBUG:
                origin = np.array(self.origin)
                cv2.polylines(origin, [np.int32(dst)], True, 0, 2, cv2.LINE_AA)
                draw_params = dict(matchColor=(
                    0, 255, 0), singlePointColor=None, matchesMask=matchesMask, flags=2)
                result = cv2.drawMatches(
                    query, kp, origin, kp0, good, None, **draw_params)
                plt.imshow(result, 'gray')
                plt.show()

            if abs(dst[0][0][0] - dst[1][0][0]) > 30 or abs(dst[2][0][0] - dst[3][0][0]) > 30 or abs(dst[0][0][1] - dst[3][0][1]) > 30 or abs(dst[1][0][1] - dst[2][0][1]) > 30:
                logger.debug(f'square is not rectangle: {dst_list}')
                return None
            dst_tp = [(np.min(dst[:, 0, 0]), np.min(dst[:, 0, 1])),
                      (np.max(dst[:, 0, 0]), np.max(dst[:, 0, 1]))]
            if dst_tp[1][0] - dst_tp[0][0] < 10 or dst_tp[1][1] - dst_tp[0][1] < 10:
                logger.debug(f'square is small: {dst_tp}')
                return None

            better = filter(
                lambda m: dst_tp[0] < kp0[m.trainIdx].pt < dst_tp[1], good)
            better_kp_x = [kp[m.queryIdx].pt[0] for m in better]
            if len(better_kp_x):
                good_area_rate = np.ptp(better_kp_x) / w
            else:
                good_area_rate = 0

            dst_tp = np.array(dst_tp, dtype=int).tolist()
            origin = self.origin[dst_tp[0][1]: dst_tp[1]
                                 [1], dst_tp[0][0]: dst_tp[1][0]]
            if np.min(origin.shape) < 10:
                logger.debug(f'origin is small: {origin.shape}')
                return None
            origin = cv2.resize(origin, query.shape[::-1])

            """draw the result"""
            if draw or MATCHER_DEBUG:
                plt.subplot(1, 2, 1)
                plt.imshow(query, 'gray')
                plt.subplot(1, 2, 2)
                plt.imshow(origin, 'gray')
                plt.show()

            hash = 1 - (aHash(query, origin) / 32)
            ssim = compare_ssim(query, origin, multichannel=True)
            return (dst_tp, good_match_rate, good_area_rate, hash, ssim)

        except Exception as e:
            logger.error(e)
            logger.debug(traceback.format_exc())
