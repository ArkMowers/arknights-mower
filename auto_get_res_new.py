import json
import shutil
import os
from collections import OrderedDict
import os
import cv2
import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from skimage.feature import hog
import pickle
from skimage import feature
import lzma
from datetime import datetime


class Arknights数据处理器:
    def __init__(self):
        self.当前时间戳 = datetime.now().timestamp()
        self.物品表 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/item_table.json"
        )
        self.干员表 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/character_table.json"
        )
        self.抽卡表 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/gacha_table.json"
        )
        self.关卡表 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/stage_table.json"
        )
        self.活动表 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/activity_table.json"
        )

    def 加载json(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def 添加物品(self):
        def 检查图标代码匹配(目标图标代码):
            限定十连 = self.抽卡表["limitTenGachaItem"]
            联动十连 = self.抽卡表["linkageTenGachaItem"]
            匹配结果 = False
            for 限定池子 in 限定十连:
                if 限定池子["itemId"] == 目标图标代码:
                    if self.当前时间戳 > 限定池子["endTime"]:
                        匹配结果 = True
                    break

            for 联动池子 in 联动十连:
                if 联动池子["itemId"] == 目标图标代码:
                    if self.当前时间戳 > 联动池子["endTime"]:
                        匹配结果 = True
                    break

            分割部分 = 目标图标代码.split("_")
            if len(分割部分) == 2 and 分割部分[0].endswith("recruitment10"):
                匹配结果 = True

            if len(分割部分) == 6 and int(分割部分[5]) < 2023:
                匹配结果 = True

            # if 目标图标代码 == "ap_supply_lt_60":
            #     匹配结果 = True

            抽卡 = self.抽卡表.get("gachaPoolClient", [])
            for 卡池 in 抽卡:
                if 卡池["LMTGSID"] == 目标图标代码 and self.当前时间戳 > int(
                    卡池["endTime"]
                ):
                    匹配结果 = True
            return 匹配结果

        物品_名称对 = {}

        for 物品代码, 物品数据 in self.物品表["items"].items():
            图标代码 = 物品数据["iconId"]
            排序代码 = 物品数据["sortId"]
            中文名称 = 物品数据["name"]
            分类类型 = 物品数据["classifyType"]
            源文件路径 = f"./ArknightsGameResource/item/{图标代码}.png"
            目标文件路径 = f"./ui/public/depot/{图标代码}.png"

            if 分类类型 != "NONE" and 排序代码 > 0:
                排除开关 = False
                排除开关 = 检查图标代码匹配(图标代码)
                if os.path.exists(源文件路径) and not 排除开关:
                    if not os.path.exists(目标文件路径):
                        shutil.copy(源文件路径, 目标文件路径)
                    物品_名称对[图标代码] = [
                        物品代码,
                        中文名称,
                        分类类型,
                        排序代码,
                    ]
                    print(f"复制 {源文件路径} 到 {目标文件路径}")
                else:
                    print(f"可以复制，但是未找到: {源文件路径}")

        # 物品_名称对 = OrderedDict(物品_名称对)
        with open(
            "./arknights_mower/data/key_mapping.json", "w", encoding="utf8"
        ) as json_file:
            json.dump(物品_名称对, json_file, ensure_ascii=False)
        with open("./ui/src/pages/key_mapping.json", "w", encoding="utf8") as json_file:
            json.dump(物品_名称对, json_file, ensure_ascii=False)
        print()

    def 添加干员(self):
        干员_名称列表 = []

        for 干员代码, 干员数据 in self.干员表.items():
            if not 干员数据["itemObtainApproach"]:
                continue

            干员名 = 干员数据["name"]
            干员_名称列表.append(干员名)
            干员头像路径 = f"./ArknightsGameResource/avatar/{干员代码}.png"
            目标路径 = f"./ui/public/avatar/{干员数据['name']}.png"
            print(f"{干员名}: {干员代码}")

            shutil.copy(干员头像路径, 目标路径)

        干员_名称列表.sort(key=len)
        with open("./arknights_mower/data/agent.json", "w", encoding="utf-8") as f:
            json.dump(干员_名称列表, f, ensure_ascii=False)
        print()

    def 读取卡池(self):

        抽卡 = self.抽卡表.get("gachaPoolClient", [])
        卡池类型映射 = {
            "SINGLE": "单人池",
            "LIMITED": "限定池",
            "NORM": "普通池",
            "CLASSIC": "中坚池",
            "CLASSIC_ATTAIN": "跨年中坚池",
            "LINKAGE": "联动池",
            "ATTAIN": "跨年池",
            "FESCLASSIC": "中坚甄选",
        }

        for 项 in 抽卡:
            卡池名称 = 项.get("gachaPoolName")
            开始时间戳 = 项.get("openTime")
            结束时间戳 = 项.get("endTime")
            卡池类型代码 = 项.get("gachaPoolId")
            卡池出人 = 项.get("dynMeta")

            if self.当前时间戳 < 结束时间戳:
                卡池类型 = 卡池类型映射.get(卡池类型代码.split("_")[0], 卡池类型代码)
                if 卡池类型代码.split("_")[1] == "ATTAIN":
                    卡池类型 = "跨年中坚池"
                if 卡池名称 == "适合多种场合的强力干员":
                    卡池名称 = 卡池类型
                开始时间 = datetime.fromtimestamp(开始时间戳)
                结束时间 = datetime.fromtimestamp(结束时间戳 + 1)
                print("卡池名称:", 卡池名称)
                print("卡池类型:", 卡池类型)
                if 卡池类型 == "中坚池":
                    print(
                        卡池出人["main6RarityCharId"],
                        卡池出人["sub6RarityCharId"],
                        卡池出人["rare5CharList"],
                    )
                if self.当前时间戳 > 开始时间戳:
                    print("正在进行")
                    print("卡池结束时间:", 结束时间)
                else:
                    print("卡池开始时间:", 开始时间)
                    print("卡池结束时间:", 结束时间)
                print(卡池类型代码)
                print()

    def 读取关卡(self):
        可以刷的活动关卡 = []
        关卡 = self.关卡表["stageValidInfo"]
        还未结束的非常驻关卡 = {
            键: 值
            for 键, 值 in 关卡.items()
            if 值["endTs"] != -1 and 值["endTs"] > self.当前时间戳
        }
        还未结束的非常驻关卡 = dict(sorted(还未结束的非常驻关卡.items()))
        for 键, _ in 还未结束的非常驻关卡.items():
            关卡代码 = self.关卡表["stages"][键]["code"]
            if 键.endswith("#f#"):
                关卡代码 += " 突袭"
            关卡名称 = self.关卡表["stages"][键]["name"]
            关卡结束时间戳 = 还未结束的非常驻关卡[键]["endTs"]
            关卡结束时间 = datetime.fromtimestamp(还未结束的非常驻关卡[键]["endTs"] + 1)
            关卡掉落表 = self.关卡表["stages"][键]["stageDropInfo"]["displayRewards"]
            关卡掉落 = {"首次掉落": [], "普通掉落": []}
            for item in 关卡掉落表:
                if item["dropType"] == 8:
                    关卡掉落["首次掉落"].append(
                        self.物品表["items"][item["id"]]["name"]
                    )
                else:
                    关卡掉落["普通掉落"].append(
                        self.物品表["items"][item["id"]]["name"]
                    )
            if 关卡掉落["普通掉落"] != []:
                可以刷的活动关卡.append(
                    {
                        "id": 关卡代码,
                        "name": 关卡名称,
                        "drop": 关卡掉落,
                        "end": 关卡结束时间戳,
                    }
                )
            # print(关卡代码, 关卡名称, 关卡掉落, 关卡结束时间)
            print(可以刷的活动关卡)
        with open(
            "./ui/src/pages/stage_data/event_data.json", "w", encoding="utf-8"
        ) as f:
            json.dump(可以刷的活动关卡, f, ensure_ascii=False)

    def knn模型训练(self):
        def 提取特征点(image):
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

        def 加载图片特征点_标签(directory,缩小宽度=64):
            images = []
            labels = []
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                image = cv2.imread(filepath)
                image = cv2.resize(image, (218, 218))
                image = cv2.resize(image, (缩小宽度, 缩小宽度))
                image_features = 提取特征点(image)
                images.append(image_features)
                labels.append(filename[:-4])  # 假设图片名称即为标签
            return images, labels

        def 训练knn模型(images, labels, k=1):
            knn_classifier = KNeighborsClassifier(n_neighbors=k, n_jobs=-1)
            knn_classifier.fit(images, labels)
            return knn_classifier

        def 保存knn模型(classifier, filename):
            with lzma.open(filename, "wb") as f:
                pickle.dump(classifier, f)

        time = datetime.now()
        模板特征点, 模板标签 = 加载图片特征点_标签("./ui/public/depot/")
        knn_classifier = 训练knn模型(模板特征点, 模板标签, k=1)
        保存knn模型(knn_classifier, "./arknights_mower/models/depot.pkl")
        print(datetime.now() - time)


if __name__ == "__main__":
    数据处理器 = Arknights数据处理器()
    数据处理器.添加物品()
    数据处理器.添加干员()
    数据处理器.读取卡池()
    数据处理器.读取关卡()
    数据处理器.knn模型训练()

# 加载模型
# model_path = "knn_classifier.pkl"
# loaded_knn_classifier = load_classifier(model_path)

# # 对指定文件夹中的图像进行预测
# folder_path = "./output/depot"
# time = datetime.now()
# predictions = predict_images_in_folder(folder_path, loaded_knn_classifier)
# for filename, predicted_label in predictions:
#     if filename.startswith(predicted_label):
#         print(f"{filename}: {predicted_label} 成功")
#     else:
#         print(f"{filename}: {predicted_label} 失败")
# print(datetime.now() - time)
# # 打印预测结果
