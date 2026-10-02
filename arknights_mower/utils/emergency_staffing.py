"""自动救急复用基建资源，按实际生效技能比较设施内临时驻员。"""

import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from math import isfinite
from pathlib import Path

import cv2

from arknights_mower import __rootdir__
from arknights_mower.utils.building_skills import skill_index
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operator
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_ui_path,
)

_TAGS = re.compile(r"<[^>]*>")
_CROSS_FACILITY = re.compile(
    r"基建内|设施数量|其他设施|感知信息|烟火|梦境|小节|无声共鸣|情报储备|乌萨斯特饮"
)


@dataclass(frozen=True)
class StaffingCandidate:
    name: str
    mood: float
    skills: tuple


def skill_icon_path(icon):
    relative = f"building_skill/{icon}.webp"
    return (
        resource_ui_path(relative)
        or Path(__rootdir__).parent / "ui" / "public" / relative
    )


@lru_cache(maxsize=256)
def _icon_templates(icon):
    image = cv2.imread(str(skill_icon_path(icon)))
    if image is None:
        return ()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return tuple(cv2.resize(gray, (size, size)) for size in (54, 60))


@register_resource_reload
def clear_staffing_skills():
    _icon_templates.cache_clear()


def card_skills(image, scope, name, facility):
    """仅匹配该干员当前设施图标；暗图标及无法区分的升级效果不假定生效。"""
    (left, top), (right, _) = scope
    if top < 113 or left < 0 or right > image.shape[1]:
        return ()
    region = image[top - 113 : top - 28, left : min(right, left + 145)]
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    groups = {}
    # 共用同一图标的资源使用最低解锁版本，避免凭姓名假定精英技能。
    icons = {}
    for skill in skill_index().get(name, ()):
        if skill["roomType"] == facility:
            icons.setdefault(skill["skillIcon"], skill)
    for icon, skill in icons.items():
        best = 0
        for template in _icon_templates(icon):
            if min(gray.shape) < template.shape[0]:
                continue
            scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, (x, y) = cv2.minMaxLoc(scores)
            size = template.shape[0]
            patch = gray[y : y + size, x : x + size]
            if patch.mean() >= 95:
                best = max(best, score)
        if best >= 0.88:
            key = skill["skill_key"]
            if key not in groups or best > groups[key][0]:
                groups[key] = (best, skill)
    return tuple(item[1] for item in groups.values())


def eligible_worker(data, name, mood, reserved):
    if name in reserved or name in TRADE_ORDER_AGENTS or name == "菲亚梅塔":
        return False
    if mood is None or not isfinite(mood) or not 0 <= mood <= 24:
        return False
    op = data.operators.get(name)
    if op is None:
        op = Operator(name, "")
        data.apply_custom_mood_limits(op)
    if op.current_room == "train":
        return False
    return mood >= data.resting_mood_threshold(op) + 1


def _amount(text, label):
    match = re.search(label + r"(?:提升|提高)?([+-]?\d+(?:\.\d+)?)%", text)
    return float(match[1]) if match else 0


