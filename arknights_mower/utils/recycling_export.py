"""Write recycling evidence snapshots as native Excel workbooks."""

import math
import re
from datetime import datetime
from tempfile import SpooledTemporaryFile
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_QUALITIES = ("未知品质", "白色材料", "绿色材料", "蓝色材料", "紫色材料", "金色材料")


def _quality(rarity):
    return _QUALITIES[rarity] if rarity in range(1, 6) else _QUALITIES[0]


def _cell(value, column, row, style=0):
    address = f"{chr(65 + column)}{row}"
    if type(value) in (int, float) and math.isfinite(value):
        return f'<c r="{address}" s="{style or (2 if type(value) is float else 0)}"><v>{value}</v></c>'
    text = str(value) if value is not None else "未计算"
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    if len(text) > 32767:
        raise ValueError("导出内容超过 Excel 单元格文字上限，请缩小日期范围")
    return f'<c r="{address}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _write_sheet(archive, index, headers, rows, widths, percent_columns=()):
    with archive.open(f"xl/worksheets/sheet{index}.xml", "w") as output:

        def write(text):
            output.write(text.encode("utf-8"))

        write(
            f'<worksheet xmlns="{_NS}"><sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            "</sheetView></sheetViews><cols>"
        )
        for column, width in enumerate(widths, 1):
            write(
                f'<col min="{column}" max="{column}" width="{width}" customWidth="1"/>'
            )
        write('</cols><sheetData><row r="1" ht="26" customHeight="1">')
        write(
            "".join(_cell(value, column, 1, 1) for column, value in enumerate(headers))
        )
        write("</row>")
        last = 1
        for last, values in enumerate(rows, 2):
            if last > 1048576:
                raise ValueError("导出记录超过 Excel 工作表行数上限，请缩小日期范围")
            write(f'<row r="{last}">')
            write(
                "".join(
                    _cell(value, column, last, 3 if column in percent_columns else 0)
                    for column, value in enumerate(values)
                )
            )
            write("</row>")
        write(
            f'</sheetData><autoFilter ref="A1:{chr(64 + len(headers))}{last}"/></worksheet>'
        )


