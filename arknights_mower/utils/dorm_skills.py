"""仅匹配排班表用到的干员，结果按资源版本缓存。"""

import json
import re
from functools import lru_cache
from typing import NamedTuple

from arknights_mower.utils.res_version import BUILDING_SKILL_DATA
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
)

_SINGLE_RECOVERY = "进驻宿舍时，使该宿舍内心情未满的某个干员每小时恢复"
_GROUP_RECOVERY = (
    "所有干员的心情每小时恢复",
    "使心情未满的宿舍成员，平均分配到",
)
_TAGS = re.compile(r"<[^>]*>")
resource_generation = 0


@lru_cache(maxsize=1)
def _skill_index():
    path = resource_pkg_path(BUILDING_SKILL_DATA)
    return {
        agent["name"]: agent.get("child_skill", [])
        for agent in json.loads(path.read_text("utf-8"))
    }


@lru_cache(maxsize=None)
def is_single_recovery_manager(name):
    # 深靛的描述省略“除自身以外”，两种文本都按指定单人恢复识别。
    return any(
        _SINGLE_RECOVERY
        in _TAGS.sub("", skill.get("des", "")).replace("除自身以外", "")
        for skill in _skill_index().get(name, [])
    )


@lru_cache(maxsize=None)
def is_group_recovery_manager(name):
    """宿舍群回与分摊恢复可补回救急空床；其他设施的恢复不计。"""
    return any(
        skill.get("roomType") == "宿舍"
        and any(text in _TAGS.sub("", skill.get("des", "")) for text in _GROUP_RECOVERY)
        for skill in _skill_index().get(name, [])
    )


class DormSkillEffects(NamedTuple):
    # 单回数值 0 表示该练度未解锁单回。comparable 表示技能作用范围已知。
    single: frozenset[float]
    comparable: bool
    affects_self: bool
    shared_recovery: float = 0
    extra_target: tuple[frozenset[str], float] | None = None
    self_rate: float | None = None

    @property
    def shares_recovery(self):
        return self.shared_recovery > 0

    def single_bonus_for(self, name):
        bonus = max(self.single, default=0)
        if bonus and self.extra_target and name in self.extra_target[0]:
            bonus += self.extra_target[1]
        return bonus


_NUMBER = r"\d+(?:\.\d+)?"
_SINGLE_TEXT = rf"进驻宿舍时，使该宿舍内(?:除自身以外)?心情未满的某个干员每小时恢复\+({_NUMBER})（同种效果取最高）"
_SINGLE = re.compile(
    _SINGLE_TEXT
    + rf"(?:；同时自身心情每小时恢复\+{_NUMBER}|，同时当前宿舍每级提供1个小节)?"
)
_TARGETED = re.compile(
    _SINGLE_TEXT + rf"，如果目标是([^，（）]+)，则恢复效果额外\+({_NUMBER})"
)
_GROUP = re.compile(
    rf"进驻宿舍时，该宿舍内所有干员的?心情每小时恢复\+{_NUMBER}"
    rf"(?:（同种效果取最高）(?:，同时当前宿舍每级提供1层梦境)?|，同时每个招募位（不包含初始招募位）额外\+{_NUMBER}恢复效果（叠加后的最终值同种效果取最高）)"
)
_PERCEPTION = re.compile(r"进驻宿舍时，每(?:1个小节|1层梦境)转化为1点感知信息")
_SHARED = re.compile(
    rf"进驻宿舍时，使心情未满的宿舍成员，平均分配到总计每小时心情恢复\+({_NUMBER})的加成"
    r"（该技能对单名干员和多名干员生效时，同种效果分别取最高）"
)
_SELF_RATE = re.compile(rf"自身心情每小时恢复([+-]{_NUMBER})")
_SELF = re.compile(
    rf"进驻宿舍时，自身心情每小时恢复[+-]{_NUMBER}"
    rf"(?:，该宿舍内所有干员的心情每小时恢复\+{_NUMBER}（同种效果取最高）)?"
)


