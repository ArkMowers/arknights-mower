"""Read-only RIIC context, knowledge and detached scheduling-plan validation."""

import copy
import html
import json
import re
from functools import wraps
from pathlib import Path

from pydantic import ValidationError

from arknights_mower import __rootdir__
from arknights_mower.agent.tools.riic_sources import riic_code_locations
from arknights_mower.agent.tools.riic_tutorial import read_riic_tutorial
from arknights_mower.utils import config
from arknights_mower.utils.building_skills import (
    _operator_skills,
    load_income_cache,
    load_skill_snapshot,
    skill_index,
    term_index,
)
from arknights_mower.utils.config.plan import (
    Facility,
    GroupBinding,
    Plan1,
    PlanConf,
    PlanModel,
    Plans,
    parse_plan_document,
)
from arknights_mower.utils.config.plan_advanced import (
    ADVANCED_SETTING_KEYS,
    apply_advanced_settings,
    export_advanced_settings,
)
from arknights_mower.utils.emergency_plan import INHERITED_WORK_ROOMS
from arknights_mower.utils.manufacture_product import (
    MANUFACTURE_PRODUCTS,
    TRADE_PRODUCTS,
)
from arknights_mower.utils.operators import Operators, build_global_plan

DATA_ROOT = Path(__rootdir__) / "data" / "riic"
FIXED_FACILITIES = {
    "central": "中枢",
    "meeting": "会客室",
    "factory": "加工站",
    "contact": "人力办公室",
    "train": "训练室",
    "recycle": "回收站",
    **{f"dormitory_{i}": "宿舍" for i in range(1, 5)},
}
FACILITY_CAPACITY = {
    "中枢": 5,
    "会客室": 2,
    "加工站": 1,
    "人力办公室": 1,
    "训练室": 2,
    "宿舍": 5,
    "制造站": 3,
    "贸易站": 3,
    "发电站": 1,
    "回收站": 2,
}
UNCHECKED = [
    "当前心情、耗尽速度与休息床位",
    "替班匹配及副表条件",
    "跨设施联动和产品条件",
    "实际设施等级及电力",
    "无人机、订单质量、跑单及长期收益",
]
COMPLETE_UNCHECKED = [
    "当前心情、实测恢复速度与实际设施建设状态",
    "设施等级与岗位对应关系、电力和布局建设可行性",
    "副表条件、专项任务保护及实时预约",
    "跨设施收益、无人机、跑单、材料持续供应和长期轮换收益",
]
OPERATOR_CONF_FIELDS = {
    "exhaust_require",
    "rest_in_full",
    "resting_priority",
    "resting_priority_replacement",
    "free_room_exclusions",
    "resting_standby",
    "free_blacklist",
    "workaholic",
    "refresh_trading",
    "refresh_drained",
    "ope_resting_priority",
}


class PlanDocumentError(ValueError):
    """Expose bounded adapter diagnostics without submitted values or model context."""

    def __init__(self, message, *, details=None):
        super().__init__(message[:240])
        self.details = details


