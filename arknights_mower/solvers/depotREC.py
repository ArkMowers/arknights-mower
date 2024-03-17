import cv2
import json

import numpy as np
import os
import pandas as pd
import pickle
import re

from datetime import datetime


import lzma
from sklearn.cluster import KMeans
from skimage.feature import hog

from .. import __rootdir__
from ..data import key_mapping
from ..utils.device import Device
from ..utils.image import loadimg, saveimg
from ..utils.log import logger
from ..utils.path import get_path
from ..utils.recognize import Recognizer, Scene
from ..utils.solver import BaseSolver

# 向下x变大 = 0
# 向右y变大 = 0
# 左上角物品y坐标 = 285
# 左上角物品x坐标 = 187
# 横排间隔 = 286
# 竖排间隔 = 234
# [140:1000, :]


def 导入_数字模板():
    模板文件夹 = f"{__rootdir__}/resources/depot_num"
    数字模板列表 = []
    for 文件名 in sorted(os.listdir(模板文件夹)):
        文件路径 = os.path.join(模板文件夹, 文件名)
        数字模板列表.append(loadimg(文件路径, True))
    return 数字模板列表


def 找几何中心(coordinates, n_clusters=3):
    if len(coordinates) > 2:
        logger.debug(coordinates)
        coordinates_array = np.array(coordinates).reshape(-1, 1)
        kmeans = KMeans(n_clusters=n_clusters)
        kmeans.fit(coordinates_array)
        centers = kmeans.cluster_centers_.flatten().astype(int)
        logger.debug(centers)
    else:
        centers = [144, 430, 715]  # 权宜之计 在扫不出足够的圆时直接固定Y坐标
    return sorted(centers)


def 找圆(
        拼接结果, 参数1=50, 参数2=30, 圆心间隔=230, 最小半径=90, 最大半径=100
):
    灰图 = cv2.cvtColor(拼接结果, cv2.COLOR_BGR2GRAY)
    saveimg(拼接结果, "depot_without_circle")
    圆 = cv2.HoughCircles(
        灰图,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=圆心间隔,
        param1=参数1,
        param2=参数2,
        minRadius=最小半径,
        maxRadius=最大半径,
    )
    if 圆 is not None:
        圆 = np.round(圆[0, :]).astype("int")
        for x, y, r in 圆:
            cv2.circle(拼接结果, (x, y), r, (128, 255, 0), 4)
        saveimg(拼接结果, "depot_with_circle")

    return 圆


def 拼图(图片列表):
    stitcher = cv2.Stitcher.create(mode=cv2.Stitcher_SCANS)
    status, result = stitcher.stitch(图片列表)
    if status == cv2.Stitcher_OK:
        logger.info("拼接完成。")
    else:
        logger.info("拼接失败:", status)
    return result


def 提取特征点(模板):
    模板 = 模板[40:173, 40:173]
    hog_features = hog(
        模板,
        orientations=18,
        pixels_per_cell=(8, 8),
        cells_per_block=(2, 2),
        block_norm="L2-Hys",
        transform_sqrt=True,
        multichannel=True,
    )
    return hog_features


def 算坐标(圆):
    circles_x = sorted(圆[:, 0])
    groups = []
    start_index = 0

    for i in range(1, len(circles_x)):
        if circles_x[i] - circles_x[i - 1] >= 20:
            groups.append(circles_x[start_index:i])
            start_index = i

    groups.append(circles_x[start_index:])
    circles_x = [int(sum(group) / len(group)) for group in groups]
    circles_y = 找几何中心(圆[:, 1], 3)
    return circles_x, circles_y


def 识别空物品(物品灰):
    _, 二值图 = cv2.threshold(物品灰, 50, 255, cv2.THRESH_BINARY)
    白像素个数 = cv2.countNonZero(二值图)
    所有像素个数 = 二值图.shape[0] * 二值图.shape[1]
    白像素比值 = int((白像素个数 / 所有像素个数) * 100)
    if 白像素比值 == 100:
        logger.info("删除一次空物品")
        return False
    else:
        return True


def 切图(圆心x坐标, 圆心y坐标, 拼接结果, 正方形边长=130):
    图片 = []
    for x in 圆心x坐标:
        for y in 圆心y坐标:

            左上角坐标 = (x - 正方形边长, y - 正方形边长)
            右下角坐标 = (x + 正方形边长, y + 正方形边长)
            正方形 = 拼接结果[
                左上角坐标[1]: 右下角坐标[1],
                左上角坐标[0]: 右下角坐标[0],
            ]
            正方形灰 = cv2.cvtColor(正方形, cv2.COLOR_BGR2GRAY)
            if 识别空物品(正方形灰):
                图片.append([正方形[26:239, 26:239], 正方形灰])
    return 图片


