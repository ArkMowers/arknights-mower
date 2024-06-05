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
from ..utils.image import loadimg, saveimg_depot
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
    coordinates_array = np.array(coordinates).reshape(-1, 1)
    kmeans = KMeans(n_clusters=n_clusters)
    kmeans.fit(coordinates_array)
    centers = kmeans.cluster_centers_.flatten().astype(int)
    logger.debug(centers)

    return sorted(centers)


def 找圆(拼接结果, 参数1=50, 参数2=30, 圆心间隔=230, 最小半径=90, 最大半径=100):
    灰图 = cv2.cvtColor(拼接结果, cv2.COLOR_RGB2GRAY)
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

    return 圆


def 拼图(图片列表):
    try:
        stitcher = cv2.Stitcher.create(mode=cv2.Stitcher_SCANS)
        status, result = stitcher.stitch(图片列表)
        if status == cv2.Stitcher_OK:
            logger.info("仓库扫描: 拼接完成。")
            return result
        else:
            logger.warning(f"仓库扫描: 拼接失败，状态码: {status}")
            raise RuntimeError(f"拼接失败，状态码: {status}")
    except RuntimeError as e:
        logger.error(f"仓库扫描: 拼接过程中出现错误: {e}")
        raise


def 提取特征点(模板):
    模板 = 模板[40:173, 40:173]
    hog_features = hog(
        模板,
        orientations=18,
        pixels_per_cell=(8, 8),
        cells_per_block=(2, 2),
        block_norm="L2-Hys",
        transform_sqrt=True,
        channel_axis=2,
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
    物品灰 = 物品灰[0:130, 130:260]
    _, 二值图 = cv2.threshold(物品灰, 60, 255, cv2.THRESH_BINARY)
    白像素个数 = cv2.countNonZero(二值图)
    所有像素个数 = 二值图.shape[0] * 二值图.shape[1]
    白像素比值 = int((白像素个数 / 所有像素个数) * 100)
    # saveimg_depot(
    #     cv2.hconcat([物品灰, 二值图]),
    #     f"{白像素比值}_{datetime.now().timestamp()}.png",
    #     "depot_3_empty",
    # )
    if 白像素比值 > 99:
        logger.info("仓库扫描: 删除一次空物品")

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
                左上角坐标[1] : 右下角坐标[1],
                左上角坐标[0] : 右下角坐标[0],
            ]
            正方形灰 = cv2.cvtColor(正方形, cv2.COLOR_RGB2GRAY)
            if 识别空物品(正方形灰):
                id = str(datetime.now().timestamp())
                正方形切 = 正方形[26:239, 26:239]
                图片.append([正方形切, 正方形灰, id])
                # saveimg_depot(正方形切, id + ".png", "depot_4_name")
                # saveimg_depot(正方形灰, id + ".png", "depot_4_num")
    return 图片


def 经验卡分类(物品):
    # 图像处理
    # return 物品名称
    logger.info("没有写具体内容 ")
    pass


