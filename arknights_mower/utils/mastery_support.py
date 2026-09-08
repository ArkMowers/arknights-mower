"""Per-plan mastery assistants. Pure route search; no screenshots or network calls."""

import json
import math
from functools import lru_cache

BASE_HOURS = {1: 8, 2: 16, 3: 24}
REDUCERS = ("逻各斯", "艾丽妮")
CONTROL_TRAINERS = frozenset(("阿斯卡纶", "烛煌", "斩业星熊"))
IGNORED_NAMES = frozenset(("", "Free", "Current"))


class SupportPlanError(ValueError):
    pass


def schedule_context(plan=None, active=None):
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
    if active is None:
        active_names = {
            room: [s.get("agent", "") for s in f.get("plans", [])]
            for room, f in base.items()
            if f
        }
    else:
        active_names = {
            room: [s.agent for s in slots] for room, slots in active.items()
        }
    central = 5 if CONTROL_TRAINERS.intersection(central_names) else 0
    return blocked, central, active_names


def check_schedule_name(name, blocked):
    if name in blocked:
        raise SupportPlanError(
            f"{name} 出现在非训练室排班（{'、'.join(sorted(blocked[name]))}），不能作为专精协助者"
        )


@lru_cache(maxsize=2)
def _read_roster(path, mtime, size):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("data", {}).get("characters", [])


def owned_roster():
    from arknights_mower.utils.path import get_path

    path = get_path("@app/tmp/cultivate.json")
    try:
        stat = path.stat()
        return _read_roster(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        raise SupportPlanError("请先从森空岛同步干员练度，再生成专精协助方案") from None


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


def trainer_stats(meta, owned, target, stage, environment):
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
        elif kind == "environment":
            speed += min(environment.get(rule["group"], 0), rule["cap"]) * rule["bonus"]
    return {
        "name": meta["name"],
        "efficiency": speed,
        "halves": halves,
    }


def rate(efficiency, central=0):
    return 1.05 + (efficiency + central) / 100


def candidates(
    char_id, roster=None, metadata=None, context=None, include_dynamic=False
):
    metadata = metadata if metadata is not None else training_data()
    roster = roster if roster is not None else owned_roster()
    blocked, central, rooms = context if context is not None else schedule_context()
    target = metadata.get(char_id)
    if not target:
        raise SupportPlanError("资源中没有此干员的训练资料")
    owned = {c["id"]: c for c in roster}
    if char_id not in owned or owned[char_id].get("evolvePhase", 0) < 2:
        raise SupportPlanError("被专精干员未拥有或未精二，请同步干员练度")
    env = {}  # dynamic/resource-conversion bonuses are deliberately not assumed
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
            level: trainer_stats(meta, char, target, level, env) for level in BASE_HOURS
        }
    return result, central


def stage_route(first, reducer, level, work, central, buffer, *, manual=False):
    speed = rate(first["efficiency"], central)
    duration, switch_after = work / speed, None
    if reducer and reducer["name"] != first["name"]:
        tail = (300 + max(1, buffer)) / 60
        remaining_work = work - tail * rate(reducer["efficiency"], central)
        if not manual and (
            remaining_work <= 0 or first["efficiency"] <= reducer["efficiency"]
        ):
            return None
        switch_after = max(0, math.floor(remaining_work / speed * 3600) / 3600)
        duration = switch_after + (work - switch_after * speed) / rate(
            reducer["efficiency"], central
        )
    route = {
        "operator": first["name"],
        "efficiency": first["efficiency"],
        "level": level,
        "swap_target": reducer["name"]
        if reducer and switch_after is not None
        else None,
        "swap_efficiency": reducer["efficiency"] if reducer else 0,
        "central_bonus": central,
        "mastery_swap_buffer": max(1, buffer),
        "hours": duration,
        "switch_after": switch_after,
    }
    return route


def plan_supports(
    char_id, current, target, *, roster=None, metadata=None, context=None, buffer=10
):
    options, central = candidates(char_id, roster, metadata, context)
    return optimize_supports(options, current, target, central, buffer)


