import json
import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, request
from flask.views import MethodView

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
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
from arknights_mower.utils.path import get_path


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
    # #147：删计划同步清持久化队列——saved_state 快照里旧队列没清，重启 load_state
    # 会把已删计划的任务复活（plan_key 派发到已删计划 + blocked 通知重发）。这里把
    # 清完的当前状态重新落库覆盖旧快照；持久化失败不阻塞删除（活队列已清）。
    # #147 边界：被删计划的任务此刻正被派发（t is current 保留在 live 队列，主循环
    # 执行完才 del tasks[0]）时，快照仍含它 → 重启复活。live 队列不能动（del tasks[0]
    # 靠 current 占位），只在持久化快照里剔除。
    try:
        from arknights_mower.solvers.record import current_state, save_state_to_db

        state = current_state()
        if state is not None:
            state["tasks"] = [
                t for t in state["tasks"] if getattr(t, "plan_key", None) not in keys
            ]
            save_state_to_db(state)
    except Exception as e:
        logger.debug(f"删除计划后持久化队列同步失败（忽略）: {e}")


def _refresh_cultivate_if_stale(force=False):
    """cultivate.json 缺失/过期（> maa_gap）时刷新（森空岛，纯网络，web 线程安全）。

    #141：立即派发依赖 cultivate.json 新鲜度做材料核算——数据过期/缺失时
    `auto_schedule_mastery_tasks` 返回空、静默空转（只加计划、不开始训练）。这里在
    派发前刷新，**尊重 maa_gap 间隔**（新鲜则跳过，不绕过间隔打森空岛）；缺 skland
    配置时 cultivate.start 内部直接返回（材料数据缺，计划等下次自然扫描兜底）。
    #141 review 跟进：`force=True` 用于「新干员不在本地数据」——用户显式点了该干员
    一键专精，强制拉一次让推荐数据包含它（不受 maa_gap 新鲜度跳过）。
    """
    try:
        path = get_path("@app/tmp/cultivate.json")
        if not force and os.path.exists(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if datetime.now() - mtime < timedelta(hours=config.conf.maa_gap):
                return
        from arknights_mower.solvers.cultivate_depot import cultivate

        cultivate().start()
    except Exception as e:
        logger.exception(f"一键专精刷新 cultivate.json 失败: {e}")


def _chars_missing_from_cultivate(char_ids) -> set:
    """char_ids 中不在 cultivate.json `data.characters` 里的（#141 review 跟进：
    新干员未录入本地数据——cultivate.json 新鲜但干员是刚获得的）。只在确实缺失时返回
    非空（在数据里的干员，含被推荐过滤的非精二，不算缺失——避免无谓拉取）。
    """
    try:
        path = get_path("@app/tmp/cultivate.json")
        if not os.path.exists(path):
            return set(char_ids)
        with open(path, "r", encoding="utf-8") as f:
            cdata = json.load(f)
        have = {c.get("id") for c in cdata.get("data", {}).get("characters", [])}
        return {cid for cid in char_ids if cid not in have}
    except Exception:
        return set(char_ids)


def _dispatch_new_plans_immediately(chars=None):
    """一键专精建计划后立即尝试开始——刷新库存数据后复用仓库扫描的派发逻辑。

    #141（用户拍板方案 A）：建计划成功后**刷新 cultivate.json**（缺失/过期才拉，
    尊重 maa_gap）→ auto_schedule 用新鲜数据核算材料 → `_dispatch_scan_start_tasks`
    把材料足够的 idle 计划入队 now 的 SKILL_UPGRADE（plan_key=计划ID），并设
    `wake_scheduler` 事件唤醒调度休眠——调度器下一轮就执行，**确认后真的开始训练**。
    #141 review 跟进：`chars` = 本次新增计划的干员 id——若某干员不在本地 cultivate
    数据（新获得、cultivate.json 还新鲜），强制拉一次让推荐数据包含它再重算，否则
    新干员一键仍会静默空转。材料不足不派发（继续等下次扫描）；受 enable_mastery 门控
    （OFF 停专精自动化）；base_scheduler 未运行（None）时防御按无任务处理。
    """
    if not config.conf.enable_mastery:
        return
    try:
        from arknights_mower.__main__ import base_scheduler
    except ImportError:
        return
    if base_scheduler is None or not hasattr(
        base_scheduler, "_dispatch_scan_start_tasks"
    ):
        return
    try:
        from arknights_mower.utils.mastery_recommendation import (
            auto_schedule_mastery_tasks,
        )

        _refresh_cultivate_if_stale()
        res = auto_schedule_mastery_tasks()
        if chars and _chars_missing_from_cultivate(chars):
            # 新干员不在本地数据 → 强制拉一次再重算（用户显式点了一键专精）
            _refresh_cultivate_if_stale(force=True)
            res = auto_schedule_mastery_tasks()
        base_scheduler._dispatch_scan_start_tasks(res.get("scheduled", []))
        if res.get("scheduled"):
            config.wake_scheduler.set()
    except Exception as e:
        logger.exception(f"一键专精立即派发失败: {e}")


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
        added = False
        added_char_ids = []
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
                    added = True
                    added_char_ids.append(char_id)
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
                    added = True
                    added_char_ids.append(char_id)
                else:
                    results.append({"key": name, "status": "error", "reason": reason})
        if added:
            _dispatch_new_plans_immediately(chars=added_char_ids)
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
        # #114：写入端校验 supports 是合法 JSON 且形态是数组/包装对象/旧字典之一，
        # 不合法拒绝保存（读取端 json.loads 无守卫，#91 review 决策——坏数据不得进库，
        # 否则该职业全无路线 operator/减半）。
        from arknights_mower.solvers.mastery import validate_route_supports

        supports_str = (
            supports
            if isinstance(supports, str)
            else json.dumps(supports, ensure_ascii=False)
        )
        err = validate_route_supports(supports_str)
        if err:
            return {"error": err}, 400
        save_route(
            profession,
            supports_str,
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
