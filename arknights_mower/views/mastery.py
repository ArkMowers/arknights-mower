import json
from functools import wraps

from flask import Blueprint, abort, current_app, request
from flask.views import MethodView

from arknights_mower.utils.mastery_db import (
    add_plan_checked,
    delete_plan,
    get_all_history,
    get_all_plans,
    get_all_routes,
    get_failed_plans,
    get_route_settings,
    save_route,
    save_route_settings,
    update_plan_priority,
)
from arknights_mower.utils.mastery_recommendation import get_skill_data


class Routes:
    PLAN = "/mastery-plan"
    PLAN_ORDER = "/mastery-plan/order"
    ROUTE = "/mastery-route"
    ROUTE_SETTINGS = "/mastery-route/settings"
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


def _purge_plan_tasks(plan_id):
    """#97：删除计划后清理队列残留任务（SKILL_UPGRADE/SWAP 按 plan_key 派发到已删计划）。

    #101：补位不再用独立 fill-{id} 键（空位与半程换人共用 plan_key=计划ID），只需清
    plan_key=计划ID。in-place 改列表（不重绑引用，避免与主循环
    `self.tasks[0]`/`del self.tasks[0]` 竞争）；**跳过当前派发任务**——主循环 dispatch
    完按 `del self.tasks[0]` 删除它，若把它移走，del 会误删下一个排队任务（review 修复）。
    base_scheduler 未运行（None）或 tasks 不可迭代时防御按无任务处理。
    """
    try:
        from arknights_mower.__main__ import base_scheduler
    except ImportError:
        return
    tasks = getattr(base_scheduler, "tasks", None)
    if not isinstance(tasks, list):
        return
    current = getattr(base_scheduler, "task", None)
    keys = {str(plan_id)}
    tasks[:] = [
        t for t in tasks if t is current or getattr(t, "plan_key", None) not in keys
    ]


class MasteryPlanView(MethodView):
    decorators = [_require_token]

    def get(self):
        # #69 展示：failed 计划也返回给前端（带 failed_reason），否则计划"凭空消失"。
        # 执行循环（reconcile）经 get_reconcile_plans 也会读 failed（#98 按截图恢复）。
        plans = get_all_plans() + get_failed_plans()
        history = get_all_history()
        char_table = get_skill_data().get("characters", {})
        plans_list = []
        for p in plans:
            char_info = char_table.get(p["char_id"], {})
            plans_list.append(
                {
                    "id": p["id"],
                    "char_id": p["char_id"],
                    "name": p.get("char_name") or char_info.get("name", p["char_id"]),
                    "skill_index": p["skill_index"],
                    "skill_name": p.get("skill_name", f"技能{p['skill_index'] + 1}"),
                    "target_level": p["target_level"],
                    "status": p["status"],
                    "priority": p["priority"],
                    "expires_at": p.get("expires_at"),
                    "failed_reason": p.get("failed_reason"),
                }
            )
        history_list = []
        for h in history:
            char_info = char_table.get(h["char_id"], {})
            history_list.append(
                {
                    "char_id": h["char_id"],
                    "name": h.get("char_name") or char_info.get("name", h["char_id"]),
                    "skill_index": h["skill_index"],
                    "skill_name": h.get("skill_name", f"技能{h['skill_index'] + 1}"),
                    "target_level": h["target_level"],
                    "status": h["status"],
                    "failed_reason": h.get("failed_reason"),
                    "time": h.get("created_at", ""),
                }
            )
        return {"plans": plans_list, "history": history_list}

    def post(self):
        data = request.json or {}
        char_table = get_skill_data().get("characters", {})
        name_to_id = {
            info.get("name", ""): cid
            for cid, info in char_table.items()
            if info.get("name")
        }

        results = []
        items = (
            data.get("items", [])
            if isinstance(data, dict) and "items" in data
            else None
        )

        if items is not None:
            for item in items:
                name = item.get("name", "")
                skill_index = item.get("skill_index", 0)
                target_level = item.get("target_level")
                char_id = name_to_id.get(name)
                if char_id is None:
                    results.append(
                        {"key": name, "status": "error", "reason": "operator not found"}
                    )
                    continue
                char_info = char_table.get(char_id, {})
                skills = char_info.get("skills", [])
                skill_name = (
                    skills[skill_index].get("name", f"技能{skill_index + 1}")
                    if len(skills) > skill_index
                    else f"技能{skill_index + 1}"
                )
                plan_id, reason = add_plan_checked(
                    char_id=char_id,
                    skill_index=skill_index,
                    target_level=target_level,
                    skill_name=skill_name,
                    char_name=name,
                )
                if plan_id > 0:
                    results.append({"key": name, "status": "added", "id": plan_id})
                else:
                    results.append({"key": name, "status": "error", "reason": reason})
        else:
            for name, skill_index in data.items():
                char_id = name_to_id.get(name)
                if char_id is None:
                    results.append(
                        {"key": name, "status": "error", "reason": "operator not found"}
                    )
                    continue
                # #112：bool 是 int 子类（True in (0,1,2) 为真），显式拒绝，否则
                # JSON true 会被静默当成二技能建错计划
                if (
                    isinstance(skill_index, bool)
                    or not isinstance(skill_index, int)
                    or skill_index not in (0, 1, 2)
                ):
                    results.append(
                        {
                            "key": name,
                            "status": "error",
                            "reason": "invalid skill_index",
                        }
                    )
                    continue
                char_info = char_table.get(char_id, {})
                skills = char_info.get("skills", [])
                skill_name = (
                    skills[skill_index].get("name", f"技能{skill_index + 1}")
                    if len(skills) > skill_index
                    else f"技能{skill_index + 1}"
                )
                plan_id, reason = add_plan_checked(
                    char_id=char_id,
                    skill_index=skill_index,
                    skill_name=skill_name,
                    char_name=name,
                )
                if plan_id > 0:
                    results.append({"key": name, "status": "added", "id": plan_id})
                else:
                    results.append({"key": name, "status": "error", "reason": reason})
        return {"results": results}

    def delete(self):
        data = request.json or {}
        plan_id = data.get("id")
        if not plan_id:
            return {"error": "id is required"}, 400
        # #113：非数字 id（如 "abc"）直接 int() → ValueError → 500；bool 是 int 子类
        # （True==1）也不得静默接受。对齐 #97 retry 畸形 id 400 的校验。
        if isinstance(plan_id, bool) or not isinstance(plan_id, int):
            return {"error": f"invalid id: {plan_id}"}, 400
        if delete_plan(plan_id):
            # #97：删计划清残留队列任务（该 plan_key 的 SKILL_UPGRADE/SWAP/fill），
            # 否则残留任务仍会按 plan_key 派发到已删计划。
            _purge_plan_tasks(plan_id)
            return {"status": "ok"}
        return {"error": "delete failed"}, 500


