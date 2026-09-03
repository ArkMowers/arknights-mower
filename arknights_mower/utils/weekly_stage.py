"""刷理智周计划：最新活动关卡推荐（纯逻辑，可单测）。

数据来自 stage_data_full（运行时、可被热更覆盖的版本）。每条记录关键字段：
id / name / stageType / zoneNameSecond（活动名，同活动各 zone 一致）/ endTs（可为
{startTs, endTs} 结构或 None{无窗口}/-1{剿灭}）/ drop（[{type, id, dropType}]）/
difficulty。id 即关卡代号（如 TO-9、TO-S-4）。

选关规则（用户已确认 + 澄清「不要 S 关 / EX 关 / MO 关」）：
1. 只留**还未结束**的活动：活动结束时间早于当前时间的不显示；
2. 最近开启 = 一场活动（活动名 zoneNameSecond 相同者算同一场）里，其带窗口（endTs
   为 {startTs,endTs}）的关的 startTs 最大者为「最新开启的活动」；
2. 只取活动的「普通关」：剔 突袭/挑战版（difficulty=FOUR_STAR 或代号含「突袭」后缀）
   与 MO 关 / S 关 / EX 关（代号含 `-MO-`/`-S-`/`-EX-` 段）；
3. 后三关：关卡代号尾部数字最大的 3 个；
4. + 所有掉落固源岩(30012) 或 装置(30062) 的关；
5. 不卡数量上限、不去重（同关同时满足两者只保留一次，因下拉 value 不能重复）。

只取 MATERIAL 类型、常规掉落（dropType 常规/NORMAL）的材料；剔 ACTIVITY_ITEM/COMPLETE。
展示的掉落物：掉固源岩/装置（30012/30062）的关只展示这两种，其余关展示其全部
MATERIAL 常规掉落；库存格式 `材料(库存:n)`。
"""

import re

# 目标掉落材料 id（固源岩 / 装置）
DROP_MATERIAL_IDS = frozenset({"30012", "30062"})
# 材料类型 & 常规掉落标记
MATERIAL_TYPE = "MATERIAL"
NORMAL_DROP = "NORMAL"
# 突袭/挑战难度，不计入可选掉落关
EXCLUDED_DIFFICULTY = "FOUR_STAR"

_TRAILING_NUMBER = re.compile(r"(\d+)$")
_CM_SUFFIX = re.compile(r"\s*突袭$")
# MO / S / EX 子 zone 的关卡（如 TO-MO-1、TO-S-4、TO-EX-1），不算普通关
_SPECIAL_ZONE = re.compile(r"-(MO|S|EX)-\d")


def _stage_code(stage) -> str | None:
    code = stage.get("id") or stage.get("code")
    return str(code) if code else None


def _event_key(stage) -> str:
    """活动标识：活动名 zoneNameSecond，缺失时退到 zoneId / 关卡代号。"""
    return stage.get("zoneNameSecond") or stage.get("zoneId") or str(_stage_code(stage))


def _window(stage) -> tuple[int, int] | None:
    """endTs 为 {startTs, endTs} 结构才算带窗口的活动关；否则视为关闭/历史，不参与。"""
    window = stage.get("endTs")
    if isinstance(window, dict):
        start, end = window.get("startTs"), window.get("endTs")
        if start is not None and end is not None:
            return start, end
    return None


def _is_farmable(stage) -> bool:
    """只留活动的「普通关」：剔 突袭/挑战 + S 关 + EX 关。"""
    code = _stage_code(stage)
    if not code or _CM_SUFFIX.search(code):
        return False
    if stage.get("difficulty") == EXCLUDED_DIFFICULTY:
        return False
    if _SPECIAL_ZONE.search(code):
        return False
    return True


def _trailing_number(code: str) -> int:
    match = _TRAILING_NUMBER.search(code)
    return int(match.group(1)) if match else -1


