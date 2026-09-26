"""Check scheduled operators against a confirmed Skland roster."""

import json

from arknights_mower.utils.path import get_path
from arknights_mower.utils.workshop_data import parse_roster

CACHE_ERROR = "森空岛干员数据缓存无效，请重新同步干员数据后验证排班"
RESOURCE_ERROR = "当前资源缺少排班干员的森空岛 ID，请更新资源包后验证排班"


def _read_roster(path):
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    data = payload.get("data") if isinstance(payload, dict) else None
    # The inventory scanner creates an items-only file before Skland is bound.
    if (
        isinstance(data, dict)
        and payload.get("code", 0) == 0
        and "characters" not in data
        and isinstance(data.get("items"), list)
    ):
        return None
    return parse_roster(payload)


def _operator_ids_by_name():
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    resources = get_skill_data()
    if not isinstance(resources, dict):
        raise ValueError("invalid operator resources")
    name_to_ids: dict[str, set[str]] = {}
    for section in ("characters", "training", "workshop"):
        entries = resources.get(section, {})
        if not isinstance(entries, dict):
            raise ValueError("invalid operator resources")
        if section != "characters":
            if entries and entries.get("version") != 1:
                raise ValueError("unsupported operator resources")
            entries = entries.get("operators", {})
        if not isinstance(entries, dict):
            raise ValueError("invalid operator resources")
        for char_id, info in entries.items():
            if not isinstance(char_id, str) or not isinstance(info, dict):
                raise ValueError("invalid operator resources")
            name = info.get("name")
            if name is not None and not isinstance(name, str):
                raise ValueError("invalid operator resources")
            if name:
                name_to_ids.setdefault(name, set()).add(char_id)
    return name_to_ids


def _refresh_roster():
    """Confirm a cache miss against Skland when an account is configured."""
    from arknights_mower.utils import config
    from arknights_mower.utils.log import logger

    if not getattr(config.conf, "skland_info", None):
        return False
    try:
        from arknights_mower.solvers.cultivate_depot import cultivate

        return cultivate().start()
    except Exception as exc:
        logger.warning(f"森空岛干员名单同步失败，跳过持有预检：{exc}")
        return False


def validate_owned_operators(global_plan) -> str | None:
    """Block only operators still absent after a successful Skland sync."""
    path = get_path("@app/tmp/cultivate.json")
    if not path.exists():
        return None

    try:
        characters = _read_roster(path)
    except (OSError, ValueError):
        return CACHE_ERROR
    if characters is None:
        return None

    scheduled = global_plan["default_plan"].scheduled_names()
    for plan in global_plan["backup_plans"]:
        scheduled.update(plan.scheduled_names(include_tasks=True))

    try:
        name_to_ids = _operator_ids_by_name()
    except (OSError, ValueError, TypeError):
        return RESOURCE_ERROR
    unknown = sorted(scheduled - name_to_ids.keys())
    if unknown:
        return f"{RESOURCE_ERROR}：{'、'.join(unknown)}"

    def missing_from(roster):
        owned_ids = {char["id"] for char in roster}
        return sorted(
            name for name in scheduled if name_to_ids[name].isdisjoint(owned_ids)
        )

    missing = missing_from(characters)
    if not missing:
        return None
    if not _refresh_roster():
        return None
    try:
        characters = _read_roster(path)
    except (OSError, ValueError):
        return CACHE_ERROR
    if characters is None:
        return None
    missing = missing_from(characters)
    if missing:
        return f"森空岛中未持有以下排班干员：{'、'.join(missing)}"
    return None
