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
        buff_table = {}
        for 角色名, 相关buff in self.基建表["buffs"].items():
            buff_table[角色名] = 相关buff["description"]
        buff2_table = {}
        for 角色名 in self.基建表["chars"]:
            buff2_table[self.干员表[角色名]["name"]] = {}
            技能数 = 1
            for item in self.基建表["chars"][角色名]["buffChar"]:
                buff2_table[self.干员表[角色名]["name"]][技能数] = {}
                for thing in item["buffData"]:
                    buff2_table[self.干员表[角色名]["name"]][技能数][
                        str((thing["cond"]["phase"], thing["cond"]["level"]))
                    ] = buff_table[thing["buffId"]]
                技能数 += 1
        buff3_table = {}
        for 角色名, 技能序号字典 in buff2_table.items():
            buff3_table[角色名] = {}
            for 技能序号, 字典 in 技能序号字典.items():
                技能列表 = []
                for 角色等级, 技能描述 in 字典.items():
                    技能列表.append([角色等级, 技能序号, 技能描述])
                for [角色等级, 技能序号, 技能描述] in 技能列表:
                    buff3_table[角色名].setdefault(角色等级, {})[技能序号] = {}
                    buff3_table[角色名][角色等级][技能序号] = 技能描述
        buff4_table = {}
        for 角色名, 角色等级字典 in buff3_table.items():
            print(角色名, 角色等级字典)
            buff4_table[角色名] = {}
            角色等级列表 = []
            for 角色等级 in sorted(角色等级字典):
                buff4_table[角色名][角色等级] = {}
                角色等级列表.append(角色等级)
            merged_value = {}
            for item in 角色等级列表:
                merged_value = {**merged_value, **角色等级字典[item]}
                buff4_table[角色名][item] = merged_value
            print(merged_value)

        with open("./skill.json", "w", encoding="utf-8") as f:
            json.dump(buff4_table, f, ensure_ascii=False, indent=4)


数据处理器 = Arknights数据处理器()
数据处理器.获得干员名与基建描述()