def optimize_supports(options, current, target, central, buffer=10):
    if not options:
        raise SupportPlanError("没有可用的协助干员（非训练室排班中的干员已排除）")
    # A route has <=3 stages. Keep best paths per carried reducer and end trainer.
    paths = {(None, None): (0, 0, [])}
    for level in range(current + 1, target + 1):
        best = {}
        stats = [levels[level] for levels in options.values()]
        fastest = max(t["efficiency"] for t in stats)
        useful = [t for t in stats if t["halves"] or t["efficiency"] == fastest]
        # Equal-speed interchangeable operators need only a deterministic representative,
        # plus carried trainers (for switch-count ties) and all reducers.
        ordinary = sorted(
            (t for t in useful if not t["halves"]),
            key=lambda t: t["name"],
        )
        useful = [t for t in useful if t["halves"]] + ordinary[:1]
        reducers = [t for t in useful if t["halves"]] if level < target else []
        for (carry, previous), (elapsed, switches, routes) in paths.items():
            for use_half in (bool(carry),):
                work = BASE_HOURS[level] * (0.5 if use_half else 1)
                for first in useful:
                    for reducer in [None, *reducers]:
                        route = stage_route(
                            first, reducer, level, work, central, buffer
                        )
                        if route is None:
                            continue
                        last = reducer if route["swap_target"] else first
                        last_hours = route["hours"] - (route["switch_after"] or 0)
                        next_carry = (
                            last["name"]
                            if (
                                level < target
                                and last["halves"]
                                and last_hours >= (300 + max(1, buffer)) / 60
                            )
                            else None
                        )
                        route.update(
                            activate_with=carry if use_half else None,
                            half_inherited=use_half,
                            next_carry=next_carry,
                            manual=False,
                        )
                        order = ([carry] if use_half else []) + [first["name"]]
                        if route["swap_target"]:
                            order.append(last["name"])
                        changes, prev = 0, previous
                        for name in order:
                            changes += int(prev is not None and name != prev)
                            prev = name
                        key = (next_carry, last["name"])
                        value = (
                            elapsed + route["hours"],
                            switches + changes,
                            routes + [route],
                        )
                        if key not in best or value[:2] < best[key][:2]:
                            best[key] = value
        paths = best
    elapsed, switches, routes = min(paths.values(), key=lambda v: v[:2])
    return {
        "version": 1,
        "stages": routes,
        "hours": elapsed,
        "switches": switches,
        "central_bonus": central,
        "current": current,
        "target": target,
    }


def profession_training_routes(
    professions, *, roster=None, metadata=None, context=None, buffer=10
):
    """Owned, unlocked trainers for profession-wide defaults; no branch assumptions.

    These are recommendations, not restrictions on the editor's manual dropdowns.
    Compute only when the route settings endpoint is requested.
    """
    roster = owned_roster() if roster is None else roster
    metadata = training_data() if metadata is None else metadata
    blocked, central, _ = schedule_context() if context is None else context
    eligible = []
    for char in roster:
        meta = metadata.get(char["id"])
        if not meta or meta["name"] in blocked:
            continue
        effects = unlocked(meta, char)
        if not any(r["kind"] in {"speed", "halve"} for r in effects):
            continue  # A control-room bonus alone is not a training skill.
        if any(r["kind"] in {"environment", "unsupported"} for r in effects):
            continue
        eligible.append((meta, char))

    defaults = {}
    for profession, label in professions.items():
        target = {"profession": profession}  # Branch-specific extras never match.
        options = {
            meta["name"]: {
                level: trainer_stats(meta, char, target, level, {})
                for level in BASE_HOURS
            }
            for meta, char in eligible
        }
        if not options:
            defaults[label] = {"supports": [], "half_off": False}
            continue
        plan = optimize_supports(options, 0, 3, central, buffer)
        defaults[label] = {
            "supports": [
                {
                    "name": stage["operator"],
                    "skill_level": stage["level"],
                    "efficiency": stage["efficiency"],
                    "swap": bool(stage["swap_target"]),
                    "swap_name": stage["swap_target"] or "",
                    "match": stage["swap_efficiency"] > 0,
                }
                for stage in plan["stages"]
            ],
            "half_off": any(stage["half_inherited"] for stage in plan["stages"]),
        }
    return {"defaults": defaults}


