import json
import lzma
import os
import pickle
import re
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.feature import hog
from sklearn.neighbors import KNeighborsClassifier

from arknights_mower.utils.image import loadimg, thres2


def 提取干员名图片(imgpath, 裁剪区域: int = 1, 模式: int = 1):
    """
    imgpath: 选人界面截图的路径，需要待提取干员处于最左侧；
    裁剪区域：1为左上，2为左下；
    模式：1为基建选择，2为训练室的训练位选择。
    保存到本地并手动重命名为干员名后可以用于训练模型。
    """
    # 只做两个裁剪区域，其他区域可能存在裁剪不准的问题
    pos = {
        "常规站": {"左上": (631, 488), "左下": (631, 909)},
        "训练室": {"左上": (578, 479), "左下": (578, 895)},
    }
    shape = {"常规站": (190, 32), "训练室": (180, 27)}
    img = Image.open(imgpath)
    站 = "常规站" if 模式 == 1 else "训练室"
    位置 = "左上" if 裁剪区域 == 1 else "左下"
    (x, y) = pos[站][位置]
    (w, h) = shape[站]
    img = img.crop((x, y, x + w, y + h))
    img.save("./arknights_mower/opname/unknown.png")


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
        self.基建表 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/building_data.json"
        )
        self.游戏变量 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/gamedata_const.json"
        )
        self.装仓库物品的字典 = {"NORMAL": [], "CONSUME": [], "MATERIAL": []}

        self.常驻关卡 = self.加载json("arknights_mower/data/stage_data.json")

        self.所有buff = []

        self.限定十连 = self.抽卡表["limitTenGachaItem"]
        self.联动十连 = self.抽卡表["linkageTenGachaItem"]
        self.普通十连 = self.抽卡表["normalGachaItem"]
        self.所有卡池 = self.限定十连 + self.联动十连 + self.普通十连

    def 加载json(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def 添加物品(self):
        def 检查图标代码匹配(目标图标代码, 物品类型):
            匹配结果 = False
            for 池子限时物品 in self.所有卡池:
                if (
                    池子限时物品["itemId"] == 目标图标代码
                    and self.当前时间戳 > 池子限时物品["endTime"]
                ):
                    匹配结果 = True
                    break
            分割部分 = 目标图标代码.split("_")
            if len(分割部分) == 2 and 分割部分[0].endswith("recruitment10"):
                匹配结果 = True
            if len(分割部分) == 6 and int(分割部分[5]) < 2023:
                匹配结果 = True

            if len(分割部分) == 3 and 目标图标代码.startswith("uni"):
                匹配结果 = True

            if len(分割部分) == 3 and 目标图标代码.startswith("voucher_full"):
                匹配结果 = True
            if 目标图标代码 == "ap_supply_lt_60":
                匹配结果 = True
            抽卡 = self.抽卡表.get("gachaPoolClient", [])
            for 卡池 in 抽卡:
                if 卡池["LMTGSID"] == 目标图标代码 and self.当前时间戳 > int(
                    卡池["endTime"]
                ):
                    匹配结果 = True
            return 匹配结果

        self.物品_名称对 = {}

        if not os.path.exists("./ui/public/depot/EXP.webp"):
            png_image = Image.open("./ArknightsGameResource/item/EXP_PLAYER.png")
            png_image.save("./ui/public/depot/EXP.webp", "WEBP")
        for 物品代码, 物品数据 in self.物品表["items"].items():
            中文名称 = 物品数据.get("name", "")
            图标代码 = 物品数据.get("iconId", "")
            排序代码 = 物品数据.get("sortId", "")

            分类类型 = 物品数据.get("classifyType", "")
            物品类型 = 物品数据.get("itemType", "")

            源文件路径 = f"./ArknightsGameResource/item/{图标代码}.png"
            排除开关 = False
            排除开关 = 检查图标代码匹配(图标代码, 物品类型)
            if 分类类型 != "NONE" and 排序代码 > 0 and not 排除开关:
                if os.path.exists(源文件路径):
                    目标文件路径 = f"./ui/public/depot/{中文名称}.webp"
                    self.装仓库物品的字典[分类类型].append([目标文件路径, 源文件路径])
                    if not os.path.exists(目标文件路径):
                        png_image = Image.open(源文件路径)
                        png_image.save(目标文件路径, "WEBP")
                    templist = [物品代码, 图标代码, 中文名称, 分类类型, 排序代码]
                    self.物品_名称对[物品代码] = templist
                    self.物品_名称对[中文名称] = templist
                    print(f"复制 {源文件路径} 到 {目标文件路径}")
                else:
                    print(f"可以复制，但是未找到: {源文件路径}")
        with open(
            "./arknights_mower/data/key_mapping.json", "w", encoding="utf8"
        ) as json_file:
            json.dump(self.物品_名称对, json_file, ensure_ascii=False, indent=4)
        print()

    def 添加干员(self):
        干员_名称列表 = []
        干员_职业列表 = {}
        for 干员代码, 干员数据 in self.干员表.items():
            if not 干员数据["itemObtainApproach"]:
                continue
            干员名 = 干员数据["name"]
            干员_名称列表.append(干员名)
            干员_职业列表[干员名] = 干员数据["profession"]
            干员头像路径 = f"./ArknightsGameResource/avatar/{干员代码}.png"
            目标路径 = f"./ui/public/avatar/{干员数据['name']}.webp"
            print(f"{干员名}: {干员代码}")
            try:
                png_image = Image.open(干员头像路径)
                png_image.save(目标路径, "WEBP")
            except Exception as ex:
                print("头像读取失败")
                print(ex)
        干员_名称列表.sort(key=len)
        with open(
            "./arknights_mower/data/agent_profession.json", "w", encoding="utf-8"
        ) as f:
            json.dump(干员_职业列表, f, ensure_ascii=False)
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

    def 读取活动关卡(self):
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
            # 关卡结束时间 = datetime.fromtimestamp(还未结束的非常驻关卡[键]["endTs"] + 1)
            关卡掉落表 = self.关卡表["stages"][键]["stageDropInfo"][
                "displayDetailRewards"
            ]

            关卡掉落 = {}
            突袭首次掉落 = [
                self.物品表.get("items", {}).get(item["id"], {}).get("name", item["id"])
                for item in 关卡掉落表
                if item["dropType"] == 1
            ]
            常规掉落 = [
                self.物品表.get("items", {}).get(item["id"], {}).get("name", item["id"])
                for item in 关卡掉落表
                if item["dropType"] == 2
            ]
            特殊掉落 = [
                self.物品表.get("items", {}).get(item["id"], {}).get("name", item["id"])
                for item in 关卡掉落表
                if item["dropType"] == 3
            ]
            额外物资 = [
                self.物品表.get("items", {}).get(item["id"], {}).get("name", item["id"])
                for item in 关卡掉落表
                if item["dropType"] == 4
            ]
            首次掉落 = [
                self.物品表.get("items", {}).get(item["id"], {}).get("name", item["id"])
                for item in 关卡掉落表
                if item["dropType"] == 8
            ]
            关卡掉落 = {
                "突袭首次掉落": 突袭首次掉落,
                "常规掉落": 常规掉落,
                "首次掉落": 首次掉落,
                "特殊掉落": 特殊掉落,
                "额外物资": 额外物资,
            }

            self.常驻关卡.append(
                {
                    "id": 关卡代码,
                    "name": 关卡名称,
                    "drop": 关卡掉落,
                    "end": 关卡结束时间戳,
                    "周一": 1,
                    "周二": 1,
                    "周三": 1,
                    "周四": 1,
                    "周五": 1,
                    "周六": 1,
                    "周日": 1,
                }
            )
        unkey = 0
        for item in self.常驻关卡:
            item["key"] = unkey
            unkey += 1
        with open(
            "./ui/src/pages/stage_data/event_data.json", "w", encoding="utf-8"
        ) as f:
            json.dump(self.常驻关卡, f, ensure_ascii=False, indent=2)

    def load_recruit_data(self):
        recruit_data = {}
        recruit_result_data = {
            4: [],
            3: [],
            2: [],
            1: [],
            -1: [],
        }
        # for 干员代码, 干员数据 in self.干员表.items():
        #     print(干员代码,干员数据)
        recruit_list = self.抽卡表["recruitDetail"].replace("\\n<@rc.eml>", "")
        recruit_list = recruit_list.replace("\\n", "")
        recruit_list = recruit_list.replace("\r", "")
        recruit_list = recruit_list.replace("★", "")
        recruit_list = recruit_list.replace("<@rc.eml>", "")
        recruit_list = recruit_list.replace("</>", "")
        recruit_list = recruit_list.replace("/", "")
        recruit_list = recruit_list.replace(" ", "\n")
        recruit_list = recruit_list.replace("--------------------", "")
        recruit_list = recruit_list.replace("<@rc.title>公开招募说明", "")
        recruit_list = recruit_list.replace("<@rc.em>※稀有职业需求招募说明※", "")
        recruit_list = recruit_list.replace(
            "<@rc.em>当职业需求包含高级资深干员，且招募时限为9小时时，招募必得6星干员",
            "",
        )
        recruit_list = recruit_list.replace(
            "<@rc.em>当职业需求包含资深干员同时不包含高级资深干员，且招募时限为9小时，则该次招募必得5星干员",
            "",
        )
        recruit_list = recruit_list.replace("<@rc.subtitle>※全部可能出现的干员※", "")
        recruit_list = recruit_list.replace("绿色高亮的不可寻访干员，可以在此招募", "")
        recruit_list = recruit_list.split("\n")

        profession = {
            "MEDIC": "医疗干员",
            "WARRIOR": "近卫干员",
            "SPECIAL": "特种干员",
            "SNIPER": "狙击干员",
            "CASTER": "术师干员",
            "TANK": "重装干员",
            "SUPPORT": "辅助干员",
            "PIONEER": "先锋干员",
        }

        for 干员代码, 干员数据 in self.干员表.items():
            干员名 = 干员数据["name"]

            if 干员数据["profession"] not in profession:
                continue

            if 干员名 in recruit_list:
                tag = 干员数据["tagList"]
                # 数据中稀有度从0-5
                干员数据["rarity"] = 干员数据["rarity"] + 1
                if len(干员名) <= 4:
                    recruit_result_data[len(干员名)].append(干员代码)
                else:
                    recruit_result_data[-1].append(干员代码)
                if 干员数据["rarity"] == 5:
                    tag.append("资深干员")
                elif 干员数据["rarity"] == 6:
                    tag.append("高级资深干员")

                if 干员数据["position"] == "MELEE":
                    tag.append("近战位")
                elif 干员数据["position"] == "RANGED":
                    tag.append("远程位")

                tag.append(profession[干员数据["profession"]])

                recruit_data[干员代码] = {
                    "name": 干员名,
                    "stars": 干员数据["rarity"],
                    "tags": 干员数据["tagList"],
                }
                print(
                    "{} stars：{} tags:{}".format(
                        干员名, 干员数据["rarity"], 干员数据["tagList"]
                    )
                )
        print("载入公招干员数据{}个".format(len(recruit_data)))
        with open("./arknights_mower/data/recruit.json", "w", encoding="utf-8") as f:
            json.dump(recruit_data, f, ensure_ascii=False, indent=4)

        with open(
            "./arknights_mower/data/recruit_result.json", "w", encoding="utf-8"
        ) as f:
            json.dump(recruit_result_data, f, ensure_ascii=False, indent=4)

    def load_recruit_template(self):
        # !/usr/bin/env python3
        template = {}
        with open("./arknights_mower/data/recruit.json", "r", encoding="utf-8") as f:
            recruit_operators = json.load(f)

        font = ImageFont.truetype("FZDYSK.TTF", 120)
        print(len(recruit_operators))
        for operator in recruit_operators:
            im = Image.new(mode="RGBA", size=(1920, 1080))
            draw = ImageDraw.Draw(im)
            draw.text((0, 0), recruit_operators[operator]["name"], font=font)
            im = im.crop(im.getbbox())
            im = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
            template[operator] = im

        with lzma.open("arknights_mower/models/recruit_result.pkl", "wb") as f:
            pickle.dump(template, f)

    def load_recruit_tag(self):
        with open("./arknights_mower/data/recruit.json", "r", encoding="utf-8") as f:
            recruit_agent = json.load(f)

        font = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 30
        )
        recruit_tag = ["资深干员", "高级资深干员"]
        recruit_tag_template = {}
        for x in recruit_agent.values():
            recruit_tag += x["tags"]
        recruit_tag = list(set(recruit_tag))
        for tag in recruit_tag:
            im = Image.new(mode="RGBA", color=(49, 49, 49), size=(215, 70))
            W, H = im.size
            draw = ImageDraw.Draw(im)
            _, _, w, h = draw.textbbox((0, 0), tag, font=font)
            draw.text(((W - w) / 2, (H - h) / 2 - 5), tag, font=font)
            recruit_tag_template[tag] = cv2.cvtColor(
                np.array(im.crop(im.getbbox())), cv2.COLOR_RGB2BGR
            )
        with lzma.open("./arknights_mower/models/recruit.pkl", "wb") as f:
            pickle.dump(recruit_tag_template, f)

    def load_recruit_resource(self):
        self.load_recruit_data()
        self.load_recruit_template()
        self.load_recruit_tag()

    def 训练仓库的knn模型(self, 模板文件夹, 模型保存路径):
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

        def 加载图片特征点_标签(模板类型):
            特征点列表 = []
            标签列表 = []
            for [目标文件路径, 源文件路径] in self.装仓库物品的字典[模板类型]:
                模板 = cv2.imread(源文件路径)
                模板 = cv2.resize(模板, (213, 213))
                特征点 = 提取特征点(模板)
                特征点列表.append(特征点)
                标签列表.append(self.物品_名称对[目标文件路径[18:-5]][2])
            return 特征点列表, 标签列表

        def 训练knn模型(images, labels):
            knn_classifier = KNeighborsClassifier(
                weights="distance", n_neighbors=1, n_jobs=-1
            )
            knn_classifier.fit(images, labels)
            return knn_classifier

        def 保存knn模型(classifier, filename):
            with lzma.open(filename, "wb") as f:
                pickle.dump(classifier, f)

        模板特征点, 模板标签 = 加载图片特征点_标签(模板文件夹)
        knn模型 = 训练knn模型(模板特征点, 模板标签)
        保存knn模型(knn模型, 模型保存路径)

    def 批量训练并保存扫仓库模型(self):
        self.训练仓库的knn模型("NORMAL", "./arknights_mower/models/NORMAL.pkl")
        self.训练仓库的knn模型("CONSUME", "./arknights_mower/models/CONSUME.pkl")
        # self.训练仓库的knn模型("MATERIAL", "./arknights_mower/models/MATERIAL.pkl")

    def 训练在房间内的干员名的模型(self):
        font = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 37
        )

        data = {}

        kernel = np.ones((12, 12), np.uint8)

        with open("./arknights_mower/data/agent.json", "r", encoding="utf-8") as f:
            agent_list = json.load(f)
        for operator in sorted(agent_list, key=lambda x: len(x), reverse=True):
            img = Image.new(mode="L", size=(400, 100))
            draw = ImageDraw.Draw(img)
            draw.text((50, 20), operator, fill=(255,), font=font)
            img = np.array(img, dtype=np.uint8)
            img = thres2(img, 200)
            dilation = cv2.dilate(img, kernel, iterations=1)
            contours, _ = cv2.findContours(
                dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )
            rect = map(lambda c: cv2.boundingRect(c), contours)
            x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
            img = img[y : y + h, x : x + w]
            tpl = np.zeros((46, 265), dtype=np.uint8)
            tpl[: img.shape[0], : img.shape[1]] = img
            # cv2.imwrite(f"/home/zhao/Desktop/data/{operator}.png", tpl)
            data[operator] = tpl

        with lzma.open("arknights_mower/models/operator_room.model", "wb") as f:
            pickle.dump(data, f)

    def 训练选中的干员名的模型(self):
        font31 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 31
        )
        font30 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 30
        )
        font25 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 25
        )
        font23 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 23
        )

        font27 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 27
        )

        data = {}

        kernel = np.ones((10, 10), np.uint8)

        with open("./arknights_mower/data/agent.json", "r", encoding="utf-8") as f:
            agent_list = json.load(f)
        for idx, operator in enumerate(agent_list):
            font = font31
            if not operator[0].encode().isalpha():
                if len(operator) == 7:
                    if "·" in operator:
                        # 维娜·维多利亚 识别的临时解决办法
                        font = font27
                    else:
                        font = font25
                elif operator == "Miss.Christine":
                    font = font23
                elif len(operator) == 6:
                    font = font30
            img = Image.new(mode="L", size=(400, 100))
            draw = ImageDraw.Draw(img)
            if "·" in operator:
                x, y = 50, 20
                char_index = {
                    i: False for i, char in enumerate(operator) if char == "·"
                }
                for i, char in enumerate(operator):
                    if i in char_index and not char_index[i]:
                        x -= 8
                        char_index[i] = True
                        if i + 1 not in char_index and char == "·":
                            char_index[i + 1] = False
                    draw.text((x, y), char, fill=(255,), font=font)  # 绘制每个字符
                    char_width, char_height = font.getbbox(char)[
                        2:4
                    ]  # getbbox 返回 (x1, y1, x2, y2)
                    x += char_width
            elif operator == "Miss.Christine":
                x, y = 50, 20
                for i, char in enumerate(operator):
                    draw.text((x, y), char, fill=(255,), font=font)
                    char_width, char_height = font.getbbox(char)[2:4]
                    x += char_width - 1
            else:
                draw.text((50, 20), operator, fill=(255,), font=font)

            img = np.array(img, dtype=np.uint8)
            local_imgpath = f"arknights_mower/opname/{operator}.png"
            if os.path.exists(local_imgpath):
                with open(local_imgpath, "rb") as f:
                    img_data = f.read()
                img_array = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
            img = thres2(img, 140)
            dilation = cv2.dilate(img, kernel, iterations=1)
            contours, _ = cv2.findContours(
                dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )
            rect = map(lambda c: cv2.boundingRect(c), contours)
            x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
            img = img[y : y + h, x : x + w]
            tpl = np.zeros((42, 200), dtype=np.uint8)
            tpl[: img.shape[0], : img.shape[1]] = img
            # cv2.imwrite(f"/home/zhao/Desktop/data/{operator}.png", tpl)
            data[operator] = tpl

        with lzma.open("arknights_mower/models/operator_select.model", "wb") as f:
            pickle.dump(data, f)

    def 训练训练室干员名的模型(self):
        font30 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 30
        )
        font28 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 28
        )
        font25 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 25
        )

        font24 = ImageFont.truetype(
            "arknights_mower/fonts/SourceHanSansCN-Medium.otf", 24
        )

        data = {}

        kernel = np.ones((10, 10), np.uint8)

        with open("./arknights_mower/data/agent.json", "r", encoding="utf-8") as f:
            agent_list = json.load(f)
        for idx, operator in enumerate(agent_list):
            font = font30
            if not operator[0].encode().isalpha():
                if len(operator) == 7:
                    if "·" in operator:
                        font = font25  # 维娜·维多利亚的特殊字号
                    else:
                        font = font24  # 泰拉大陆调查团
                elif len(operator) == 6:
                    font = font28
            img = Image.new(mode="L", size=(400, 100))
            draw = ImageDraw.Draw(img)
            draw.text((50, 20), operator, fill=(255,), font=font)

            img = np.array(img, dtype=np.uint8)
            local_imgpath = f"arknights_mower/opname/{operator}_train.png"
            if os.path.exists(local_imgpath):
                with open(local_imgpath, "rb") as f:
                    img_data = f.read()
                img_array = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
            img = thres2(img, 140)
            dilation = cv2.dilate(img, kernel, iterations=1)
            contours, _ = cv2.findContours(
                dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )
            rect = map(lambda c: cv2.boundingRect(c), contours)
            x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
            img = img[y : y + h, x : x + w]
            tpl = np.zeros((42, 200), dtype=np.uint8)
            h = min(img.shape[0], tpl.shape[0])
            w = min(img.shape[1], tpl.shape[1])
            tpl[:h, :w] = img[:h, :w]
            data[operator] = tpl

        with lzma.open("arknights_mower/models/operator_train.model", "wb") as f:
            pickle.dump(data, f)

    def auto_fight_avatar(self):
        avatar_mapping = {}  # char_285_medic2 -> Lancet-2
        for name, data in self.干员表.items():
            avatar_mapping[name] = data["name"]
        avatar = {}  # Lancet-2 -> List[avatar image]
        avatar_path = "./ArknightsGameResource/avatar"
        for i in os.listdir(avatar_path):
            # i: char_285_medic2.png
            for j, k in avatar_mapping.items():
                # j: char_285_medic2
                # k: Lancet-2
                if i.startswith(j):
                    img = loadimg(os.path.join(avatar_path, i), True)
                    img = cv2.resize(img, None, None, 0.5, 0.5)
                    if k not in avatar:
                        avatar[k] = []
                    avatar[k].append(img)
                    break
        with lzma.open("./arknights_mower/models/avatar.pkl", "wb") as f:
            pickle.dump(avatar, f)

    def 获得干员基建描述(self):
        buff描述 = self.基建表["buffs"]
        buff_table = {}
        for buff名称, 相关buff in buff描述.items():
            buff_table[buff名称] = [
                相关buff["buffName"],
                相关buff["description"],
                相关buff["roomType"],
                相关buff["buffCategory"],
                相关buff["skillIcon"],
                相关buff["buffColor"],
                相关buff["textColor"],
            ]

        干员技能列表 = []

        name_key = 0
        for 角色id, 相关buff in self.基建表["chars"].items():
            干员技能字典 = {
                "key": 0,
                "name": "",
                "span": 0,
                "child_skill": [],
            }

            干员技能字典["name"] = self.干员表[角色id]["name"]

            skill_key = 0
            name_key += 1
            干员技能字典["key"] = name_key
            for item in 相关buff["buffChar"]:
                skill_level = 0

                if item["buffData"] != []:
                    for item2 in item["buffData"]:
                        干员技能详情 = {}

                        干员技能详情["skill_key"] = skill_key
                        干员技能详情["skill_level"] = skill_level
                        skill_level += 1
                        干员技能详情["phase_level"] = (
                            f"精{item2['cond']['phase']} {item2['cond']['level']}级"
                        )
                        干员技能详情["skillname"] = buff_table[item2["buffId"]][0]
                        text = buff_table[item2["buffId"]][1]
                        pattern = r"<\$(.*?)>"
                        matches = re.findall(pattern, text)
                        ex_string = []
                        干员技能详情["buffer"] = False
                        干员技能详情["buffer_des"] = []
                        if matches:
                            干员技能详情["buffer"] = True
                            ex_string = list(
                                set([match.replace(".", "_") for match in matches])
                            )
                            ex_string.sort()
                            干员技能详情["buffer_des"] = ex_string
                            self.所有buff.extend(ex_string)

                        干员技能详情["des"] = text
                        干员技能详情["roomType"] = roomType[
                            buff_table[item2["buffId"]][2]
                        ]
                        干员技能详情["buffCategory"] = buff_table[item2["buffId"]][3]
                        干员技能详情["skillIcon"] = buff_table[item2["buffId"]][4]
                        干员技能详情["buffColor"] = buff_table[item2["buffId"]][5]
                        干员技能详情["textColor"] = buff_table[item2["buffId"]][6]

                        干员技能字典["child_skill"].append(干员技能详情)

                        干员技能详情 = []
                    干员技能字典["span"] = len(干员技能字典["child_skill"])
                skill_key += 1
            干员技能列表.append(干员技能字典.copy())
        干员技能列表 = sorted(干员技能列表, key=lambda x: (-x["key"]))
        # print(干员技能列表)
        with open(
            "./ui/src/pages/basement_skill/skill.json", "w", encoding="utf-8"
        ) as f:
            json.dump(干员技能列表, f, ensure_ascii=False, indent=2)

    def buff转换(self):
        buff_table = {}
        pattern = r"<\$(.*?)>"

        for item in self.游戏变量["termDescriptionDict"]:
            matches = re.findall(
                pattern, self.游戏变量["termDescriptionDict"][item]["description"]
            )
            matches = [match.replace(".", "_") for match in matches]
            dict1 = self.游戏变量["termDescriptionDict"][item]
            dict1["buffer"] = []
            if item.startswith("cc") and matches:
                dict1["buffer"] = matches
            buff_table[item.replace(".", "_")] = dict1

        with open(
            "./ui/src/pages/basement_skill/buffer.json", "w", encoding="utf-8"
        ) as f:
            json.dump(buff_table, f, ensure_ascii=False, indent=2)

    def 添加基建技能图标(self):
        # 源目录和目标目录
        source_dir = "./ArknightsGameResource/building_skill"
        destination_dir = "./ui/public/building_skill"

        # 创建目标目录（如果不存在）
        os.makedirs(destination_dir, exist_ok=True)
        # 遍历源目录中的所有文件
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                if file.endswith(".png"):
                    src_file_path = os.path.join(root, file)
                    # 修改文件扩展名为 .webp
                    dest_file_name = os.path.splitext(file)[0] + ".webp"
                    dest_file_path = os.path.join(destination_dir, dest_file_name)
                    if not os.path.exists(dest_file_path):
                        with Image.open(src_file_path) as img:
                            img.save(dest_file_path, "webp")
                        print(f"转换: {src_file_path} 到 {dest_file_path}")
                    else:
                        print(f"跳过: {dest_file_path} 已存在")

    def 获取加工站配方类别(self):
        配方类别 = {}
        种类 = set([])

        # 从基建表获取所有配方
        配方数据 = self.基建表.get("workshopFormulas", {})

        # 遍历所有配方
        for 配方ID, 配方信息 in 配方数据.items():
            # 从物品表获取配方产出物品的名称
            物品ID = 配方信息.get("itemId")
            物品名称 = self.物品表["items"].get(物品ID, {}).get("name", 物品ID)
            子类材料 = [
                self.物品表["items"].get(i["id"], {}).get("name")
                for i in 配方信息.get("costs")
            ]
            # 获取配方类型
            配方类型 = 配方信息.get("formulaType")
            种类.add(配方类型)
            # 添加到结果字典中
            # 会有重复
            if 物品名称 == "家具零件":
                物品名称 += "_" + 子类材料[0]
            配方类别[物品名称] = {
                "tab": formulaType[配方类型],
                "apCost": 配方信息.get("apCost") / 360000,
                "goldCost": 配方信息.get("goldCost"),
                "items": 子类材料,
            }
        with open(
            "./arknights_mower/data/workshop_formula.json", "w", encoding="utf8"
        ) as json_file:
            json.dump(配方类别, json_file, ensure_ascii=False, indent=4)


