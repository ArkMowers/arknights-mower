import json
import os
import pandas as pd
from typing import Dict, List, Union
from .path import get_path
from .log import logger
from arknights_mower.data import key_mapping
from datetime import datetime

# depot_file = get_path('@app/tmp/itemlist.csv')

# def process_itemlist(d):
#     itemlist = {"时间": datetime.datetime.now(), "data": {key: 0 for key in key_mapping.keys()}}

#     itemlist["data"] = json.loads(d["details"]["lolicon"]["data"])

#     # Check if file exists, if not, create the file
#     if not os.path.exists(depot_file):
#         with open(depot_file, "w", newline="", encoding="utf-8") as csvfile:
#             fieldnames = ["时间", "data"]
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#             writer.writeheader()
#             writer.writerow({"时间": datetime.datetime.now(), "data": '{"空":0}'})

#         # Append data to the CSV file
#     with open(depot_file, "a", newline="", encoding="utf-8") as csvfile:
#         fieldnames = itemlist.keys()
#         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#         writer.writerow(itemlist)


def 读取仓库():
    path = get_path("@app/tmp/depotresult.csv")
    if not os.path.exists(path):
        创建csv()
    depotinfo = pd.read_csv(path)
    新物品 = json.loads(depotinfo.iloc[-1, 1])
    time = depotinfo.iloc[-1, 0]
    新物品json = depotinfo.iloc[-1, 2]
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
    return [classified_data, 新物品json, str(datetime.fromtimestamp(int(time)))]


def 创建csv():
    path = get_path("@app/tmp/depotresult.csv")
    now_time = int(datetime.now().timestamp()) - 24 * 3600
    result = [
        now_time,
        json.dumps({"还未开始过扫描": 0}, ensure_ascii=False),
        json.dumps({"空": ""}, ensure_ascii=False),
    ]
    depotinfo = pd.DataFrame([result], columns=["Timestamp", "Data", "json"])
    depotinfo.to_csv(path, mode="a", index=False,
                     header=True, encoding="utf-8")
