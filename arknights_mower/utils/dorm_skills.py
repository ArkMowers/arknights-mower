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
    # 0 表示该练度没有单回；comparable 仅指同房住客的速度能否相减。
    single: frozenset[float]
    comparable: bool
    affects_self: bool
    shares_recovery: bool = False
    extra_target: tuple[str, float] | None = None


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
    rf"(?:（同种效果取最高）|，同时每个招募位（不包含初始招募位）额外\+{_NUMBER}恢复效果（叠加后的最终值同种效果取最高）)"
)
_SHARED = re.compile(
    rf"进驻宿舍时，使心情未满的宿舍成员，平均分配到总计每小时心情恢复\+{_NUMBER}的加成"
    r"（该技能对单名干员和多名干员生效时，同种效果分别取最高）"
)
_SELF = re.compile(
    rf"进驻宿舍时，自身心情每小时恢复[+-]{_NUMBER}"
    rf"(?:，该宿舍内所有干员的心情每小时恢复\+{_NUMBER}（同种效果取最高）)?"
)


@lru_cache(maxsize=None)
def dorm_skill_effects(name, stage):
    """仅解释已知的同房恢复差值。分摊另行核对人数，未知技能保留未知。"""
    from arknights_mower.utils.building_skills import _requirement, skill_statuses

    skills = _skill_index().get(name)
    if skills is None:
        return DormSkillEffects(frozenset(), False, False)
    if stage is None:
        points = {_requirement(skill) for skill in skills} | {(0, 1)}
        if None in points:
            return DormSkillEffects(frozenset(), False, False)
        options = [dorm_skill_effects(name, point) for point in points]
        extra_targets = {option.extra_target for option in options}
        return DormSkillEffects(
            (
                frozenset().union(*(option.single for option in options))
                if all(option.single for option in options)
                else frozenset()
            ),
            len(extra_targets) == 1 and all(option.comparable for option in options),
            any(option.affects_self for option in options),
            any(option.shares_recovery for option in options),
            extra_targets.pop() if len(extra_targets) == 1 else None,
        )
    single = set()
    extra_target = None
    comparable, affects_self, shares_recovery = True, False, False
    for skill, status in skill_statuses(skills, stage):
        if skill.get("roomType") != "宿舍" or status in ("locked", "replaced"):
            continue
        text = _TAGS.sub("", skill.get("des", ""))
        if match := _SINGLE.fullmatch(text):
            single.add(float(match[1]))
        elif match := _TARGETED.fullmatch(text):
            single.add(float(match[1]))
            extra_target = match[2], float(match[3])
        elif _SHARED.fullmatch(text):
            shares_recovery = True
        elif not (_SELF.fullmatch(text) or _GROUP.fullmatch(text)):
            # 有定向额外恢复时仍是可能的来源，不能当作技能未解锁。
            if _SINGLE_RECOVERY in text.replace("除自身以外", ""):
                return DormSkillEffects(frozenset(), False, False)
            comparable = False
        affects_self |= "自身心情每小时恢复" in text
        comparable &= status == "active"
    return DormSkillEffects(
        frozenset(single or {0}),
        comparable,
        affects_self,
        shares_recovery,
        extra_target,
    )


@register_resource_reload
def clear_dorm_skill_cache():
    global resource_generation
    _skill_index.cache_clear()
    dorm_skill_effects.cache_clear()
    is_single_recovery_manager.cache_clear()
    is_group_recovery_manager.cache_clear()
    resource_generation += 1
