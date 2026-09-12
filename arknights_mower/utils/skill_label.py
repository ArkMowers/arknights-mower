"""专精技能名全局规范（#58/#61/#63 定稿）。

规范格式：`{序数}技能·真名`，如 `二技能·飞翔瞪射`（一/二/三技能 + `·` + 真名）。
- 计划 `skill_name` 存规范格式；创建端点/懒填充时填真名。
- 主页面面板技能名 ⊂ 计划 skill_name（包含匹配），长名截断后仍为前缀、匹配不受影响。
- 前端/日志/邮件/API 统一调用 `format_skill_label`。
"""

import re
from typing import Optional

CN_ORDINAL = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "七"}
_CANONICAL_RE = re.compile(r"^[一二三四五六]技能·")
_PLACEHOLDER_RE = re.compile(r"^技能[0-9]+$")
_SEPARATORS = "·・．.。 　\t"


def is_placeholder_skill_name(skill_name) -> bool:
    """是否为占位技能名 `技能{N}`（无真名可查时使用的回退格式）。"""
    if not skill_name:
        return True
    return bool(_PLACEHOLDER_RE.match(str(skill_name).strip()))


def format_skill_label(skill_index: int, skill_name=None) -> str:
    """生成全局规范技能名：`{序数}技能·真名`。

    - 已规范（以 `X技能·` 开头）→ 原样返回。
    - 有真名（非占位 `技能{N}`）→ `{序数}技能·{真名}`。
    - 占位/无真名 → 回退 `{N}技能`（1-indexed）。
    """
    if skill_name:
        s = str(skill_name).strip()
        if s and _CANONICAL_RE.match(s):
            return s
        if s and not _PLACEHOLDER_RE.match(s):
            ordinal = CN_ORDINAL.get(skill_index)
            if ordinal:
                return f"{ordinal}技能·{s}"
    return f"技能{skill_index + 1}"


def normalize_skill_text(s) -> str:
    """归一化技能文本用于比较：去方括号/空白，统一中文序数点分隔符。"""
    if not s:
        return ""
    s = str(s).replace("[", "").replace("]", "")
    for sep in _SEPARATORS:
        s = s.replace(sep, "·")
    return s


def panel_skill_matches(panel_skill, plan_skill_name) -> bool:
    """主页面面板技能名 ⊂ 计划 skill_name（归一化后的包含匹配）。

    面板可能因长名截断只显示前缀，故用包含而非全等；
    同一干员内技能名不重复，无歧义（#63）。
    OCR 偶尔在技能名后多读一个拉丁字母/数字（如「破坏与滋养」→「破坏与滋养A」），
    直接比不中；去掉尾部 ASCII 再比一次兜底。合法含尾字母的「红桃K」等先直接命中，
    不受影响。
    """
    if not panel_skill or not plan_skill_name:
        return False
    panel = normalize_skill_text(panel_skill)
    plan = normalize_skill_text(plan_skill_name)
    if panel and plan and panel in plan:
        return True
    stripped = re.sub(r"[A-Za-z0-9]+$", "", panel)
    return bool(stripped and plan and stripped in plan)


_name_to_char_id_cache = None


def _resolve_operator_char_id(operator_name) -> Optional[str]:
    """面板干员名 → skill_data 的 char_id；查无 / 多名撞名 → None。

    直接命中 char_id（dev 模式面板显示 id）或按显示名反查（缓存，撞名保守不采纳）。
    """
    global _name_to_char_id_cache
    if not operator_name:
        return None
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    characters = get_skill_data().get("characters", {})
    if operator_name in characters:
        return operator_name
    if _name_to_char_id_cache is None:
        _name_to_char_id_cache = {}
        for char_id, char in characters.items():
            name = char.get("name")
            if name:
                _name_to_char_id_cache.setdefault(name, []).append(char_id)
    ids = _name_to_char_id_cache.get(operator_name)
    if ids and len(ids) == 1:
        return ids[0]
    return None


def resolve_panel_skill(operator_name, panel_skill_text) -> Optional[int]:
    """面板技能文本 → 干员已知技能序号（skill_data 对照解析）。

    已知技能 ≤3（skill_data.json characters[char_id].skills[].name）。面板文本对
    每个有名字的已知技能做归一化互含匹配（面板 ⊂ 真名 或 真名 ⊂ 面板，容忍长名截断
    与 OCR 首尾噪声）；命中**唯一**技能才返回序号；查无干员 / 无命名技能 / 0 或多候选
    → 返回 None（调用方回退 panel_skill_matches 现行为）。#95
    """
    if not operator_name or not panel_skill_text:
        return None
    char_id = _resolve_operator_char_id(operator_name)
    if char_id is None:
        return None
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    skills = get_skill_data().get("characters", {}).get(char_id, {}).get("skills", [])
    panel = normalize_skill_text(panel_skill_text)
    if not panel:
        return None
    hits = []
    for idx, skill in enumerate(skills):
        name = skill.get("name") if isinstance(skill, dict) else None
        if not name:
            continue
        known = normalize_skill_text(name)
        if known and (panel in known or known in panel):
            hits.append(idx)
    return hits[0] if len(hits) == 1 else None
