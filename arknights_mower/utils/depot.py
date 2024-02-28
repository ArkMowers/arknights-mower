import json
from .log import logger
import os
from arknights_mower.data import key_mapping
from .path import get_path
import pandas as pd


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
    融合 = {}
    # 读取 CSV 文件
    if os.path.exists(path):
        df = pd.read_csv(path)
        新物品 = json.loads(df.iloc[-1, 1])  # 最后一行的第一个值
        if len(df) > 2:
            旧物品 = json.loads(df.iloc[-3, 1])
        else:
            旧物品 = {"空": 0}

        拥有过的物品 = set(新物品.keys()) | set(旧物品.keys())

        for key in 拥有过的物品:
            new = 新物品.get(key, 0)
            old = 旧物品.get(key, 0)
            融合[key] = [new, old]

    else:
        融合 = {"空": [0, 0]}
    return 融合
