"""Generate shared building-skill data and its legacy resource-package entry."""

import json
from pathlib import Path

from arknights_mower.utils.res_version import (
    BUILDING_SKILL_DATA,
    BUILDING_SKILL_PACKAGE_PATH,
)


def write_building_skill_data(operators, root=Path(".")):
    """Serialize once; export identical bytes for the existing resource publisher."""
    content = json.dumps(operators, ensure_ascii=False, indent=2)
    for relative in (BUILDING_SKILL_DATA, BUILDING_SKILL_PACKAGE_PATH):
        target = Path(root) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
