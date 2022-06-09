import copy
import traceback

import cv2
import numpy as np
from PIL import Image

from ..utils.log import logger
from .config import crnn_model_path, dbnet_model_path
from .crnn import CRNNHandle
from .dbnet import DBNET
from .utils import fix


def sorted_boxes(dt_boxes):
    """
    Sort text boxes in order from top to bottom, left to right
    args:
        dt_boxes(array):detected text boxes with shape [4, 2]
    return:
        sorted boxes(array) with shape [4, 2]
    """
    num_boxes = dt_boxes.shape[0]
    sorted_boxes = sorted(dt_boxes, key=lambda x: (x[0][1], x[0][0]))
    _boxes = list(sorted_boxes)

    for i in range(num_boxes - 1):
        if abs(_boxes[i+1][0][1] - _boxes[i][0][1]) < 10 and \
                (_boxes[i + 1][0][0] < _boxes[i][0][0]):
            tmp = _boxes[i]
            _boxes[i] = _boxes[i + 1]
            _boxes[i + 1] = tmp
    return _boxes


def get_rotate_crop_image(img, points):
    img_height, img_width = img.shape[0:2]
    left = int(np.min(points[:, 0]))
    right = int(np.max(points[:, 0]))
    top = int(np.min(points[:, 1]))
    bottom = int(np.max(points[:, 1]))
    img_crop = img[top:bottom, left:right, :].copy()
    points[:, 0] = points[:, 0] - left
    points[:, 1] = points[:, 1] - top
    img_crop_width = int(np.linalg.norm(points[0] - points[1]))
    img_crop_height = int(np.linalg.norm(points[0] - points[3]))
    pts_std = np.float32([[0, 0], [img_crop_width, 0],
                          [img_crop_width, img_crop_height], [0, img_crop_height]])

    M = cv2.getPerspectiveTransform(points, pts_std)
    dst_img = cv2.warpPerspective(
        img_crop,
        M, (img_crop_width, img_crop_height),
        borderMode=cv2.BORDER_REPLICATE)
    dst_img_height, dst_img_width = dst_img.shape[0:2]
    if dst_img_height * 1.0 / dst_img_width >= 1.5:
        dst_img = np.rot90(dst_img)
    return dst_img


class OcrHandle(object):
    def __init__(self):
        self.text_handle = DBNET(dbnet_model_path)
        self.crnn_handle = CRNNHandle(crnn_model_path)

    def crnnRecWithBox(self, im, boxes_list, score_list, is_rgb=False):
        results = []
        boxes_list = sorted_boxes(np.array(boxes_list))

        count = 1
        for (box, score) in zip(boxes_list, score_list):

            tmp_box = copy.deepcopy(box)
            partImg_array = get_rotate_crop_image(
                im, tmp_box.astype(np.float32))

            try:
                if is_rgb:
                    partImg = Image.fromarray(partImg_array).convert('RGB')
                    simPred = self.crnn_handle.predict_rbg(partImg)
                else:
                    partImg = Image.fromarray(partImg_array).convert('L')
                    simPred = self.crnn_handle.predict(partImg)
            except Exception as e:
                logger.debug(traceback.format_exc())
                continue

            if simPred.strip() != '':
                results.append([count, simPred, tmp_box.tolist(), score])
                count += 1

        return results

    def predict(self, img, is_rgb=False):
        short_size = min(img.shape[:-1])
        short_size = short_size // 32 * 32
        boxes_list, score_list = self.text_handle.process(img, short_size)
        result = self.crnnRecWithBox(img, boxes_list, score_list, is_rgb)
        for i in range(len(result)):
            result[i][1] = fix(result[i][1])
        logger.debug(result)
        return result
