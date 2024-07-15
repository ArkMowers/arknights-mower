from __future__ import annotations

import lzma
import pickle
import traceback
from typing import Optional, Tuple

import cv2
import numpy as np
import sklearn.pipeline  # noqa
import sklearn.preprocessing
import sklearn.svm  # noqa
from skimage.metrics import structural_similarity as compare_ssim

from arknights_mower import __rootdir__
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg
from arknights_mower.utils.log import logger

GOOD_DISTANCE_LIMIT = 0.7

ORB = cv2.ORB_create(nfeatures=100000, edgeThreshold=0)
ORB_no_pyramid = cv2.ORB_create(nfeatures=100000, edgeThreshold=0, nlevels=1)


def keypoints_scale_invariant(img: tp.GrayImage):
    return ORB.detectAndCompute(img, None)


def keypoints(img: tp.GrayImage):
    return ORB_no_pyramid.detectAndCompute(img, None)


with lzma.open(f"{__rootdir__}/models/svm.model", "rb") as f:
    SVC = pickle.loads(f.read())


# build FlannBasedMatcher

# FLANN_INDEX_KDTREE = 1
FLANN_INDEX_LSH = 6

index_params = dict(
    algorithm=FLANN_INDEX_LSH,
    table_number=6,  # 12
    key_size=12,  # 20
    multi_probe_level=0,  # 2
)
search_params = dict(checks=50)  # 100
flann = cv2.FlannBasedMatcher(index_params, search_params)


def getHash(data: list[float]) -> tp.Hash:
    """calc image hash"""
    avreage = np.mean(data)
    return np.where(data > avreage, 1, 0)


def hammingDistance(hash1: tp.Hash, hash2: tp.Hash) -> int:
    """calc Hamming distance between two hash"""
    return np.count_nonzero(hash1 != hash2)


def aHash(img1: tp.GrayImage, img2: tp.GrayImage) -> int:
    """calc image hash"""
    data1 = cv2.resize(img1, (8, 4)).flatten()
    data2 = cv2.resize(img2, (8, 4)).flatten()
    hash1 = getHash(data1)
    hash2 = getHash(data2)
    return hammingDistance(hash1, hash2)


