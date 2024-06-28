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
        self.游戏变量 = self.加载json(
            "./ArknightsGameResource/gamedata/excel/gamedata_const.json"
        )
        self.装仓库物品的字典 = {"NORMAL": [], "CONSUME": [], "MATERIAL": []}

        self.所有buff = []

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

        name_key = 0
        for 角色id, 相关buff in self.基建表["chars"].items():
            干员技能字典 = {
                "key": 0,
                "name": "",
                "span":0,
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
                            f"精{item2["cond"]["phase"]} {item2["cond"]["level"]}级"
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
                    干员技能字典["span"]=len(干员技能字典["child_skill"])
                skill_key += 1
            干员技能列表.append(干员技能字典.copy())
        干员技能列表 = sorted(
            干员技能列表, key=lambda x: (-x["key"])
        )
        # print(干员技能列表)
        with open(r".\ui\src\pages\skill.json", "w", encoding="utf-8") as f:
            json.dump(干员技能列表, f, ensure_ascii=False, indent=4)

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

        with open(r".\ui\src\pages\buffer.json", "w", encoding="utf-8") as f:
            json.dump(buff_table, f, ensure_ascii=False, indent=4)


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


数据处理器 = Arknights数据处理器()
数据处理器.获得干员名与基建描述()
数据处理器.buff转换()
