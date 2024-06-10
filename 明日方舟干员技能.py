import json
import shutil
import os
import re
import cv2
import numpy as np
import pickle
import lzma

from datetime import datetime

from sklearn.neighbors import KNeighborsClassifier
from skimage.feature import hog

from PIL import Image, ImageDraw, ImageFont
from arknights_mower.data import agent_list
from arknights_mower.utils.image import thres2


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
        self.装仓库物品的字典 = {"NORMAL": [], "CONSUME": [], "MATERIAL": []}

    def 加载json(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def 获得干员名与基建描述(self):
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

        key = 0
        for 角色id, 相关buff in self.基建表["chars"].items():
            干员技能字典 = {
                "key": 0,
                "name": "",
                "phase_level": "",
                "skillname": "",
                "des": "",
                "roomType": "",
                "buffCategory": "",
                "skillIcon": "",
                "buffColor": "",
                "textColor": "",
            }

            干员技能字典["name"] = self.干员表[角色id]["name"]
            for item in 相关buff["buffChar"]:
                if item["buffData"] != []:
                    for item2 in item["buffData"]:
                        干员技能字典["key"] = key
                        key += 1
                        干员技能字典["phase_level"] = (
                            f"精{item2["cond"]["phase"]} {item2["cond"]["level"]}级"
                        )
                        干员技能字典["skillname"] = buff_table[item2["buffId"]][0]
                        text=buff_table[item2["buffId"]][1]
                        for pattern, replacement in replacement_dict.items():
                            text = re.sub(pattern, replacement, text)
                        干员技能字典["des"] = text
                        干员技能字典["roomType"] = roomType[
                            buff_table[item2["buffId"]][2]
                        ]
                        干员技能字典["buffCategory"] = buff_table[item2["buffId"]][3]
                        干员技能字典["skillIcon"] = buff_table[item2["buffId"]][4]
                        干员技能字典["buffColor"] = buff_table[item2["buffId"]][5]
                        干员技能字典["textColor"] = buff_table[item2["buffId"]][6]
                        干员技能列表.append(干员技能字典.copy())

        # print(干员技能列表)
        with open(r".\ui\src\pages\skill.json", "w", encoding="utf-8") as f:
            json.dump(干员技能列表, f, ensure_ascii=False, indent=4)


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

replacement_dict = {
    r"<@cc.vup>(.*?)<\/>": r"<span style='color:#0098DC'>\1</span>",
    r"<@cc.vdown>(.*?)<\/>": r"<span style='color:#FF6237'>\1</span>",
    r"<@cc.rem>(.*?)<\/>": r"<span style='color:#F49800'>\1</span>",
    r"<@cc.kw>(.*?)<\/>": r"<span style='color:#00B0FF'>\1</span>"
}
数据处理器 = Arknights数据处理器()
数据处理器.获得干员名与基建描述()




# 定义要匹配的字符串
text = "这是一个示例字符串 <@cc.vup>{0}</>，<@cc.vdown>{1}</>，<@cc.rem>{2}</>，<@cc.kw>{3}</>，其中包含了一些其他的文本"

# 定义替换规则字典


# 遍历替换规则字典，逐个替换字符串
for pattern, replacement in replacement_dict.items():
    text = re.sub(pattern, replacement, text)

# 输出替换后的字符串
print(text)


