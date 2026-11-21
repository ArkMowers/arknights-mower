"""只读投影任务检查、待执行安排和作业进度，不推断每日完成。"""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

ACTIVITY_KEYS = (
    "base",
    "runorder",
    "dorm",
    "drone",
    "reload",
    "clue",
    "fiammetta",
    "workshop",
    "training",
    "trust",
    "recruit",
    "depot",
    "shop",
    "mission",
    "stage-plan",
    "annihilation",
    "long",
)
_TASK_GROUPS = {
    "RUN_ORDER": ("base", "runorder"),
    "SHIFT_OFF": ("base",),
    "SHIFT_ON": ("base",),
    "EXHAUST_OFF": ("base",),
    "SELF_CORRECTION": ("base",),
    "RE_ORDER": ("base", "dorm"),
    "RELEASE_DORM": ("base", "dorm"),
    "FILL_DORM": ("base", "dorm"),
    "FIAMMETTA": ("base", "fiammetta"),
    "SWITCH_PRODUCT": ("base",),
    "REFRESH_TIME": ("base", "runorder"),
    "CLUE": ("clue",),
    "CLUE_PARTY": ("clue",),
    "RECRUIT": ("recruit",),
    "DEPOT": ("depot",),
    "WORKSHOP": ("workshop",),
    "SKILL_UPGRADE": ("training",),
    "SWAP_SUPPORT": ("training",),
    "CREDIT_SHOP": ("shop",),
    "MAA_MALL": ("shop",),
    "MISSION": ("mission",),
    "STAGE_PLAN": ("stage-plan",),
    "ROGUELIKE": ("long",),
    "SSS": ("long",),
    "RECLAMATION": ("long",),
    "RA": ("long",),
    "SECRET_FRONT": ("long",),
}
_OUTCOMES = {
    "running",
    "checked",
    "completed",
    "incomplete",
    "error",
    "stopped",
    "reward_full",
    "agency_locked",
}


@contextmanager
def readonly_connection(path):
    """只打开已有实例数据库；缺库不建文件，查询具有有限预算。"""
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=1
    )
    deadline = time.monotonic() + 2
    connection.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
    try:
        yield connection
    finally:
        connection.close()


def _moment(value):
    if isinstance(value, str) and len(value) <= 80:
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    try:
        return value.astimezone()
    except (ValueError, OverflowError, OSError):
        return None


def _integer(value, maximum=1_000_000):
    return type(value) is int and 0 <= value <= maximum


def snapshot_activity_values(read, *, live):
    """从实际字段捕获有限展示数据，不调用求解器或创建作业进度。"""
    from arknights_mower.solvers.local_operation import FOLLOWUP_TASK_META
    from arknights_mower.utils.scheduler_task import TaskScope, task_view

    tasks = read("tasks")
    tasks = tasks if isinstance(tasks, (list, tuple)) else ()
    bounded_tasks = tasks[:10_000]
    dispatchable = {
        id(task)
        for task in task_view(
            bounded_tasks,
            TaskScope.DISPATCH,
            op_data=read("op_data") if live else None,
        )
    }
    queue = []
    # 顶栏不传输逐位置安排；最多观察一万条排队任务。
    for task in bounded_tasks:
        task_type = getattr(getattr(task, "type", None), "name", "")
        groups = list(_TASK_GROUPS.get(task_type, ()))
        plan = getattr(task, "plan", None)
        if (
            task_type == "NOT_SPECIFIC"
            and getattr(task, "meta_data", None) == FOLLOWUP_TASK_META
        ):
            groups.append("stage-plan")
        elif task_type == "NOT_SPECIFIC" and isinstance(plan, dict) and plan:
            groups.append("base")
        if (
            "base" in groups
            and isinstance(plan, dict)
            and any(
                isinstance(room, str) and room.startswith("dormitory_")
                for room in tuple(plan)
            )
        ):
            groups.append("dorm")
        queue.append(
            {
                "groups": tuple(dict.fromkeys(groups)),
                "at": _moment(getattr(task, "time", None)),
                "blocked": id(task) not in dispatchable,
            }
        )
    observations = read("display_observations")
    values = {
        "queue": queue,
        "queue_truncated": len(tasks) > 10_000,
        "party_time": _moment(read("party_time")),
        "display_observations": {
            key: dict(value)
            for key, value in observations.items()
            if key in ACTIVITY_KEYS and isinstance(value, dict)
        }
        if isinstance(observations, dict)
        else {},
    }
    if live:
        execution = read("last_execution")
        values.update(
            recruit=_moment(execution.get("recruit"))
            if isinstance(execution, dict)
            else None,
            clue=_moment(read("last_clue")),
            drone=_moment(read("drone_time")),
            reload=_moment(read("reload_time")),
        )
    return values


