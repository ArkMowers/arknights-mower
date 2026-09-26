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

_SINGLE_RECOVERY = "进驻宿舍时，使该宿舍内除自身以外心情未满的某个干员每小时恢复"
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
    return any(
        _SINGLE_RECOVERY in _TAGS.sub("", skill.get("des", ""))
        for skill in _skill_index().get(name, [])
    )


@register_resource_reload
def clear_dorm_skill_cache():
    global resource_generation
    _skill_index.cache_clear()
    is_single_recovery_manager.cache_clear()
    resource_generation += 1