def _is_material_drop(drop) -> bool:
    return (
        isinstance(drop, dict)
        and drop.get("type") == MATERIAL_TYPE
        and drop.get("dropType") == NORMAL_DROP
    )


def _materials(stage, key_mapping) -> list[dict]:
    """该关展示的材料：[{id, name}]，去重（按 id）。

    掉固源岩/装置（30012/30062）的关只展示这两种；其余关展示其全部 MATERIAL 常规掉落。
    """
    all_mats = []
    target_mats = []
    seen_all = set()
    seen_target = set()
    for drop in stage.get("drop") or []:
        if not _is_material_drop(drop):
            continue
        mat_id = drop.get("id")
        if not mat_id or mat_id in seen_all:
            continue
        seen_all.add(mat_id)
        info = key_mapping.get(mat_id)
        name = info[2] if isinstance(info, list) and len(info) > 2 else mat_id
        all_mats.append({"id": mat_id, "name": name})
        if mat_id in DROP_MATERIAL_IDS and mat_id not in seen_target:
            seen_target.add(mat_id)
            target_mats.append({"id": mat_id, "name": name})
    return target_mats if target_mats else all_mats


def _drops_target(stage) -> bool:
    return any(
        _is_material_drop(drop) and drop.get("id") in DROP_MATERIAL_IDS
        for drop in (stage.get("drop") or [])
    )


def select_latest_activity_stages(stages, key_mapping, now) -> list[dict]:
    """返回「最近开启活动」的选中普通关，按代号尾号大到小。

    只留还未结束的活动：活动结束时间 endTs 早于 now 的直接不显示（now 为当前时间戳）。
    返回 [{code, materials: [{id, name}]}]。
    """
    groups: dict[str, dict] = {}
    for stage in stages:
        if stage.get("stageType") != "ACTIVITY":
            continue
        window = _window(stage)
        if window is None:
            continue
        start, end = window
        if end < now:  # 活动已结束，不显示
            continue
        key = _event_key(stage)
        group = groups.setdefault(key, {"start": start, "stages": []})
        group["stages"].append(stage)
        group["start"] = max(group["start"], start)

    if not groups:
        return []

    # 最新开启的活动 = 其内关 startTs 最大者
    newest = max(groups, key=lambda key: groups[key]["start"])
    pool = groups[newest]["stages"]

    entries = []
    for stage in pool:
        if not _is_farmable(stage):
            continue
        code = _stage_code(stage)
        if not code:
            continue
        entries.append(
            {
                "code": code,
                "materials": _materials(stage, key_mapping),
                "_num": _trailing_number(code),
                "_target": _drops_target(stage),
            }
        )

    if not entries:
        return []

    ranked = sorted(entries, key=lambda entry: entry["_num"], reverse=True)
    selected = []
    seen = set()

    # 后三关：代号尾号最大的 3 个
    for entry in ranked[:3]:
        if entry["code"] not in seen:
            selected.append(entry)
            seen.add(entry["code"])

    # + 掉固源岩/装置的关（与后三关重叠的去重）
    for entry in ranked:
        if entry["_target"] and entry["code"] not in seen:
            selected.append(entry)
            seen.add(entry["code"])

    return [
        {"code": entry["code"], "materials": entry["materials"]} for entry in selected
    ]


def build_options(selected, inventory) -> list[dict]:
    """把选中关拼成前端可直接用的下拉项 [{value, label, code, materials}]。

    label = 代号 （无目标材料）或 代号:材料(库存:n),材料(库存:n)——库存无/为 0 时不带 (库存:n)。
    """
    options = []
    for item in selected:
        code = item["code"]
        materials = item["materials"]
        if materials:
            segments = []
            for mat in materials:
                count = inventory.get(mat["id"])
                segments.append(
                    f"{mat['name']}(库存:{count})" if count else mat["name"]
                )
            label = f"{code}:" + ",".join(segments)
        else:
            label = code
        options.append(
            {"value": code, "label": label, "code": code, "materials": materials}
        )
    return options
