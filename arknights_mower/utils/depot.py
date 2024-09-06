import json
import os
from datetime import datetime

import pandas as pd

# from .log import logger
from arknights_mower.data import key_mapping

# from typing import Dict, List, Union
from arknights_mower.utils.path import get_path


def 读取仓库():
    path = get_path("@app/tmp/cultivate.json")
    if not os.path.exists(path):
        创建json()
    with open(path, "r", encoding="utf-8") as f:
        depotinfo = json.load(f)
    物品数量 = depotinfo["data"]["items"]
    新物品1 = {
        key_mapping[item["id"]][2]: int(item["count"])
        for item in 物品数量
        if int(item["count"]) != 0
    }

    csv_path = get_path("@app/tmp/depotresult.csv")
    if not os.path.exists(csv_path):
        创建csv()

    # 读取CSV文件
    depotinfo = pd.read_csv(csv_path)

    # 取出最后一行数据中的物品信息并进行合并
    最后一行物品 = json.loads(depotinfo.iloc[-1, 1])
    新物品 = {**最后一行物品, **新物品1}  # 合并字典
    新物品json = {}
    for item in 新物品:
        新物品json[key_mapping[item][0]] = 新物品[item]
    time = depotinfo.iloc[-1, 0]

    sort = {
        "A常用": [
            "至纯源石",
            "合成玉",
            "寻访凭证",
            "十连寻访凭证",
            "龙门币",
            "高级凭证",
            "资质凭证",
            "招聘许可",
        ],
        "B经验卡": ["基础作战记录", "初级作战记录", "中级作战记录", "高级作战记录"],
        "C稀有度5": ["烧结核凝晶", "晶体电子单元", "D32钢", "双极纳米片", "聚合剂"],
        "D稀有度4": [
            "提纯源岩",
            "改量装置",
            "聚酸酯块",
            "糖聚块",
            "异铁块",
            "酮阵列",
            "转质盐聚块",
            "切削原液",
            "精炼溶剂",
            "晶体电路",
            "炽合金块",
            "聚合凝胶",
            "白马醇",
            "三水锰矿",
            "五水研磨石",
            "RMA70-24",
            "环烃预制体",
            "固化纤维板",
        ],
        "E稀有度3": [
            "固源岩组",
            "全新装置",
            "聚酸酯组",
            "糖组",
            "异铁组",
            "酮凝集组",
            "转质盐组",
            "化合切削液",
            "半自然溶剂",
            "晶体元件",
            "炽合金",
            "凝胶",
            "扭转醇",
            "轻锰矿",
            "研磨石",
            "RMA70-12",
            "环烃聚质",
            "褐素纤维",
        ],
        "F稀有度2": ["固源岩", "装置", "聚酸酯", "糖", "异铁", "酮凝集"],
        "G稀有度1": ["源岩", "破损装置", "酯原料", "代糖", "异铁碎片", "双酮"],
        "H模组": ["模组数据块", "数据增补仪", "数据增补条"],
        "I技能书": ["技巧概要·卷3", "技巧概要·卷2", "技巧概要·卷1"],
        "J芯片相关": [
            "重装双芯片",
            "重装芯片组",
            "重装芯片",
            "狙击双芯片",
            "狙击芯片组",
            "狙击芯片",
            "医疗双芯片",
            "医疗芯片组",
            "医疗芯片",
            "术师双芯片",
            "术师芯片组",
            "术师芯片",
            "先锋双芯片",
            "先锋芯片组",
            "先锋芯片",
            "近卫双芯片",
            "近卫芯片组",
            "近卫芯片",
            "辅助双芯片",
            "辅助芯片组",
            "辅助芯片",
            "特种双芯片",
            "特种芯片组",
            "特种芯片",
            "采购凭证",
            "芯片助剂",
        ],
        "K未分类": [],
    }
    classified_data = {}
    classified_data["K未分类"] = {}
    for category, items in sort.items():
        classified_data[category] = {
            item: {"number": 0, "sort": key_mapping[item][4], "icon": item}
            for item in items
        }

    for key, value in 新物品.items():
        found_category = False
        for category, items in sort.items():
            if key in items:
                classified_data[category][key] = {
                    "number": value,
                    "sort": key_mapping[key][4],
                    "icon": key,
                }
                found_category = True
                break
        if not found_category:
            # 如果未找到匹配的分类，则放入 "K未分类" 中
            classified_data["K未分类"][key] = {
                "number": value,
                "sort": key_mapping[key][4],
                "icon": key,
            }

    classified_data["B经验卡"]["全部经验（计算）"] = {
        "number": (
            classified_data["B经验卡"]["基础作战记录"]["number"] * 200
            + classified_data["B经验卡"]["初级作战记录"]["number"] * 400
            + classified_data["B经验卡"]["中级作战记录"]["number"] * 1000
            + classified_data["B经验卡"]["高级作战记录"]["number"] * 2000
        ),
        "sort": 9999999,
        "icon": "EXP",
    }
    合成玉数量 = classified_data["A常用"].get("合成玉", {"number": 0})["number"]
    寻访凭证数量 = (
        classified_data["A常用"].get("寻访凭证", {"number": 0})["number"]
        + classified_data["A常用"].get("十连寻访凭证", {"number": 0})["number"] * 10
    )
    源石数量 = classified_data["A常用"].get("至纯源石", {"number": 0})["number"]
    源石碎片 = classified_data["K未分类"].get("源石碎片", {"number": 0})["number"]

    土 = classified_data["F稀有度2"].get("固源岩", {"number": 0})["number"]
    classified_data["A常用"]["玉+卷"] = {
        "number": round(合成玉数量 / 600 + 寻访凭证数量, 1),
        "sort": 9999999,
        "icon": "寻访凭证",
    }
    classified_data["A常用"]["玉+卷+石"] = {
        "number": round((合成玉数量 + 源石数量 * 180) / 600 + 寻访凭证数量, 1),
        "sort": 9999999,
        "icon": "寻访凭证",
    }
    classified_data["A常用"]["额外+碎片"] = {
        "number": round(
            (合成玉数量 + 源石数量 * 180 + int(源石碎片 / 2) * 20) / 600 + 寻访凭证数量,
            1,
        ),
        "sort": 9999999,
        "icon": "寻访凭证",
    }
    待定碎片 = int(土 / 2)
    classified_data["A常用"]["额外+碎片+土"] = {
        "number": round(
            (合成玉数量 + 源石数量 * 180 + int((源石碎片 + 待定碎片) / 2) * 20) / 600
            + 寻访凭证数量,
            1,
        ),
        "sort": 9999999,
        "icon": "寻访凭证",
    }
    return [
        classified_data,
        json.dumps(新物品json),
        str(datetime.fromtimestamp(int(time))),
    ]


def 创建csv():
    path = get_path("@app/tmp/depotresult.csv")
    now_time = int(datetime.now().timestamp()) - 24 * 3600
    result = [
        now_time,
        json.dumps({"还未开始过扫描": 0}, ensure_ascii=False),
        json.dumps({"空": ""}, ensure_ascii=False),
    ]
    depotinfo = pd.DataFrame([result], columns=["Timestamp", "Data", "json"])
    depotinfo.to_csv(path, mode="a", index=False, header=True, encoding="utf-8")


def 创建json():
    path = get_path("@app/tmp/cultivate.json")
    a = {
        "code": 0,
        "message": "OK",
        "timestamp": "1719065002",
        "data": {"items": [{"id": "31063", "count": "0"}]},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(a, f)