def facility_score(workers, facility, product):
    """固定效果与已支持的同设施联动；未知、概率及跨设施收益不计分。"""
    skills = [s for worker in workers for s in worker.skills]
    icons = {s["skillIcon"] for s in skills}
    bonuses, storage = [], []
    control = {}
    for worker in workers:
        bonus = capacity = 0
        for skill in worker.skills:
            text = _TAGS.sub("", skill["des"])
            if facility != "中枢":
                text = re.sub(r"心情每小时消耗[+-]\d+(?:\.\d+)?", "", text)
            if _CROSS_FACILITY.search(text):
                continue
            if facility == "制造站":
                capacity_match = re.search(r"仓库容量上限([+-]\d+)", text)
                if capacity_match:
                    capacity += int(capacity_match[1])
                if "当前制造站内" in text or "每" in text:
                    continue
                if "作战记录" in text and product not in (
                    "exp",
                    "exp1",
                    "exp2",
                    "exp3",
                ):
                    continue
                if "贵金属" in text and product != "gold":
                    continue
                if "源石" in text and product not in ("orirock", "orirock_device"):
                    continue
                bonus += _amount(text, "生产力")
            elif facility == "贸易站":
                capacity_match = re.search(r"订单上限([+-]\d+)", text)
                if capacity_match:
                    capacity += int(capacity_match[1])
                if "每" not in text and "其他干员" not in text:
                    bonus += _amount(text, "订单获取效率")
            elif facility == "发电站":
                if "每" not in text:
                    bonus += _amount(text, "无人机充能速度")
            elif facility == "人力办公室":
                if "每" not in text:
                    bonus += _amount(text, "联络速度")
            elif facility == "会客室":
                if "处于" not in text and "每" not in text:
                    bonus += _amount(text, "线索搜集速度")
            elif facility == "中枢":
                for label in ("制造站生产力", "订单效率", "订单获取效率", "联络速度"):
                    control[label] = max(control.get(label, 0), _amount(text, label))
                if "心情" in text:
                    reduction = re.search(
                        r"心情(?:每小时)?消耗([+-]\d+(?:\.\d+)?)", text
                    )
                    if reduction:
                        bonus += max(0, -float(reduction[1]))
                    recovery = re.search(r"心情每小时恢复\+(\d+(?:\.\d+)?)", text)
                    if recovery:
                        bonus += float(recovery[1])
        bonuses.append(bonus)
        storage.append(capacity)
    total = sum(bonuses)
    if facility == "制造站":
        if "bskill_man_spd_variable31" in icons:
            total += sum(max(0, n) * (3 if n > 16 else 1) for n in storage)
        elif "bskill_man_spd_variable11" in icons:
            total += sum(max(0, n) * 2 for n in storage)
        if "bskill_man_spd_variable21" in icons:
            total += min(40, int(total / 5) * 5)
    elif facility == "贸易站":
        if "bskill_tra_vodfox" in icons and product == "lmd":
            total = 45 * max(0, len(workers) - 1)
        elif "bskill_tra_limit_count" in icons:
            total += max(1, 10 + sum(storage) - int(total / 10)) * 4
        elif "bskill_tra_limit_diff" in icons:
            total += (10 + sum(storage)) * 4 / 4.12
    return total + sum(control.values())


def select_workers(candidates, facility, product, slots, *, current=(), fixed=()):
    """比较有界候选组合；同分优先保持当前阵容，再取较高心情。"""
    fixed = tuple({c.name: c for c in fixed}.values())
    fixed_names = {c.name for c in fixed}
    candidates = list(
        {c.name: c for c in candidates if c.name not in fixed_names}.values()
    )
    if not candidates or slots <= 0:
        return []
    current = set(current)
    # 制造和贸易最多三个岗位；其他设施用较小候选池限制枚举开销。
    limit = 48 if facility in ("制造站", "贸易站") else 16
    candidates.sort(
        key=lambda c: (
            facility_score([c, *fixed], facility, product),
            c.name in current,
            c.mood,
        ),
        reverse=True,
    )
    # Keep supported local synergy participants even when their isolated score is low.
    synergy_icons = {
        "bskill_man_spd_variable31",
        "bskill_man_spd_variable11",
        "bskill_man_spd_variable21",
        "bskill_tra_vodfox",
        "bskill_tra_limit_count",
        "bskill_tra_limit_diff",
    }
    synergistic = [
        c
        for c in candidates
        if any(
            s["skillIcon"] in synergy_icons
            or (facility == "制造站" and "仓库容量上限" in s["des"])
            or (facility == "贸易站" and "订单上限" in s["des"])
            for s in c.skills
        )
    ]

    def synergy_value(worker):
        capacity = 0
        for skill in worker.skills:
            text = _TAGS.sub("", skill["des"])
            match = re.search(r"(?:仓库容量上限|订单上限)([+-]\d+)", text)
            if match:
                capacity += int(match[1])
        producer = any(s["skillIcon"] in synergy_icons for s in worker.skills)
        return (
            producer,
            capacity,
            facility_score([worker, *fixed], facility, product),
            worker.mood,
        )

    synergistic.sort(key=synergy_value, reverse=True)
    # A bounded part of the pool preserves producers and capacity contributors.
    candidates = list(
        {c.name: c for c in [*synergistic[: limit // 2], *candidates]}.values()
    )[:limit]
    count = min(len(candidates), slots)
    best = max(
        combinations(candidates, count),
        key=lambda group: (
            facility_score([*group, *fixed], facility, product),
            sum(c.name in current for c in group),
            sum(c.mood for c in group),
        ),
    )
    return [c.name for c in best]
