"""Validate local Yituliu valuation imports and calculator assumptions."""

import math
import posixpath
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from arknights_mower.data import key_mapping
from arknights_mower.utils.recycling import recycling_model

DEFAULT_RATIOS = {
    "experience": 1.0,
    "gold": 0.8,
    "order": 733 / 2990,
    "efficiency": 1.0,
}
MAX_IMPORT_BYTES = 2 * 1024 * 1024
_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def default_valuation():
    model = recycling_model()
    return {
        "prices": {
            row["name"]: row["sanity"] for row in model["ordinary"] + model["extra"]
        },
        "lmd_sanity": 0.0036,
        "source": "计算器内置价值快照",
        "imported_at": None,
        "ratios": dict(DEFAULT_RATIOS),
        "item_ids": {
            row["name"]: str(key_mapping[row["name"]][0])
            for row in model["ordinary"] + model["extra"]
        },
    }


def validate_ratios(values):
    if not isinstance(values, dict) or values.keys() != DEFAULT_RATIOS.keys():
        raise ValueError("请填写经验书、赤金、订单价值比例和回收站效率")
    for key, value in values.items():
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1000
        ):
            raise ValueError("价值比例和效率必须是 0 至 1000 的有限数值")
        if key == "experience" and value < 0.000001:
            raise ValueError("经验书价值比例必须不小于 0.000001")
    return dict(values)


def import_yituliu_values(content):
    """Read numeric item prices from the first worksheet without executing formulas."""
    if not content or len(content) > MAX_IMPORT_BYTES:
        raise ValueError("请导入不超过 2 MiB 的一图流物品价值表 Excel")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if (
                len(archive.infolist()) > 200
                or sum(info.file_size for info in archive.infolist()) > 16 * 1024 * 1024
            ):
                raise ValueError("Excel 解压内容过大")

            def xml(path):
                raw = archive.read(path)
                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    raise ValueError("Excel XML 不支持文档类型或实体声明")
                return ET.fromstring(raw)

            workbook = xml("xl/workbook.xml")
            sheet = workbook.find("s:sheets/s:sheet", _NS)
            if sheet is None:
                raise ValueError("Excel 缺少工作表")
            relation_id = sheet.attrib[f"{{{_REL}}}id"]
            target = next(
                row.attrib["Target"]
                for row in xml("xl/_rels/workbook.xml.rels")
                if row.attrib.get("Id") == relation_id
                and row.attrib.get("TargetMode") != "External"
            )
            path = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else "xl/" + target
            )
            if not path.startswith("xl/worksheets/"):
                raise ValueError("Excel 工作表路径无效")
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = [
                    "".join(row.itertext())
                    for row in xml("xl/sharedStrings.xml").findall("s:si", _NS)
                ]
            rows = xml(path).findall("s:sheetData/s:row", _NS)
            if len(rows) > 5000:
                raise ValueError("物品价值表行数过多")
            headers = None
            prices = {}
            item_ids = {}
            unpriced = []
            required = set(default_valuation()["prices"]) | {"龙门币"}
            by_id = {str(value[0]): name for name, value in key_mapping.items()}
            by_id["4001"] = "龙门币"
            for index, row in enumerate(rows):
                cells = {}
                formulas = set()
                for cell in row.findall("s:c", _NS):
                    column = "".join(
                        char for char in cell.attrib["r"] if char.isalpha()
                    )
                    value = cell.find("s:v", _NS)
                    text = (value.text or "") if value is not None else ""
                    if cell.attrib.get("t") == "s":
                        text = strings[int(text)]
                    elif cell.attrib.get("t") == "inlineStr":
                        text = "".join(cell.find("s:is", _NS).itertext())
                    cells[column] = text.strip()
                    if cell.find("s:f", _NS) is not None:
                        formulas.add(column)
                if headers is None:
                    if index > 9:
                        break
                    reverse = {value: column for column, value in cells.items()}
                    if {"物品id", "物品名称", "等效理智"} <= reverse.keys():
                        headers = reverse
                    continue
                item_id = cells.get(headers["物品id"], "")
                name = cells.get(headers["物品名称"], "")
                if not item_id and not name:
                    continue
                if (
                    not re.fullmatch(r"[A-Za-z0-9_+.-]{1,100}", item_id)
                    or not name
                    or len(name) > 100
                ):
                    raise ValueError("物品 ID 或名称无效")
                canonical = by_id.get(item_id)
                if (
                    (canonical or name) in key_mapping
                    and key_mapping[canonical or name][3] != "MATERIAL"
                    and item_id != "4001"
                ):
                    continue
                if item_id in by_id and by_id[item_id] != name:
                    raise ValueError(f"物品 ID 与名称不符：{item_id}")
                if name in key_mapping and str(key_mapping[name][0]) != item_id:
                    raise ValueError(f"物品名称与 ID 不符：{name}")
                if headers["等效理智"] in formulas:
                    raise ValueError(f"{name} 的价值必须为数值，不能为公式")
                text = cells.get(headers["等效理智"], "")
                if name not in required and text.lower() in {
                    "",
                    "infinity",
                    "inf",
                    "nan",
                    "n/a",
                }:
                    unpriced.append(name)
                    continue
                try:
                    value = float(text)
                except ValueError as exc:
                    raise ValueError(f"{name} 的理智价值必须是数值") from exc
                if (
                    not math.isfinite(value)
                    or not 0 <= value <= 1000000
                    or (name == "龙门币" and value < 0.000000001)
                ):
                    raise ValueError(f"{name} 的理智价值无效")
                if name in prices and (
                    prices[name] != value or item_ids[name] != item_id
                ):
                    raise ValueError(f"{name} 存在冲突的重复价值")
                if item_id in item_ids.values() and item_ids.get(name) != item_id:
                    raise ValueError(f"物品 ID 存在冲突：{item_id}")
                prices[name] = value
                item_ids[name] = item_id
            if headers is None:
                raise ValueError("未找到一图流表头：物品id、物品名称、等效理智")
            if not prices:
                raise ValueError("价值表没有有效的物品价值")
            result = {
                "prices": {
                    name: price for name, price in prices.items() if name != "龙门币"
                },
                "item_ids": item_ids,
                "unpriced": unpriced,
            }
            if "龙门币" in prices:
                result["lmd_sanity"] = prices["龙门币"]
            return result
    except (
        BadZipFile,
        ET.ParseError,
        KeyError,
        IndexError,
        TypeError,
        StopIteration,
        OverflowError,
        RuntimeError,
    ) as exc:
        raise ValueError("无法读取一图流物品价值表，请导入原始 .xlsx 导出文件") from exc
