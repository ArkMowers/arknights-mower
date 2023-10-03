import json
import csv
import datetime
import ast
from .log import logger
import os
from arknights_mower.data import key_mapping

depot_file = os.path.join("tmp", "itemlist.csv")
current_datetime = datetime.datetime.now()


def process_itemlist(d):
    itemlist = {"时间": current_datetime, "data": {key: 0 for key in key_mapping.keys()}}

    if d.get("what") == "DepotInfo" and d["details"].get("done") is True:
        itemlist["data"] = json.loads(d["details"]["lolicon"]["data"])

        # Check if file exists, if not, create the file
        if not os.path.exists(depot_file):
            with open(depot_file, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = ["时间", "data"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({"时间": current_datetime, "data": '{"空":0}'})

        # Append data to the CSV file
        with open(depot_file, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = itemlist.keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(itemlist)


def read_and_compare_depots():
    def format_data(depot_data):
        deopt_time = depot_data[0]
        depot_dict = ast.literal_eval(depot_data[1])
        return deopt_time, depot_dict

    def rename_depot(original_dict):
        """
        重命名字典中的键名，根据给定的映射关系。

        参数:
        original_dict (dict): 需要重命名键名的原始字典。

        返回:
        dict: 重命名后的字典。
        """
        renamed_dict = {
            key_mapping.get(key, key): value for key, value in original_dict.items()
        }
        return renamed_dict

    def find_difference(dict1, dict2):
        """
        寻找两个字典之间的差异，返回差异的键和值。

        参数:
        dict1 (dict): 第一个字典。
        dict2 (dict): 第二个字典。

        返回:
        dict: 包含差异的字典，格式为 {键: (dict1中的值, dict2中的值)}。
        """
        difference = {}

        # 处理dict1中的项
        for key, value in dict1.items():
            if key in dict2:
                if dict2[key] != value:
                    difference[key] = [value, dict2[key]]
            else:
                difference[key] = [value, 0]  # 缺失项的值设置为0

        # 处理dict2中的项，避免遗漏在dict2中有而dict1中没有的项
        for key, value in dict2.items():
            if key not in dict1:
                difference[key] = [0, value]  # 缺失项的值设置为0
        return difference

    if not os.path.exists(depot_file):
        with open(depot_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["时间", "data"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({"时间": current_datetime, "data": '{"空":0}'})
    with open(depot_file, "r", encoding="utf-8") as csvfile:
        csvreader = csv.reader(csvfile)
        all_rows = list(csvreader)
        if len(all_rows) < 3:
            depot_old_time, depot_old = format_data(all_rows[1])
            depot_new_time, depot_new = format_data(all_rows[1])
        else:
            depot_old_time, depot_old = format_data(all_rows[-2])
            depot_new_time, depot_new = format_data(all_rows[-1])

    renamed_depot_old = rename_depot(depot_old)
    renamed_depot_new = rename_depot(depot_new)
    logger.debug(f"上次读取时间为：{depot_old_time}，有{renamed_depot_old}")
    logger.info(f"这次读取时间为：{depot_new_time}，有{renamed_depot_new}")

    difference = find_difference(renamed_depot_old, renamed_depot_new)
    logger.info(f"差异为：{difference}")
    result = [f'"{key}": {value}' for key, value in depot_new.items()]
    result_str = ", ".join(result)
    result_str = "{" + result_str + "}"
    logger.info(f"明日方舟工具箱代码：{result_str}")
    return [
        renamed_depot_old,
        renamed_depot_new,
        difference,
        result_str,
        depot_new_time,
    ]
