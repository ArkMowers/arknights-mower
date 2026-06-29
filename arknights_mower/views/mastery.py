import json
from enum import Enum
from functools import wraps

from flask import Blueprint, abort, current_app, request
from flask.views import MethodView

from arknights_mower.utils.mastery_db import (
    get_all_history,
    get_all_plans,
    get_all_routes,
    get_current_plan,
    get_history,
    has_train_group_plan,
    insert_plan,
    save_route,
)
from arknights_mower.utils.mastery_recommendation import get_skill_data


class PlanStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Routes(str, Enum):
    PLAN = "/mastery-plan"
    ROUTE = "/mastery-route"
    HISTORY = "/mastery-history"


mastery_bp = Blueprint("mastery", __name__)


def _require_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = getattr(current_app, "token", None)
        if token and request.headers.get("token", "") != token:
            abort(403)
        return f(*args, **kwargs)

    return wrapper


class MasteryPlanView(MethodView):
    decorators = [_require_token]

    def get(self):
        plans = get_all_plans()
        history = get_all_history()
        char_table = get_skill_data().get("characters", {})
        plans_dict = {}
        for p in plans:
            key = f"{p['char_id']}_{p['skill_index']}"
            char_info = char_table.get(p["char_id"], {})
            plans_dict[key] = {
                "status": p["status"],
                "skill_name": p.get("skill_name", f"技能{p['skill_index'] + 1}"),
                "name": char_info.get("name", p["char_id"]),
            }
        history_list = []
        for h in history:
            char_info = char_table.get(h["char_id"], {})
            history_list.append(
                {
                    "char_id": h["char_id"],
                    "skill_index": h["skill_index"],
                    "status": h["status"],
                    "failed_reason": h.get("failed_reason"),
                    "level": h.get("level", 1),
                    "skill_name": h.get("skill_name", f"技能{h['skill_index'] + 1}"),
                    "name": char_info.get("name", h["char_id"]),
                    "time": h.get("created_at", ""),
                }
            )
        return {"plans": plans_dict, "history": history_list}

    def post(self):
        if has_train_group_plan():
            return {
                "results": [],
                "error": "训练室已设置小组轮换，请先清理后再添加专精计划",
            }
        data = request.json or {}
        char_table = get_skill_data().get("characters", {})
        name_to_id = {}
        for cid, info in char_table.items():
            n = info.get("name", "")
            if n:
                name_to_id[n] = cid
        results = []
        for name, skill_index in data.items():
            char_id = name_to_id.get(name)
            if char_id is None:
                results.append(
                    {
                        "key": name,
                        "status": "error",
                        "reason": "operator name not found",
                    }
                )
                continue
            if not isinstance(skill_index, int) or skill_index not in (0, 1, 2):
                results.append(
                    {
                        "key": name,
                        "status": "error",
                        "reason": "invalid skill_index, must be 0/1/2",
                    }
                )
                continue
            char_info = char_table.get(char_id, {})
            skill_name = (
                char_info.get("skills", [{}])[skill_index].get(
                    "name", f"技能{skill_index + 1}"
                )
                if len(char_info.get("skills", [])) > skill_index
                else f"技能{skill_index + 1}"
            )
            existing = get_current_plan(char_id, skill_index)
            if existing is None:
                insert_plan(
                    char_id, skill_index, PlanStatus.PENDING, skill_name=skill_name
                )
                results.append(
                    {
                        "key": name,
                        "status": "added",
                        "name": name,
                        "skill": skill_name,
                    }
                )
            elif existing["status"] == PlanStatus.COMPLETED:
                results.append(
                    {
                        "key": name,
                        "status": "already_completed",
                        "name": name,
                        "skill": skill_name,
                    }
                )
            elif existing["status"] == PlanStatus.FAILED:
                insert_plan(
                    char_id,
                    skill_index,
                    PlanStatus.PENDING,
                    skill_name=skill_name,
                )
                results.append(
                    {
                        "key": name,
                        "status": "retry",
                        "name": name,
                        "skill": skill_name,
                    }
                )
            elif existing["status"] in (
                PlanStatus.PENDING,
                PlanStatus.IN_PROGRESS,
            ):
                results.append(
                    {
                        "key": name,
                        "status": "already_planned",
                        "name": name,
                        "skill": skill_name,
                    }
                )
            else:
                results.append(
                    {
                        "key": name,
                        "status": "error",
                        "reason": f"unknown status {existing['status']}",
                    }
                )
        return {"results": results}


class MasteryRouteView(MethodView):
    decorators = [_require_token]

    def get(self):
        try:
            from arknights_mower.utils.mastery_recommendation import (
                _load_default_route,
            )

            defaults = _load_default_route()
            routes = get_all_routes()
            saved_profs = {r["profession"] for r in routes}
            for prof, data in defaults.items():
                if prof.startswith("_"):
                    continue
                if prof not in saved_profs:
                    routes.append(
                        {
                            "profession": prof,
                            "supports": json.dumps(
                                data.get("supports", []),
                                ensure_ascii=False,
                            ),
                            "is_default": 1,
                        }
                    )
            default_routes = []
            for prof, data in defaults.items():
                if prof.startswith("_"):
                    continue
                default_routes.append(
                    {
                        "profession": prof,
                        "supports": json.dumps(
                            data.get("supports", []),
                            ensure_ascii=False,
                        ),
                    }
                )
            return {
                "routes": routes,
                "backups": defaults.get("_backups", {}),
                "defaults": default_routes,
            }
        except Exception:
            return {"routes": [], "backups": {}}

    def post(self):
        data = request.json or {}
        profession = data.get("profession", "")
        supports = data.get("supports", "[]")
        if not profession:
            return {"error": "profession is required"}, 400
        save_route(
            profession,
            supports if isinstance(supports, str) else json.dumps(supports),
            is_default=0,
        )
        return {"status": "ok"}


class MasteryHistoryView(MethodView):
    decorators = [_require_token]

    def get(self):
        char_id = request.args.get("char_id", "")
        skill_index = request.args.get("skill_index", 0, type=int)
        history = get_history(char_id, skill_index)
        return {"history": history}


mastery_bp.add_url_rule(Routes.PLAN, view_func=MasteryPlanView.as_view("mastery_plan"))
mastery_bp.add_url_rule(
    Routes.ROUTE, view_func=MasteryRouteView.as_view("mastery_route")
)
mastery_bp.add_url_rule(
    Routes.HISTORY, view_func=MasteryHistoryView.as_view("mastery_history")
)