roomType = {
    "POWER": "发电站",
    "DORMITORY": "宿舍",
    "MANUFACTURE": "制造站",
    "MEETING": "会客室",
    "WORKSHOP": "加工站",
    "TRADING": "贸易站",
    "HIRE": "人力办公室",
    "TRAINING": "训练室",
    "CONTROL": "中枢",
}
formulaType = {
    "F_SKILL": "技巧概要",
    "F_ASC": "芯片",
    "F_BUILDING": "基建材料",
    "F_EVOLVE": "精英材料",
}

# 提取干员名图片("./clst.png",1,2)

数据处理器 = Arknights数据处理器()

数据处理器.添加物品()  # 显示在仓库里的物品

数据处理器.添加干员()

数据处理器.读取卡池()

数据处理器.读取活动关卡()

# 和 数据处理器.添加物品() 有联动 ， 添加物品提供了分类的图片位置
数据处理器.批量训练并保存扫仓库模型()
print("批量训练并保存扫仓库模型,完成")

数据处理器.训练在房间内的干员名的模型()
print("训练在房间内的干员名的模型,完成")

数据处理器.训练选中的干员名的模型()
print("训练选中的干员名的模型,完成")

数据处理器.训练训练室干员名的模型()
print("训练训练室干员名的模型,完成")


数据处理器.auto_fight_avatar()

数据处理器.获得干员基建描述()

数据处理器.buff转换()  # 所有buff描述,包括其他buff

数据处理器.添加基建技能图标()

数据处理器.load_recruit_resource()

数据处理器.获取加工站配方类别()
