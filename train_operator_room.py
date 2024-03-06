import lzma
import pickle

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from arknights_mower.data import agent_list
from arknights_mower.utils.image import thres2

font = ImageFont.truetype("arknights_mower/fonts/SourceHanSansCN-Medium.otf", 37)

data = {}

kernel = np.ones((12, 12), np.uint8)

for operator in sorted(agent_list, key=lambda x: len(x), reverse=True):
    img = Image.new(mode="L", size=(400, 100))
    draw = ImageDraw.Draw(img)
    draw.text((50, 20), operator, fill=(255,), font=font)
    img = np.array(img, dtype=np.uint8)
    img = thres2(img, 200)
    dilation = cv2.dilate(img, kernel, iterations=1)
    contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    rect = map(lambda c: cv2.boundingRect(c), contours)
    x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
    img = img[y : y + h, x : x + w]
    tpl = np.zeros((46, 265), dtype=np.uint8)
    tpl[: img.shape[0], : img.shape[1]] = img
    # cv2.imwrite(f"/home/zhao/Desktop/data/{operator}.png", tpl)
    data[operator] = tpl

with lzma.open("arknights_mower/models/operator_room.model", "wb") as f:
    pickle.dump(data, f)