class Matcher(object):
    """image matching module"""

    def __init__(self, origin: tp.GrayImage) -> None:
        logger.debug(f"Matcher init: shape ({origin.shape})")
        self.origin = origin
        self.kp, self.des = keypoints(self.origin)

    def match(
        self,
        query: tp.GrayImage,
        draw: bool = False,
        scope: tp.Scope = None,
        dpi_aware: bool = False,
        prescore: float = 0.0,
        judge: bool = True,
    ) -> Optional[tp.Scope]:
        """check if the image can be matched"""
        rect_score = self.score(
            query,
            draw,
            scope,
            only_score=False,
            dpi_aware=dpi_aware,
        )  # get matching score
        if rect_score is None:
            return None  # failed in matching
        else:
            rect, score = rect_score

        if prescore > 0:
            if score[3] >= prescore:
                logger.debug(f"match success: {rect_score}")
                return rect
            else:
                logger.debug(f"score is not greater than {prescore}: {rect_score}")
                return None
        if judge and not SVC.predict([score])[0]:
            logger.debug(f"match fail: {rect_score}")
            return None
        logger.debug(f"match success: {rect_score}")
        return rect

    def score(
        self,
        query: tp.GrayImage,
        draw: bool = False,
        scope: tp.Scope = None,
        only_score: bool = False,
        dpi_aware: bool = False,
    ) -> Optional[Tuple[tp.Scope, tp.Score]]:
        """scoring of image matching"""
        try:
            # if feature points is empty
            if self.des is None:
                logger.debug("feature points is None")
                return None

            # specify the crop scope
            if scope is not None:
                ori_kp, ori_des = [], []
                for _kp, _des in zip(self.kp, self.des):
                    if (
                        scope[0][0] <= _kp.pt[0]
                        and scope[0][1] <= _kp.pt[1]
                        and _kp.pt[0] <= scope[1][0]
                        and _kp.pt[1] <= scope[1][1]
                    ):
                        ori_kp.append(_kp)
                        ori_des.append(_des)
                logger.debug(f"match crop: {scope}, {len(self.kp)} -> {len(ori_kp)}")
                ori_kp, ori_des = np.array(ori_kp), np.array(ori_des)
            else:
                ori_kp, ori_des = self.kp, self.des

            # if feature points is less than 2
            if len(ori_kp) < 2:
                logger.debug("feature points is less than 2")
                return None

            # the height & width of query image
            h, w = query.shape

            # the feature point of query image
            if dpi_aware:
                qry_kp, qry_des = keypoints_scale_invariant(query)
            else:
                qry_kp, qry_des = keypoints(query)

            matches = flann.knnMatch(qry_des, ori_des, k=2)

            # store all the good matches as per Lowe's ratio test
            good = []
            for pair in matches:
                if (len_pair := len(pair)) == 2:
                    x, y = pair
                    if x.distance < GOOD_DISTANCE_LIMIT * y.distance:
                        good.append(x)
                elif len_pair == 1:
                    good.append(pair[0])
            good_matches_rate = len(good) / len(qry_des)

            # draw all the good matches, for debug
            if draw:
                result = cv2.drawMatches(query, qry_kp, self.origin, ori_kp, good, None)

                from matplotlib import pyplot as plt

                plt.imshow(result)
                plt.show()
            # if the number of good matches no more than 4
            if len(good) <= 4:
                logger.debug(
                    f"not enough good matches are found: {len(good)} / {len(qry_des)}"
                )
                return None

            # get the coordinates of good matches
            qry_pts = np.int32([qry_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            ori_pts = np.int32([ori_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            # calculated transformation matrix and the mask
            M, mask = cv2.estimateAffine2D(qry_pts, ori_pts, None, cv2.RANSAC)

            # if transformation matrix is None
            if M is None:
                logger.debug("calculated transformation matrix failed")
                return None
            else:
                logger.debug(f"transform matrix: {M.tolist()}")

            M[0][1] = 0
            M[1][0] = 0
            avg = (M[0][0] + M[1][1]) / 2
            M[0][0] = avg
            M[1][1] = avg

            # calc the location of the query image
            # quad = np.float32([[[0, 0]], [[0, h-1]], [[w-1, h-1]], [[w-1, 0]]])
            quad = np.int32([[[0, 0]], [[w, h]]])
            quad = cv2.transform(quad, M)  # quadrangle
            rect = quad.reshape(2, 2).tolist()

            # draw the result, for debug
            if draw:
                matchesMask = mask.ravel().tolist()
                origin_copy = cv2.cvtColor(self.origin, cv2.COLOR_GRAY2RGB)
                cv2.rectangle(origin_copy, rect[0], rect[1], (255, 0, 0), 3)
                draw_params = dict(
                    matchColor=(0, 255, 0),
                    singlePointColor=None,
                    matchesMask=matchesMask,
                    flags=2,
                )
                result = cv2.drawMatches(
                    query, qry_kp, origin_copy, ori_kp, good, None, **draw_params
                )
                plt.imshow(result)
                plt.show()

            min_width = max(10, 0 if dpi_aware else w * 0.8)
            min_height = max(10, 0 if dpi_aware else h * 0.8)

            # if rectangle is too small
            if (
                rect[1][0] - rect[0][0] < min_width
                or rect[1][1] - rect[0][1] < min_height
            ):
                logger.debug(f"rectangle is too small: {rect}")
                return None

            if not dpi_aware:
                max_width = w * 1.25
                if rect[1][0] - rect[0][0] > max_width:
                    logger.debug(f"rectangle is too big: {rect}")
                    return None

            # measure the rate of good match within the rectangle (x-axis)
            better = filter(
                lambda m: rect[0][0] < ori_kp[m.trainIdx].pt[0] < rect[1][0]
                and rect[0][1] < ori_kp[m.trainIdx].pt[1] < rect[1][1],
                good,
            )
            better_kp_x = [qry_kp[m.queryIdx].pt[0] for m in better]
            if len(better_kp_x):
                good_area_rate = np.ptp(better_kp_x) / w
            else:
                good_area_rate = 0

            # rectangle: float -> int
            rect = np.array(rect, dtype=int).tolist()
            rect_img = cropimg(self.origin, rect)

            # if rect_img is too small
            if rect_img.shape[0] < min_height or rect_img.shape[1] < min_width:
                logger.debug(f"rect_img is too small: {rect_img.shape}")
                return None

            # transpose rect_img
            rect_img = cv2.resize(rect_img, query.shape[::-1])

            # draw the result
            if draw:
                plt.subplot(1, 2, 1)
                plt.imshow(query, cmap="gray", vmin=0, vmax=255)
                plt.subplot(1, 2, 2)
                plt.imshow(rect_img, cmap="gray", vmin=0, vmax=255)
                plt.show()

            # calc aHash between query image and rect_img
            hash = 1 - (aHash(query, rect_img) / 16)

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
