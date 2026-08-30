"""专精技能名全局规范（#58/#61/#63 定稿）。

规范格式：`{序数}技能·真名`，如 `二技能·飞翔瞪射`（一/二/三技能 + `·` + 真名）。
- 计划 `skill_name` 存规范格式；创建端点/懒填充时填真名。
- 主页面面板技能名 ⊂ 计划 skill_name（包含匹配），长名截断后仍为前缀、匹配不受影响。
- 前端/日志/邮件/API 统一调用 `format_skill_label`。
"""

import re

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
    """
    if not panel_skill or not plan_skill_name:
        return False
    panel = normalize_skill_text(panel_skill)
    plan = normalize_skill_text(plan_skill_name)
    return bool(panel and plan and panel in plan)
