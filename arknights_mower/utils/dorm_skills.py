"""仅匹配排班表用到的干员，结果按资源版本缓存。"""

import json
import re
from functools import lru_cache
from pathlib import Path

from arknights_mower import __rootdir__
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_ui_path,
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
    relative = "pages/basement_skill/skill.json"
    path = resource_ui_path(relative, source=True)
    if path is None:
        path = Path(__rootdir__).parent / "ui" / "src" / relative
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


@register_resource_reload
def clear_dorm_skill_cache():
    global resource_generation
    _skill_index.cache_clear()
    is_single_recovery_manager.cache_clear()
    is_group_recovery_manager.cache_clear()
    resource_generation += 1
