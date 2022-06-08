import re

import numpy as np
from PIL import Image

from ..data import ocr_error
from ..utils.log import logger


class resizeNormalize(object):

    def __init__(self, size, interpolation=Image.BILINEAR):
        self.size = size
        self.interpolation = interpolation

    def __call__(self, img):
        size = self.size
        imgW, imgH = size
        scale = img.size[1] * 1.0 / imgH
        w = img.size[0] / scale
        w = int(w)
        img = img.resize((w, imgH), self.interpolation)
        w, h = img.size
        if w <= imgW:
            newImage = np.zeros((imgH, imgW), dtype='uint8')
            newImage[:] = 255
            newImage[:, :w] = np.array(img)
            img = Image.fromarray(newImage)
        else:
            img = img.resize((imgW, imgH), self.interpolation)
        img = np.array(img, dtype=np.float32)
        img -= 127.5
        img /= 127.5
        img = img.reshape([*img.shape, 1])
        return img


class strLabelConverter(object):

    def __init__(self, alphabet):
        self.alphabet = alphabet + 'ç'  # for `-1` index
        self.dict = {}
        for i, char in enumerate(alphabet):
            # NOTE: 0 is reserved for 'blank' required by wrap_ctc
            self.dict[char] = i + 1

    def decode(self, t, length, raw=False):
        t = t[:length]
        if raw:
            return ''.join([self.alphabet[i - 1] for i in t])
        else:
            char_list = []
            for i in range(length):

                if t[i] != 0 and (not (i > 0 and t[i - 1] == t[i])):
                    char_list.append(self.alphabet[t[i] - 1])
            return ''.join(char_list)


def fix(s):
    """
    对识别结果进行简单处理，并查询是否在 ocr_error 中有过记录
    """
    s = re.sub(r'[。？！，、；：“”‘’（）《》〈〉【】『』「」﹃﹄〔〕…～﹏￥－＿]', '', s)
    s = re.sub(r'[\'\"\,\.\(\)]', '', s)
    if s in ocr_error.keys():
        logger.debug(f'fix with ocr_error: {s} -> {ocr_error[s]}')
        s = ocr_error[s]
    return s