def _json_tool(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            payload = function(*args, **kwargs)
        except PlanDocumentError as error:
            payload = {"error": {"code": "invalid_arguments", "message": str(error)}}
            if error.details is not None:
                payload["error"]["details"] = error.details
        except (ValueError, TypeError, KeyError):
            payload = {
                "error": {
                    "code": "invalid_arguments",
                    "message": "请检查正式代号、参数类型和数量上限",
                }
            }
        except OSError:
            payload = {
                "error": {
                    "code": "resource_unavailable",
                    "message": "本地基建资料不可用，请检查资源包",
                }
            }
        rendered = json.dumps(payload, ensure_ascii=False)
        if len(rendered) > 200_000:
            return json.dumps(
                {"error": {"code": "result_too_large", "message": "请缩小查询范围"}},
                ensure_ascii=False,
            )
        return rendered

    return invoke


def _read_data(name):
    return json.loads((DATA_ROOT / f"{name}.json").read_text("utf-8"))


def _text(value):
    return html.unescape(re.sub(r"<[^>]*>", "", value))


def _names(value, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("name count")
    if any(not isinstance(n, str) or not n.strip() or len(n) > 64 for n in value):
        raise ValueError("formal names")
    return value


def _roster(overrides):
    snapshot = load_skill_snapshot()
    operators = {a["name"]: dict(a, source="box") for a in snapshot["operators"]}
    if overrides is None:
        overrides = []
    if not isinstance(overrides, list) or len(overrides) > 64:
        raise ValueError("override count")
    seen = set()
    for entry in overrides:
        if not isinstance(entry, dict) or set(entry) - {
            "name",
            "owned",
            "phase",
            "level",
        }:
            raise ValueError("override fields")
        name = _names([entry["name"]], 1)[0]
        if (
            name in seen
            or name not in skill_index()
            or type(entry["owned"]) is not bool
        ):
            raise ValueError("override identity")
        seen.add(name)
        phase, level = entry.get("phase"), entry.get("level")
        if (phase is None) != (level is None):
            raise ValueError("incomplete growth")
        if phase is not None and (
            type(phase) is not int
            or phase not in (0, 1, 2)
            or type(level) is not int
            or not 1 <= level <= 90
        ):
            raise ValueError("growth range")
        operators[name] = {
            "name": name,
            "owned": entry["owned"],
            "phase": phase,
            "level": level,
            "source": "user",
        }
    return snapshot, operators


def _operator(name, roster):
    catalog = skill_index().get(name)
    operator = roster.get(
        name,
        {
            "name": name,
            "owned": None,
            "phase": None,
            "level": None,
            "source": "unknown",
        },
    )
    phase, level = operator.get("phase"), operator.get("level")
    progress = None
    if (
        operator["owned"] is True
        and type(phase) is int
        and phase in (0, 1, 2)
        and type(level) is int
        and 1 <= level <= 90
    ):
        progress = (phase, level)
    statuses = _operator_skills(name, progress)
    active = {
        (s["skill_key"], s["skill_level"]) for s in statuses if s["status"] == "active"
    }
    skills = [
        dict(s, des=_text(s.get("des", "")))
        for s in catalog or ()
        if (s["skill_key"], s["skill_level"]) in active
    ]
    versions = [
        {
            "skillname": skill["skillname"],
            "roomType": skill["roomType"],
            "requirement": skill["phase_level"],
            "description": _text(skill.get("des", "")),
            "status": status["status"],
            "terms": re.findall(r"<\$([^>]+)>", skill.get("des", "")),
        }
        for skill, status in zip(catalog or (), statuses)
    ]
    return {
        "name": name,
        "known": catalog is not None,
        "owned": operator["owned"],
        "phase": phase,
        "level": level,
        "growth_known": progress is not None,
        "source": operator["source"],
        "active_skills": skills,
        "skills": versions,
    }


def _plan():
    plan = getattr(config, "plan", None)
    return plan.plan1.model_dump(exclude_none=True) if plan is not None else {}


def _facility(room, facility):
    return FIXED_FACILITIES.get(room, facility.get("name", ""))


def _references(plan, *, inherit_blank_work_slots=False):
    """Read staffing and task references without exposing backup expressions."""
    names = set()
    for primary in [plan.plan1, *(entry.plan for entry in plan.backup_plans)]:
        for room, facility in primary.model_dump(exclude_none=True).items():
            for slot in facility["plans"]:
                if (
                    inherit_blank_work_slots
                    and room in INHERITED_WORK_ROOMS
                    and not slot["agent"]
                ):
                    continue
                names.add(slot["agent"])
                for binding in [slot, *slot.get("group_bindings", [])]:
                    names.update(binding.get("replacement", []))
    for conf in [plan.conf, *(entry.conf for entry in plan.backup_plans)]:
        for field in OPERATOR_CONF_FIELDS:
            names.update(getattr(conf, field).split(","))
        names.update(conf.operator_mood_limits)
    for backup in plan.backup_plans:
        for row in backup.task.model_dump(exclude_none=True).values():
            names.update(row)
    return names - {"", "Free", "Current"}


def _main_snapshot(plan):
    document = plan.model_dump(exclude_none=True)
    document.pop("backup_groups", None)
    document["backup_plans"] = []
    document["advanced_settings"] = export_advanced_settings(config.conf)
    return document


@_json_tool
def get_riic_context(roster_overrides=None):
    """Read cached resources, safe main-plan fields and curated combinations."""
    snapshot, roster = _roster(roster_overrides)
    if len(roster) > 1024:
        raise ValueError("roster size")
    combinations = []
    for group in _read_data("combinations"):
        members = list(
            dict.fromkeys(group["core"] + group["support"] + group["accessory"])
        )
        item = dict(group)
        for key, ownership in (("owned", True), ("missing", False), ("unknown", None)):
            item[key] = [
                name
                for name in members
                if roster.get(name, {}).get("owned") is ownership
            ]
        item["core_owned"] = all(
            roster.get(n, {}).get("owned") is True for n in group["core"]
        )
        combinations.append(item)
    plan = _plan()
    cached = load_income_cache()
    saved = getattr(config, "plan", None)
    if saved is None:
        errors, warnings = [{"code": "plan_unavailable"}], []
    else:
        primary = saved.model_copy(deep=True)
        primary.backup_plans = []
        errors, warnings = _check_complete_staffing(primary, roster)
    return {
        "has_data": snapshot["has_data"],
        "message": snapshot["message"],
        "base_conditions": snapshot.get("base_conditions", {}),
        "has_inventory": cached["has_inventory"],
        "inventory": cached["inventory"],
        "observed_at": cached["observed_at"],
        "observation_scope": "本地缓存库存观察时间；练度和设施不代表实时游戏状态",
        "normal_plan": _main_snapshot(saved) if saved is not None else None,
        "normal_plan_issues": {
            "scope": "main_staffing_static_only",
            "errors": errors,
            "warnings": warnings,
            "native_checked": False,
            "income_checked": False,
        },
        "normal_backup_count": len(saved.backup_plans) if saved is not None else 0,
        "normal_reserved_names": sorted(_references(saved))
        if saved is not None
        else [],
        "facility_levels": dict(saved.facility_levels) if saved is not None else {},
        "owned_operators": [
            {k: a.get(k) for k in ("name", "phase", "level", "source")}
            for a in roster.values()
            if a["owned"] is True
        ],
        "facilities": [
            {
                "room": room,
                "facility": _facility(room, f),
                "capacity": len(f["plans"]),
                "product": f.get("product"),
                "level": saved.facility_levels.get(room) if saved is not None else None,
                "plans": f["plans"],
            }
            for room, f in plan.items()
        ],
        "combinations": combinations,
        "catalog_operator_count": len(skill_index()),
        "provenance": _read_data("knowledge")["provenance"],
        "unchecked": UNCHECKED,
    }


@_json_tool
def get_riic_knowledge(operators=None, topic="overview", roster_overrides=None):
    """Read one mechanics topic and current unlocked skills with nested terms."""
    names = _names([] if operators is None else operators, 12)
    knowledge = _read_data("knowledge")
    if not isinstance(topic, str) or topic not in knowledge["topics"]:
        raise ValueError("unknown topic")
    _, roster = _roster(roster_overrides)
    entries = [_operator(name, roster) for name in names]
    # Expand references before removing game rich-text tags.
    pending = []
    for name in names:
        pending.extend(
            re.findall(
                r"<\$([^>]+)>",
                " ".join(s.get("des", "") for s in skill_index().get(name, ())),
            )
        )
    terms, missing, seen = [], [], set()
    catalog = term_index() if pending else {}
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        if len(seen) >= 150:
            raise ValueError("term reference count")
        seen.add(key)
        term = catalog.get(key)
        if term is None:
            missing.append(key)
            continue
        pending.extend(re.findall(r"<\$([^>]+)>", term["description"]))
        terms.append(
            {
                "id": key,
                "name": term["termName"],
                "description": _text(term["description"]),
            }
        )
    return {
        "topic": topic,
        "guide": knowledge["topics"][topic],
        **({"tutorial": read_riic_tutorial()} if topic == "mower_tutorial" else {}),
        **(
            {"code_locations": riic_code_locations()}
            if topic == "code_diagnosis"
            else {}
        ),
        "operators": entries,
        "terms": terms,
        "missing_terms": missing,
        "provenance": knowledge["provenance"],
        "catalog_operator_count": len(skill_index()),
    }


def _try_assignments(assignments, roster_overrides=None):
    """Validate a detached primary staffing draft; never save or execute it."""
    if not isinstance(assignments, list) or len(assignments) > 24:
        raise ValueError("assignment count")
    _, roster = _roster(roster_overrides)
    draft = _plan()
    errors, warnings, rooms = [], [], set()
    for assignment in assignments:
        if not isinstance(assignment, dict) or set(assignment) != {"room", "operators"}:
            raise ValueError("assignment fields")
        room = assignment["room"]
        if not isinstance(room, str) or len(room) > 32:
            raise ValueError("room identity")
        names = _names(assignment["operators"], 5)
        if room in rooms:
            errors.append({"code": "duplicate_room", "room": room})
            continue
        rooms.add(room)
        if room not in draft:
            errors.append({"code": "unknown_room", "room": room})
            continue
        capacity = len(draft[room]["plans"])
        if len(names) > capacity:
            errors.append(
                {"code": "capacity_exceeded", "room": room, "capacity": capacity}
            )
            continue
        if len(names) < capacity:
            warnings.append(
                {"code": "unfilled_slots", "room": room, "count": capacity - len(names)}
            )
        draft[room]["plans"] = [
            {"agent": name, "group": "", "replacement": []} for name in names
        ]
    if not draft:
        errors.append(
            {"code": "plan_unavailable", "message": "请先配置实际基建设施和工位"}
        )
    seen = {}
    for room, facility in draft.items():
        kind = _facility(room, facility)
        if kind not in FACILITY_CAPACITY:
            errors.append({"code": "unsupported_facility", "room": room})
        elif len(facility["plans"]) > FACILITY_CAPACITY[kind]:
            errors.append(
                {
                    "code": "capacity_exceeded",
                    "room": room,
                    "capacity": FACILITY_CAPACITY[kind],
                }
            )
        for slot in facility["plans"]:
            name = slot["agent"]
            if name == "Free" and kind == "宿舍":
                continue
            if name in seen:
                errors.append(
                    {
                        "code": "duplicate_operator",
                        "operator": name,
                        "room": room,
                        "other_room": seen[name],
                    }
                )
            seen[name] = room
            operator = _operator(name, roster)
            if not operator["known"]:
                code = "unknown_operator"
            elif operator["owned"] is False:
                code = "unowned_operator"
            elif operator["owned"] is not True:
                code = "ownership_unknown"
            elif not operator["growth_known"]:
                code = "growth_unknown"
            else:
                code = None
            if code:
                errors.append({"code": code, "room": room, "operator": name})
                continue
            active = [s for s in operator["active_skills"] if s["roomType"] == kind]
            if not active:
                matching = [s for s in skill_index()[name] if s["roomType"] == kind]
                target = errors if matching else warnings
                target.append(
                    {
                        "code": "skill_not_unlocked"
                        if matching
                        else "no_facility_skill",
                        "room": room,
                        "operator": name,
                    }
                )
    return {
        "valid": not errors,
        "saved": False,
        "scope": "primary_staffing_only",
        "draft": draft,
        "errors": errors,
        "warnings": warnings,
        "unchecked": UNCHECKED,
    }


def _strict_document(document):
    if not isinstance(document, dict):
        raise PlanDocumentError("plan 必须是包含 plan1 的完整 Mower 文档对象")
    if len(json.dumps(document, ensure_ascii=False)) > 65536:
        raise PlanDocumentError("plan 文档超过 65536 字符上限，请缩小草案")
    if set(document) - {
        "default",
        "plan1",
        "conf",
        "facility_levels",
        "advanced_settings",
        "backup_plans",
    }:
        raise PlanDocumentError(
            "plan 含不支持的字段；只允许 default、plan1、conf、facility_levels、advanced_settings 和空 backup_plans"
        )
    if document.get("backup_plans", []) != []:
        raise PlanDocumentError("plan.backup_plans 必须为空；本工具只检查单一主表")
    if document.get("default", "plan1") != "plan1":
        raise PlanDocumentError("plan.default 只支持 plan1")
    primary = document.get("plan1")
    if not isinstance(primary, dict):
        raise PlanDocumentError("plan.plan1 必须是按房间名组织的设施对象")
    if set(primary) - Plan1.model_fields.keys():
        raise PlanDocumentError(
            "plan.plan1 含未知字段，只能填写设施；conf 应放在 plan.conf，其他设置应放在 plan 对应的顶层字段"
        )
    for room, facility in primary.items():
        if room.startswith("gaming_") or not isinstance(facility, dict):
            raise PlanDocumentError(
                f"plan.plan1.{room} 必须是受支持的普通基建设施对象；不支持活动室"
            )
        if set(facility) - Facility.model_fields.keys():
            raise PlanDocumentError(
                f"plan.plan1.{room} 含未知字段；设施只允许 name、plans 和 product"
            )
        slots = facility.get("plans")
        if not isinstance(slots, list) or len(slots) > 5:
            raise PlanDocumentError(
                f"plan.plan1.{room}.plans 必须是至多 5 个工位的列表"
            )
        for index, slot in enumerate(slots):
            path = f"plan.plan1.{room}.plans[{index}]"
            if not isinstance(slot, dict) or set(slot) - Plans.model_fields.keys():
                raise PlanDocumentError(
                    f"{path} 含未知字段或类型错误；工位只允许 agent、group、replacement 和 group_bindings"
                )
            agent = slot.get("agent")
            if not isinstance(agent, str) or len(agent) > 64:
                raise PlanDocumentError(f"{path}.agent 必须是至多 64 字符的干员代号")
            bindings = slot.get("group_bindings", [])
            if not isinstance(bindings, list) or len(bindings) > 16:
                raise PlanDocumentError(
                    f"{path}.group_bindings 必须是至多 16 条额外绑定的列表"
                )
            for binding_index, binding in enumerate([slot, *bindings]):
                binding_path = (
                    path
                    if binding_index == 0
                    else f"{path}.group_bindings[{binding_index - 1}]"
                )
                if not isinstance(binding, dict) or (
                    binding is not slot
                    and set(binding) - GroupBinding.model_fields.keys()
                ):
                    raise PlanDocumentError(
                        f"{binding_path} 含未知字段或类型错误；额外绑定只允许 group 和 replacement"
                    )
                group = binding.get("group", "")
                if not isinstance(group, str) or len(group) > 64:
                    raise PlanDocumentError(
                        f"{binding_path}.group 必须是至多 64 字符的组名"
                    )
                try:
                    _names(binding.get("replacement", []), 64)
                except (ValueError, TypeError):
                    raise PlanDocumentError(
                        f"{binding_path}.replacement 必须是至多 64 个非空干员代号的列表，每个代号至多 64 字符"
                    ) from None
    conf = document.get("conf", {})
    if not isinstance(conf, dict) or set(conf) - PlanConf.model_fields.keys():
        raise PlanDocumentError(
            "plan.conf 含未知字段或类型错误；请按工具声明填写主表设置"
        )
    for key, value in conf.items():
        if key in OPERATOR_CONF_FIELDS or key == "dorm_order":
            if not isinstance(value, str) or len(value) > 4096:
                raise PlanDocumentError(
                    f"plan.conf.{key} 必须是至多 4096 字符的逗号分隔字符串"
                )
    limits = conf.get("operator_mood_limits", {})
    if not isinstance(limits, dict) or len(limits) > 1024:
        raise PlanDocumentError(
            "plan.conf.operator_mood_limits 必须是至多 1024 名干员的心情范围对象"
        )
    try:
        _names(list(limits), 1024)
    except (ValueError, TypeError):
        raise PlanDocumentError(
            "plan.conf.operator_mood_limits 的键必须是至多 64 字符的非空干员代号"
        ) from None
    for limit in [conf.get("mood_limits"), *limits.values()]:
        if limit is not None and (
            not isinstance(limit, dict) or set(limit) - {"lower", "upper"}
        ):
            raise PlanDocumentError("plan.conf 的心情范围只允许 lower 和 upper 字段")
    advanced = document.get("advanced_settings")
    if advanced is not None and (
        not isinstance(advanced, dict) or set(advanced) - set(ADVANCED_SETTING_KEYS)
    ):
        raise PlanDocumentError(
            "plan.advanced_settings 含未知字段或类型错误；只允许工具声明中的排班高级设置"
        )
    try:
        return parse_plan_document(copy.deepcopy(document))
    except ValidationError as error:
        safe_fields = (
            set(PlanModel.model_fields)
            | set(Plan1.model_fields)
            | set(Facility.model_fields)
            | set(Plans.model_fields)
            | set(PlanConf.model_fields)
            | set(ADVANCED_SETTING_KEYS)
            | {"lower", "upper"}
        )
        details = [
            {
                "loc": [
                    "plan",
                    *[
                        part
                        if (isinstance(part, str) and part in safe_fields)
                        or (type(part) is int and 0 <= part <= 1024)
                        else "<key>"
                        for part in item["loc"][:8]
                    ],
                ],
                "type": item["type"][:64],
            }
            for item in error.errors(
                include_input=False, include_context=False, include_url=False
            )[:16]
        ]
        raise PlanDocumentError(
            "排班字段类型或数值无效，请按 details 中的 loc 和 type 修正",
            details=details,
        ) from None


def _check_operator(name, roster, errors, warnings, *, room=None, role=None, kind=None):
    operator = _operator(name, roster)
    code = (
        "unknown_operator"
        if not operator["known"]
        else "unowned_operator"
        if operator["owned"] is False
        else "ownership_unknown"
        if operator["owned"] is not True
        else "growth_unknown"
        if not operator["growth_known"]
        else None
    )
    detail = {"operator": name, "room": room, "role": role}
    if code:
        errors.append({"code": code, **detail})
    elif kind and not any(s["roomType"] == kind for s in operator["active_skills"]):
        locked = any(s["roomType"] == kind for s in skill_index()[name])
        (errors if locked else warnings).append(
            {
                "code": "skill_not_unlocked" if locked else "no_facility_skill",
                **detail,
            }
        )


def _check_complete_staffing(plan, roster, *, sparse=False):
    errors, warnings, seen, checked = [], [], {}, set()
    for room, facility in plan.plan1.model_dump(exclude_none=True).items():
        kind = _facility(room, facility)
        slots = facility["plans"]
        if kind not in FACILITY_CAPACITY and not (sparse and not kind):
            errors.append({"code": "unsupported_facility", "room": room})
        elif kind in FACILITY_CAPACITY and len(slots) > FACILITY_CAPACITY[kind]:
            errors.append({"code": "capacity_exceeded", "room": room})
        if room in FIXED_FACILITIES and facility.get("name") not in {"", kind}:
            errors.append(
                {
                    "code": "invalid_fixed_facility",
                    "room": room,
                    "expected": kind,
                    "actual": facility.get("name"),
                }
            )
        if (
            room.startswith("room_")
            and kind not in {"制造站", "贸易站", "发电站"}
            and not (sparse and not kind)
        ):
            errors.append({"code": "invalid_left_facility", "room": room})
        if kind in {"制造站", "贸易站"}:
            products = MANUFACTURE_PRODUCTS if kind == "制造站" else TRADE_PRODUCTS
            if facility.get("product") not in products and not (
                sparse and not facility.get("product")
            ):
                errors.append(
                    {
                        "code": "invalid_product",
                        "room": room,
                        "actual": facility.get("product"),
                        "allowed": list(products),
                    }
                )
        for slot in slots:
            name = slot["agent"]
            if name in {"Free", "Current"} or (sparse and not name):
                continue
            if name in seen:
                errors.append(
                    {
                        "code": "duplicate_operator",
                        "operator": name,
                        "room": room,
                        "other_room": seen[name],
                    }
                )
            seen[name] = room
            _check_operator(
                name, roster, errors, warnings, room=room, role="primary", kind=kind
            )
            checked.add(name)
            for binding in [slot, *slot.get("group_bindings", [])]:
                for replacement in binding.get("replacement", []):
                    if replacement in {"Free", "Current"}:
                        continue
                    _check_operator(
                        replacement,
                        roster,
                        errors,
                        warnings,
                        room=room,
                        role="fia_target" if name == "菲亚梅塔" else "replacement",
                        kind=None if name == "菲亚梅塔" else kind,
                    )
                    checked.add(replacement)
    for name in sorted(_references(plan, inherit_blank_work_slots=sparse) - checked):
        _check_operator(name, roster, errors, warnings, role="configuration")
    if not any(
        facility["plans"]
        for facility in plan.plan1.model_dump(exclude_none=True).values()
    ):
        errors.append({"code": "plan_unavailable"})
    return errors, warnings


def _native_operators(plan, conf):
    data = Operators(
        build_global_plan(plan_model=plan, conf_model=conf),
        runtime_conf=conf,
        facility_levels=plan.facility_levels,
    )
    if error := data.init_and_validate():
        raise ValueError(str(error))
    return data


@_json_tool
def try_riic_plan(assignments=None, roster_overrides=None, plan=None, mode="normal"):
    """Check one detached main plan or legacy primary assignments without execution."""
    if (assignments is None) == (plan is None) or mode not in {"normal", "rescue"}:
        raise ValueError("exclusive plan input")
    if assignments is not None:
        if mode != "normal":
            raise ValueError("rescue requires a plan snapshot")
        return _try_assignments(assignments, roster_overrides)
    schedule = _strict_document(plan)
    _, roster = _roster(roster_overrides)
    errors, warnings = _check_complete_staffing(
        schedule, roster, sparse=mode == "rescue"
    )
    conf = apply_advanced_settings(
        config.conf.model_copy(deep=True), schedule.advanced_settings
    )
    schedule.advanced_settings = export_advanced_settings(conf)
    result = {
        "valid": False,
        "saved": False,
        "status": "failed",
        "scope": "complete_main_plan" if mode == "normal" else "rescue_snapshot",
        "draft": schedule.plan1.model_dump(exclude_none=True),
        "plan": schedule.model_dump(exclude_none=True, exclude={"backup_groups"}),
        "errors": errors,
        "warnings": warnings,
        "native_checked": False,
        "unchecked": COMPLETE_UNCHECKED,
    }
    if errors:
        return result
    try:
        if mode == "normal":
            _native_operators(schedule, conf)
            result["native_checked"] = True
        else:
            from arknights_mower.utils.emergency_plan import (
                effective_rescue_plan,
                validate_rescue_schedule,
            )

            normal = getattr(config, "plan", None)
            if normal is None:
                raise ValueError("正常排班不可用")
            explicit = _references(schedule, inherit_blank_work_slots=True)
            overlap = sorted(explicit & _references(normal))
            if overlap:
                errors.append(
                    {"code": "normal_reference_overlap", "operators": overlap}
                )
                return result
            normal_conf = config.conf.model_copy(deep=True)
            data = _native_operators(normal, normal_conf)
            result["normal_native_checked"] = True
            resolved = validate_rescue_schedule(data, schedule)
            inherited_errors, inherited_warnings = _check_complete_staffing(
                resolved, roster, sparse=True
            )
            errors.extend(inherited_errors)
            warnings.extend(inherited_warnings)
            if errors:
                return result
            result["rescue_snapshot_checked"] = True
            if normal.backup_plans:
                result["status"] = "incomplete"
                warnings.append(
                    {
                        "code": "conditional_normal_plan",
                        "message": "正常排班含副表；需实测确定生效排班后再核验救急兼容性",
                    }
                )
                return result
            effective_rescue_plan(data, schedule)
            result["resolvedPlan"] = resolved.model_dump(
                exclude_none=True, exclude={"backup_groups"}
            )
    except (ValueError, TypeError) as error:
        errors.append({"code": "native_validation_failed", "message": str(error)})
        return result
    result.update(valid=True, status="passed")
    return result


OVERRIDES_SCHEMA = {
    "type": "array",
    "maxItems": 64,
    "description": "仅填写用户明确声明的拥有和练度，优先于BOX；本次调用生效，不保存。练度未知不填phase/level。",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "maxLength": 64},
            "owned": {"type": "boolean"},
            "phase": {"type": "integer", "minimum": 0, "maximum": 2},
            "level": {"type": "integer", "minimum": 1, "maximum": 90},
        },
        "required": ["name", "owned"],
        "additionalProperties": False,
    },
}

