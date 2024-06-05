import json
import shutil
import os

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
            buff_table[buff名称] = {相关buff["buffName"]: [相关buff["description"],相关buff["roomType"],相关buff["buffCategory"],相关buff["skillIcon"]]}
        干员技能列表 = {}
        for 角色名, 相关buff in self.基建表["chars"].items():
            buffId = {}
            for item in 相关buff["buffChar"]:
                if item["buffData"] != []:
                    buffId[
                        精英化翻译(
                            item["buffData"][0]["cond"]["phase"],
                            item["buffData"][0]["cond"]["level"],
                        )
                    ] = [item["buffData"][0]["buffId"]]
            a=merge_values(buffId,buff_table)

                    
            # new_dict = {}
            # prev_value = None
            # for key, value in buffId.items():
            #     if prev_value is not None:
            #         value.update(prev_value)
            #     new_dict[key] = value
            #     prev_value = value
            # prev_value = None
            # print(new_dict)
            干员技能列表[self.干员表[角色名]["name"]] = a
        
        with open(r".\ui\src\pages\skill.json", "w", encoding="utf-8") as f:
            json.dump(dict(reversed(干员技能列表.items())), f, ensure_ascii=False, indent=4)


def 精英化翻译(精英化, 等级):
    return f"精{精英化} {等级}级"

def merge_values(dictionary,translations):
    for key in dictionary:
        # 检查是否存在前一个键
        if key != list(dictionary.keys())[0]:
            previous_key = list(dictionary.keys())[list(dictionary.keys()).index(key) - 1]
            previous_value = dictionary[previous_key]
            current_value = dictionary[key]
            # 将当前键的值与前一个键的值相加
            dictionary[key] = previous_value + current_value
    for key, value in dictionary.items():
        if isinstance(value, list):
            for i in range(len(value)):
                if value[i] in translations:
                    dictionary[key][i] = translations[value[i]]
        elif isinstance(value, dict):
            translate_values(value, translations)
    return dictionary

def translate_values(dictionary, translations):
    for key, value in dictionary.items():
        if isinstance(value, list):
            for i in range(len(value)):
                if value[i] in translations:
                    dictionary[key][i] = translations[value[i]]
        elif isinstance(value, dict):
            translate_values(value, translations)
    return dictionary
数据处理器 = Arknights数据处理器()
数据处理器.获得干员名与基建描述()
