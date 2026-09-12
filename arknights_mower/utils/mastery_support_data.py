"""Roster, schedule exclusions and unlocked training skills."""

import json
from functools import lru_cache

from .mastery_support_types import (
    BASE_HOURS,
    CONTROL_TRAINERS,
    IGNORED_NAMES,
    RosterUnavailableError,
    SupportPlanError,
    TrainingInputs,
)


def schedule_context(plan=None):
    if plan is None:
        from arknights_mower.utils import config

        plan = config.plan
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump(exclude_none=True)
    base = plan.get(plan.get("default", "plan1"), {})
    blocked = {}
    central_names = set()
    for table in [base, *(p.get("plan", {}) for p in plan.get("backup_plans", []))]:
        for room, facility in table.items():
            if room == "train" or not facility:
                continue
            for slot in facility.get("plans", []):
                for name in [slot.get("agent", ""), *slot.get("replacement", [])]:
                    if name not in IGNORED_NAMES:
                        blocked.setdefault(name, set()).add(room)
                        if room == "central":
                            central_names.add(name)
    central = 5 if CONTROL_TRAINERS.intersection(central_names) else 0
    return blocked, central


def check_schedule_name(name, blocked):
    if name in blocked:
        raise SupportPlanError(
            f"{name} 出现在非训练室排班（{'、'.join(sorted(blocked[name]))}），不能作为专精协助者"
        )


def training_room_group_error(plan=None):
    """Protect training-room groups declared in primary and backup schedules."""
    if plan is None:
        from arknights_mower.utils import config

        plan = config.plan
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump(exclude_none=True)
    base = plan.get(plan.get("default", "plan1"), {})
    tables = [("主排班", base)] + [
        (f"备用排班「{p.get('name', '未命名')}」", p.get("plan", {}))
        for p in plan.get("backup_plans", [])
    ]
    conflicts = []
    for label, table in tables:
        for slot in (table.get("train") or {}).get("plans", []):
            name, group = slot.get("agent", ""), slot.get("group", "").strip()
            if name not in IGNORED_NAMES and group:
                conflicts.append(f"{label}：{name}（组名：{group}）")
    if conflicts:
        return (
            f"训练室排班含绑组干员：{'；'.join(conflicts)}。"
            "已阻止自动专精换人，请先解除训练室干员绑组后重试"
        )
    return None


@lru_cache(maxsize=2)
def _read_roster(path, mtime, size):
    with open(path, encoding="utf-8") as f:
        content = json.load(f)
    payload = content.get("data") if isinstance(content, dict) else None
    roster = payload.get("characters") if isinstance(payload, dict) else None
    if not isinstance(roster, list) or not roster:
        raise ValueError("Missing BOX characters")
    return roster


def owned_roster():
    from arknights_mower.utils.path import get_path

    path = get_path("@app/tmp/cultivate.json")
    try:
        stat = path.stat()
        return _read_roster(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        raise RosterUnavailableError(
            "请先从森空岛同步干员练度，再生成专精协助方案"
        ) from None


def training_data():
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    data = get_skill_data().get("training", {})
    if data.get("version") != 1:
        raise SupportPlanError("当前资源缺少训练技能规则，请更新资源包")
    return data["operators"]


def unlocked(meta, owned):
    elite, level = owned.get("evolvePhase", 0), owned.get("level", 1)
    effects = []
    for group in meta.get("groups", []):
        valid = [v for v in group if (elite, level) >= (v["elite"], v["level"])]
        if valid:
            effects.extend(
                max(valid, key=lambda v: (v["elite"], v["level"]))["effects"]
            )
    return effects


def trainer_stats(meta, owned, target, stage):
    speed, halves = 0, False
    for rule in unlocked(meta, owned):
        kind = rule["kind"]
        matches = (
            not rule.get("professions") or target["profession"] in rule["professions"]
        )
        stage_match = not rule.get("stage") or rule["stage"] == stage
        branch_match = not rule.get("branch") or rule["branch"] == target.get(
            "subProfessionId"
        )
        if kind == "speed" and matches:
            speed += rule["bonus"]
            if stage_match and branch_match:
                speed += rule.get("extra", 0)
        elif kind == "halve":
            halves = True
    return {
        "name": meta["name"],
        "efficiency": speed,
        "halves": halves,
    }


def rate(efficiency, central=0):
    return 1.05 + (efficiency + central) / 100


def candidates(char_id, inputs=None, include_dynamic=False):
    inputs = resolve_inputs(inputs)
    metadata, roster = inputs.metadata, inputs.roster
    blocked, central = inputs.schedule
    target = metadata.get(char_id)
    if not target:
        raise SupportPlanError("资源中没有此干员的训练资料")
    owned = {c["id"]: c for c in roster}
    if char_id not in owned or owned[char_id].get("evolvePhase", 0) < 2:
        raise SupportPlanError("被专精干员未拥有或未精二，请同步干员练度")
    result = {}
    for cid, char in owned.items():
        meta = metadata.get(cid)
        if not meta or cid == char_id or meta["name"] in blocked:
            continue
        # Martial Arts can instantly consume a stored charge and invalidates duration estimates.
        excluded_kinds = set() if include_dynamic else {"unsupported", "environment"}
        if any(r["kind"] in excluded_kinds for r in unlocked(meta, char)):
            continue
        result[meta["name"]] = {
            level: trainer_stats(meta, char, target, level) for level in BASE_HOURS
        }
    return result, central


def resolve_inputs(inputs=None):
    inputs = inputs or TrainingInputs()
    roster = owned_roster() if inputs.roster is None else inputs.roster
    metadata = training_data() if inputs.metadata is None else inputs.metadata
    schedule = schedule_context() if inputs.schedule is None else inputs.schedule
    return TrainingInputs(roster, metadata, schedule, inputs.buffer)