class depotREC(BaseSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

        time = datetime.now()

        sift = cv2.SIFT_create()
        # surf = cv2.xfeatures2d.SURF_create()
        # ORB = cv2.ORB_create()
        self.detector = sift
        self.matcher = cv2.FlannBasedMatcher(
            dict(algorithm=1, trees=2), dict(checks=50)
        )

        self.仓库输出 = get_path("@app/tmp/depotresult.csv")
        # with lzma.open(f"{__rootdir__}/models/depot.pkl", "rb") as pkl:
        #     self.knn模型 = pickle.load(pkl)
        with lzma.open(f"{__rootdir__}/models/CONSUME.pkl", "rb") as pkl:
            self.knn模型_CONSUME = pickle.load(pkl)
        with lzma.open(f"{__rootdir__}/models/MATERIAL.pkl", "rb") as pkl:
            self.knn模型_MATERIAL = pickle.load(pkl)
        with lzma.open(f"{__rootdir__}/models/NORMAL.pkl", "rb") as pkl:
            self.knn模型_NORMAL = pickle.load(pkl)
        # self.时间模板 = self.导入_时间模板()
        self.物品数字 = 导入_数字模板()

        self.结果字典 = {}
        self.明日方舟工具箱json = {}

        logger.info(f"吟唱用时{datetime.now() - time}")

    def 切图主程序(self, 拼接好的图片):
        圆 = 找圆(拼接好的图片)
        横坐标, 纵坐标 = 算坐标(圆)
        结果 = 切图(横坐标, 纵坐标, 拼接好的图片)
        return 结果

    def 读取物品数字(self, 数字图片, 距离阈值=5, 阈值=0.85):
        结果 = {}
        for idx, 模板图片 in enumerate(self.物品数字):
            res = cv2.matchTemplate(数字图片, 模板图片, cv2.TM_CCORR_NORMED)
            loc = np.where(res >= 阈值)
            for i in range(len(loc[0])):
                pos_x = loc[1][i]
                accept = True
                for o in 结果:
                    if abs(o - pos_x) < 距离阈值:
                        accept = False
                        break
                if accept:
                    结果[loc[1][i]] = idx

        物品个数 = ""
        for k in sorted(结果):
            物品个数 += (
                str(结果[k]) if 结果[k] < 10 else ("万" if 结果[k] == 10 else ".")
            )

        if not 物品个数:
            return 999999
        # # 格式化数字
        格式化数字 = int(
            float("".join(re.findall(r"\d+\.\d+|\d+", 物品个数)))
            * (10000 if "万" in 物品个数 else 1)
        )
        # 保存结果图片
        saveimg(数字图片, "depot")

        return 格式化数字

    def 匹配物品一次(self, 物品, 物品灰, 模型名称):
        物品特征 = 提取特征点(物品)
        predicted_label = 模型名称.predict([物品特征])
        物品数字 = self.读取物品数字(物品灰)
        return [predicted_label[0], 物品数字]

    def run(self) -> None:
        logger.info("Start: 仓库扫描")
        super().run()

    def transition(self) -> bool:
        logger.info("仓库扫描: 回到桌面")
        self.back_to_index()
        if self.scene() == Scene.INDEX:
            self.tap_themed_element("index_warehouse")
            logger.info("仓库扫描: 从主界面点击仓库界面")

            time = datetime.now()
            任务组 = [
                (1200, self.knn模型_CONSUME),
                (1400, self.knn模型_NORMAL),
                (1700, self.knn模型_MATERIAL)
            ]

            for 任务 in 任务组:
                self.tap((任务[0], 70))
                if not self.find("depot_empty"):
                    self.分类扫描(任务[1])
                else:
                    logger.info("这个分类下没有物品")
            logger.info(f"仓库扫描: 匹配，识别用时{datetime.now() - time}")
            logger.info(f"仓库扫描:结果{self.结果字典}")
            result = [
                int(datetime.now().timestamp()),
                json.dumps(self.结果字典, ensure_ascii=False),
                json.dumps(self.明日方舟工具箱json, ensure_ascii=False),
            ]
            depotinfo = pd.DataFrame(
                [result], columns=["Timestamp", "Data", "json"])
            depotinfo.to_csv(self.仓库输出, mode="a", index=False,
                             header=False, encoding="utf-8")
        else:
            self.back_to_index()
        return True

    def compare_screenshot(self, image1, image2):
        image1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
        image2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
        keypoints1, descriptors1 = self.detector.detectAndCompute(image1, None)
        _, descriptors2 = self.detector.detectAndCompute(image2, None)

        matches = self.matcher.knnMatch(descriptors1, descriptors2, k=2)
        good_matches = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:
                good_matches.append(m)
        similarity = len(good_matches) / len(keypoints1) * 100
        return similarity

    def 分类扫描(self, 模型名称):
        截图列表 = []
        旧的截图 = self.recog.img
        旧的截图 = 旧的截图[140:1000, :]
        截图列表.append(旧的截图)
        saveimg(旧的截图, "depot_screenshot")
        self.recog.update()

        logger.info(f"仓库扫描: 把第{len(截图列表)}页保存进内存中等待识别")
        while True:
            self.swipe_noinertia((1800, 450), (-1000, 0))  # 滑动
            self.recog.update()
            新的截图 = self.recog.img
            新的截图 = 新的截图[140:1000, :]
            saveimg(新的截图, "depot_screenshot")
            相似度 = self.compare_screenshot(截图列表[-1], 新的截图)
            if 相似度 < 70:
                截图列表.append(新的截图)
                logger.info(f"仓库扫描: 把第{len(截图列表)}页保存进内存中等待识别,相似度{相似度}")
            else:
                logger.info("仓库扫描: 这大抵是最后一页了")
                break
        logger.info(f"仓库扫描: 截图读取完了,有{len(截图列表)}张截图")
        logger.info(f"仓库扫描: 开始计算裁切图像")

        if len(截图列表) > 1:
            拼接好的图片 = 拼图(截图列表)
        else:
            拼接好的图片 = 截图列表[0]
        切图列表 = self.切图主程序(拼接好的图片)
        saveimg(拼接好的图片, "stitcher")
        logger.info(f"仓库扫描: 需要识别{len(切图列表)}个物品")

        for [物品, 物品灰] in 切图列表:
            [物品名称, 物品数字] = self.匹配物品一次(物品, 物品灰, 模型名称)
            logger.debug([物品名称, 物品数字])
            self.结果字典[物品名称] = self.结果字典.get(物品名称, 0) + 物品数字
            self.明日方舟工具箱json[key_mapping[物品名称][0]] = (
                self.明日方舟工具箱json.get(key_mapping[物品名称][0], 0) + 物品数字)
