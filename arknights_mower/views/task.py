"""`/task` 新增任务 HTTP 契约（#71 一键专精流接入 DB 计划架构）。

前端一键专精（MasteryRecommendation.vue）与手动对话框（TaskDialog.vue）已改走
`POST /mastery-plan`（DB 计划状态机，dispatch 只认 DB 计划）。原始「技能专精」/task
（旧流不带 operator/skill，提交即死路）被**明确拒绝并指引计划 API**，不再静默接受。
`mower_thread` 由 server.py 运行时注入（判定「mower 正在运行」），本模块保持可独立测试。
"""

import json
from datetime import datetime
from functools import wraps

import pytz
from flask import Blueprint, abort, current_app, request
from tzlocal import get_localzone

from arknights_mower.utils.log import logger
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

task_bp = Blueprint("task", __name__)

# server.py 注入：当前 mower 线程（None = 未运行）。路由用它判定「mower 正在运行」。
mower_thread = None


def set_mower_thread(thread):
    global mower_thread
    mower_thread = thread


def _require_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = getattr(current_app, "token", None)
        if token and request.headers.get("token", "") != token:
            abort(403)
        return f(*args, **kwargs)

    return wrapper


@task_bp.route("/task", methods=["GET", "POST"])
@_require_token
def add_task():
    from arknights_mower.__main__ import base_scheduler

    if request.method == "POST":
        try:
            req = request.json
            task = req["task"]
            logger.debug(f"收到新增任务请求：{req}")
            if base_scheduler and mower_thread and mower_thread.is_alive():
                if task:
                    utc_time = datetime.strptime(task["time"], "%Y-%m-%dT%H:%M:%S.%f%z")
                    task_time = (
                        utc_time.replace(tzinfo=pytz.utc)
                        .astimezone(get_localzone())
                        .replace(tzinfo=None)
                    )
                    new_task = SchedulerTask(
                        time=task_time,
                        task_plan=task["plan"],
                        task_type=task["task_type"],
                        meta_data=task["meta_data"],
                    )
                    if base_scheduler.find_next_task(
                        compare_time=task_time, compare_type="="
                    ):
                        raise Exception("找到同时间任务请勿重复添加")
                    if new_task.type == TaskTypes.SKILL_UPGRADE:
                        # #71：专精训练由 DB 计划状态机驱动（POST /mastery-plan），
                        # dispatch 只认 DB 计划；原始「技能专精」/task 不带 operator/
                        # skill，提交即死路。明确拒绝并指引计划 API。
                        raise Exception(
                            "专精任务请通过专精计划接口创建（POST /mastery-plan），"
                            "系统会自动调度训练"
                        )
                    base_scheduler.tasks.append(new_task)
                    logger.debug(f"成功：{str(new_task)}")
                    return "添加任务成功！"
            raise Exception("添加任务失败！！请确保Mower正在运行")
        except Exception as e:
            logger.exception(f"添加任务失败：{str(e)}")
            return str(e)
    else:
        if base_scheduler and mower_thread and mower_thread.is_alive():
            from jsonpickle import encode

            return [
                json.loads(encode(i, unpicklable=False)) for i in base_scheduler.tasks
            ]
        else:
            return []
