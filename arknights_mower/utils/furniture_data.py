"""家具资源投影与整套保留数量；生成期不依赖游戏或资源加载器。"""

import json
from collections import Counter


def normalize_name(name):
    return "".join(name.split())


def build_furniture_data(building_data):
    custom = building_data["customData"]
    result = {
        "furnitures": {
            key: {
                field: value[field]
                for field in ("name", "themeId", "quantity", "canBeDestroy")
            }
            for key, value in custom["furnitures"].items()
        },
        "themes": {
            key: {
                "name": value["name"],
                "counts": dict(
                    Counter(item["furnitureId"] for item in value["quickSetup"])
                ),
            }
            for key, value in custom["themes"].items()
        },
    }
    furniture_keep_counts(result)  # 生成时校验，不能发布缺失数量的资源。
    return result


def furniture_keep_counts(data):
    """精确名称匹配；同名家具、不可分解或未知数量不参与自动分解。"""
    furnitures, themes = data["furnitures"], data["themes"]
    if not furnitures or not isinstance(themes, dict):
        raise ValueError("家具资源为空或格式无效")
    counts = {}
    for key, value in furnitures.items():
        count = value["quantity"]
        if type(count) is not int or count < 0:
            raise ValueError(f"家具 {key} 数量无效")
        if not isinstance(value["name"], str) or not value["name"].strip():
            raise ValueError(f"家具 {key} 名称无效")
        if type(value["canBeDestroy"]) is not bool:
            raise ValueError(f"家具 {key} 分解属性无效")
        if value["themeId"] and value["themeId"] not in themes:
            raise ValueError(f"家具 {key} 套装缺失")
        counts[key] = count
    for theme in themes.values():
        for key, count in theme["counts"].items():
            if key not in counts or type(count) is not int or count < 1:
                raise ValueError(f"套装家具 {key} 数量无效")
            # 兼容同一家具在多个主题中出现，按需求最多的一套保留。
            counts[key] = max(counts[key], count)
    names = Counter(normalize_name(value["name"]) for value in furnitures.values())
    return {
        normalize_name(value["name"]): counts[key]
        for key, value in furnitures.items()
        if value["canBeDestroy"]
        and counts[key] > 0
        and names[normalize_name(value["name"])] == 1
    }


def load_furniture_keep_counts():
    # 每次任务从当前整包版本读取，旧包缺少本文件时由资源选择器回退内置包。
    from arknights_mower.utils.resource_pkg import resource_pkg_path

    path = resource_pkg_path("arknights_mower/data/furniture.json")
    return furniture_keep_counts(json.loads(path.read_text(encoding="utf-8")))