get_riic_context_tool_def = {
    "type": "function",
    "function": {
        "name": "get_riic_context",
        "description": "按实际拥有干员尝试排班前必读：本地BOX练度、库存观察时间、完整正常主表、显式设施等级、正常排班全部保留姓名和既有组合。只读，不同步森空岛。",
        "parameters": {
            "type": "object",
            "properties": {"roster_overrides": OVERRIDES_SCHEMA},
        },
    },
}
get_riic_knowledge_tool_def = {
    "type": "function",
    "function": {
        "name": "get_riic_knowledge",
        "description": "查询现有排班纠错与局部优化规则、一条龙教程，以及至多12名干员当前技能和未解锁技能的养成要求；缺失资料不假定最高技能，目标练度不视为实际练度。",
        "parameters": {
            "type": "object",
            "properties": {
                "operators": {
                    "type": "array",
                    "maxItems": 12,
                    "items": {"type": "string", "maxLength": 64},
                },
                "topic": {
                    "type": "string",
                    "enum": [
                        "overview",
                        "facilities",
                        "orders",
                        "links",
                        "simulation",
                        "coverage",
                        "taxonomy",
                        "mower_plan",
                        "new_operators",
                        "income_export",
                        "freshness",
                        "plan_review",
                        "mower_tutorial",
                        "code_diagnosis",
                    ],
                },
                "roster_overrides": OVERRIDES_SCHEMA,
            },
        },
    },
}
try_riic_plan_tool_def = {
    "type": "function",
    "function": {
        "name": "try_riic_plan",
        "description": "只读校验现有主表的修改建议，不从零生成排班。局部优化使用plan保留完整plan1/conf/facility_levels/advanced_settings及替班绑组；assignments只检查主班并清空被修改房间绑定，二者恰选一项。完整主表检查全部主班、替班、多绑及充能目标的拥有练度，并运行原生Operators校验；不接收副表，不能将返回主表当作删除原副表的完整替换文件。mode=rescue按保存正常排班编译继承，显式姓名不得与正常全引用重叠；正常含副表则incomplete。不保存、执行或演算，不证明电力、建设、长期轮换或收益。",
        "parameters": {
            "type": "object",
            "properties": {
                "assignments": {
                    "type": "array",
                    "maxItems": 24,
                    "items": {
                        "type": "object",
                        "properties": {
                            "room": {"type": "string", "maxLength": 32},
                            "operators": {
                                "type": "array",
                                "maxItems": 5,
                                "items": {"type": "string", "maxLength": 64},
                            },
                        },
                        "required": ["room", "operators"],
                        "additionalProperties": False,
                    },
                },
                "roster_overrides": OVERRIDES_SCHEMA,
                "plan": {},
                "mode": {"type": "string", "enum": ["normal", "rescue"]},
            },
            "additionalProperties": False,
        },
    },
}


