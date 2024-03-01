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


def 读取仓库() -> List[Union[Dict[str, List[int]], str]]:
    path = get_path("@app/tmp/depotresult.csv")
    融合: Dict[str, List[int]] = {}

    if not os.path.exists(path):
        创建csv()
    depotinfo = pd.read_csv(path)
    新物品 = json.loads(depotinfo.iloc[-1, 1])
    新物品json = depotinfo.iloc[-1, 2]
    sort = {
        "A常用": [
            "DIAMOND",
            "DIAMOND_SHD",
            "TKT_GACHA",
            "TKT_GACHA_10",
            "GOLD",
            "HGG_SHD",
            "LGG_SHD",
            "TKT_RECRUIT",
        ],
        "B经验卡": [
            "sprite_exp_card_t1",
            "sprite_exp_card_t2",
            "sprite_exp_card_t3",
            "sprite_exp_card_t4",
        ],
        "C稀有度5": ["MTL_SL_SHJ", "MTL_SL_OEU", "MTL_SL_DS", "MTL_SL_BN", "MTL_SL_PP"],
        "D稀有度4": [
            "MTL_SL_G4",
            "MTL_SL_BOSS4",
            "MTL_SL_RUSH4",
            "MTL_SL_STRG4",
            "MTL_SL_IRON4",
            "MTL_SL_KETONE4",
            "MTL_SL_ZYK",
            "MTL_SL_PLCF",
            "MTL_SL_RS",
            "MTL_SL_OC4",
            "MTL_SL_IAM4",
            "MTL_SL_PGEL4",
            "MTL_SL_ALCOHOL2",
            "MTL_SL_MANGANESE2",
            "MTL_SL_PG2",
            "MTL_SL_RMA7024",
            "MTL_SL_HTT",
            "MTL_SL_XWB",
        ],
        "E稀有度3": [
            "MTL_SL_G3",
            "MTL_SL_BOSS3",
            "MTL_SL_RUSH3",
            "MTL_SL_STRG3",
            "MTL_SL_IRON3",
            "MTL_SL_KETONE3",
            "MTL_SL_ZY",
            "MTL_SL_CCF",
            "MTL_SL_SS",
            "MTL_SL_OC3",
            "MTL_SL_IAM3",
            "MTL_SL_PGEL3",
            "MTL_SL_ALCOHOL1",
            "MTL_SL_MANGANESE1",
            "MTL_SL_PG1",
            "MTL_SL_RMA7012",
            "MTL_SL_HT",
            "MTL_SL_XW",
        ],
        "F稀有度2": [
            "MTL_SL_G2",
            "MTL_SL_BOSS2",
            "MTL_SL_RUSH2",
            "MTL_SL_STRG2",
            "MTL_SL_IRON2",
            "MTL_SL_KETONE2",
        ],
        "G稀有度1": [
            "MTL_SL_G1",
            "MTL_SL_BOSS1",
            "MTL_SL_RUSH1",
            "MTL_SL_STRG1",
            "MTL_SL_IRON1",
            "MTL_SL_KETONE1",
        ],
        "H模组": ["mod_unlock_token", "mod_update_token_2", "mod_update_token_1"],
        "I技能书": ["MTL_SKILL3", "MTL_SKILL2", "MTL_SKILL1"],
        "J芯片相关": [
            "MTL_ASC_TNK3",
            "MTL_ASC_TNK2",
            "MTL_ASC_TNK1",
            "MTL_ASC_SNP3",
            "MTL_ASC_SNP2",
            "MTL_ASC_SNP1",
            "MTL_ASC_MED3",
            "MTL_ASC_MED2",
            "MTL_ASC_MED1",
            "MTL_ASC_CST3",
            "MTL_ASC_CST2",
            "MTL_ASC_CST1",
            "MTL_ASC_PIO3",
            "MTL_ASC_PIO2",
            "MTL_ASC_PIO1",
            "MTL_ASC_GRD3",
            "MTL_ASC_GRD2",
            "MTL_ASC_GRD1",
            "MTL_ASC_SUP3",
            "MTL_ASC_SUP2",
            "MTL_ASC_SUP1",
            "MTL_ASC_SPC3",
            "MTL_ASC_SPC2",
            "MTL_ASC_SPC1",
            "EXGG_SHD",
            "MTL_ASC_DI",
        ],
        "K未知": [],
    }

    classified_data = {}
    classified_data["K未知"] = {}
    for category, items in sort.items():
        classified_data[category] = {
            item: {"number": 0, "sort": key_mapping[item][3]} for item in items
        }

    for key, value in 新物品.items():
        found_category = False
        for category, items in sort.items():
            if key in items:
                classified_data[category][key] = {
                    "number": value,
                    "sort": key_mapping[key][3],
                }
                found_category = True
                break
        if not found_category:
            # 如果未找到匹配的分类，则放入 "K未知" 中
            classified_data["K未知"][key] = {"number": value, "sort": key_mapping[key][3]}

    logger.info(classified_data)
    return [classified_data, 新物品json]


def 创建csv(path=get_path("@app/tmp/depotresult.csv")):
    now_time = int(datetime.now().timestamp())
    result = [
        now_time,
        json.dumps({"还未开始过扫描": 0}, ensure_ascii=False),
        json.dumps({"空": ""}, ensure_ascii=False),
    ]
    depotinfo = pd.DataFrame([result], columns=["Timestamp", "Data", "json"])
    depotinfo.to_csv(path, mode="a", index=False, header=True)
