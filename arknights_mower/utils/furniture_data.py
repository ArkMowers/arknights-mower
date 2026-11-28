"""家具资源投影与整套保留数量；生成期不依赖游戏或资源加载器。"""

import json
import unicodedata
from collections import Counter

FURNITURE_DATA_PATH = "arknights_mower/data/furniture.json"


def write_furniture_data(path, building_data):
    """先完成校验，再原子替换；复用支持 Windows 临时占用重试的写入器。"""
    from arknights_mower.utils.update_runtime import write_json

    data = build_furniture_data(building_data)
    write_json(path, data, indent=2)


def normalize_name(name):
    """统一 ™/TM、全角/半角等兼容字符，再移除 OCR 空白。"""
    return "".join(unicodedata.normalize("NFKC", name).split())


def names_one_edit_apart(left, right):
    """只用于提高保留量，不用近似名称放行未知家具。"""
    if len(left) > len(right):
        left, right = right, left
    if len(right) - len(left) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return left[index:] == right[index + 1 :]
    return True


def conservative_keep_counts(counts):
    """识别成只差一个字的另一合法家具时，仍按两者较大套装数量保护。"""
    result = counts.copy()
    for name, count in counts.items():
        if count <= 1:
            continue
        for candidate, other in counts.items():
            if other < count and names_one_edit_apart(name, candidate):
                result[candidate] = max(result[candidate], count)
    return result


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
    """归一化后精确匹配；同名家具、不可分解或未知数量不参与自动分解。"""
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
            # 当前资源两者相等；作为上游数据变化的防御性核对，取较大值。
            # 同一家具将来若出现在多个主题，也按需求最多的一套保留。
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

    path = resource_pkg_path(FURNITURE_DATA_PATH)
    return furniture_keep_counts(json.loads(path.read_text(encoding="utf-8")))