class MasteryPlanOrderView(MethodView):
    decorators = [_require_token]

    def patch(self):
        data = request.json or []
        for item in data:
            plan_id = item.get("id")
            priority = item.get("priority")
            if plan_id is not None and priority is not None:
                # #113：int() 对非数字（"abc"）抛 ValueError → 500，id/priority 同型；
                # bool 是 int 子类也不得静默接受。对齐 #97 retry 畸形 id 400 的校验。
                if isinstance(plan_id, bool) or not isinstance(plan_id, int):
                    return {"error": f"invalid id: {plan_id}"}, 400
                if isinstance(priority, bool) or not isinstance(priority, int):
                    return {"error": f"invalid priority: {priority}"}, 400
                update_plan_priority(plan_id, priority)
        return {"status": "ok"}


class MasteryRouteView(MethodView):
    decorators = [_require_token]

    def get(self):
        from arknights_mower.solvers.mastery import DEFAULT_ROUTES

        routes = get_all_routes()
        return {
            "routes": routes,
            "defaults": DEFAULT_ROUTES,
            "settings": get_route_settings(),
        }

    def post(self):
        data = request.json or {}
        profession = data.get("profession", "")
        supports = data.get("supports", "[]")
        if not profession:
            return {"error": "profession is required"}, 400
        save_route(
            profession,
            supports
            if isinstance(supports, str)
            else json.dumps(supports, ensure_ascii=False),
            is_default=0,
            optimal=bool(data.get("optimal", False)),
            half_off=bool(data.get("half_off", True)),
        )
        return {"status": "ok"}


class MasteryRouteSettingsView(MethodView):
    decorators = [_require_token]

    def post(self):
        data = request.json or {}
        save_route_settings(
            central_bonus=int(data.get("central_bonus", 0)),
            mastery_swap_buffer=int(data.get("mastery_swap_buffer", 10)),
        )
        return {"status": "ok"}


class MasteryHistoryView(MethodView):
    decorators = [_require_token]

    def get(self):
        history = get_all_history()
        return {"history": history}


mastery_bp.add_url_rule(Routes.PLAN, view_func=MasteryPlanView.as_view("mastery_plan"))
mastery_bp.add_url_rule(
    Routes.PLAN_ORDER, view_func=MasteryPlanOrderView.as_view("mastery_plan_order")
)
mastery_bp.add_url_rule(
    Routes.ROUTE, view_func=MasteryRouteView.as_view("mastery_route")
)
mastery_bp.add_url_rule(
    Routes.ROUTE_SETTINGS,
    view_func=MasteryRouteSettingsView.as_view("mastery_route_settings"),
)
mastery_bp.add_url_rule(
    Routes.HISTORY, view_func=MasteryHistoryView.as_view("mastery_history")
)
