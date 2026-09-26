"""专精技能名全局规范。

规范格式：`{序数}技能·真名`，如 `二技能·飞翔瞪射`（一/二/三技能 + `·` + 真名）。
- 计划 `skill_name` 存规范格式；创建端点/懒填充时填真名。
- 主页面面板技能名 ⊂ 计划 skill_name（包含匹配），长名截断后仍为前缀、匹配不受影响。
- 前端/日志/邮件/API 统一调用 `format_skill_label`。
"""

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple

CN_ORDINAL = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "七"}
_CANONICAL_RE = re.compile(r"^[一二三四五六]技能·")
_PLACEHOLDER_RE = re.compile(r"^技能[0-9]+$")

# 面板上的括号定界符。除半角/全角方括号外，一并收 OCR 常把方括号读成的其它括号形
# （花括号/直角/书名号/圆括号等）——技能名与干员名里这些字符实测零命中（906 条技能名、
# 482 个干员名），只可能是结构性噪声，认下来才能干净切分、比对时才不会被残渣绊住。
PANEL_LEFT_BRACKETS = (
    "[",
    "【",
    "［",
    "{",
    "｛",
    "〔",
    "〈",
    "《",
    "「",
    "『",
    "（",
    "(",
)
PANEL_RIGHT_BRACKETS = (
    "]",
    "】",
    "］",
    "}",
    "｝",
    "〕",
    "〉",
    "》",
    "」",
    "』",
    "）",
    ")",
)
PANEL_BRACKETS = PANEL_LEFT_BRACKETS + PANEL_RIGHT_BRACKETS


def strip_panel_brackets(text: str) -> str:
    """去掉字符串里的面板括号字符（名字/技能名实测不含这些字符，只可能是噪声）。"""
    if not text:
        return ""
    s = str(text)
    for ch in PANEL_BRACKETS:
        s = s.replace(ch, "")
    return s


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
    """归一化技能文本用于比较：去括号/空白，统一中文序数点分隔符。

    去掉的是全部面板括号形（不只半角方括号）：OCR 读出的技能名常粘着半个括号
    （`}“挨打”`），只清半角方括号时残渣会留在串里把互含比对挡掉。
    """
    if not s:
        return ""
    s = strip_panel_brackets(str(s))
    for sep in _SEPARATORS:
        s = s.replace(sep, "·")
    return s


def panel_skill_matches(panel_skill, plan_skill_name) -> bool:
    """主页面面板技能名 ⊂ 计划 skill_name（归一化后的包含匹配）。

    面板可能因长名截断只显示前缀，故用包含而非全等；
    同一干员内技能名不重复，无歧义。
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


def resolve_panel_skill(operator_name, panel_skill_text, char_id=None) -> Optional[int]:
    """面板技能文本 → 干员已知技能序号（skill_data 对照解析）。

    已知技能 ≤3（skill_data.json characters[char_id].skills[].name）。面板文本对
    每个有名字的已知技能做归一化互含匹配（面板 ⊂ 真名 或 真名 ⊂ 面板，容忍长名截断
    与 OCR 首尾噪声）；同名多形态干员也逐形态比对。已知计划 char_id 且姓名一致时
    只查该形态。命中**唯一**技能才返回序号；
    查无干员 / 无命名技能 / 0 或多候选 → 返回 None。
    """
    if not operator_name or not panel_skill_text:
        return None
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    characters = get_skill_data().get("characters", {})
    if operator_name in characters:
        candidates = [characters[operator_name]]
    elif char_id in characters and characters[char_id].get("name") == operator_name:
        candidates = [characters[char_id]]
    else:
        unique_id = _resolve_operator_char_id(operator_name)
        candidates = (
            [characters[unique_id]]
            if unique_id is not None
            else [
                char
                for char in characters.values()
                if char.get("name") == operator_name
            ]
        )
    panel = normalize_skill_text(panel_skill_text)
    if not panel:
        return None
    hits = []
    for char in candidates:
        for idx, skill in enumerate(char.get("skills", [])):
            name = skill.get("name") if isinstance(skill, dict) else None
            if not name:
                continue
            known = normalize_skill_text(name)
            if known and (panel in known or known in panel):
                hits.append(idx)
    return hits[0] if len(hits) == 1 else None


def resolve_panel_skill_fuzzy(
    operator_name, panel_skill_text
) -> Optional[Tuple[int, str]]:
    """Recover one mostly matching skill when exact OCR resolution failed.

    Compare only skills belonging to the recognized operator. Similar names
    such as β/γ variants must remain unknown when neither is clearly best.
    """
    panel = normalize_skill_text(panel_skill_text)
    if not operator_name or len(panel) < 3:
        return None
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    candidates = {}
    for char in get_skill_data().get("characters", {}).values():
        if char.get("name") != operator_name:
            continue
        for index, skill in enumerate(char.get("skills", [])):
            name = skill.get("name") if isinstance(skill, dict) else None
            known = normalize_skill_text(name)
            if len(known) < 4:
                continue
            candidates[(index, name)] = SequenceMatcher(None, panel, known).ratio()
    if not candidates:
        return None
    ranked = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
    (index, name), score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if score < 0.80 or score - runner_up < 0.15:
        return None
    return index, name
