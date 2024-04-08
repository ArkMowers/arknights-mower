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
        "A\u5e38\u7528": [
            "\u81f3\u7eaf\u6e90\u77f3",
            "\u5408\u6210\u7389",
            "\u5bfb\u8bbf\u51ed\u8bc1",
            "\u5341\u8fde\u5bfb\u8bbf\u51ed\u8bc1",
            "\u9f99\u95e8\u5e01",
            "\u9ad8\u7ea7\u51ed\u8bc1",
            "\u8d44\u8d28\u51ed\u8bc1",
            "\u62db\u8058\u8bb8\u53ef",
        ],
        "B\u7ecf\u9a8c\u5361": [
            "\u57fa\u7840\u4f5c\u6218\u8bb0\u5f55",
            "\u521d\u7ea7\u4f5c\u6218\u8bb0\u5f55",
            "\u4e2d\u7ea7\u4f5c\u6218\u8bb0\u5f55",
            "\u9ad8\u7ea7\u4f5c\u6218\u8bb0\u5f55",
        ],
        "C\u7a00\u6709\u5ea65": [
            "\u70e7\u7ed3\u6838\u51dd\u6676",
            "\u6676\u4f53\u7535\u5b50\u5355\u5143",
            "D32\u94a2",
            "\u53cc\u6781\u7eb3\u7c73\u7247",
            "\u805a\u5408\u5242",
        ],
        "D\u7a00\u6709\u5ea64": [
            "\u63d0\u7eaf\u6e90\u5ca9",
            "\u6539\u91cf\u88c5\u7f6e",
            "\u805a\u9178\u916f\u5757",
            "\u7cd6\u805a\u5757",
            "\u5f02\u94c1\u5757",
            "\u916e\u9635\u5217",
            "\u8f6c\u8d28\u76d0\u805a\u5757",
            "\u5207\u524a\u539f\u6db2",
            "\u7cbe\u70bc\u6eb6\u5242",
            "\u6676\u4f53\u7535\u8def",
            "\u70bd\u5408\u91d1\u5757",
            "\u805a\u5408\u51dd\u80f6",
            "\u767d\u9a6c\u9187",
            "\u4e09\u6c34\u9530\u77ff",
            "\u4e94\u6c34\u7814\u78e8\u77f3",
            "RMA70-24",
            "\u73af\u70c3\u9884\u5236\u4f53",
            "\u56fa\u5316\u7ea4\u7ef4\u677f",
        ],
        "E\u7a00\u6709\u5ea63": [
            "\u56fa\u6e90\u5ca9\u7ec4",
            "\u5168\u65b0\u88c5\u7f6e",
            "\u805a\u9178\u916f\u7ec4",
            "\u7cd6\u7ec4",
            "\u5f02\u94c1\u7ec4",
            "\u916e\u51dd\u96c6\u7ec4",
            "\u8f6c\u8d28\u76d0\u7ec4",
            "\u5316\u5408\u5207\u524a\u6db2",
            "\u534a\u81ea\u7136\u6eb6\u5242",
            "\u6676\u4f53\u5143\u4ef6",
            "\u70bd\u5408\u91d1",
            "\u51dd\u80f6",
            "\u626d\u8f6c\u9187",
            "\u8f7b\u9530\u77ff",
            "\u7814\u78e8\u77f3",
            "RMA70-12",
            "\u73af\u70c3\u805a\u8d28",
            "\u8910\u7d20\u7ea4\u7ef4",
        ],
        "F\u7a00\u6709\u5ea62": [
            "\u56fa\u6e90\u5ca9",
            "\u88c5\u7f6e",
            "\u805a\u9178\u916f",
            "\u7cd6",
            "\u5f02\u94c1",
            "\u916e\u51dd\u96c6",
        ],
        "G\u7a00\u6709\u5ea61": [
            "\u6e90\u5ca9",
            "\u7834\u635f\u88c5\u7f6e",
            "\u916f\u539f\u6599",
            "\u4ee3\u7cd6",
            "\u5f02\u94c1\u788e\u7247",
            "\u53cc\u916e",
        ],
        "H\u6a21\u7ec4": [
            "\u6a21\u7ec4\u6570\u636e\u5757",
            "\u6570\u636e\u589e\u8865\u4eea",
            "\u6570\u636e\u589e\u8865\u6761",
        ],
        "I\u6280\u80fd\u4e66": [
            "\u6280\u5de7\u6982\u8981\u00b7\u53773",
            "\u6280\u5de7\u6982\u8981\u00b7\u53772",
            "\u6280\u5de7\u6982\u8981\u00b7\u53771",
        ],
        "J\u82af\u7247\u76f8\u5173": [
            "\u91cd\u88c5\u53cc\u82af\u7247",
            "\u91cd\u88c5\u82af\u7247\u7ec4",
            "\u91cd\u88c5\u82af\u7247",
            "\u72d9\u51fb\u53cc\u82af\u7247",
            "\u72d9\u51fb\u82af\u7247\u7ec4",
            "\u72d9\u51fb\u82af\u7247",
            "\u533b\u7597\u53cc\u82af\u7247",
            "\u533b\u7597\u82af\u7247\u7ec4",
            "\u533b\u7597\u82af\u7247",
            "\u672f\u5e08\u53cc\u82af\u7247",
            "\u672f\u5e08\u82af\u7247\u7ec4",
            "\u672f\u5e08\u82af\u7247",
            "\u5148\u950b\u53cc\u82af\u7247",
            "\u5148\u950b\u82af\u7247\u7ec4",
            "\u5148\u950b\u82af\u7247",
            "\u8fd1\u536b\u53cc\u82af\u7247",
            "\u8fd1\u536b\u82af\u7247\u7ec4",
            "\u8fd1\u536b\u82af\u7247",
            "\u8f85\u52a9\u53cc\u82af\u7247",
            "\u8f85\u52a9\u82af\u7247\u7ec4",
            "\u8f85\u52a9\u82af\u7247",
            "\u7279\u79cd\u53cc\u82af\u7247",
            "\u7279\u79cd\u82af\u7247\u7ec4",
            "\u7279\u79cd\u82af\u7247",
            "\u91c7\u8d2d\u51ed\u8bc1",
            "\u82af\u7247\u52a9\u5242",
        ],
        "K\u672a\u5206\u7c7b": [],
    }
    classified_data = {}
    classified_data["K未分类"] = {}
    for category, items in sort.items():
        classified_data[category] = {
            item: {"number": 0, "sort": key_mapping[item][4], "icon": item} for item in items
        }

    for key, value in 新物品.items():
        found_category = False
        for category, items in sort.items():
            if key in items:
                classified_data[category][key] = {
                    "number": value,
                    "sort": key_mapping[key][4],
                    "icon": key
                }
                found_category = True
                break
        if not found_category:
            # 如果未找到匹配的分类，则放入 "K未分类" 中
            classified_data["K未分类"][key] = {
                "number": value,
                "sort": key_mapping[key][4],
                "icon": key
            }

    classified_data["B经验卡"]["全部经验（计算）"] = {
        "number": (
            classified_data["B经验卡"]["基础作战记录"]["number"] * 200
            + classified_data["B经验卡"]["初级作战记录"]["number"] * 400
            + classified_data["B经验卡"]["中级作战记录"]["number"] * 1000
            + classified_data["B经验卡"]["高级作战记录"]["number"] * 2000
        ),
        "sort": 9999999,
        "icon": "全部经验（计算）"
    }

    classified_data["A常用"]["玉+卷"] = {
        "number": (
            classified_data["A常用"]["合成玉"]["number"]/600 +
            classified_data["A常用"]["寻访凭证"]["number"] +
            classified_data["A常用"]["十连寻访凭证"]["number"]
        ),
        "sort": 9999999,
        "icon": "寻访凭证"
    }
    classified_data["A常用"]["玉+卷+石"] = {
        "number": (
            classified_data["A常用"]["玉+卷"]["number"] +
            classified_data["A常用"]["至纯源石"]["number"]*180/600
        ),
        "sort": 9999999,
        "icon": "寻访凭证"
    }
    return [classified_data, 新物品json, str(datetime.fromtimestamp(time))]


def 创建csv(path=get_path("@app/tmp/depotresult.csv")):
    now_time = int(datetime.now().timestamp()) - 24 * 3600
    result = [
        now_time,
        json.dumps({"还未开始过扫描": 0}, ensure_ascii=False),
        json.dumps({"空": ""}, ensure_ascii=False),
    ]
    depotinfo = pd.DataFrame([result], columns=["Timestamp", "Data", "json"])
    depotinfo.to_csv(path, mode="a", index=False,
                     header=True, encoding="utf-8")