def _plan_schema():
    """Publish the accepted main-plan fields from the existing configuration models."""
    source = PlanModel.model_json_schema()
    definitions = source["$defs"]

    def inline(value):
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return inline(definitions[value["$ref"].rsplit("/", 1)[1]])
        if "allOf" in value and len(value["allOf"]) == 1:
            return inline(value["allOf"][0])
        rendered = {
            key: inline(item)
            for key, item in value.items()
            if key not in {"$defs", "title", "default"}
        }
        if rendered.get("type") == "object" and "properties" in rendered:
            rendered["additionalProperties"] = False
        return rendered

    properties = source["properties"]
    plan = {
        "type": "object",
        "properties": {},
        "required": ["plan1"],
        "additionalProperties": False,
    }
    for key in ("plan1", "conf", "facility_levels"):
        plan["properties"][key] = inline(properties[key])
    plan["properties"]["default"] = {"type": "string", "enum": ["plan1"]}
    plan["properties"]["backup_plans"] = {"type": "array", "maxItems": 0, "items": {}}
    plan["properties"]["plan1"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            key: {"$ref": "#/$defs/RIICFacility"}
            for key in Plan1.model_fields
            if not key.startswith("gaming_")
        },
    }
    plan["$defs"] = {"RIICFacility": inline(source["$defs"]["Facility"])}
    plan["$defs"]["RIICFacility"]["properties"]["name"]["enum"] = [
        "",
        *FACILITY_CAPACITY,
    ]
    product = plan["$defs"]["RIICFacility"]["properties"]["product"]
    for variant in product["anyOf"]:
        if variant.get("type") == "string":
            variant["enum"] = ["", *MANUFACTURE_PRODUCTS, *TRADE_PRODUCTS]
    slots = plan["$defs"]["RIICFacility"]["properties"]["plans"]
    slots["maxItems"] = 5
    slot = slots["items"]["properties"]
    slot["agent"]["maxLength"] = 64
    slot["group_bindings"]["maxItems"] = 16
    for binding in [slot, slot["group_bindings"]["items"]["properties"]]:
        binding["group"]["maxLength"] = 64
        binding["replacement"]["maxItems"] = 64
        binding["replacement"]["items"]["maxLength"] = 64
    conf_schema = config.Conf.model_json_schema()
    definitions.update(conf_schema.get("$defs", {}))
    plan["properties"]["advanced_settings"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            key: inline(conf_schema["properties"][key]) for key in ADVANCED_SETTING_KEYS
        },
    }
    return plan


_schema = _plan_schema()
try_riic_plan_tool_def["function"]["parameters"]["$defs"] = _schema.pop("$defs")
try_riic_plan_tool_def["function"]["parameters"]["properties"]["plan"] = _schema