def _detail_rows(records):
    for record in records:
        timestamp = datetime.fromtimestamp(record["collected_at"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        operators = record["operators"]
        names = "未识别" if operators is None else "、".join(operators) or "无人进驻"
        for name, count in (record["materials"] or {"未完整识别": "未知"}).items():
            yield timestamp, names, name, count, record["id"]


def write_recycling_workbook(start_date, end_date, summary, records):
    """Stream evidence and valuation inputs; spill archives above 8 MiB to disk."""
    comparison = summary["comparison"]
    materials = summary["materials"]
    quantity = sum(item["count"] for item in materials)
    source = comparison["source"]
    overview = [
        ("日期范围", f"{start_date} 至 {end_date}", "包含起止日期，全部收取记录"),
        (
            "时间口径",
            datetime.now().astimezone().strftime("%Z / UTC%z"),
            "按运行 Mower 的本机时区",
        ),
        ("收取次数", summary["total"], "一次收取可以包含多件材料"),
        ("已识别材料总数", quantity, "未完整识别的批次不估算数量"),
        ("总理智收益", comparison["actual_sanity"], "实际材料数量 × 当前材料理智价值"),
        ("理论期望收益", comparison["expected_sanity"], "相同材料总数 × 长期单件期望"),
        ("与期望的差额", comparison["difference"], "实际收益减去理论期望"),
        (
            "单件材料长期期望",
            comparison["per_material"],
            "双池收益除以双池材料数量，单位：理智/件",
        ),
        (
            "未完整识别的收取",
            comparison["unknown_collections"],
            "存在未知批次时不计算总收益对比",
        ),
        (
            "未定价材料",
            "、".join(comparison["unknown_materials"]) or "无",
            "存在未定价材料时不计算总收益对比",
        ),
        (
            "概率来源",
            source["source"],
            f"{source['sheet']}：{'、'.join(source['ranges'])}",
        ),
        (
            "比较说明",
            "同材料量的长期期望",
            "不推算干员效率、收取对应抽数或每日产能，不保证短期结果",
        ),
        (
            "明细说明",
            "每件材料类型一行",
            "同一收取标识的多行属于同一次收取；未知干员与无人进驻分别保留",
        ),
    ]
    valuation = comparison["valuation"]
    calculator = comparison["calculator"]
    overview.extend(
        [
            (
                "缺少概率的材料",
                "、".join(comparison["unmodeled_materials"]) or "无",
                "新材料价值不代表掉落概率；缺少概率时不计算期望对比",
            ),
            (
                "材料价值来源",
                valuation["source"],
                "导入为本地快照，具体价值见价值参数表",
            ),
            (
                "100%回收站理论日产理智",
                calculator["daily_sanity"],
                "双池各产一次：100%效率每两天一次普通抽取；不是实测日产量",
            ),
            (
                "设定效率下理论日产理智",
                calculator["configured_daily_sanity"],
                "按价值参数中的回收站效率计算",
            ),
            (
                "等效制造站效率",
                calculator["manufacturing_equivalent"],
                "理论换算，以每日8000经验为100%制造站效率",
            ),
            (
                "精零旅骨等效制造站效率",
                calculator["elite0_equivalent"],
                "计算器20%回收站效率假设",
            ),
            (
                "精二旅骨等效制造站效率",
                calculator["elite2_equivalent"],
                "计算器30%回收站效率假设",
            ),
        ]
    )
    replacement = calculator["replacement"]
    overview.extend(
        [
            (
                "顶替机制：100%回收站理论日产理智",
                replacement["daily_sanity"],
                "假设额外池顶替普通池，作为对照；实际机制尚未确认",
            ),
            (
                "顶替机制：设定效率下理论日产理智",
                replacement["configured_daily_sanity"],
                "按价值参数中的回收站效率计算",
            ),
            (
                "顶替机制：等效制造站效率",
                replacement["manufacturing_equivalent"],
                "以每日8000经验为100%制造站效率",
            ),
            (
                "顶替机制：精零旅骨等效制造站效率",
                replacement["elite0_equivalent"],
                "计算器20%回收站效率假设",
            ),
            (
                "顶替机制：精二旅骨等效制造站效率",
                replacement["elite2_equivalent"],
                "计算器30%回收站效率假设",
            ),
        ]
    )
    actual_quality = {item["rarity"]: item["count"] for item in summary["qualities"]}
    expected_quality = {
        item["rarity"]: item["probability"] for item in comparison["qualities"]
    }
    qualities = sorted(
        actual_quality.keys() | expected_quality.keys(), key=lambda value: value or 0
    )
    sheets = [
        ("收益概览", ("指标", "数值", "说明"), overview, (26, 66, 92), ()),
        (
            "收取明细",
            ("收取时间", "回收站进驻干员", "材料", "数量", "收取标识"),
            _detail_rows(records),
            (24, 36, 28, 16, 42),
            (),
        ),
        (
            "材料汇总",
            ("材料", "品质", "数量"),
            (
                (item["name"], _quality(item["rarity"]), item["count"])
                for item in materials
            ),
            (28, 20, 18),
            (),
        ),
        (
            "品质统计",
            ("品质", "实际数量", "实际占比", "理论占比"),
            (
                (
                    _quality(rarity),
                    actual_quality.get(rarity, 0),
                    actual_quality.get(rarity, 0) / quantity if quantity else None,
                    expected_quality.get(rarity),
                )
                for rarity in qualities
            ),
            (22, 18, 18, 18),
            (2, 3),
        ),
        (
            "价值参数",
            ("参数或材料", "数值", "说明"),
            [
                ("价值来源", valuation["source"], "本次导出的估值快照"),
                (
                    "导入时间",
                    datetime.fromtimestamp(valuation["imported_at"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if valuation["imported_at"]
                    else "内置快照",
                    "运行 Mower 的本机时区",
                ),
                (
                    "经验书价值比例",
                    valuation["ratios"]["experience"],
                    "用于制造站效率换算",
                ),
                ("赤金价值比例", valuation["ratios"]["gold"], "用于制造站效率换算"),
                ("订单价值比例", valuation["ratios"]["order"], "用于制造站效率换算"),
                (
                    "回收站效率",
                    valuation["ratios"]["efficiency"],
                    "1表示100%，只用于理论换算",
                ),
                ("龙门币", valuation["lmd_sanity"], "理智/龙门币"),
                *(
                    (
                        name,
                        price,
                        "理智/件；物品 ID：" + valuation["item_ids"].get(name, "未知"),
                    )
                    for name, price in sorted(valuation["prices"].items())
                ),
            ],
            (30, 30, 55),
            (),
        ),
    ]
    output = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                + "".join(
                    f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for index in range(1, len(sheets) + 1)
                )
                + "</Types>",
            )
            archive.writestr(
                "_rels/.rels",
                f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/workbook.xml",
                f'<workbook xmlns="{_NS}" xmlns:r="{_REL}"><sheets>'
                + "".join(
                    f'<sheet name="{sheet[0]}" sheetId="{index}" r:id="rId{index}"/>'
                    for index, sheet in enumerate(sheets, 1)
                )
                + "</sheets></workbook>",
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(
                    f'<Relationship Id="rId{index}" Type="{_REL}/worksheet" Target="worksheets/sheet{index}.xml"/>'
                    for index in range(1, len(sheets) + 1)
                )
                + f'<Relationship Id="rId{len(sheets) + 1}" Type="{_REL}/styles" Target="styles.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/styles.xml",
                f'<styleSheet xmlns="{_NS}">'
                '<fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Microsoft YaHei"/></font></fonts>'
                '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF238570"/><bgColor indexed="64"/></patternFill></fill></fills>'
                '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf>'
                '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment vertical="center" wrapText="1"/></xf>'
                '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
                '<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
                '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
            )
            for index, (_, headers, rows, widths, percents) in enumerate(sheets, 1):
                _write_sheet(archive, index, headers, rows, widths, percents)
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise
