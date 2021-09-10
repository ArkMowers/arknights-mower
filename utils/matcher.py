import cv2
import numpy as np
from matplotlib import pyplot as plt

from utils.log import logger

MATCHER_DEBUG = False
FLANN_INDEX_KDTREE = 0
GOOD_DISTANCE_LIMIT = 0.7
SIFT = cv2.SIFT_create()


class FlannBasedMatcher():

    def __init__(self, origin):
        self.origin = origin
        self.kp, self.des = SIFT.detectAndCompute(origin, None)
        logger.debug(f'FlannBasedMatcher init: shape ({origin.shape})')

    def match(self, query, ret_square=True, draw=False, scope=None):
        if self.des is None:
            logger.debug('feature points is None')
            if ret_square:
                return None
            return False

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

        good_kp_x = [kp[x.queryIdx].pt[0] for x in good]
        if len(good_kp_x):
            good_area_rate = np.ptp(good_kp_x) / w
        else:
            good_area_rate = 0

        logger.debug(
            f'matches: {len(good)} / {len(matches)} / {len(des)} / {len(good) / len(des)} / {good_area_rate}')

        if draw:
            result = cv2.drawMatches(
                query, kp, self.origin, kp0, good, None)
            plt.imshow(result, 'gray')
            plt.show()

        if len(good) <= 4 or len(good) / len(des) < 0.2:
            logger.debug('not enough good matches are found')
            if ret_square:
                return None
            return False

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
            if ret_square:
                return None
            return False

        pts = np.float32([[0, 0], [0, h-1], [w-1, h-1],
                         [w-1, 0]]).reshape(-1, 1, 2)
        dst = cv2.perspectiveTransform(pts, M)

        if abs(dst[0][0][0] - dst[1][0][0]) > 10 or abs(dst[2][0][0] - dst[3][0][0]) > 10 or abs(dst[0][0][1] - dst[3][0][1]) > 10 or abs(dst[1][0][1] - dst[2][0][1]) > 10:
            logger.debug('square is not rectangle')
            if ret_square:
                return None
            return False

        if good_area_rate < 0.5:
            logger.debug('good_area_rate is not enough')
            if ret_square:
                return None
            return False

        logger.info(
            f'matches: {len(good)} / {len(matches)} / {len(des)} / {len(good) / len(des)} / {good_area_rate}')

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

        dst = np.int32(dst).reshape(4, 2).tolist()
        logger.debug(f'find in {dst}')

        if ret_square:
            return dst
        return True
