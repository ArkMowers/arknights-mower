"""Check scheduled ownership and training eligibility against a Skland roster."""

import json

from arknights_mower.utils.mastery_support_types import IGNORED_NAMES
from arknights_mower.utils.path import get_path
from arknights_mower.utils.workshop_data import parse_roster

CACHE_ERROR = "森空岛干员数据缓存无效，请前往「养成规划」页面手动点击「刷新」后验证排班"
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
    """Refresh ownership and skill data when a Skland account is configured."""
    from arknights_mower.utils import config
    from arknights_mower.utils.log import logger

    if not getattr(config.conf, "skland_info", None):
        return False
    try:
        from arknights_mower.solvers.cultivate_depot import cultivate

        return cultivate().start()
    except Exception as exc:
        logger.warning(f"森空岛干员名单同步失败，使用已有缓存校验训练位：{exc}")
        return False


def _training_requirement_error(char):
    level = char.get("mainSkillLevel")
    if type(level) is not int or not 1 <= level <= 7:
        return (
            "无法确认基础技能等级，请前往「养成规划」页面手动点击「刷新」，"
            "同步干员数据后重新验证排班"
        )
    if level < 7:
        return (
            f"基础技能仅 {level} 级，须达到 7 级才能进驻训练位；升至 7 级后，"
            "请前往「养成规划」页面手动点击「刷新」后重新验证排班"
        )
    skills = char.get("skills")
    if (
        not isinstance(skills, list)
        or not skills
        or any(
            not isinstance(skill, dict)
            or type(skill.get("level")) is not int
            or not 0 <= skill["level"] <= 3
            for skill in skills
        )
    ):
        return (
            "无法确认技能专精等级，请前往「养成规划」页面手动点击「刷新」，"
            "同步干员数据后重新验证排班"
        )
    if all(skill["level"] == 3 for skill in skills):
        return (
            "所有技能均已专三，无法进驻训练位；更换干员后，"
            "请前往「养成规划」页面手动点击「刷新」后重新验证排班"
        )
    return None


def _training_slot_errors(global_plan, characters, name_to_ids):
    owned = {char["id"]: char for char in characters}
    errors = []
    plans = [global_plan["default_plan"], *global_plan["backup_plans"]]
    for index, plan in enumerate(plans):
        source = "主表" if index == 0 else f"副表“{plan.name or index}”"
        slots = plan.plan.get("train", [])
        names = set()
        if len(slots) > 1:
            names.update((slots[1].agent, *slots[1].all_replacements))
        if index > 0:
            task = (plan.task or {}).get("train", [])
            if len(task) > 1:
                names.add(task[1])
        for name in sorted(names - IGNORED_NAMES):
            candidates = [
                owned[cid] for cid in sorted(name_to_ids[name]) if cid in owned
            ]
            # Missing operators remain subject to the ownership refresh policy.
            reasons = [_training_requirement_error(char) for char in candidates]
            if reasons and all(reasons):
                errors.append(
                    f"{source}训练位 {name}：{'；'.join(dict.fromkeys(reasons))}"
                )
    return errors


def validate_owned_operators(global_plan) -> str | None:
    """Check ownership and named training assignments, refreshing at most once."""
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
    training_errors = _training_slot_errors(global_plan, characters, name_to_ids)
    if not missing and not training_errors:
        return None
    if _refresh_roster():
        try:
            characters = _read_roster(path)
        except (OSError, ValueError):
            return CACHE_ERROR
        if characters is None:
            return None
        missing = missing_from(characters)
        if missing:
            return (
                f"森空岛中未持有以下排班干员：{'、'.join(missing)}；获取干员后，"
                "请前往「养成规划」页面手动点击「刷新」后重新验证排班"
            )
        training_errors = _training_slot_errors(global_plan, characters, name_to_ids)
    if training_errors:
        return "训练位干员不满足进驻条件：" + "；".join(training_errors)
    return None
