"""Generate shared building-skill data and its legacy resource-package entry."""

import json
from pathlib import Path

from arknights_mower.utils.res_version import (
    BUILDING_SKILL_DATA,
    BUILDING_SKILL_PACKAGE_PATH,
)

BUILDING_ROOM_NAMES = {
    "POWER": "发电站",
    "DORMITORY": "宿舍",
    "MANUFACTURE": "制造站",
    "MEETING": "会客室",
    "WORKSHOP": "加工站",
    "TRADING": "贸易站",
    "HIRE": "人力办公室",
    "TRAINING": "训练室",
    "CONTROL": "中枢",
    "RECYCLE": "回收站",
}


def selection_sort_fields(buff):
    fields = {}
    if type(buff.get("sortId")) is int:
        fields["sortId"] = buff["sortId"]
    if buff["roomType"] in ("MANUFACTURE", "TRADING"):
        for field in ("targets", "efficiency"):
            if field in buff:
                fields[field] = buff[field]
    return fields


def write_building_skill_data(operators, root=Path(".")):
    """Serialize once; export identical bytes for the existing resource publisher."""
    content = json.dumps(operators, ensure_ascii=False, indent=2)
    for relative in (BUILDING_SKILL_DATA, BUILDING_SKILL_PACKAGE_PATH):
        target = Path(root) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
