"""Read-only RIIC knowledge and owned-operator primary staffing trials."""

import html
import json
import re
from functools import wraps
from pathlib import Path

from arknights_mower import __rootdir__
from arknights_mower.utils import config
from arknights_mower.utils.building_skills import (
    _operator_skills,
    load_skill_snapshot,
    skill_index,
    term_index,
)

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


def _json_tool(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            payload = function(*args, **kwargs)
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


@_json_tool
def get_riic_context(roster_overrides=None):
    """Read saved roster, configured primary facilities and curated combination candidates."""
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
    return {
        "has_data": snapshot["has_data"],
        "message": snapshot["message"],
        "base_conditions": snapshot.get("base_conditions", {}),
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
    catalog = term_index()
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
        "operators": entries,
        "terms": terms,
        "missing_terms": missing,
        "provenance": knowledge["provenance"],
        "catalog_operator_count": len(skill_index()),
    }


@_json_tool
def try_riic_plan(assignments, roster_overrides=None):
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
        "description": "按实际拥有干员尝试排班前必读：共享BOX练度、主表设施工位和既有基建组合。只读，不同步森空岛。",
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
        "description": "查询基建机制和至多12名干员当前已解锁技能、明确成员与嵌套术语；缺失资料不假定最高技能。",
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
        "description": "试排并检查主班草案。只覆盖指定设施，检查所有保留设施的冲突。通过仅证明主班拥有、练度、工位和占岗检查；不保存或执行，不证明收益或轮换可行。",
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
            },
            "required": ["assignments"],
        },
    },
}
