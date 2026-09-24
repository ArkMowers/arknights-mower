import csv
import json
import os
from datetime import datetime

from arknights_mower.data import key_mapping, workshop_formula
from arknights_mower.solvers.record import save_inventory_counts
from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


def cloud_inventory_snapshot(payload):
    """Only a successful sync made by this version can replace local crafting counts."""
    observed_at = payload.get("_mower_inventory_observed_at", 0)
    items = payload.get("data", {}).get("items")
    if (
        not isinstance(observed_at, (int, float))
        or observed_at <= 0
        or not isinstance(items, list)
    ):
        return {}, 0
    # Skland supplies material inventory; basic/consumable categories are scanned
    # in-game. Never synthesize zero counts for those unreported categories.
    counts = {
        name: 0
        for name, entry in key_mapping.items()
        if name == entry[2] and entry[3] == "MATERIAL" and "信物" not in name
    }
    for item in items:
        entry = key_mapping.get(item["id"])
        if entry is not None and "信物" not in entry[2]:
            counts[entry[2]] = int(item["count"])
    return counts, observed_at


def 折算抽数(合成玉数量, 寻访凭证数量, 源石数量, 源石碎片, 土数量):
    """把仓库物料折算成四档寻访抽数，返回 {档位: 抽数}。

    口径：600 合成玉一抽；1 至纯源石 = 180 合成玉（0.3 抽）；源石碎片 2 片算一抽
    （20 合成玉）；固源岩 2 块搓 1 碎片，再按碎片折算。寻访凭证按十连 ×10 并入。

    这是全项目唯一的抽数换算实现：读取仓库写派生条目、读取仓库历史回填历史快照都调
    这里，前端不再重算。两处各写一份迟早会在舍入边界上对不上——Python 的 round() 是
    银行家舍入，JS 的 Math.round() 遇 .5 一律进位，同一份仓库能差出 0.1 抽。
    """
    基础 = 合成玉数量 / 600 + 寻访凭证数量
    含源石 = (合成玉数量 + 源石数量 * 180) / 600 + 寻访凭证数量
    含碎片 = (合成玉数量 + 源石数量 * 180 + int(源石碎片 / 2) * 20) / 600 + 寻访凭证数量
    待定碎片 = int(土数量 / 2)
    含固源岩 = (
        合成玉数量 + 源石数量 * 180 + int((源石碎片 + 待定碎片) / 2) * 20
    ) / 600 + 寻访凭证数量
    return {
        "玉+卷": round(基础, 1),
        "玉+卷+石": round(含源石, 1),
        "额外+碎片": round(含碎片, 1),
        "额外+碎片+土": round(含固源岩, 1),
    }


# 派生档位的键名，供剔除旧值时引用；顺序与 折算抽数 的插入顺序一致（Python 3.7+
# 的 dict 保序，前端据此渲染档位按钮）。
抽数档位 = ("玉+卷", "玉+卷+石", "额外+碎片", "额外+碎片+土")


def 读取仓库():
    path = get_path("@app/tmp/cultivate.json")
    if not os.path.exists(path):
        创建json()
    with open(path, "r", encoding="utf-8") as f:
        depotinfo = json.load(f)
    cloud_counts, cloud_at = cloud_inventory_snapshot(depotinfo)
    物品数量 = depotinfo["data"]["items"]
    新物品1 = {}
    for item in 物品数量:
        if int(item["count"]) == 0:
            continue
        entry = key_mapping.get(item["id"])
        if entry is None:
            # 活动/新素材 id 不在本地 key_mapping（资源包 vs 内置数据可能不同步），
            # 跳过而不是让整个扫描 KeyError。
            logger.warning(f"仓库扫描: 忽略未知物品 id {item['id']}")
            continue
        新物品1[entry[2]] = int(item["count"])

    csv_path = get_path("@app/tmp/depotresult.csv")
    if not os.path.exists(csv_path):
        创建csv()

    # 读取CSV文件
    _, depotinfo = read_csv_rows(csv_path)

    # 取出最后一行数据中的物品信息并进行合并
    最后一行物品 = json.loads(depotinfo[-1][1])
    新物品 = {**最后一行物品, **新物品1}  # 合并字典
    新物品json = {}
    db_dict = {}
    for k in workshop_formula.keys():
        db_dict[k] = 0
    for item, count in 新物品.items():
        entry = key_mapping.get(item)
        if entry is None:
            # 上一轮 CSV 里残留的旧物品名（key_mapping 更新后可能失效）也跳过，
            # 避免合并历史数据时再次 KeyError。
            logger.warning(f"仓库扫描: 忽略未知物品名 {item}")
            continue
        新物品json[entry[0]] = count
        db_dict[entry[2]] = count
    time = depotinfo[-1][0]
    scanned_counts = {
        key_mapping[name][2]: count
        for name, count in 最后一行物品.items()
        if name in key_mapping
    }
    db_dict = save_inventory_counts(
        db_dict,
        scanned_counts=scanned_counts,
        scanned_at=float(depotinfo[-1][0]),
        cloud_counts=cloud_counts,
        cloud_at=cloud_at,
    )
    新物品 = {
        name: count
        for name, count in db_dict.items()
        if name in key_mapping and "信物" not in name
    }
    新物品json = {key_mapping[name][0]: count for name, count in 新物品.items()}
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
        "C稀有度5": [
            "烧结核凝晶",
            "晶体电子单元",
            "D32钢",
            "双极纳米片",
            "聚合剂",
            "重相位对映体",
        ],
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
            "手性屈光体",
            "聚能动力单元",
            "液化醚吸聚体",
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
            "类凝结核",
            "电极单元",
            "液化高能气体",
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

    # 派生条目的 icon 用资源包里真实存在的图：经验卡合计用 EXP.webp，
    # 而不是「高级作战记录」（那是 B经验卡 分类下真实物料的图）。
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

    抽数 = 折算抽数(合成玉数量, 寻访凭证数量, 源石数量, 源石碎片, 土)
    for 档位, 数值 in 抽数.items():
        classified_data["A常用"][档位] = {
            "number": 数值,
            "sort": 9999999,
            "icon": "寻访凭证",
        }
    return [
        classified_data,
        json.dumps(新物品json),
        str(datetime.fromtimestamp(int(time))),
    ]


