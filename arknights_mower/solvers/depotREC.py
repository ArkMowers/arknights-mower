import cv2
import functools
import itertools
import json
import multiprocessing
import numpy as np
import os
import pandas as pd
import pickle
import re
import time
from datetime import datetime
from pathlib import Path

import lzma
from rapidocr_onnxruntime import RapidOCR
from sklearn.cluster import KMeans
from sklearn.neighbors import KNeighborsClassifier
from skimage.feature import hog
from skimage.metrics import structural_similarity

from .. import __rootdir__
from ..data import key_mapping
from ..utils import typealias as tp
from ..utils.device import Device
from ..utils.image import loadimg
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


class depotREC(BaseSolver):
    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        time = datetime.now()
        os.makedirs("temp", exist_ok=True)
        sift = cv2.SIFT_create()
        # surf = cv2.xfeatures2d.SURF_create(**surf_arg)
        ORB = cv2.ORB_create()
        self.detector = sift  # 检测器类型
        self.结果目录 = get_path("@app/screenshot/depot")
        get_path("@app/screenshot/depot").mkdir(exist_ok=True)
        self.matcher = cv2.FlannBasedMatcher(
            dict(algorithm=1, trees=2), dict(checks=50)
        )  # 初始化一个识别
        knn模型目录 = get_path("@internal/arknights_mower\models\depot.pkl")
        self.仓库输出 = get_path("@app/tmp/depotresult.csv")
        with lzma.open(knn模型目录, "rb") as pkl:
            self.knn模型 = pickle.load(pkl)
        # self.时间模板 = self.导入_时间模板()
        self.模板名称 = key_mapping
        self.物品数字 = self.导入_数字模板()
        self.截图字典 = {}  # 所有截图的字典（尽量不重不漏）
        self.截图计数器 = 1  # 所有截图的列表的计数器
        # self.仓库图片 = self.导入_仓库图片()  # [140:1000, :] 需要传入&裁剪
        self.结果字典 = {}
        logger.info(f"吟唱用时{datetime.now() - time}")

    # def 导入_时间模板(self) -> list[str, np.ndarray]:
    #     templates_folder_path = "./item_expire_time"
    #     templates_list = []
    #     file_list = os.listdir(templates_folder_path)
    #     for file_name in file_list:
    #         file_path = os.path.join(templates_folder_path, file_name)
    #         image = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
    #         templates_list.append([file_name, image])

    # def 导入_模板名称(self) -> dict:
    #     with open("key_mapping.json", "r", encoding="utf-8") as file:
    #         json_data = json.loads(file.read())
    #         return json_data

    def 导入_数字模板(self) -> list:
        模板文件夹 = get_path("@internal/arknights_mower/resources/depot_num")
        数字模板列表 = []
        for 文件名 in os.listdir(模板文件夹):
            文件路径 = os.path.join(模板文件夹, 文件名)
            数字模板列表.append(cv2.imread(文件路径, cv2.IMREAD_GRAYSCALE))
        return 数字模板列表

    def 识别空物品(self, 物品灰) -> bool:
        # 对灰度图像进行阈值处理，得到二值图像
        _, 二值图 = cv2.threshold(物品灰, 50, 255, cv2.THRESH_BINARY)
        # 计算白色像素所占的比例
        白像素个数 = cv2.countNonZero(二值图)
        所有像素个数 = 二值图.shape[0] * 二值图.shape[1]
        白像素比值 = int((白像素个数 / 所有像素个数) * 100)
        if 白像素比值 == 100:
            logger.info("删除一次空物品")
            return False
        else:
            return True

    def 找几何中心(self, coordinates, n_clusters=3) -> list:
        coordinates_array = np.array(coordinates).reshape(-1, 1)
        kmeans = KMeans(n_clusters=n_clusters)
        kmeans.fit(coordinates_array)
        centers = kmeans.cluster_centers_.flatten().astype(int)
        return centers

    def 拼图(self, 图片列表) -> np.ndarray:
        stitcher = cv2.Stitcher.create(mode=cv2.Stitcher_SCANS)
        status, result = stitcher.stitch(图片列表)

        if status == cv2.Stitcher_OK:
            cv2.imwrite(f"{self.结果目录}/result.png", result)
            logger.info("拼接完成。")
        else:
            logger.info("拼接失败:", status)

        return result

    def 找圆(
        self, 拼接结果, 参数1=50, 参数2=30, 圆心间隔=230, 最小半径=90, 最大半径=100
    ):
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

        if 圆 is not None:
            圆 = np.round(圆[0, :]).astype("int")
            for x, y, r in 圆:
                cv2.circle(拼接结果, (x, y), r, (128, 255, 0), 4)
            cv2.imwrite(f"{self.结果目录}/result_with_circles.png", 拼接结果)
        return 圆

    def 算坐标(self, 圆) -> tuple[list, list]:
        if 圆 is not None:
            circles_x = sorted(圆[:, 0])
            groups = []
            start_index = 0

            for i in range(1, len(circles_x)):
                if circles_x[i] - circles_x[i - 1] >= 20:
                    groups.append(circles_x[start_index:i])
                    start_index = i

            groups.append(circles_x[start_index:])
            circles_x = [int(sum(group) / len(group)) for group in groups]

            circles_y = self.找几何中心(圆[:, 1], 3)
            return circles_x, circles_y

    def 切图(self, 圆心x坐标, 圆心y坐标, 拼接结果, 正方形边长=130) -> list[np.ndarray]:
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
                if self.识别空物品(正方形灰):
                    图片.append([正方形, 正方形灰])
        return 图片

    def 切图主程序(self, 仓库图片):
        拼接好的图片 = self.拼图(仓库图片)
        圆 = self.找圆(拼接好的图片)
        横坐标, 纵坐标 = self.算坐标(圆)
        return self.切图(横坐标, 纵坐标, 拼接好的图片)

    def 读取物品数字(self, 数字图片, 物品名称, 识别次数, 距离阈值=5, 阈值=0.85):

        结果 = {}

        # 匹配数字模板
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

        # # 对数字进行格式化
        # 物品个数 = re.sub(r"\.{2,}", "", 物品个数)
        # 物品个数 = 物品个数[1:] if 物品个数.startswith(".") else 物品个数

        if not 物品个数:
            return 0
        # # 格式化数字
        格式化数字 = int("".join(re.findall(r"\d+", 物品个数))) * (
            1000 if "万" in 物品个数 else 1
        )
        # 保存结果图片
        cv2.imencode(".png", 数字图片)[1].tofile(
            os.path.join(self.结果目录, f"{物品名称}_{格式化数字}_{识别次数}.png")
        )

        return 格式化数字

    def 匹配物品一次(self, 物品, 物品灰, 次数):
        物品切 = 物品[21:239, 21:239]
        物品特征 = cv2.resize(物品特征, (64, 64)) ## 把图片缩小了
        物品特征 = self.特征点提取(物品切)
        predicted_label = self.knn模型.predict([物品特征])
        物品数字 = self.读取物品数字(物品灰, predicted_label[0], 次数)
        return [predicted_label[0], 物品数字]

    def 特征点提取(self, image):
        # 提取HOG特征
        hog_features, _ = hog(
            image,
            orientations=18,
            pixels_per_cell=(8, 8),
            cells_per_block=(2, 2),
            block_norm="L2-Hys",
            visualize=True,
            transform_sqrt=True,
        )
        return hog_features

    def run(self) -> None:
        logger.info("Start: 仓库扫描")
        super().run()

    def transition(self) -> bool:
        logger.info("仓库扫描: 回到桌面")
        self.back_to_index()
        if self.scene() == Scene.INDEX:
            logger.info("仓库扫描: 从主界面点击仓库界面")
            self.tap_themed_element("index_warehouse")

            旧的截图 = self.recog.img
            旧的截图 = cv2.cvtColor(旧的截图[140:1000, :], cv2.COLOR_RGB2BGR)
            self.recog.update()
            self.截图字典[self.截图计数器] = 旧的截图  # 1 第一张图片
            logger.info(f"仓库扫描: 把第{self.截图计数器}页保存进内存中等待识别")
            while True:
                self.swipe_noinertia((1800, 450), (-1000, 0))  # 滑动
                self.recog.update()
                新的截图 = self.recog.img
                新的截图 = cv2.cvtColor(新的截图[140:1000, :], cv2.COLOR_RGB2BGR)
                相似度 = self.compare_screenshot(
                    self.截图字典[self.截图计数器], 新的截图
                )
                self.截图计数器 += 1  # 第二张图片
                if 相似度 < 70:
                    self.截图字典[self.截图计数器] = 新的截图
                    logger.info(
                        f"仓库扫描: 把第{self.截图计数器}页保存进内存中等待识别,相似度{相似度}"
                    )
                else:
                    logger.info("仓库扫描: 这大抵是最后一页了")
                    break
            logger.info(f"仓库扫描: 截图读取完了,有{len(self.截图字典)}张截图")
            logger.info(f"仓库扫描: 开始计算裁切图像")
            time = datetime.now()
            self.截图列表 = list(self.截图字典.values())
            for index, img in enumerate(self.截图列表):
                cv2.imwrite(f"{self.结果目录}/{index}.png", img)
            self.切图列表 = self.切图主程序(self.截图列表)
            logger.info(
                f"仓库扫描: 切图用时{datetime.now() - time},需要识别{len(self.切图列表)}个物品"
            )

            time = datetime.now()
            for idx, [物品, 物品灰] in enumerate(self.切图列表):
                [物品名称, 物品数字] = self.匹配物品一次(物品, 物品灰, idx)
                logger.debug([物品名称, 物品数字])
                if 物品名称 in self.结果字典:
                    self.结果字典[物品名称] += 物品数字
                else:
                    self.结果字典[物品名称] = 物品数字
            logger.info(f"仓库扫描: 匹配，识别用时{datetime.now() - time}")
            logger.info(f"仓库扫描:结果{self.结果字典}")
            result = [
                int(datetime.now().timestamp()),
                json.dumps(self.结果字典, ensure_ascii=False),
            ]
            df = pd.DataFrame([result], columns=["Timestamp", "Data"])
            df.to_csv(self.仓库输出, mode="a", index=False, header=True)

        return True

    def compare_screenshot(self, image1, image2):
        image1 = cv2.cvtColor(image1, cv2.COLOR_RGB2GRAY)
        image2 = cv2.cvtColor(image2, cv2.COLOR_RGB2GRAY)
        keypoints1, descriptors1 = self.detector.detectAndCompute(image1, None)
        _, descriptors2 = self.detector.detectAndCompute(image2, None)

        matches = self.matcher.knnMatch(descriptors1, descriptors2, k=2)
        good_matches = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:
                good_matches.append(m)
        similarity = len(good_matches) / len(keypoints1) * 100
        return similarity