def profession_reference_trainers(routes, professions, *, roster, metadata):
    """Display the original default trainers independently of personal availability.

    A missing roster/rule is unknown, not evidence that an operator is unowned or
    locked. Unlock status refers to the displayed bonus, including skill upgrades.
    """
    owned = None if roster is None else {c["id"]: c for c in roster}
    by_name = {m["name"]: (cid, m) for cid, m in metadata.items()}
    result = {}
    for profession, label in professions.items():
        result[label] = {}
        for level in BASE_HOURS:
            entry = routes.get(label, {}).get(f"level_{level}")
            if not entry:
                continue
            name, efficiency = entry["operator"], entry["efficiency"]
            cid, meta = by_name.get(name, (None, None))
            has_operator = cid in owned if owned is not None and cid else None
            has_skill = None
            if has_operator and meta:
                stats = trainer_stats(
                    meta, owned[cid], {"profession": profession}, level, {}
                )
                has_skill = stats["efficiency"] >= efficiency
            result[label][level] = {
                "name": name,
                "efficiency": efficiency,
                "owned": has_operator,
                "unlocked": has_skill,
            }
    return result


def decode_supports(plan):
    return decode_json(plan.get("support_plan"))


def decode_json(value):
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            raise SupportPlanError("协助方案数据损坏，请重新添加计划") from None
    return value


def editable_after(plan):
    if plan.get("status") in ("idle", "failed"):
        return 0
    runtime = decode_json(plan.get("support_runtime")) or {}
    return runtime.get("level", plan["target_level"])


def stage_for(plan, level):
    value = decode_supports(plan)
    stage = next(
        (dict(s) for s in (value or {}).get("stages", []) if s["level"] == level), None
    )
    runtime = decode_json(plan.get("support_runtime"))
    if stage and runtime and runtime.get("level") == level:
        stage.update(runtime)
    return stage


def edit_supports(plan, edits):
    """Manual choices need identity/roster/schedule checks, not a speed eligibility test."""
    saved = decode_supports(plan)
    if not saved:
        raise SupportPlanError("此计划尚无自动协助方案，请重新添加计划")
    if not isinstance(edits, list) or len(edits) != len(saved["stages"]):
        raise SupportPlanError("请提交全部专精阶段的协助者")
    blocked, central, rooms = schedule_context()
    metadata = training_data()
    target = metadata.get(plan["char_id"], {})
    owned = {c["id"]: c for c in owned_roster()}
    names = {m["name"]: (m, owned[cid]) for cid, m in metadata.items() if cid in owned}
    environment = {}
    stages = []
    for stage, edit in zip(saved["stages"], edits):
        if not isinstance(edit, dict) or edit.get("level") != stage["level"]:
            raise SupportPlanError("专精阶段不匹配")
        if stage["level"] <= editable_after(plan):
            if any(edit.get(f) != stage.get(f) for f in ("operator", "swap_target")):
                raise SupportPlanError("已开始的专精阶段不能修改协助者")
            stages.append(dict(stage))
            continue
        changed = any(edit.get(f) != stage.get(f) for f in ("operator", "swap_target"))
        stage = dict(stage)
        for field in ("operator", "swap_target"):
            name = edit.get(field)
            if name is None and field == "swap_target":
                stage[field] = None
                continue
            if (
                not isinstance(name, str)
                or name not in names
                or name == target.get("name")
            ):
                raise SupportPlanError("协助者必须是已拥有的其他干员")
            check_schedule_name(name, blocked)
            stage[field] = name
            meta, char = names[name]
            stats = trainer_stats(meta, char, target, stage["level"], environment)
            prefix = "swap_" if field == "swap_target" else ""
            stage[prefix + "efficiency"] = stats["efficiency"]
            if field == "swap_target" and not stats["halves"]:
                # An ordinary manual assistant is allowed, but never promises a halving.
                stage["swap_halves"] = False
            elif field == "swap_target":
                stage["swap_halves"] = True
        if stage["level"] == saved["target"]:
            stage["swap_target"] = None
        stage.update(
            manual=stage.get("manual", False) or changed,
            central_bonus=central,
            activate_with=None,
            half_inherited=False,
            next_carry=None,
        )
        # Edited chains have no guaranteed carry. Runtime uses the observed countdown.
        stage["hours"] = BASE_HOURS[stage["level"]] / rate(stage["efficiency"], central)
        stage["switch_after"] = None
        stages.append(stage)
    return {
        **saved,
        "stages": stages,
        "hours": sum(s["hours"] for s in stages),
        "central_bonus": central,
    }