def _extra_recipients(description, target):
    if target in _skill_index():
        return frozenset({target})

    from arknights_mower.utils.building_skills import term_index

    condition = description.partition("如果目标是")[2].partition("，则")[0]
    terms = re.findall(r"<\$([^>]+)>", condition)
    if not terms:
        return None
    try:
        catalog = term_index()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    members = set()
    for term_id in terms:
        entry = catalog.get(term_id)
        if not isinstance(entry, dict) or not isinstance(entry.get("description"), str):
            return None
        lines = entry["description"].splitlines()
        if len(lines) < 2 or lines[0] != "包含以下干员":
            return None
        members.update(n.strip() for line in lines[1:] for n in line.split("、"))
    return frozenset(members) if members and members.issubset(_skill_index()) else None


@lru_cache(maxsize=None)
def dorm_skill_options(name, stage):
    """每种可能练度保留一组同时生效的技能。"""
    from arknights_mower.utils.building_skills import _requirement

    skills = _skill_index().get(name)
    if skills is None:
        return (DormSkillEffects(frozenset(), False, False),)
    if stage is not None:
        return (_effects_at_stage(skills, stage),)
    dorm_keys = {s["skill_key"] for s in skills if s.get("roomType") == "宿舍"}
    # 高练度的同一技能若换了设施，也会替换原有宿舍技能。
    points = {_requirement(s) for s in skills if s["skill_key"] in dorm_keys} | {(0, 1)}
    if None in points:
        return (DormSkillEffects(frozenset(), False, False),)
    return tuple(
        dict.fromkeys(_effects_at_stage(skills, point) for point in sorted(points))
    )


@lru_cache(maxsize=None)
def dorm_skill_effects(name, stage):
    """为排班汇总可用单回及自回、分摊和定向效果。"""
    options = dorm_skill_options(name, stage)
    if len(options) == 1:
        return options[0]
    extra_targets = {option.extra_target for option in options}
    self_rates = {option.self_rate for option in options}
    return DormSkillEffects(
        (
            frozenset().union(*(option.single for option in options))
            if all(option.single for option in options)
            else frozenset()
        ),
        len(extra_targets) == 1 and all(option.comparable for option in options),
        any(option.affects_self for option in options),
        max(option.shared_recovery for option in options),
        extra_targets.pop() if len(extra_targets) == 1 else None,
        self_rates.pop() if len(self_rates) == 1 else None,
    )


def _effects_at_stage(skills, stage):
    from arknights_mower.utils.building_skills import skill_statuses

    single = 0.0
    extra_target = None
    comparable, affects_self = True, False
    self_rate = shared_recovery = 0.0
    for skill, status in skill_statuses(skills, stage):
        if skill.get("roomType") != "宿舍" or status in ("locked", "replaced"):
            continue
        text = _TAGS.sub("", skill.get("des", ""))
        if match := _SINGLE.fullmatch(text):
            single = max(single, float(match[1]))
        elif match := _TARGETED.fullmatch(text):
            base = float(match[1])
            single = max(single, base)
            members = _extra_recipients(skill["des"], match[2])
            if members is None or (extra_target and members != extra_target[0]):
                comparable = False
            else:
                total = base + float(match[3])
                extra_target = (
                    members,
                    max(total, extra_target[1] if extra_target else 0),
                )
        elif match := _SHARED.fullmatch(text):
            shared_recovery = max(shared_recovery, float(match[1]))
        elif not (
            _SELF.fullmatch(text)
            or _GROUP.fullmatch(text)
            or _PERCEPTION.fullmatch(text)
        ):
            # 有定向额外恢复时仍是可能的来源，不能当作技能未解锁。
            if _SINGLE_RECOVERY in text.replace("除自身以外", ""):
                return DormSkillEffects(frozenset(), False, False)
            comparable = False
        affects_self |= "自身心情每小时恢复" in text
        if match := _SELF_RATE.search(text):
            self_rate += float(match[1])
        comparable &= status == "active"
    if extra_target:
        members, total = extra_target
        extra_target = (members, total - single) if total > single else None
    return DormSkillEffects(
        frozenset({single}),
        comparable,
        affects_self,
        shared_recovery,
        extra_target,
        self_rate,
    )


@register_resource_reload
def clear_dorm_skill_cache():
    global resource_generation
    _skill_index.cache_clear()
    dorm_skill_options.cache_clear()
    dorm_skill_effects.cache_clear()
    is_single_recovery_manager.cache_clear()
    is_group_recovery_manager.cache_clear()
    resource_generation += 1