def read_long_progress(path, mode):
    """读取已有进度行，不调用会初始化或保存作业的运行入口。"""
    table = {
        "copilot": "maa_copilot_progress",
        "paradox": "maa_paradox_progress",
        "sss": "maa_sss_progress",
    }.get(mode)
    if table is None:
        return {}
    try:
        with readonly_connection(path) as connection:
            row = connection.execute(
                f"SELECT payload FROM {table} WHERE id = 1"
            ).fetchone()
        if row and isinstance(row[0], str) and len(row[0]) <= 65_536:
            value = json.loads(row[0])
            if isinstance(value, dict):
                return value
    except (sqlite3.Error, ValueError, RecursionError):
        pass
    return {}


def _progress(conf, saved):
    mode = getattr(conf, "maa_long_task_type", None)
    part = getattr(conf, mode, None) if mode in {"copilot", "paradox", "sss"} else None
    if part is None or not getattr(conf, "maa_rg_enable", False):
        return None
    from arknights_mower.utils.maa_copilot import queue_key

    if not isinstance(saved, dict) or saved.get("key") != queue_key(part):
        return None
    scripts = part.scripts
    position = saved.get("next")
    if not _integer(position, len(scripts)):
        return None
    result = {
        "completed": position,
        "total": len(scripts),
        "failed": saved.get("failed") is True,
    }
    if mode == "sss" and position < len(scripts):
        rounds = saved.get("completed")
        if _integer(rounds, scripts[position].times):
            result.update(rounds=rounds, round_total=scripts[position].times)
    return result


def build_task_activities(values, *, source, game_day, now, conf, progress=None):
    """保留周期观测与原队列，周满结果只属于对应游戏周。"""
    if values is None or source == "none":
        return {}
    activities = {key: {} for key in ACTIVITY_KEYS}
    if not isinstance(game_day, date):
        return activities
    week_start = game_day - timedelta(days=game_day.weekday())
    activities["annihilation"]["week_start"] = week_start.isoformat()
    for task in values["queue"]:
        for key in task["groups"]:
            item = activities[key]
            item["scheduled_count"] = item.get("scheduled_count", 0) + 1
            if task["blocked"]:
                item["blocked_count"] = item.get("blocked_count", 0) + 1
            elif task["at"] is not None:
                at = task["at"].isoformat()
                previous = _moment(item.get("next_task_at"))
                if previous is None or task["at"] < previous:
                    item["next_task_at"] = at
    if values.get("queue_truncated"):
        for item in activities.values():
            item["queue_truncated"] = True
            item.pop("next_task_at", None)
    if values["party_time"] is not None and values["party_time"] > now:
        activities["clue"]["exchange_ends_at"] = values["party_time"].isoformat()
    if source == "live":
        for key, gap in (
            ("recruit", getattr(conf, "recruit_gap", None)),
            ("clue", 1),
            ("drone", getattr(conf, "drone_interval", None)),
            ("reload", getattr(conf, "maa_gap", None)),
        ):
            observed = values.get(key)
            if observed is None:
                continue
            activities[key]["last_checked_at"] = observed.isoformat()
            if type(gap) in (int, float) and 0 <= gap <= 8760:
                activities[key]["next_eligible_at"] = (
                    observed + timedelta(hours=gap)
                ).isoformat()
    for key, raw in values["display_observations"].items():
        at = _moment(raw.get("at"))
        outcome = raw.get("outcome")
        if (
            at is None
            or at > now
            or not isinstance(outcome, str)
            or outcome not in _OUTCOMES
        ):
            continue
        if key == "annihilation":
            observation_day = (
                at.astimezone(timezone(timedelta(hours=8))) - timedelta(hours=4)
            ).date()
            if not week_start <= observation_day < week_start + timedelta(days=7):
                continue
        observation = {"at": at.isoformat(), "outcome": outcome}
        if source != "live" and outcome == "running":
            observation["outcome"] = "stopped"
        for field in ("runner", "stage", "reason"):
            if isinstance(raw.get(field), str) and len(raw[field]) <= 256:
                observation[field] = raw[field]
        if _integer(raw.get("executed_runs")):
            observation["executed_runs"] = raw["executed_runs"]
        activities[key]["last_observation"] = observation
    queue_progress = _progress(conf, progress)
    if queue_progress is not None:
        activities["long"]["progress"] = queue_progress
    return activities