def 读取仓库历史(limit=60):
    """读取 depotresult.csv 的扫描快照序列，供仓库页趋势使用。

    返回 [{at: 秒级时间戳, items: {物品名: 数量}}]，按时间升序，只保留最近 limit 条。
    文件不存在、只有占位行或全部损坏时返回 []，调用方不必判空。

    CSV 的 Data 列是每次扫描的**全量**快照（不是增量），所以相邻两条的差值就是
    这段时间的净变化；创建文件时写入的占位行 "还未开始过扫描" 必须排除，
    否则第一次真实扫描会相对它产生一整份假增量。

    每条快照的 items 会回填四个派生档位（玉+卷 … 额外+碎片+土）。CSV 里只存了原始
    物料，抽数得现算；在这里补上，前端就能直接读，不必自己再折算一遍，页面上的
    "折合寻访抽数" 卡片与趋势线也就不会因为舍入口径不同而对不上。
    """
    path = get_path("@app/tmp/depotresult.csv")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []

    try:
        _, rows = read_csv_rows(path)
    except (EmptyDataError, OSError, UnicodeDecodeError, csv.Error) as error:
        # UnicodeDecodeError 也要收：文件可能被别的编辑器存成 GBK，或写入中途被截断，
        # 让这点瑕疵把整个 /depot/history 变成 500 不值得。
        logger.warning(f"仓库历史: 读取 {path} 失败，按无历史处理：{error}")
        return []

    snapshots = []
    for row in rows:
        # 列顺序固定为 Timestamp,Data,json；列数异常的残行直接跳过。
        if len(row) < 2:
            continue
        try:
            at = int(float(row[0]))
        except (TypeError, ValueError):
            continue
        try:
            payload = json.loads(row[1])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        # 占位行/空快照没有可比较的物料，参与环比只会制造假变化。
        if "还未开始过扫描" in payload:
            continue
        items = {}
        for name, count in payload.items():
            if not isinstance(name, str) or "信物" in name:
                continue
            try:
                # 与 读取仓库 一致：取整，反向解析出的浮点值（"1.2万"）向下取整。
                items[name] = int(count)
            except (TypeError, ValueError):
                continue
        if not items:
            continue
        # 派生档位以当前换算为准：旧快照里可能残留上一版公式写下的同名键，
        # 直接更新会留下旧值，所以先剔掉再统一补算。
        for 档位 in 抽数档位:
            items.pop(档位, None)
        items.update(
            折算抽数(
                items.get("合成玉", 0),
                items.get("寻访凭证", 0) + items.get("十连寻访凭证", 0) * 10,
                items.get("至纯源石", 0),
                items.get("源石碎片", 0),
                items.get("固源岩", 0),
            )
        )
        snapshots.append({"at": at, "items": items})

    # 排序必须先于截断：CSV 正常是追加写的，但换机/合并/时钟回拨都可能留下乱序行，
    # 若先截断就会取到"文件里最后 limit 行"而不是"最近 limit 次扫描"。
    snapshots.sort(key=lambda entry: entry["at"])

    if limit is None or limit <= 0:
        return snapshots
    return snapshots[-limit:]


def 创建csv():
    path = get_path("@app/tmp/depotresult.csv")
    now_time = int(datetime.now().timestamp()) - 24 * 3600
    result = [
        now_time,
        json.dumps({"还未开始过扫描": 0}, ensure_ascii=False),
        json.dumps({"空": ""}, ensure_ascii=False),
    ]
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["Timestamp", "Data", "json"])
        writer.writerow(result)


def 创建json():
    path = get_path("@app/tmp/cultivate.json")
    a = {
        "code": 0,
        "message": "OK",
        "timestamp": "1719065002",
        "data": {"items": [{"id": "31063", "count": "0"}]},
    }

    def dump(f):
        json.dump(a, f)

    # 与 cultivate_depot.py 共用写点，原子写防撕裂（web 刷新线程并发）
    atomic_write(path, dump)