class depotREC(BaseSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

        start_time = datetime.now()

        # sift = cv2.SIFT_create()
        orb = cv2.ORB_create()
        bf = cv2.BFMatcher(cv2.NORM_HAMMING2, crossCheck=True)
        # flann = cv2.FlannBasedMatcher(
        #     dict(algorithm=1, trees=2), dict(checks=50))
        self.detector = orb
        self.matcher = bf

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

        logger.info(f"仓库扫描: 吟唱用时{datetime.now() - start_time}")

    def 切图主程序(self, 拼接好的图片):
        圆 = 找圆(拼接好的图片)
        if 圆 is not None and len(圆[0]) > 2:
            圆 = np.round(圆[0, :]).astype("int")
            横坐标, 纵坐标 = 算坐标(圆)
        else:
            横坐标 = [188 + 234 * i for i in range(0, 8)]
            纵坐标 = [144, 430, 715]
            logger.warning("仓库扫描: 在这个分类下没有找到足够多的圆，使用预设坐标")
        切图列表 = 切图(横坐标, 纵坐标, 拼接好的图片)
        return 切图列表

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
            self.tap_index_element("warehouse")
            logger.info("仓库扫描: 从主界面点击仓库界面")

            time = datetime.now()
            任务组 = [
                (1200, self.knn模型_CONSUME, "消耗物品"),
                (1400, self.knn模型_NORMAL, "基础物品"),
                (1700, self.knn模型_MATERIAL, "养成材料"),
            ]

            for 任务 in 任务组:
                self.tap((任务[0], 70))
                if not self.find("depot_empty"):
                    self.分类扫描(任务[1], 任务[2])
                    logger.info(
                        f"仓库扫描: {任务[2]}识别，识别用时{datetime.now() - time}"
                    )
                else:
                    logger.info("仓库扫描: 这个分类下没有物品")
            logger.info(f"仓库扫描: {self.结果字典}")
            result = [
                int(datetime.now().timestamp()),
                json.dumps(self.结果字典, ensure_ascii=False),
                json.dumps(self.明日方舟工具箱json, ensure_ascii=False),
            ]
            depotinfo = pd.DataFrame([result], columns=["Timestamp", "Data", "json"])
            depotinfo.to_csv(
                self.仓库输出, mode="a", index=False, header=False, encoding="utf-8"
            )
        else:
            self.back_to_index()
        return True

    def 对比截图(self, image1, image2):
        image1 = cv2.cvtColor(image1, cv2.COLOR_RGB2GRAY)
        image2 = cv2.cvtColor(image2, cv2.COLOR_RGB2GRAY)
        keypoints1, descriptors1 = self.detector.detectAndCompute(image1, None)
        keypoints2, descriptors2 = self.detector.detectAndCompute(image2, None)
        matches = self.matcher.match(descriptors1, descriptors2)
        similarity = len(matches) / max(len(descriptors1), len(descriptors2))
        return similarity * 100

    def 分类扫描(self, 模型名称, 分类名称):
        截图列表 = []
        旧的截图 = self.recog.img
        旧的截图 = 旧的截图[140:1000, :]
        截图列表.append(旧的截图)
        # saveimg(旧的截图, "depot_1_screenshot")
        self.recog.update()

        logger.info(f"仓库扫描: 把第{len(截图列表)}页保存进内存中等待识别")
        if "养成材料" in 分类名称:
            while True:
                self.swipe_noinertia((1800, 450), (-1000, 0))  # 滑动
                self.recog.update()
                新的截图 = self.recog.img
                新的截图 = 新的截图[140:1000, :]
                # saveimg(新的截图, "depot_1_screenshot")
                相似度 = self.对比截图(截图列表[-1], 新的截图)
                if 相似度 < 70:
                    截图列表.append(新的截图)
                    logger.info(
                        f"仓库扫描: 把第{len(截图列表)}页保存进内存中等待识别,相似度{相似度}"
                    )
                else:
                    logger.info("仓库扫描: 这大抵是最后一页了")
                    break
        logger.info(f"仓库扫描: 截图读取完了,有{len(截图列表)}张截图")
        logger.info("仓库扫描: 开始计算裁切图像")

        if len(截图列表) > 1:
            拼接好的图片 = 拼图(截图列表)
        else:
            拼接好的图片 = 截图列表[0]
        # saveimg(拼接好的图片, "depot_2_stitcher")

        切图列表 = self.切图主程序(拼接好的图片)

        logger.info(f"仓库扫描: 需要识别{len(切图列表)}个物品")

        for [物品, 物品灰, id] in 切图列表:
            [物品名称, 物品数字] = self.匹配物品一次(物品, 物品灰, 模型名称)
            # saveimg_depot(
            #     物品,
            #     f"{id}_{物品名称}_{物品数字}.png",
            #     "depot_5_result",
            # )
            logger.debug([物品名称, 物品数字])
            if "作战记录" in 物品名称:
                logger.info("对经验卡进行重新识别")
                经验卡分类(物品)
            self.结果字典[物品名称] = self.结果字典.get(物品名称, 0) + 物品数字
            self.明日方舟工具箱json[key_mapping[物品名称][0]] = (
                self.明日方舟工具箱json.get(key_mapping[物品名称][0], 0) + 物品数字
            )
