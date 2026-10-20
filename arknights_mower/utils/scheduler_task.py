import copy
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Literal

from arknights_mower.solvers.record import get_inventory_counts
from arknights_mower.utils import config
from arknights_mower.utils.datetime import the_same_time
from arknights_mower.utils.dorm_candidates import (
    dorm_candidate_mood,
    dorm_candidates,
    dorm_task_reservations,
    retained_task_reservations,
    vacant_dorm_slots,
)
from arknights_mower.utils.dorm_recovery import recovery_order_target
from arknights_mower.utils.furniture_task import (
    FURNITURE_EXIT_SECONDS,
    FURNITURE_RUN_SECONDS,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.operation_timing import (
    estimate_dorm_minutes,
    estimate_work_minutes,
)
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operator, Operators
from arknights_mower.utils.resting_priority import (
    RestingTier,
    bed_takeover_allowed,
    busy_resting_names,
    crafting_rest_order,
    has_resting_mood,
    resting_key,
    resting_mood,
    resting_tier,
)


class TaskTypes(Enum):
    RUN_ORDER = ("run_order", "跑单", 1)
    SWITCH_PRODUCT = ("switch_product", "切换产物/订单", 2)
    FIAMMETTA = ("菲亚梅塔", "肥鸭", 2)
    SHIFT_OFF = ("shifit_off", "下班", 2)
    SHIFT_ON = ("shifit_on", "上班", 2)
    EXHAUST_OFF = ("exhaust_on", "用尽下班", 2)
    SELF_CORRECTION = ("self_correction", "纠错", 2)
    CLUE_PARTY = ("Impart", "趴体", 2)
    CLUE = ("clue", "线索任务", 2)
    MAA_MALL = ("maa_Mall", "MAA信用购物", 2)
    NOT_SPECIFIC = ("", "空任务", 2)
    RECRUIT = ("recruit", "公招", 2)
    SKLAND = ("skland", "森空岛签到", 2)
    RE_ORDER = ("宿舍排序", "宿舍排序", 2)
    RELEASE_DORM = ("释放宿舍空位", "释放宿舍空位", 2)
    FILL_DORM = ("宿舍补位", "宿舍补位", 2)
    REFRESH_TIME = ("强制刷新任务时间", "强制刷新任务时间", 2)
    SKILL_UPGRADE = ("技能专精", "技能专精", 2)
    SWAP_SUPPORT = ("换协助位", "换协助位", 2)
    DEPOT = ("仓库扫描", "仓库扫描", 2)
    WORKSHOP = ("加工材料", "加工材料", 2)
    FURNITURE = ("分解所有重复家具", "分解所有重复家具", 2)

    def __new__(cls, value, display_value, priority):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display_value = display_value
        obj.priority = priority
        return obj


class TaskScope(Enum):
    PENDING = "pending"
    DISPATCH = "dispatch"
    REPLAN = "replan"


def task_view(tasks, scope, op_data=None):
    """按用途读取同一队列；返回原任务引用，不复制执行状态。"""
    if scope == TaskScope.PENDING:
        return list(tasks)
    if scope == TaskScope.DISPATCH:
        blocked = blocked_run_order_ids(tasks, op_data)
        return [
            task
            for task in tasks
            if not getattr(task, "execution_failure", None) and id(task) not in blocked
        ]
    if scope == TaskScope.REPLAN:
        return [task for task in tasks if not task.retains_execution]
    raise ValueError(f"未知任务查询用途：{scope}")


def merge_restored_waiting_shifts(waiting):
    """旧缓存中的重复派生上班保留最早原任务；未知执行状态保持原样。"""
    planning_fields = {
        "time",
        "type",
        "plan",
        "meta_data",
        "adjusted",
        "strict_mood_limit",
        "mood_limit",
        "initial_fia",
        "return_windows",
        "group_shift_waiting",
        "group_shift_predecessors",
        "group_shift_transitions",
    }
    result, buckets = [], defaultdict(list)
    for task in waiting:
        predecessors = getattr(task, "group_shift_predecessors", ())
        if (
            type(task) is not SchedulerTask
            or task.type != TaskTypes.SHIFT_ON
            or task.meta_data
            or task.adjusted
            or task.strict_mood_limit
            or task.initial_fia
            or task.mood_limit is not None
            or not task.plan
            or not any(
                name not in ("Current", "Free", "")
                for row in task.plan.values()
                for name in row
            )
            or not hasattr(task, "group_shift_waiting")
            or not (predecessors or task.group_shift_waiting)
            or set(vars(task)) - planning_fields
        ):
            result.append(task)
            continue
        # 执行、补偿、副表或未知字段不在白名单内，即使数值相同也不合并。
        metadata = {
            name: value
            for name, value in vars(task).items()
            if name not in ("time", "group_shift_predecessors", "return_windows")
        }
        windows = getattr(task, "return_windows", {})
        key = (
            tuple((room, tuple(row)) for room, row in sorted(task.plan.items())),
            tuple(id(previous) for previous in predecessors),
            frozenset(task.group_shift_waiting),
            tuple(sorted(getattr(task, "group_shift_transitions", {}).items())),
            "return_windows" in vars(task),
            tuple((name, identity) for name, (identity, _) in sorted(windows.items())),
        )
        for index, previous_metadata in buckets[key]:
            if metadata == previous_metadata:
                earlier, later = (
                    (task, result[index])
                    if task.time < result[index].time
                    else (result[index], task)
                )
                earlier_windows = getattr(earlier, "return_windows", {})
                later_windows = getattr(later, "return_windows", {})
                # 同轮等待沿用首次起点；原任务时间与窗口起点不一致时不推断责任。
                if all(
                    earlier_windows[name][1] <= later_windows[name][1]
                    for name in earlier_windows
                ):
                    result[index] = earlier
                    break
        else:
            buckets[key].append((len(result), metadata))
            result.append(task)
    removed = len(waiting) - len(result)
    if removed:
        logger.info("恢复等待换班时合并 %d 份重复安排，保留最早任务与原时间", removed)
    return result


def find_next_task(
    tasks,
    compare_time: datetime | None = None,
    task_type="",
    compare_type: Literal["<", "=", ">"] = "<",
    meta_data="",
    *,
    scope=TaskScope.DISPATCH,
    op_data=None,
):
    """找符合条件的下一个任务

    Args:
        tasks: 任务列表
        compare_time: 截止时间
        scope: 派发、普通重规划或全部未完成任务（去重／预约）
    """
    tasks = task_view(tasks, scope, op_data)
    if compare_type == "=":
        return next(
            (
                e
                for e in tasks
                if the_same_time(e.time, compare_time)
                and (True if task_type == "" else task_type == e.type)
                and (True if meta_data == "" else meta_data in e.meta_data)
            ),
            None,
        )
    elif compare_type == ">":
        return next(
            (
                e
                for e in tasks
                if (True if compare_time is None else e.time > compare_time)
                and (True if task_type == "" else task_type == e.type)
                and (True if meta_data == "" else meta_data in e.meta_data)
            ),
            None,
        )
    else:
        return next(
            (
                e
                for e in tasks
                if (True if compare_time is None else e.time < compare_time)
                and (True if task_type == "" else task_type == e.type)
                and (True if meta_data == "" else meta_data in e.meta_data)
            ),
            None,
        )


def scheduling(
    tasks, run_order_delay=5, execution_time=None, time_now=None, op_data=None
):
    time_now = time_now or datetime.now()
    merge_release_dorm(tasks, config.conf.merge_interval)
    enabled = config.conf.enable_mastery
    conflict = _find_run_order_conflict(tasks, run_order_delay, time_now, op_data)
    protect_priority_tasks(tasks, run_order_delay, execution_time, time_now, op_data)
    if enabled:
        # 临近换人暂停可选无人机调时，关键任务保护决定执行顺序。
        if any(
            t.type == TaskTypes.SWAP_SUPPORT
            and t.time
            <= time_now
            + _support_swap_duration(t, execution_time, op_data)
            + timedelta(minutes=1)
            for t in task_view(tasks, TaskScope.DISPATCH, op_data)
        ):
            return None
    return conflict


def protect_priority_tasks(
    tasks, run_order_delay=5, execution_time=None, time_now=None, op_data=None
):
    """按操作耗时保护关键任务，跑单冲突时提前专精换人。"""
    now = time_now or datetime.now()
    # 依赖用完整队列判断；失败与等待任务保留原状，不参加操作预算。
    dispatch_queue = tasks
    active = task_view(tasks, TaskScope.DISPATCH, op_data)
    active_ids = {id(task) for task in active}
    waiting = [task for task in tasks if id(task) not in active_ids]
    if any(
        getattr(task, "emergency_takeover", False) and task.time <= now
        for task in active
    ):
        _sort_dispatch_tasks(active, now, op_data)
        dispatch_queue[:] = active + waiting
        return
    # 保留任务只在临时副本上计算避让时间，派发队列仍使用原任务和原时间。
    originals = {}
    tasks = active
    for index, task in enumerate(tasks):
        if task.retains_execution:
            projected = copy.copy(task)
            projected.plan = copy.deepcopy(task.plan)
            originals[id(projected)] = task
            tasks[index] = projected
    for task in tasks:
        simplify_dorm_fill(task, tasks, now, op_data)
    swaps = sorted(
        (
            t
            for t in tasks
            if config.conf.enable_mastery and t.type == TaskTypes.SWAP_SUPPORT
        ),
        key=lambda t: t.time,
    )
    _advance_support_swaps_for_maintenance(
        swaps, run_order_delay, execution_time, now, op_data
    )
    for swap in swaps:
        _advance_swap_before_orders(tasks, swap, now, execution_time, op_data)
    _schedule_priority_tasks(tasks, execution_time, now, op_data)
    _advance_mood_limit_releases(
        tasks,
        run_order_delay,
        0.75 if execution_time is None else execution_time,
        now,
        op_data,
    )
    _sort_dispatch_tasks(tasks, now, op_data)
    dispatch_queue[:] = [originals.get(id(task), task) for task in tasks] + waiting


def _advance_support_swaps_for_maintenance(
    swaps, run_order_delay, execution_time, now, op_data
):
    if not swaps:
        return
    windows = [NewsChecker.get_daily_reset(now), NewsChecker.get_maintenance()]
    # 先处理较晚边界，提前换人产生的新冲突在同轮继续向前处理。
    for maintenance in sorted(
        (info for info in windows if info is not None),
        key=lambda info: info.start,
        reverse=True,
    ):
        if now >= maintenance.start:
            continue
        deadline = maintenance.start - timedelta(minutes=max(10, run_order_delay * 2))
        # 公告维护使用完整区间；即时刷新也保护恰好位于刷新时刻的换人。
        affected = [
            swap
            for swap in swaps
            if deadline < swap.time
            and (
                swap.time < maintenance.end
                or swap.time == maintenance.start == maintenance.end
            )
        ]
        # 从后往前预留操作窗口；提前标记复用执行器的训练与候选校验。
        for swap in reversed(affected):
            original = swap.time
            swap.time = min(
                original,
                max(
                    now,
                    deadline
                    - _support_swap_duration(swap, execution_time, op_data)
                    - timedelta(seconds=1),
                ),
            )
            swap.advance_support_swap = True
            deadline = swap.time
            logger.info(
                f"专精换人避让维护，从 {original:%H:%M:%S} 提前至 {swap.time:%H:%M:%S}"
            )


def _sort_dispatch_tasks(tasks, now, op_data=None):
    # 尚未开始的清退可以提前；关键任务已经到点时，不再被清退抢占。
    due_priority = {
        id(task) for task in _priority_tasks(tasks, op_data) if task.time <= now
    }
    initial_fia_due = any(
        getattr(task, "initial_fia", False) and task.time <= now for task in tasks
    )
    tasks.sort(
        key=lambda task: (
            bool(getattr(task, "execution_failure", None)),
            not (getattr(task, "emergency_takeover", False) and task.time <= now),
            id(task) not in due_priority,
            not (
                initial_fia_due
                and task.time <= now
                and (
                    getattr(task, "initial_fia", False)
                    or getattr(task, "strict_mood_limit", False)
                )
            ),
            not (
                config.conf.enable_mastery
                and task.type == TaskTypes.SWAP_SUPPORT
                and getattr(task, "advance_support_swap", False)
                and task.time <= now
            ),
            not (getattr(task, "strict_mood_limit", False) and task.time <= now),
            task.time,
        )
    )


def _advance_mood_limit_releases(
    tasks, run_order_delay, execution_time, now, op_data=None
):
    """上限是离宿截止时间；提前腾出操作窗口，不等阻塞任务结束。"""
    releases = [
        task
        for task in tasks
        if getattr(task, "strict_mood_limit", False) and task.plan
    ]
    if not releases:
        return
    blocked_orders = blocked_run_order_ids(tasks, op_data)
    blockers = sorted(
        (
            task
            for task in tasks
            if not getattr(task, "strict_mood_limit", False)
            and id(task) not in blocked_orders
            and not getattr(task, "emergency_recovery_release", False)
            and (task.plan or task.type != TaskTypes.NOT_SPECIFIC)
            and (task.type != TaskTypes.SWAP_SUPPORT or config.conf.enable_mastery)
        ),
        key=lambda task: task.time,
        reverse=True,
    )
    next_start = datetime.max
    for release in sorted(
        releases,
        key=lambda task: (
            getattr(task, "mood_limit_deadline", task.time),
            task.meta_data,
            tuple(sorted(task.plan)),
        ),
        reverse=True,
    ):
        # 固定原始截止时间，重复调度不能不断扣减操作耗时。
        if not hasattr(release, "mood_limit_deadline"):
            release.mood_limit_deadline = release.time
        duration = timedelta(
            minutes=sum(estimate_dorm_minutes(room, 1.5) for room in release.plan)
        )
        start = min(
            release.time, min(release.mood_limit_deadline, next_start) - duration
        )
        for task in blockers:
            if (
                task.type in (TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT)
                or getattr(task, "run_order_window_observation", False)
            ) and task.time <= now:
                # 已到期的关键任务先执行，不再尝试把清退塞到它前面。
                continue
            if task.type == TaskTypes.RUN_ORDER or getattr(
                task, "run_order_window_observation", False
            ):
                # 跑单时间已扣除进站提前量，还需预留确认、收单和归位。
                minutes = (
                    max(run_order_delay, config.conf.run_order_delay)
                    + 2 * execution_time
                )
            elif task.type == TaskTypes.SWAP_SUPPORT:
                minutes = _ordinary_task_minutes(task, execution_time)
            elif _is_dorm_only_task(task):
                minutes = sum(estimate_dorm_minutes(room, 1.5) for room in task.plan)
            else:
                minutes = _ordinary_task_minutes(task, execution_time)
            blocker_start = max(now, task.time)
            end = blocker_start + timedelta(minutes=minutes)
            if start <= end and max(now, start) + duration >= blocker_start:
                start = min(start, blocker_start - duration - timedelta(seconds=1))
        if start < release.time:
            logger.info(
                f"心情上限离宿提前至 {start:%H:%M:%S}，"
                f"截止 {release.mood_limit_deadline:%H:%M:%S}：{release.meta_data}"
            )
            release.time = start
        next_start = start


def _support_swap_duration(task, execution_time=None, op_data=None):
    # 专精换人保留至少一分钟的操作窗口，慢房间实测预算可以上调。
    return max(
        timedelta(
            minutes=_ordinary_task_minutes(
                task, 0.75 if execution_time is None else execution_time
            )
        ),
        estimate_task_duration(task, execution_time, op_data),
    )


def _advance_swap_before_orders(tasks, swap, now, execution_time, op_data=None):
    entry_delay = timedelta(minutes=config.conf.run_order_delay)
    order_operations = timedelta(
        minutes=2 * (0.75 if execution_time is None else execution_time)
    )
    swap_duration = _support_swap_duration(swap, execution_time, op_data)
    # 从晚到早检查，提前产生的新冲突在同一轮内收敛。
    blocked_orders = blocked_run_order_ids(tasks, op_data)
    orders = sorted(
        (
            t
            for t in tasks
            if (
                t.type == TaskTypes.RUN_ORDER
                or getattr(t, "run_order_window_observation", False)
            )
            and t.meta_data
            and not getattr(t, "run_order_restore_pending", False)
            and id(t) not in blocked_orders
        ),
        key=lambda t: t.time,
        reverse=True,
    )
    for task in orders:
        start = max(now, task.time)
        # 已流逝的提前量不再占用后续时间，过期任务仍预留进驻与归位。
        finish = max(start, task.time + entry_delay) + order_operations
        if finish <= swap.time or start >= max(now, swap.time) + swap_duration:
            continue
        if swap.time > now:
            original = swap.time
            swap.time = max(now, task.time - swap_duration - timedelta(seconds=1))
            logger.info(
                f"专精换人与跑单冲突，换人从 {original:%H:%M:%S} "
                f"提前至 {swap.time:%H:%M:%S}，随后执行跑单"
            )
        # 到点或已过期的换人同样先执行，跑单时间保持原值。
        swap.advance_support_swap = True


def _ordinary_task_minutes(task, execution_time):
    if task.type == TaskTypes.FURNITURE:
        return (FURNITURE_RUN_SECONDS + FURNITURE_EXIT_SECONDS) / 60
    minutes = max(1, len(task.plan) * execution_time)
    if task.type in (TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY):
        minutes = max(minutes, 3)
    # A downshift can insert an extra dorm-reordering action before itself.
    return minutes * 2 if task.type == TaskTypes.SHIFT_OFF else minutes


def _is_dorm_only_task(task):
    return (
        task.type
        in (
            TaskTypes.SHIFT_OFF,
            TaskTypes.SHIFT_ON,
            TaskTypes.RE_ORDER,
            TaskTypes.RELEASE_DORM,
            TaskTypes.FILL_DORM,
            TaskTypes.NOT_SPECIFIC,
        )
        and bool(task.plan)
        and all(room.startswith("dormitory_") for room in task.plan)
    )


def blocked_run_order_ids(tasks, op_data=None):
    """根据实际驻员判断等待中的普通跑单；保留任务，但不占用关键窗口。"""
    restorations = [
        task
        for task in tasks
        if task.type == TaskTypes.RUN_ORDER
        and getattr(task, "run_order_restore_pending", False)
    ]
    if not restorations:
        return set()
    rooms = {room for task in restorations for room in task.run_order_original_roster}
    reserved = {
        name
        for task in restorations
        for row in task.run_order_original_roster.values()
        for name in row
        if name not in ("", "Free", "Current")
    }
    conflicting_rooms = set(rooms)
    if op_data is not None:
        conflicting_rooms.update(
            op.current_room
            for name in reserved
            if (op := op_data.operators.get(name)) is not None and op.is_working()
        )
        reserved.update(
            name for name, op in op_data.operators.items() if op.current_room in rooms
        )
        # 首次选人可能尚未确认；配置中的实际换入人选仍归这次补偿占用。
        reserved.update(
            next(
                (name for name in slot.all_replacements if name in TRADE_ORDER_AGENTS),
                "",
            )
            for room in rooms
            for slot in op_data.plan.get(room, [])
        )
    blocked = {
        id(task)
        for task in tasks
        if restorations
        and task.type == TaskTypes.RUN_ORDER
        and task.meta_data
        and not getattr(task, "run_order_restore_pending", False)
        and (
            op_data is None
            or conflicting_rooms.intersection(task.plan)
            or any(
                name in reserved
                for row in task.plan.values()
                for name in row
                if name not in ("", "Free", "Current")
            )
        )
    }
    if op_data is not None:
        blocked.update(
            id(task)
            for task in restorations
            if any(
                (op := op_data.operators.get(name)) is not None
                and op.is_working()
                and op.current_room != room
                for room, row in task.run_order_original_roster.items()
                for name in row
                if name not in ("", "Free", "Current")
            )
        )
    return blocked


def _priority_tasks(tasks, op_data=None):
    return sorted(
        (
            task
            for task in task_view(tasks, TaskScope.DISPATCH, op_data)
            if task.type == TaskTypes.RUN_ORDER
            or getattr(task, "run_order_window_observation", False)
            or config.conf.enable_mastery
            and task.type == TaskTypes.SWAP_SUPPORT
        ),
        key=lambda task: task.time,
    )


def simplify_dorm_fill(task, tasks, time_now=None, op_data=None):
    """临近关键任务时退回原始补空名单，避免新入住者竞争单回而扩大操作。"""
    if (
        task.retains_execution
        or (task.type != TaskTypes.FILL_DORM)
        or getattr(task, "simple_dorm_fill", False)
        or getattr(task, "dorm_recovery_restore", [])
    ):
        return
    now = time_now or datetime.now()
    window_end = now + timedelta(minutes=max(10, config.conf.run_order_delay * 2))
    if not any(
        t.time <= window_end and (task.time <= now or task.time <= t.time)
        for t in _priority_tasks(tasks, op_data)
    ):
        return
    original = getattr(task, "dorm_fill_plan", task.plan)
    task.plan = {
        room: names.copy() for room, names in original.items() if room in task.plan
    }
    task.simple_dorm_fill = True


def _dorm_deadline(task, tasks, start, minutes, now, op_data=None):
    if (
        (not _is_dorm_only_task(task))
        or getattr(task, "strict_mood_limit", False)
        or getattr(task, "dorm_recovery_restore", [])
    ):
        return None
    # 跑单时刻已扣除进站提前量，专精时刻已含换人缓冲；统一另留一分钟。
    finish = start + timedelta(minutes=minutes + 1)
    return next(
        (
            deadline
            for deadline in _priority_tasks(tasks, op_data)
            if (task.time <= now or task.time <= deadline.time)
            and finish >= deadline.time
        ),
        None,
    )


def defer_dorm_before_priority_task(task, tasks, room, time_now=None, op_data=None):
    """逐房复核剩余时间；不足时保留未完成计划，关键任务结束后续行。"""
    if not room.startswith("dormitory_") or not _is_dorm_only_task(task):
        return False
    now = time_now or datetime.now()
    deadline = _dorm_deadline(
        task, tasks, now, estimate_dorm_task_minutes(task, room, op_data), now, op_data
    )
    if deadline is None:
        return False
    if task.retains_execution:
        tasks[:] = [queued for queued in tasks if queued is not task]
        tasks.insert(
            next(i for i, queued in enumerate(tasks) if queued is deadline) + 1, task
        )
    else:
        task.time = max(now, deadline.time) + timedelta(seconds=1)
        tasks.sort(key=lambda t: t.time)
    logger.info(
        f"{room} 操作可能挤占{deadline.type.display_value}时间，剩余宿舍安排延后"
    )
    return True


def _merge_deferred_dorm_schedules(tasks):
    """把同一批延期任务里的宿舍中间态合成一次最终安排。"""
    mergeable_types = {
        TaskTypes.SHIFT_OFF,
        TaskTypes.SHIFT_ON,
        TaskTypes.RE_ORDER,
    }
    mergeable_tasks = [
        task
        for task in task_view(tasks, TaskScope.REPLAN)
        if task.type in mergeable_types
    ]
    dorm_tasks = [
        task
        for task in mergeable_tasks
        if any(room.startswith("dormitory_") for room in task.plan)
    ]
    if len(dorm_tasks) < 2 and not any(
        task.type == TaskTypes.SHIFT_OFF for task in dorm_tasks
    ):
        return tasks

    merged = {}

    def remove_from_dorm(name):
        if name in ("", "Current", "Free"):
            return
        for agents in merged.values():
            for index, current in enumerate(agents):
                if current == name:
                    agents[index] = "Free"

    for task in mergeable_tasks:
        # agent_arrange 同一任务内先处理工作站；回班人员不应再出现在最终宿舍。
        for room, agents in task.plan.items():
            if room.startswith("dormitory_"):
                continue
            for name in agents:
                remove_from_dorm(name)
        for room, agents in task.plan.items():
            if not room.startswith("dormitory_"):
                continue
            target = merged.setdefault(room, ["Current"] * len(agents))
            if len(target) < len(agents):
                target.extend(["Current"] * (len(agents) - len(target)))
            for index, name in enumerate(agents):
                if name == "Current":
                    continue
                remove_from_dorm(name)
                target[index] = name

    # SHIFT_OFF 需要读取新入住者的休息时间，优先承载合并后的宿舍安排。
    anchor = next(
        (task for task in dorm_tasks if task.type == TaskTypes.SHIFT_OFF),
        dorm_tasks[-1],
    )
    dorm_ids = {id(task) for task in dorm_tasks}
    for task in dorm_tasks:
        for room in list(task.plan):
            if room.startswith("dormitory_"):
                del task.plan[room]
    anchor.plan.update(merged)

    removed_task_ids = {
        id(task)
        for task in dorm_tasks
        if task is not anchor and task.type != TaskTypes.SHIFT_OFF and not task.plan
    }
    redundant_followup_ids = set()
    for index, task in enumerate(tasks[:-1]):
        if (
            id(task) in removed_task_ids
            and task.type == TaskTypes.RE_ORDER
            and id(tasks[index + 1]) not in dorm_ids
            and tasks[index + 1].type == TaskTypes.NOT_SPECIFIC
            and not tasks[index + 1].plan
            and tasks[index + 1].time == task.time
        ):
            redundant_followup_ids.add(id(tasks[index + 1]))

    result = []
    for task in tasks:
        if id(task) in removed_task_ids:
            continue
        # 只删除已移除重排的后续唤醒；保留最终重排及仍有工作安排的重排的唤醒。
        if id(task) in redundant_followup_ids:
            continue
        result.append(task)
    logger.info("合并同批延期任务的宿舍安排，仅保留一次最终排班")
    return result


def _task_has_phase_state(task, *, ignored=()):
    # Phase, return-window and reservation state belongs to the complete task.
    fields = {
        "time",
        "plan",
        "type",
        "meta_data",
        "adjusted",
        "strict_mood_limit",
        "mood_limit",
        "initial_fia",
    }
    return bool(vars(task).keys() - fields - set(ignored))


def _static_room_task(task):
    return (
        not _task_has_phase_state(task)
        and not task.meta_data
        and not task.strict_mood_limit
        and not task.initial_fia
        and task.type
        in (
            TaskTypes.SHIFT_OFF,
            TaskTypes.SHIFT_ON,
            TaskTypes.SELF_CORRECTION,
            TaskTypes.NOT_SPECIFIC,
        )
    )


def estimate_dorm_task_minutes(task, room, op_data=None, execution_time=0.75):
    single_recovery = False
    if (
        isinstance(op_data, Operators)
        and task.type != TaskTypes.FIAMMETTA
        and not getattr(task, "simple_dorm_fill", False)
        and room not in getattr(task, "dorm_recovery_restore", [])
    ):
        names = task.plan[room]
        if "Current" in names:
            current = op_data.get_current_room(room, True)
            names = [
                current[index] if name == "Current" and index < len(current) else name
                for index, name in enumerate(names)
            ]
        single_recovery = (
            recovery_order_target(
                op_data,
                room,
                names,
                group_transitions=op_data.arrangement_group_transitions(
                    task.plan,
                    group_transitions=getattr(task, "group_shift_transitions", None),
                ),
            )
            is not None
        )
    return estimate_dorm_minutes(room, execution_time, single_recovery=single_recovery)


def estimate_task_duration(task, execution_time=None, op_data=None):
    """Estimate queued work from room occupancy and bounded measurements."""
    if task.type == TaskTypes.FURNITURE:
        return timedelta(seconds=FURNITURE_RUN_SECONDS + FURNITURE_EXIT_SECONDS)
    if task.type in (TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY):
        return timedelta(minutes=3)
    if not task.plan:
        return timedelta(minutes=1)
    if execution_time is not None:
        return timedelta(
            minutes=sum(
                estimate_dorm_task_minutes(task, room, op_data, execution_time)
                if room.startswith("dormitory_")
                else execution_time
                for room in task.plan
            )
        )
    seconds = 10
    for room, names in task.plan.items():
        if room.startswith("dormitory_"):
            seconds += estimate_dorm_task_minutes(task, room, op_data) * 60
            continue
        unchanged = all(name == "Current" for name in names)
        if not unchanged and op_data is not None and room in op_data.plan:
            current = op_data.get_current_room(room)
            unchanged = (
                current is not None
                and len(current) == len(names)
                and all(
                    name == "Current" or name == current[index]
                    for index, name in enumerate(names)
                )
            )
        seconds += 15 if unchanged else estimate_work_minutes(room) * 60
    return timedelta(seconds=seconds)


def independent_room_plans(task, op_data):
    """仅拆分已知驻员的普通换班，人员移动和同组房间保持在同一部分。"""
    if (
        task.retains_execution
        or op_data is None
        or len(task.plan) < 2
        or not _static_room_task(task)
        or getattr(op_data, "backup_plans", ())
        or task.adjusted
    ):
        return [task.plan]

    rooms = list(task.plan)
    linked = {room: {room} for room in rooms}
    owners = {}
    for room in rooms:
        if room not in op_data.plan:
            return [task.plan]
        current = op_data.get_current_room(room)
        if current is None or any(name in ("Free", "") for name in task.plan[room]):
            return [task.plan]
        names = set(current) | set(task.plan[room])
        for name in names - {"Current", "Free", ""}:
            operator = op_data.operators.get(name)
            if operator is None:
                return [task.plan]
            keys = [("operator", name)]
            groups = {operator.group} | {
                binding["group"] for binding in getattr(operator, "group_bindings", ())
            }
            keys.extend(("group", group) for group in groups if group)
            for key in keys:
                if key in owners:
                    other = owners[key]
                    linked[room].add(other)
                    linked[other].add(room)
                else:
                    owners[key] = room

    result = []
    visited = set()
    for room in rooms:
        if room in visited:
            continue
        component = set()
        pending = [room]
        while pending:
            current_room = pending.pop()
            if current_room in component:
                continue
            component.add(current_room)
            pending.extend(linked[current_room] - component)
        visited.update(component)
        result.append({r: task.plan[r] for r in rooms if r in component})
    return result


def _project_admitted_task(op_data, task):
    if op_data is None or not _static_room_task(task) or op_data.backup_plans:
        return None
    if any(
        name != "Current" and name not in op_data.operators
        for names in task.plan.values()
        for name in names
    ) or any(room not in op_data.plan for room in task.plan):
        return None
    return op_data.project_arrangements([task.plan])


def _find_run_order_conflict(tasks, run_order_delay=5, time_now=None, op_data=None):
    now = time_now or datetime.now()
    if not tasks:
        return None
    active = task_view(tasks, TaskScope.DISPATCH, op_data)
    adjust_run_order_for_maintenance(active, run_order_delay, now=now, op_data=op_data)
    active.sort(key=lambda task: task.time)
    previous_order = None
    for task in active:
        if task.type != TaskTypes.RUN_ORDER or getattr(
            task, "run_order_restore_pending", False
        ):
            continue
        if (
            previous_order is not None
            and config.conf.run_order_grandet_mode.enable
            and task.time - previous_order.time < timedelta(minutes=run_order_delay)
            and now < previous_order.time
            and not task.adjusted
        ):
            logger.info("检测到跑单任务过于接近，准备修正跑单时间")
            return previous_order, task
        previous_order = task


def _fits_before_priority(task, start, duration, priority):
    has_dorm = any(r.startswith("dormitory_") for r in task.plan)
    deadline = priority.time - timedelta(seconds=60 if has_dorm else 15)
    # 与逐房宿舍复核一致：恰好用尽一分钟保护余量时也让行。
    return start + duration < deadline if has_dorm else start + duration <= deadline


def _future_dorm_deferrals(task, following, op_data):
    """保留人员、槽位及绑组依赖；未知状态不证明后续任务独立。"""

    def resources(pending):
        release_fields = (
            ("release_start", "release_targets")
            if pending.type == TaskTypes.RELEASE_DORM
            else ()
        )
        if (
            not pending.plan
            or _task_has_phase_state(pending, ignored=release_fields)
            or not (_is_dorm_only_task(pending) or _static_room_task(pending))
        ):
            return None
        names, slots = _arrangement_resources(pending.plan)
        if not slots:
            return set()
        if not isinstance(op_data, Operators) or op_data.backup_plans:
            return None
        if pending.type == TaskTypes.RELEASE_DORM:
            names.update(getattr(pending, "release_targets", {}))
        for room, index in slots:
            if room not in op_data.plan:
                return None
            current = op_data.get_current_room(room)
            if current is None or index >= len(current):
                return None
            if (
                pending.plan[room][index] == "Free"
                and pending.type != TaskTypes.RELEASE_DORM
            ):
                return None
            names.add(current[index])
        keys = {("slot", room, index) for room, index in slots}
        for name in names:
            operator = op_data.operators.get(name)
            if operator is None:
                return None
            keys.add(("operator", name))
            groups = {operator.group} | {
                binding["group"] for binding in operator.group_bindings
            }
            keys.update(("group", group) for group in groups if group)
        return keys

    pending = [task, *following]
    keys = [resources(item) for item in pending]
    if any(item is None for item in keys):
        deferred = [task] + [
            item for item, affected in zip(following, keys[1:]) if affected != set()
        ]
    else:
        affected = set(keys[0])
        deferred = [task]
        for item, changed in zip(following, keys[1:]):
            if affected & changed:
                deferred.append(item)
                affected.update(changed)
    if any(item.strict_mood_limit or item.adjusted for item in deferred):
        return None
    return deferred


def _schedule_priority_tasks(tasks, execution_time=None, time_now=None, op_data=None):
    now = time_now or datetime.now()
    tasks.sort(key=lambda task: task.time)
    priority_ids = {id(task) for task in _priority_tasks(tasks, op_data)}
    # 严格上限保留离宿截止；补位任务可以延期，但不参加宿舍合成。
    fixed = {id(task) for task in tasks if task.strict_mood_limit}
    adjusted = {id(task) for task in tasks if task.adjusted}
    # Each queued operation advances the cursor once, including scheduled waiting.
    ordered = list(tasks)
    deferred_dorm_tail = {}
    projected = op_data if isinstance(op_data, Operators) else None
    cursor = now
    index = 0
    while index < len(ordered):
        task = ordered[index]
        if id(task) in priority_ids:
            start = max(cursor, task.time)
            if task.type == TaskTypes.SWAP_SUPPORT:
                cursor = start + _support_swap_duration(task, execution_time, projected)
            elif getattr(task, "run_order_restore_pending", False):
                cursor = start + estimate_task_duration(task, execution_time, projected)
            elif config.conf.run_order_buffer_time > 0 and not task.adjusted:
                cursor = max(
                    start + timedelta(seconds=45),
                    task.time + timedelta(minutes=config.conf.run_order_delay),
                ) + timedelta(seconds=45)
            else:
                cursor = start + timedelta(seconds=90)
            projected = None
            index += 1
            continue
        next_priority_index = next(
            (
                j
                for j in range(index + 1, len(ordered))
                if id(ordered[j]) in priority_ids
            ),
            None,
        )
        start = max(cursor, task.time)
        duration = estimate_task_duration(task, execution_time, projected)
        if next_priority_index is None:
            # 到期关键任务仍先执行；宿舍续行保留一次明确的交回时间。
            deadline = _dorm_deadline(
                task, tasks, start, duration.total_seconds() / 60, now, op_data
            )
            if deadline is not None:
                task.time = max(now, deadline.time) + timedelta(seconds=1)
            else:
                cursor = start + duration
            index += 1
            continue
        priority = ordered[next_priority_index]
        # 未来普通任务仅在跑单前十分钟延期；到期任务仍按实际操作预算保护跑单。
        # 宿舍保留提前规划；只有确认独立的后续任务保留原时间。
        if (
            (
                priority.type == TaskTypes.RUN_ORDER
                or getattr(priority, "run_order_window_observation", False)
            )
            and priority.time - now > timedelta(minutes=10)
            and task.time > now
        ):
            if (
                _is_dorm_only_task(task)
                and not task.strict_mood_limit
                and not task.adjusted
                and not getattr(task, "dorm_recovery_restore", [])
                and not _fits_before_priority(task, start, duration, priority)
            ):
                deferred = _future_dorm_deferrals(
                    task, ordered[index + 1 : next_priority_index], projected
                )
                if deferred is None:
                    cursor = start + duration
                    projected = _project_admitted_task(projected, task)
                    index += 1
                    continue
                # 同一跑单后的宿舍安排按原顺序追加，避免后移任务覆盖最终驻员。
                previous = deferred_dorm_tail.get(id(priority), priority)
                for pending in deferred:
                    original_time = pending.time
                    pending.time = priority.time + timedelta(seconds=1)
                    logger.debug(
                        "宿舍提前规划：%s（%s）从 %s 延至 %s，避让 %s 跑单",
                        ", ".join(pending.plan),
                        pending.meta_data or pending.type.display_value,
                        original_time,
                        pending.time,
                        priority.time,
                    )
                deferred_ids = {id(pending) for pending in deferred}
                ordered[:] = [
                    pending for pending in ordered if id(pending) not in deferred_ids
                ]
                insert_index = (
                    next(i for i, pending in enumerate(ordered) if pending is previous)
                    + 1
                )
                ordered[insert_index:insert_index] = deferred
                deferred_dorm_tail[id(priority)] = deferred[-1]
            else:
                cursor = start + duration
                projected = _project_admitted_task(projected, task)
                index += 1
            continue
        # Runtime dorm dispatch keeps its one-minute margin and observed budget.
        margin = 60 if any(r.startswith("dormitory_") for r in task.plan) else 15
        deadline = priority.time - timedelta(seconds=margin)
        batch_fits = None
        if task.type == TaskTypes.WORKSHOP and not task.adjusted:
            # Admit the complete workshop batch before this critical task, including
            # intervening operations and scheduled waiting, or defer its suffix.
            batch_end = max(
                j
                for j in range(index, next_priority_index)
                if ordered[j].type == TaskTypes.WORKSHOP
            )
            batch_cursor = start
            batch_fits = True
            for pending_task in ordered[index : batch_end + 1]:
                pending_start = max(batch_cursor, pending_task.time)
                pending_duration = estimate_task_duration(pending_task, execution_time)
                batch_fits &= _fits_before_priority(
                    pending_task, pending_start, pending_duration, priority
                )
                batch_cursor = pending_start + pending_duration
            if batch_fits:
                cursor = batch_cursor
                projected = None
                index = batch_end + 1
                continue
            duration = batch_cursor - start
        protected = fixed | (
            adjusted
            if priority.type == TaskTypes.RUN_ORDER
            or getattr(priority, "run_order_window_observation", False)
            else set()
        )
        if id(task) in protected or (
            batch_fits is not False
            and _fits_before_priority(task, start, duration, priority)
        ):
            cursor = start + duration
            projected = _project_admitted_task(projected, task)
            index += 1
            continue

        original_time = task.time
        task_rooms = ", ".join(task.plan) or task.meta_data or task.type.display_value
        before_plan = {}
        after_plan = {}
        for plan in (
            []
            if task.type == TaskTypes.WORKSHOP
            else independent_room_plans(task, projected)
        ):
            part = copy.copy(task)
            part.plan = before_plan | plan
            if _fits_before_priority(
                part,
                start,
                estimate_task_duration(part, execution_time, projected),
                priority,
            ):
                before_plan.update(plan)
            else:
                after_plan.update(plan)
        pending = ordered[index:next_priority_index]
        if before_plan:
            remainder = copy.deepcopy(task)
            remainder.plan = copy.deepcopy(after_plan)
            task.plan = copy.deepcopy(before_plan)
            pending = [remainder] + ordered[index + 1 : next_priority_index]
            cursor = start + estimate_task_duration(task, execution_time, projected)
            projected = _project_admitted_task(projected, task)
        retained = [t for t in pending if id(t) in protected]
        deferred = [t for t in pending if id(t) not in protected]
        # Preserve phase state; ordinary deferred dorm plans reuse composition.
        if not retained and all(
            not _task_has_phase_state(t) and t.type != TaskTypes.FILL_DORM
            for t in deferred
        ):
            deferred = _merge_deferred_dorm_schedules(deferred)
        for offset, pending_task in enumerate(deferred, 1):
            pending_task.time = max(now, priority.time) + timedelta(seconds=offset)
        log = logger.debug if original_time > now else logger.info
        log(
            "%s任务（%s，计划 %s）预计耗时 %.1f 秒，可用时间 %.1f 秒，"
            "将未完成部分移至%s（%s）之后",
            task.type.display_value,
            task_rooms,
            original_time,
            duration.total_seconds(),
            max(0, (deadline - start).total_seconds()),
            priority.type.display_value,
            priority.time,
        )
        ordered[index : next_priority_index + 1] = (
            ([task] if before_plan else []) + retained + [priority] + deferred
        )
        if before_plan:
            index += 1
    tasks[:] = sorted(ordered, key=lambda task: task.time)


def adjust_run_order_for_maintenance(
    tasks, run_order_delay=5, advance_time=None, now=None, op_data=None
):
    """
    将公告维护附近的跑单提前，并按用户前置延时保护每日四点刷新。
    :param tasks: 任务列表
    :param run_order_delay: 公告维护使用的跑单间隔（分钟）
    :param advance_time: 维护副表要求更早执行时使用的截止时间
    :param now: 本轮调度时间，未提供时使用本地当前时间
    """
    time_gap = max(run_order_delay * 2, 10)  # 确保最小间隔为10分钟操作时间
    reset = NewsChecker.get_daily_reset(now or datetime.now())
    windows = [
        (*NewsChecker.get_update_time(), False),
        (reset.start, reset.end, True),
    ]
    blocked_orders = blocked_run_order_ids(tasks, op_data)
    orders = [
        task
        for task in task_view(tasks, TaskScope.REPLAN)
        if task.type == TaskTypes.RUN_ORDER
        and not getattr(task, "run_order_restore_pending", False)
        and id(task) not in blocked_orders
    ]
    adjusted = {}
    for st, ed, daily_reset in sorted(
        (
            window
            for window in windows
            if window[0] is not None and window[1] is not None
        ),
        reverse=True,
    ):
        if daily_reset:
            entry_delay = timedelta(minutes=config.conf.run_order_delay)
            deadline = st - timedelta(minutes=max(config.conf.run_order_delay, 5))
            daily_orders = []
            for task in sorted(orders, key=lambda task: task.time):
                expected_end = task.time + entry_delay
                if (
                    task.time >= st
                    or expected_end < deadline
                    and not (
                        advance_time is not None
                        and getattr(task, "maintenance_start", None) == st
                    )
                ):
                    continue
                daily_orders.append((task, expected_end))
            for index, (task, expected_end) in enumerate(daily_orders, 1):
                if advance_time is not None:
                    new_time = min(deadline, advance_time) - timedelta(seconds=index)
                else:
                    new_time = deadline if expected_end >= st else task.time
                if advance_time is None and task.adjusted and task.time == new_time:
                    continue
                logger.info(
                    f"每日四点刷新附近的跑单改用无人机，开始时间 {task.time} -> {new_time}"
                    f"（预计订单完成 {expected_end}）"
                )
                task.time = new_time
                task.adjusted = True
                if advance_time is not None:
                    task.maintenance_start = st
                adjusted[id(task)] = task
            continue
        window_start = st - timedelta(minutes=time_gap)
        window_end = ed + timedelta(minutes=time_gap)
        run_order_tasks = [
            t
            for t in orders
            if window_start < t.time < window_end
            or advance_time is not None
            and getattr(t, "maintenance_start", None) == st
        ]
        run_order_tasks.sort(key=lambda t: t.time)
        for i, t in enumerate(run_order_tasks, 1):
            new_time = min(window_start, advance_time or window_start) - timedelta(
                seconds=i
            )
            logger.info(f"维护期附近的跑单任务已提前到 {new_time}（原定 {t.time}）")
            t.time = new_time
            t.adjusted = True
            t.maintenance_start = st
            adjusted[id(t)] = t
    return list(adjusted.values())


def _native_return(op_data, plan, names, *, excluded_names=()):
    """把需要结束休息的干员按当前排班写回原岗位。"""
    for name in names:
        if name in excluded_names:
            continue
        op = op_data.operators[name]
        if not op.room or op.room not in op_data.plan:
            continue
        slots = plan.setdefault(op.room, ["Current"] * len(op_data.plan[op.room]))
        if slots[op.index] in ("Current", name):
            slots[op.index] = name
    op_data.normalize_shared_arrangement(plan, excluded_names=excluded_names)


def _active_recovery_room(op_data, name):
    """只有实际床位仍匹配的单回标记参与豁免。"""
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    position = active_recovery_position(op_data.operators[name])
    return position[0] if position else ""


def _recovery_aware_assignments(
    op_data, beds, candidates, *, clear_invalid_recovery=True, preserve_positions=True
):
    """按正常排名选人，保留有效原床位，只迁移床位失效的入住者。

    candidates 的统一布局为 ``(排序键, 原床位顺序, 姓名, 时间, 原位置)``。
    副表显式切换床位顺序时关闭 preserve_positions，按新顺序重排。
    单回目标若原本会因缩容落选，会替换保留区末尾的非单回目标；若目标
    所在宿舍仍有动态床，保位模式下优先保留原床或同房床。普通床也保留原位，
    日常不因心情变化互换。确实换房/离床时清除旧标记，使后续
    宿舍任务重新执行一次单回入驻。同房换床也不能沿用旧单回标记。
    """
    capacity = len(beds)
    eligible = [
        candidate
        for candidate in candidates
        if resting_tier(op_data, candidate[2]) != RestingTier.EXCLUDED
    ]
    protected = {
        candidate[2]
        for candidate in candidates
        if _active_recovery_room(op_data, candidate[2])
    }
    kept = list(eligible[:capacity])
    kept_names = {candidate[2] for candidate in kept}
    for candidate in eligible[capacity:]:
        name = candidate[2]
        if name not in protected:
            continue
        replace_index = next(
            (
                index
                for index in range(len(kept) - 1, -1, -1)
                if kept[index][2] not in protected
                and resting_key(op_data, name)[0]
                <= resting_key(op_data, kept[index][2])[0]
            ),
            None,
        )
        if replace_index is None:
            continue
        kept_names.remove(kept[replace_index][2])
        kept[replace_index] = candidate
        kept_names.add(name)
    kept.sort(key=candidates.index)
    # 被排除者仍交给调用方释放原床或恢复工作主班。
    dropped = [candidate for candidate in candidates if candidate[2] not in kept_names]

    available = list(beds)
    assignments = {}
    assigned_names = set()
    original_positions = {candidate[2]: candidate[4] for candidate in kept}
    # 单回目标先占原宿舍；同房内优先原床，避免无意义地重做单回。
    for candidate in kept if preserve_positions else ():
        name = candidate[2]
        recovery_room = _active_recovery_room(op_data, name)
        if not recovery_room:
            continue
        same_room = [bed for bed in available if bed.position[0] == recovery_room]
        if not same_room:
            continue
        op = op_data.operators[name]
        bed = next(
            (
                item
                for item in same_room
                if item.position == (op.current_room, op.current_index)
            ),
            same_room[0],
        )
        assignments[bed.position] = candidate
        assigned_names.add(name)
        available.remove(bed)

    # 排名决定缩容时谁保留，不意味着保留者必须按名次重新映射床位。
    for candidate in kept if preserve_positions else ():
        name = candidate[2]
        if name in assigned_names:
            continue
        bed = next(
            (item for item in available if item.position == original_positions[name]),
            None,
        )
        if bed is not None:
            assignments[bed.position] = candidate
            assigned_names.add(name)
            available.remove(bed)

    remaining = [candidate for candidate in kept if candidate[2] not in assigned_names]
    for bed, candidate in zip(available, remaining):
        assignments[bed.position] = candidate

    assigned_positions = {
        candidate[2]: position for position, candidate in assignments.items()
    }
    if clear_invalid_recovery:
        for name in protected:
            op = op_data.operators[name]
            if assigned_positions.get(name) != (op.current_room, op.current_index):
                op_data.operators[name].clear_dorm_recovery()
    return assignments, dropped


def rebalance_closing_dorm_slots(op_data, plan, recalled):
    """固定宿舍成员回班前，统一重排仍在恢复中的动态床位。

    关闭临时 Free 位时，被挤出者和其他动态床位入住者使用同一套
    “休息层级、当前心情、原床位次序”排序。容量不足时只淘汰排序
    最后的成员；如果该成员属于主班，则其整组一并回班并再次计算，
    避免留下无岗位、无床位的半组状态。
    """
    closing = {
        (room, index)
        for room, names in plan.items()
        for index, name in enumerate(names)
        if name not in ("Current", "Free", "")
        and room.startswith("dorm")
        and index < len(op_data.plan.get(room, []))
        and "Free" in op_data.plan[room][index].all_replacements
        and op_data.plan[room][index].agent == name
    }
    if not closing:
        return set(recalled)

    original = [
        (order, bed, bed.name, bed.time)
        for order, bed in enumerate(op_data.dorm)
        if bed.name and bed.name in op_data.operators
    ]
    recalled = set(recalled)
    inactive_groups = {
        op_data.operators[name].group
        for name in recalled
        if name in op_data.operators and op_data.operators[name].group
    }
    now = datetime.now()

    while True:
        beds = [
            bed
            for bed in op_data.ordered_dorms(inactive_groups=inactive_groups)
            if bed.position not in closing
            and op_data.is_effective_free_slot(bed, inactive_groups=inactive_groups)
        ]
        candidates = []
        seen = set()
        for order, _bed, name, saved_time in original:
            if name in seen or name in recalled:
                continue
            op = op_data.operators[name]
            if op.group and op.group in inactive_groups:
                continue
            seen.add(name)
            candidates.append(
                (
                    resting_key(op_data, name, now),
                    order,
                    name,
                    saved_time,
                    _bed.position,
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        _assignments, dropped = _recovery_aware_assignments(
            op_data, beds, candidates, clear_invalid_recovery=False
        )
        dropped_groups = {
            op_data.operators[name].group
            for _key, _order, name, _time, _position in dropped
            if op_data.operators[name].is_high()
            and op_data.is_group_shift_anchor(op_data.operators[name])
            and op_data.operators[name].group
            and op_data.operators[name].group not in inactive_groups
        }
        if not dropped_groups:
            break
        for group in dropped_groups:
            members = set(op_data.groups[group])
            recalled.update(members)
            inactive_groups.add(group)
            _native_return(op_data, plan, members)
            for member in members:
                member_op = op_data.operators[member]
                if op_data.is_auto_free_dorm_operator(member_op):
                    closing.add((member_op.room, member_op.index))

    assignments, _dropped = _recovery_aware_assignments(op_data, beds, candidates)
    for bed in op_data.dorm:
        room, index = bed.position
        if bed.position in closing:
            bed.reset()
            continue
        candidate = assignments.get(bed.position)
        desired = candidate[2] if candidate else ""
        saved_time = candidate[3] if candidate else None
        if bed.name != desired:
            plan.setdefault(room, ["Current"] * len(op_data.plan[room]))[index] = (
                desired or "Free"
            )
        bed.name = desired
        bed.time = saved_time
    return recalled


def dorm_rebalance_signature(op_data):
    """Return the dorm layout state that can require a plan-swap migration.

    Backup plans may change products, operators, or other settings without changing
    dorm recovery beds.  Those switches must not reshuffle every current sleeper.
    """
    beds = []
    for bed in op_data.dorm:
        room, index = bed.position
        slot = op_data.plan[room][index]
        if slot.agent == "Free":
            slot_type = ("free",)
        else:
            slot_type = ("auto_free", slot.agent, slot.group)
        beds.append(
            (
                bed.position,
                slot_type,
                op_data.is_effective_free_slot(bed),
                bed.name,
                resting_tier(op_data, bed.name) if bed.name else None,
            )
        )
    return tuple(op_data.config.dorm_order), tuple(beds)


def rebalance_plan_swap_dorms(
    op_data,
    previous_dorms=None,
    reserved_names: set[str] | None = None,
    *,
    reorder=False,
    reserved_slots=(),
):
    """切表改变优先级时重排可移动住客，其余切表只迁移失效床位。

    previous_dorms 保留切表前的位置和计时；换床后重新读取恢复时间。
    预约和显式副表安排不参与优先级重排。
    """
    reserved_names = reserved_names or set()
    locked_positions = set(reserved_slots)
    if reorder:
        locked_positions.update(bed.position for bed in op_data.group_dorm)
        locked_positions.update(op_data.reserved_product_beds)
        locked_positions.update(
            bed.position for bed in op_data.dorm if bed.name in reserved_names
        )
    if previous_dorms is not None:
        sources = [
            bed
            for bed in previous_dorms
            if bed.name
            and bed.name in op_data.operators
            and bed.name not in reserved_names
        ]
    else:
        sources = [
            *(
                bed
                for bed in op_data.dorm
                if bed.name
                and bed.name in op_data.operators
                and bed.name not in reserved_names
            ),
            *(
                bed
                for bed in getattr(op_data, "displaced_dorms", [])
                if bed.name
                and bed.name in op_data.operators
                and bed.name not in reserved_names
            ),
        ]
    # 显式安排可能把原住客移到另一锁定床位；按投影后的住客保护，
    # 不能重复分配已安置者，也不能漏掉被新安排挤出的原住客。
    locked_residents = {
        current.name
        for position in locked_positions
        if (current := op_data.get_current_operator(*position)) is not None
    }
    sources = [bed for bed in sources if bed.name not in locked_residents]
    if not sources:
        return {}
    now = datetime.now()
    unique = {}
    for order, bed in enumerate(sources):
        unique.setdefault(bed.name, (order, bed))
    candidates = sorted(
        (
            resting_key(op_data, name, now),
            order,
            name,
            bed.time,
            bed.position,
        )
        for name, (order, bed) in unique.items()
    )
    beds = [
        bed
        for bed in op_data.ordered_dorms()
        if bed.position not in locked_positions and op_data.is_effective_free_slot(bed)
    ]
    assignments, dropped = _recovery_aware_assignments(
        op_data, beds, candidates, preserve_positions=not reorder
    )
    plan = {}
    for _key, _order, name, _time, _position in dropped:
        op = op_data.operators[name]
        if op.is_high() and (not op.group or op_data.is_group_shift_anchor(op)):
            members = op_data.groups[op.group] if op.group else [name]
            _native_return(op_data, plan, members)

    destinations = {}
    for bed in beds:
        candidate = assignments.get(bed.position)
        if candidate is None:
            continue
        _key, _order, name, saved_time, _position = candidate
        destinations[bed.position] = name
        current = op_data.get_current_operator(*bed.position)
        if current is None or current.name != name:
            room, index = bed.position
            plan.setdefault(room, ["Current"] * len(op_data.plan[room]))[index] = name
        bed.name = name
        bed.time = None if reorder and bed.position != _position else saved_time

    effective_positions = {bed.position for bed in beds}
    for _key, _order, _name, _time, position in candidates:
        if position in destinations or position in locked_positions:
            continue
        room, index = position
        if room not in op_data.plan or index >= len(op_data.plan[room]):
            continue
        target = (
            "Free"
            if position in effective_positions
            else op_data.plan[room][index].agent
        )
        plan.setdefault(room, ["Current"] * len(op_data.plan[room]))[index] = target

    assigned = set(destinations.values())
    for bed in op_data.dorm:
        if bed.position not in destinations and bed.position not in locked_positions:
            bed.reset()
    logger.info(
        "副表切换后重排宿舍：保留%s，离开%s",
        sorted(assigned),
        sorted(set(unique) - assigned),
    )
    return {
        room: names
        for room, names in plan.items()
        if any(name != "Current" for name in names)
    }


def _arrangement_resources(plan):
    return (
        {
            name
            for names in plan.values()
            for name in names
            if name not in ("Current", "Free", "")
        },
        {
            (room, index)
            for room, names in plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        },
    )


def _after_pending_arrangements(plan, pending_resources):
    names, slots = _arrangement_resources(plan)
    # 从迁移后的状态派生的任务须晚于相关迁移，不拖延无关房间的回班。
    return max(
        (
            ready + timedelta(seconds=1)
            for ready, moving, changed in pending_resources
            if names & moving or slots & changed
        ),
        default=datetime.min,
    )


def generate_plan_by_drom(
    tasks,
    op_data,
    existing_targets=None,
    release_tasks=None,
    pending_arrangements=(),
    *,
    excluded_names=(),
):
    # 同时刻的回班与释放床位必须分别保留类型，并共用一次未来状态演算。
    batches = list(tasks.items()) + list((release_tasks or {}).items())
    if not batches:
        return []
    # 未来回班只能修改演算快照，不能提前释放正在休息的真实床位。
    # 批次另行复制，避免床位换人后把原入住者的时间套给新入住者。
    op_data = copy.copy(op_data)
    op_data.dorm = copy.deepcopy(op_data.dorm)
    op_data.group_dorm = copy.deepcopy(getattr(op_data, "group_dorm", []))
    op_data.operators = copy.deepcopy(op_data.operators)
    op_data.groups = copy.deepcopy(op_data.groups)
    op_data.group_shift_state = dict(op_data.group_shift_state)
    op_data.group_recovery_full_members = copy.deepcopy(
        getattr(op_data, "group_recovery_full_members", {})
    )
    op_data.group_recovery_return_time = dict(
        getattr(op_data, "group_recovery_return_time", {})
    )
    batches = copy.deepcopy(batches)
    ordered = sorted(batches, key=lambda batch: batch[0])
    result = []
    planned = set()
    release_positions = {bed.name: bed.position for bed in op_data.dorm if bed.name}
    current_time = datetime.now()
    pending_resources = [
        (task.time, *_arrangement_resources(task.plan)) for task in pending_arrangements
    ]
    for time, (dorms, rest_in_full) in ordered:
        logger.debug(f"{time},{dorms},{rest_in_full}")
        plan = {}
        for room in dorms:
            if not room.name or room.name not in op_data.operators:
                logger.debug(f"跳过已失效的宿舍回班项：{room}")
                continue
            # 回班可能因副表依赖延后，不能因此省略个人清退。
            if (
                rest_in_full is not None and room.name in planned
            ) or room.name in excluded_names:
                continue
            op = op_data.operators[room.name]
            if (
                op.multi_group
                and rest_in_full is not None
                and (not op.independent_rest or op_data.resting_binding_groups(op))
            ):
                continue
            # 不养闲人只释放个人床位；主班身份不能把清退变成整组回班。
            if not op.is_high() or (rest_in_full is None):
                if rest_in_full is None and op_data.skip_idle_dorm_release(op.name):
                    continue
                # 释放宿舍类别
                if (
                    op.current_room not in op_data.plan
                    or not 0 <= op.current_index < len(op_data.plan[op.current_room])
                ):
                    logger.debug(
                        f"跳过位置已失效的宿舍释放项：{op.name},"
                        f"{op.current_room},{op.current_index}"
                    )
                    continue
                target_room, target_index = op.current_room, op.current_index
                projected_bed = next(
                    (bed for bed in op_data.dorm if bed.name == op.name), None
                )
                # 未来回班可能关闭临时 Free 位，个人清退仍核验原来的床位。
                position = projected_bed.position if projected_bed is not None else None
                if position is None and rest_in_full is None:
                    position = release_positions.get(op.name)
                if position is None:
                    continue
                target_room, target_index = position
                if projected_bed is not None:
                    projected_bed.reset()
                if rest_in_full is None:
                    # 执行端按姓名和床位双重校验；同刻回满也分别记录身份，
                    # 避免空身份被跳过，或旧任务误清后来入住的人。
                    if op_data.config.free_room:
                        release_plan = {
                            target_room: ["Current"] * len(op_data.plan[target_room])
                        }
                        release_plan[target_room][target_index] = "Free"
                        result.append(
                            SchedulerTask(
                                task_plan=release_plan,
                                time=max(
                                    time,
                                    current_time - timedelta(seconds=1),
                                    _after_pending_arrangements(
                                        release_plan, pending_resources
                                    ),
                                ),
                                task_type=TaskTypes.RELEASE_DORM,
                                meta_data=op.name,
                            )
                        )
                        # 主班离宿后仍须参加后续回班，不能标记为已完成排班。
                        if not op.is_high():
                            planned.add(op.name)
                    continue
                plan.setdefault(
                    target_room, ["Current"] * len(op_data.plan[target_room])
                )[target_index] = "Free"
            else:
                # 拉全组
                agents = (
                    op_data.shift_group_members(op.group)
                    if op.group != ""
                    else [op.name]
                )
                for agent in agents:
                    if agent in excluded_names:
                        continue
                    o = op_data.operators[agent]
                    if o.independent_rest and o.name != op.name:
                        continue
                    target_room, target_index = o.room, o.index
                    if existing_targets and agent in existing_targets:
                        t_room, t_index = existing_targets[agent]
                        if (
                            t_room in op_data.plan
                            and t_index < len(op_data.plan[t_room])
                            and (
                                t_room not in plan
                                or plan[t_room][t_index] in ("Current", agent)
                            )
                        ):
                            native_agent = op_data.plan[t_room][t_index].agent
                            if native_agent == agent or not any(
                                getattr(d, "name", None) == native_agent for d in dorms
                            ):
                                target_room, target_index = t_room, t_index
                    if target_room not in plan:
                        plan[target_room] = ["Current"] * len(op_data.plan[target_room])
                    if plan[target_room][target_index] not in ("Current", agent):
                        target_room, target_index = o.room, o.index
                        if target_room not in plan:
                            plan[target_room] = ["Current"] * len(
                                op_data.plan[target_room]
                            )
                    plan[target_room][target_index] = agent
                    planned.add(agent)
        if not plan:
            continue
        if rest_in_full is not None:
            transitions = op_data.arrangement_group_transitions(plan)
            if not op_data.normalize_shared_arrangement(
                plan, transitions, excluded_names=excluded_names
            ):
                continue
            # Shared primaries kept off shift still participate in later returns.
            planned.difference_update(
                op.name
                for op in op_data.operators.values()
                if op.multi_group and op_data.resting_binding_groups(op, transitions)
            )
            op_data.commit_group_shifts(transitions)
            planned.update(rebalance_closing_dorm_slots(op_data, plan, planned))
        earliest = _after_pending_arrangements(plan, pending_resources)
        if rest_in_full:
            time = max(time, current_time, earliest)
            result.append(
                SchedulerTask(
                    task_plan=plan,
                    time=time,
                    task_type=TaskTypes.SHIFT_ON,
                )
            )
        else:
            added = False
            if rest_in_full is None and not (op_data.config.free_room):
                continue
            for idx in range(len(result) - 1, -1, -1):
                if result[idx].time < time:
                    break
                if result[idx].type == (
                    TaskTypes.RELEASE_DORM
                    if rest_in_full is None
                    else TaskTypes.SHIFT_ON
                ):
                    result.insert(
                        idx,
                        SchedulerTask(
                            task_plan=plan,
                            time=max(
                                result[idx].time,
                                current_time - timedelta(seconds=1),
                                earliest,
                            ),
                            task_type=TaskTypes.RELEASE_DORM
                            if rest_in_full is None
                            else TaskTypes.SHIFT_ON,
                        ),
                    )
                    added = True
                    break
            if not added:
                result.append(
                    SchedulerTask(
                        task_plan=plan,
                        time=max(time, current_time - timedelta(seconds=1), earliest)
                        if rest_in_full is None
                        else max(
                            time - timedelta(minutes=8),
                            current_time - timedelta(seconds=1),
                            earliest,
                        ),
                        task_type=TaskTypes.RELEASE_DORM
                        if rest_in_full is None
                        else TaskTypes.SHIFT_ON,
                    )
                )
    result.sort(key=lambda task: task.time)
    logger.debug("生成任务: " + ("||".join([str(t) for t in result])))
    return result


def plan_metadata(op_data, tasks, *, excluded_names=()):
    # 部分换班的剩余目标必须先确认，不能从中间驻员状态重建回班队列。
    if any(
        getattr(task, "backup_shift_active", False)
        or getattr(task, "group_shift_expected", {})
        for task in task_view(tasks, TaskScope.DISPATCH)
    ):
        # 保留未确认安排，但个人上限仍按已经实读的入住位置和期限独立清退。
        releases = plan_mood_limit_releases(op_data, previous_tasks=tasks)
        tasks[:] = [
            task for task in tasks if not getattr(task, "strict_mood_limit", False)
        ]
        tasks.extend(releases)
        return tasks
    from arknights_mower.utils.group_recovery import (
        group_recovery_deadline,
        observed_full_mood,
    )

    actual_data = op_data
    for group in config.conf.group_mood_gap_exclusions:
        actual_data.group_recovery_full_members.pop(group, None)
        actual_data.group_recovery_return_time.pop(group, None)
    op_data.refresh_idle_dorm_search()
    locked_tasks = [
        task
        for task in tasks
        if getattr(task, "product_shift_locked", False) or task.retains_execution
    ]
    locked_names, locked_slots = retained_task_reservations(op_data, tasks)
    for task in locked_tasks:
        locked_names.update(getattr(task, "product_lock_names", ()))
        locked_slots.update(getattr(task, "product_lock_slots", ()))
    locked_groups = {
        op_data.operators[name].group
        for name in locked_names
        if name in op_data.operators and op_data.operators[name].group
    }

    def recovery_reservations(group):
        names, slots = retained_task_reservations(
            actual_data, locked_tasks, returning_groups=[group] if group else ()
        )
        for pending in locked_tasks:
            names.update(getattr(pending, "product_lock_names", ()))
            slots.update(getattr(pending, "product_lock_slots", ()))
        groups = {
            actual_data.operators[name].group
            for name in names
            if name in actual_data.operators and actual_data.operators[name].group
        }
        return names, slots, groups

    locked_ids = {id(task) for task in locked_tasks}
    # 仅当副表处于激活状态时，保留既有回班任务中的工位快照，避免副表临时调整工位覆盖回班目标；
    # 当所有副表均已失效（恢复纯主表）时，所有干员统一按主表规划回班，避免副表工位粘滞。
    existing_targets = {}
    previous_windows = {}
    for task in tasks:
        if task.type != TaskTypes.SHIFT_ON or id(task) in locked_ids:
            continue
        names = {name for row in task.plan.values() for name in row}
        for name, (identity, start) in getattr(task, "return_windows", {}).items():
            if name in names:
                previous_windows[identity] = min(
                    start, previous_windows.get(identity, start)
                )
    if any(getattr(op_data, "plan_condition", [])):
        for t in tasks:
            if t.type == TaskTypes.SHIFT_ON and t.plan:
                for room, agents in t.plan.items():
                    for idx, name in enumerate(agents):
                        if name not in ("Current", "Free", ""):
                            existing_targets[name] = (room, idx)
    previous_releases = [t for t in tasks if getattr(t, "strict_mood_limit", False)]
    # 失败保留与切产物预约保留原对象和时间，只重算无关回班／清退。
    tasks = [
        t
        for t in tasks
        if t.type not in [TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM]
        or id(t) in locked_ids
    ]
    _, reserved_slots = dorm_task_reservations(
        op_data,
        [
            task
            for task in tasks
            if task.type != TaskTypes.FILL_DORM or task.retains_execution
        ],
    )
    vacancies = vacant_dorm_slots(op_data, reserved_slots)
    tasks = [
        task
        for task in tasks
        if task.type != TaskTypes.FILL_DORM
        or id(task) in locked_ids
        or getattr(task, "dorm_recovery_restore", [])
        or bool(_arrangement_resources(getattr(task, "dorm_fill_plan", task.plan))[1])
        and _arrangement_resources(getattr(task, "dorm_fill_plan", task.plan))[1]
        <= vacancies
    ]
    pending_arrangements = []
    # 按实际床位定时；迁移完成读房后会重建，避免清理尚未发生的未来位置。
    limited_releases = plan_mood_limit_releases(
        op_data, previous_tasks=previous_releases
    )
    limited_releases = [task for task in limited_releases if id(task) not in locked_ids]
    # 纠偏／重排是已经确定的安排，普通回班属于其后的派生计划。
    # 从最终驻员和床位计算，避免两个规划器各自从旧床位召回同一个人。
    # 已锁定的产物任务继续由上面的资源锁管理，不能提前视为完成。
    pending_arrangements = [
        task
        for task in sorted(tasks, key=lambda task: task.time)
        if task.type in (TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER)
        and id(task) not in locked_ids
        and task.plan
    ]
    observed_operators = op_data.operators
    op_data = op_data.project_arrangements(task.plan for task in pending_arrangements)
    _time = datetime.max
    min_resting_time = datetime.max
    _plan = {}
    _type = []
    # 第一个心情低的且小于3 则只休息半小时
    total_agent = sorted(
        (
            v
            for v in op_data.operators.values()
            if v.is_high()
            and v.name not in excluded_names
            and not v.multi_group
            and (not v.group or op_data.is_group_shift_anchor(v))
            and not v.room.startswith("dorm")
            and not v.is_resting()
            and not op_data.is_standby(v.name)
        ),
        key=lambda x: x.current_mood() - x.lower_limit,
    )

    # 工作心情预测与本轮休息等待窗口分别计算，重算不能重启等待。
    for agent in total_agent:
        min_resting_time = min(min_resting_time, agent.predict_exhaust())

    return_windows = {}
    now = datetime.now()

    def normal_return_time(dorms):
        operator = op_data.operators[dorms[0].name]
        members = (
            op_data.shift_group_members(operator.group)
            if operator.group
            else [operator.name]
        )
        identity = (
            tuple(
                sorted(
                    (
                        bed.name,
                        getattr(
                            op_data.operators[bed.name], "dorm_position_version", 0
                        ),
                    )
                    for bed in dorms
                )
            ),
            tuple(
                sorted(
                    (name, existing_targets.get(name, (op.room, op.index)), op.group)
                    for name in members
                    for op in [op_data.operators[name]]
                    if not operator.group or op_data.is_group_shift_anchor(op)
                )
            ),
        )
        start = previous_windows.get(identity, now)
        if operator.independent_rest:
            observed = observed_operators[operator.name]
            saved = getattr(observed, "individual_return_window", None)
            if saved is not None and saved[0] == identity:
                start = min(start, saved[1])
            # 具名组接管岗位期间没有个人回班任务，恢复窗口仍属于原休息周期。
            if observed.dorm_position_version == operator.dorm_position_version:
                observed.individual_return_window = (identity, start)
        for bed in dorms:
            return_windows[bed.name] = (identity, start)
        return min(bed.time for bed in dorms if bed.time is not None)

    logger.debug(f"预测最低休息时间为: {min_resting_time}")
    grouped_dorms = defaultdict(list)
    free_rooms = []
    # 固定宿舍恢复位始终参与回班计时；动态床位只处理当前排班仍为 Free 的位置。
    for dorm in op_data.all_dorms():
        if dorm in op_data.dorm and not op_data.is_effective_free_slot(dorm):
            continue
        if dorm.name and dorm.name in op_data.operators:
            operator = op_data.operators[dorm.name]
            return_names, return_slots, return_groups = recovery_reservations(
                operator.group
            )
            if (
                dorm.name not in return_names | set(excluded_names)
                and operator.group not in return_groups
                and dorm.position not in return_slots
                and (not operator.multi_group or operator.independent_rest)
                and (not operator.group or op_data.is_group_shift_anchor(operator))
            ):
                grouped_dorms[operator.group].append(dorm)
            if (
                dorm in op_data.dorm
                and dorm.name not in locked_names | set(excluded_names)
                and operator.group not in locked_groups
                and dorm.position not in locked_slots
                and not op_data.has_rest_mood_limit(dorm.name)
                and not op_data.skip_idle_dorm_release(dorm.name)
            ):
                free_rooms.append(dorm)
    new_task = {}
    for group_name, dorms in grouped_dorms.items():
        logger.debug(f"开始计算:{group_name}")
        logger.debug(f"开始计算:{dorms}")
        task_time = datetime.max
        # 高优先宿舍
        _high_dorms = [
            dorm
            for dorm in dorms
            if op_data.operators[dorm.name].is_high()
            and op_data.operators[dorm.name].resting_priority == "high"
        ]
        if len(_high_dorms) == 0:
            high_dorms = [
                dorm
                for dorm in dorms
                if op_data.operators[dorm.name].is_high()
                and op_data.operators[dorm.name].resting_priority != "standby"
            ]
            if not high_dorms:
                high_dorms = [
                    dorm for dorm in dorms if op_data.operators[dorm.name].is_high()
                ]
        else:
            high_dorms = _high_dorms
        if high_dorms and group_name:
            required, deadline = group_recovery_deadline(op_data, group_name, now=now)
            if (
                group_name in op_data.group_recovery_full_members
                and op_data.group_is_resting(group_name)
                and actual_data.group_is_resting(group_name)
            ):
                actual_data.group_recovery_full_members[group_name] = list(
                    op_data.group_recovery_full_members[group_name]
                )
                if group_name in op_data.group_recovery_return_time:
                    actual_data.group_recovery_return_time[group_name] = (
                        op_data.group_recovery_return_time[group_name]
                    )
            if required or deadline is not None:
                if deadline is None:
                    continue
                task_time = deadline
            else:
                if not any(dorm.time is not None for dorm in high_dorms):
                    continue
                task_time = normal_return_time(high_dorms)
            if task_time not in new_task:
                new_task[task_time] = (high_dorms, deadline is not None)
            else:
                combined = new_task[task_time][0] + high_dorms
                full = new_task[task_time][1] or deadline is not None
                new_task[task_time] = (combined, full)
        if high_dorms and not group_name:
            # 单独添加，最后合并
            # high_droms 如果触发急救模式，后面的移送到急救前
            for room in high_dorms:
                if room.time and room.name:
                    rest_in_full = op_data.operators[room.name].rest_in_full
                    task_time = (
                        normal_return_time([room]) if not rest_in_full else room.time
                    )
                    if task_time not in new_task:
                        new_task[task_time] = ([room], rest_in_full)
                    else:
                        combined = new_task[task_time][0] + [room]
                        new_task[task_time] = (
                            combined,
                            new_task[task_time][1] or rest_in_full,
                        )
    release_tasks = {}
    if op_data.config.free_room:
        for room in free_rooms:
            operator = op_data.operators[room.name]
            observed_full = (
                operator.time_stamp is not None
            ) and operator.mood >= operator.upper_limit
            if (room.time or observed_full) and room.name:
                # 清退使用个人回满时刻；主班抢床交给轮休层级接管。
                task_time = datetime.now() if observed_full else room.time
                release_tasks.setdefault(task_time, ([], None))[0].append(room)
    # 独立的个人离宿时刻不受整组回满、不养闲人和任务合并影响。
    generated = generate_plan_by_drom(
        new_task,
        op_data,
        existing_targets=existing_targets,
        release_tasks=release_tasks,
        pending_arrangements=pending_arrangements,
        excluded_names=excluded_names,
    )
    for task in generated:
        if task.type == TaskTypes.SHIFT_ON:
            task.return_windows = {
                name: return_windows[name]
                for row in task.plan.values()
                for name in row
                if name in return_windows
            }
    tasks.extend(generated)
    # 全组都已达到各自上限并离宿时，不再有床位能派生回班任务。
    # 复用原回班及临时床关闭流程，避免最后一次离宿后把整组留在空闲。
    returning = {
        name for task in generated for names in task.plan.values() for name in names
    }
    busy = busy_resting_names()
    pending_resources = [
        (task.time, *_arrangement_resources(task.plan)) for task in pending_arrangements
    ]
    for op in op_data.operators.values():
        if (
            not op.is_high()
            or op.name in excluded_names
            or op.multi_group
            and (not op.independent_rest or op_data.resting_binding_groups(op))
            or op.group
            and not op_data.is_group_shift_anchor(op)
            or op.room.startswith("dorm")
            or op.current_room
        ):
            continue
        required, deadline = (
            group_recovery_deadline(op_data, op.group, now=now)
            if op.group
            else ([], None)
        )
        if not (
            op_data.rest_mood_complete(op.name)
            or op.independent_rest
            and observed_full_mood(op)
            or op.group
            and observed_full_mood(op)
            and (
                required
                or config.conf.group_rest_in_full_on_mood_gap
                and op_data.group_is_resting(op.group)
            )
        ):
            continue
        if required and deadline is None:
            continue
        if op.group in op_data.group_recovery_full_members:
            actual_data.group_recovery_full_members[op.group] = list(
                op_data.group_recovery_full_members[op.group]
            )
            if op.group in op_data.group_recovery_return_time:
                actual_data.group_recovery_return_time[op.group] = (
                    op_data.group_recovery_return_time[op.group]
                )
        members = (
            set(op_data.shift_group_members(op.group)) if op.group else {op.name}
        ) - set(excluded_names)
        anchors = {
            name
            for name in members
            if not op_data.operators[name].multi_group
            or op_data.operators[name].independent_rest
        }
        return_names, return_slots, return_groups = recovery_reservations(op.group)
        if (
            anchors & returning
            or members & (return_names | busy)
            or op.group in return_groups
        ):
            continue
        workers = [
            op_data.operators[name]
            for name in members
            if op_data.is_group_shift_anchor(op_data.operators[name])
        ]
        if (
            not required
            and deadline is None
            and not all(
                not worker.current_room
                and (
                    op_data._can_standby(worker)
                    or (
                        has_resting_mood(worker)
                        and worker.current_mood() >= worker.upper_limit
                    )
                )
                for worker in workers
            )
        ):
            continue
        plan = {}
        _native_return(op_data, plan, members, excluded_names=excluded_names)
        recalled = rebalance_closing_dorm_slots(
            op_data.project_arrangements([]), plan, members
        )
        if recalled & (return_names | busy) or any(
            (room, index) in return_slots
            for room, names in plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        ):
            continue
        tasks.append(
            SchedulerTask(
                task_plan=plan,
                time=max(
                    deadline or datetime.now(),
                    _after_pending_arrangements(plan, pending_resources),
                ),
                task_type=TaskTypes.SHIFT_ON,
            )
        )
        returning.update(members | recalled)
    return_tasks = sorted(
        (
            task
            for task in tasks
            if task.type == TaskTypes.SHIFT_ON and id(task) not in locked_ids
        ),
        key=lambda task: task.time,
    )
    for op in op_data.operators.values():
        if (
            op.group
            or op.name in returning | locked_names | busy
            or op.name in excluded_names
            or (op.room, op.index) in locked_slots
            or not op_data.is_standby(op.name)
        ):
            continue
        return_plan = {}
        _native_return(op_data, return_plan, [op.name], excluded_names=excluded_names)
        earliest = _after_pending_arrangements(return_plan, pending_resources)
        for task in return_tasks:
            slots = task.plan.get(op.room, ["Current"] * len(op_data.plan[op.room]))
            if task.time < earliest or slots[op.index] != "Current":
                continue
            _native_return(op_data, task.plan, [op.name], excluded_names=excluded_names)
            returning.add(op.name)
            break
    tasks.extend(limited_releases)
    merge_release_dorm(tasks, config.conf.merge_interval)
    return tasks


def plan_mood_limit_releases(op_data, *, recovery_targets=None, previous_tasks=()):
    previous = {
        task.meta_data: task
        for task in previous_tasks
        if getattr(task, "strict_mood_limit", False)
    }
    now = datetime.now()
    result = [
        task
        for task in previous_tasks
        if task.retains_execution
        and (
            getattr(task, "strict_mood_limit", False)
            or recovery_targets is not None
            and getattr(task, "emergency_recovery_release", False)
        )
    ]
    retained_strict = {
        name
        for task in result
        if getattr(task, "strict_mood_limit", False)
        for name in task.release_dorm_targets()
    }
    retained_recovery = {
        name
        for task in result
        if getattr(task, "emergency_recovery_release", False)
        for name in task.release_dorm_targets()
    }
    for bed in op_data.all_dorms():
        op = op_data.operators.get(bed.name)
        if op is None or (op.current_room, op.current_index) != bed.position:
            continue
        if not op_data.is_recovery_dorm(bed, op.name):
            continue
        target = (recovery_targets or {}).get(op.name)
        if (
            target is not None
            and op.name not in retained_recovery
            and 0 <= target <= op.upper_limit
            and not (target == op.upper_limit and op_data.has_rest_mood_limit(op.name))
            and has_resting_mood(op)
        ):
            due = None
            if op.mood >= target:
                due = now
            elif (
                bed.time is not None
                and op.time_stamp is not None
                and bed.time > op.time_stamp
                and op.mood < op.upper_limit
            ):
                due = op.time_stamp + (bed.time - op.time_stamp) * (
                    (target - op.mood) / (op.upper_limit - op.mood)
                )
            if due is not None:
                room, index = bed.position
                names = ["Current"] * len(op_data.plan[room])
                names[index] = "Free"
                task = SchedulerTask(
                    time=max(now, due),
                    task_plan={room: names},
                    task_type=TaskTypes.RELEASE_DORM,
                    meta_data=op.name,
                    mood_limit=target,
                )
                task.emergency_recovery_release = True
                result.append(task)
        if not op_data.has_rest_mood_limit(bed.name) or op.name in retained_strict:
            continue
        complete = op_data.rest_mood_complete(op.name)
        if complete:
            due = now
        elif bed.time is not None:
            due = max(now, bed.time)
        else:
            # 未读到恢复时间时不能凭默认心情提前释放。
            continue
        room, index = bed.position
        names = ["Current"] * len(op_data.plan[room])
        names[index] = "Free"
        source = (bed.time, op.upper_limit, complete)
        task = previous.get(op.name)
        if (
            task is None
            or task.plan != {room: names}
            or getattr(task, "mood_limit_source", None) != source
        ):
            task = SchedulerTask(
                time=due,
                task_plan={room: names},
                task_type=TaskTypes.RELEASE_DORM,
                meta_data=op.name,
                strict_mood_limit=True,
                mood_limit=op.upper_limit,
            )
            task.mood_limit_source = source
        result.append(task)
    return result


def prioritize_new_dorm_recovery(
    op_data,
    plan,
    reserved_slots=(),
    preceding_plan=None,
    *,
    reserved_names=(),
    configuration_changed=False,
):
    """宿舍事件按恢复层级分配单回位及普通位，同级优先保留实际原位。

    配置的宿舍顺序表达各类位置的恢复速度偏好；仅心情变化不搬床。
    只修改投影计划，保留住客集合、预约和真实恢复标记。
    """
    from arknights_mower.utils.dorm_recovery import single_recovery_bed_cost
    from arknights_mower.utils.dorm_skills import is_single_recovery_manager

    if not plan and not preceding_plan and not configuration_changed:
        return plan
    projected = op_data.project_arrangements([preceding_plan or {}, plan])
    beds = [
        bed
        for bed in projected.ordered_dorms()
        if projected.is_effective_free_slot(bed)
    ]
    explicit_names = {
        name
        for arrangement in (preceding_plan or {}, plan)
        for names in arrangement.values()
        for name in names
    }
    locked_rooms = {
        room for room, _ in set(reserved_slots) | set(op_data.reserved_product_beds)
    }
    # 其他任务尚未执行的床位预约不能作为本轮可移动的住客。
    for bed in op_data.dorm:
        op = op_data.operators.get(bed.name)
        if op is not None and (
            bed.name not in explicit_names
            and (op.current_room, op.current_index) != bed.position
        ):
            locked_rooms.add(bed.position[0])
    for bed in beds:
        if bed.name and (
            bed.name not in op_data.operators
            or bed.name in reserved_names
            or op_data.is_free_room_excluded(bed.name)
            or projected.rest_mood_complete(bed.name)
            or resting_tier(projected, bed.name) == RestingTier.EXCLUDED
        ):
            locked_rooms.add(bed.position[0])
    beds = [bed for bed in beds if bed.position[0] not in locked_rooms]
    actual = {
        bed.position: old.name
        if (old := op_data.get_current_operator(*bed.position))
        else ""
        for bed in beds
    }
    if not configuration_changed and all(actual[b.position] == b.name for b in beds):
        return plan

    # 保留 alpha 显式高优位/低优位的完整顺序；同房普通床为一个同速组。
    first = {}
    for bed in sorted(beds, key=lambda bed: bed.position):
        first.setdefault(bed.position[0], bed.position)
    groups = []
    for bed in beds:
        if (
            groups
            and bed.position != first[bed.position[0]]
            and groups[-1][0].position[0] == bed.position[0]
            and groups[-1][0].position != first[bed.position[0]]
        ):
            groups[-1].append(bed)
        else:
            groups.append([bed])
    now = datetime.now()
    # 满心情垫位者与空床同级，不能仅为填满前方空床而搬动满心情住客。
    filler_tier = int(RestingTier.EXCLUDED) + 1

    def tier(name):
        if not name:
            return filler_tier
        op = projected.operators[name]
        if has_resting_mood(op, now) and resting_mood(op, now) >= op.upper_limit:
            return filler_tier
        return resting_tier(projected, name)

    names = [bed.name for bed in beds if bed.name]
    names.sort(key=lambda name: resting_key(projected, name, now))
    names = crafting_rest_order(projected, names)
    desired = sorted(tier(bed.name) for group in groups for bed in group)
    allocations = {}
    quotas = []
    offset = 0
    for group in groups:
        quotas.append(Counter(desired[offset : offset + len(group)]))
        offset += len(group)

    def retain(group, quota, *, completed_only=False):
        for bed in group:
            if bed.position in allocations:
                continue
            level = tier(bed.name)
            if completed_only and (not bed.name or level != filler_tier):
                continue
            if (
                bed.name
                and actual[bed.position] == bed.name
                and bed.name in names
                and quota[level]
            ):
                allocations[bed.position] = bed.name
                quota[level] -= 1
                if bed.name:
                    names.remove(bed.name)

    def fill(group, quota, *, include_fillers=False):
        vacant = iter(bed for bed in group if bed.position not in allocations)
        for level, count in sorted(quota.items()):
            if level == filler_tier and not include_fillers:
                continue
            for _ in range(count):
                bed = next(vacant)
                name = next((name for name in names if tier(name) == level), "")
                allocations[bed.position] = name
                quota[level] -= 1
                if name:
                    names.remove(name)

    targets = [
        i
        for i, group in enumerate(groups)
        if group[0].position == first[group[0].position[0]]
    ]
    ordinary = [i for i in range(len(groups)) if i not in targets]
    # 满心情住客先保留可用原位，不参与快床补位；更高层级仍可让其让床。
    for group, quota in zip(groups, quotas):
        retain(group, quota, completed_only=True)
    # 配额已经遵循完整配置顺序；同级单回保位，余下目标先于普通床保位补齐。
    for index in targets:
        retain(groups[index], quotas[index])
    for index in targets:
        fill(groups[index], quotas[index])
    for index in ordinary:
        retain(groups[index], quotas[index])
    for index in ordinary:
        fill(groups[index], quotas[index])
    # 被未恢复者挤出的满心情垫位者按完整顺序补空，不优先搬去后续单回位。
    for group, quota in zip(groups, quotas):
        fill(group, quota, include_fillers=True)
    if any(
        allocations[groups[index][0].position] != actual[groups[index][0].position]
        for index in targets
    ):
        # 单回归属改变时，同级恢复者重新按缺口分配；满心情垫位保留兼容原位。
        remaining = [
            bed.name for bed in beds if bed.name and tier(bed.name) != filler_tier
        ]
        allocations = {
            position: name
            for position, name in allocations.items()
            if tier(name) == filler_tier
        }
        for group in groups:
            slots = [bed for bed in group if bed.position not in allocations]
            residents = {actual[bed.position] for bed in slots}
            remaining.sort(
                key=lambda name: (
                    *resting_key(projected, name, now),
                    name not in residents,
                )
            )
            remaining = crafting_rest_order(projected, remaining)
            selected, remaining = remaining[: len(slots)], remaining[len(slots) :]
            for bed in slots:
                name = actual[bed.position]
                if name in selected:
                    allocations[bed.position] = name
                    selected.remove(name)
            for bed in slots:
                if bed.position not in allocations:
                    allocations[bed.position] = selected.pop(0)

    all_beds = [bed for bed in projected.dorm if projected.is_effective_free_slot(bed)]
    providers = [
        name
        for name in allocations.values()
        if name and tier(name) != filler_tier and is_single_recovery_manager(name)
    ]
    providers.sort(key=lambda name: resting_key(projected, name, now))
    placed = set()
    for name in providers:
        source = next(bed for bed in beds if allocations[bed.position] == name)
        destination = next(
            (
                bed
                for bed in beds
                if allocations[bed.position] not in placed
                and single_recovery_bed_cost(bed, all_beds)
                < single_recovery_bed_cost(source, all_beds)
                and (
                    not allocations[bed.position]
                    or tier(allocations[bed.position]) == tier(name)
                )
            ),
            None,
        )
        if destination is not None:
            allocations[source.position], allocations[destination.position] = (
                allocations[destination.position],
                name,
            )
        placed.add(name)
    result = copy.deepcopy(plan)
    for bed in beds:
        name = allocations[bed.position]
        if name != bed.name:
            room, index = bed.position
            result.setdefault(room, ["Current"] * len(projected.plan[room]))[index] = (
                name or "Free"
            )
    return result


def plan_dorm_isolation(op_data, plan, reserved_slots=(), *, reserved_names=()):
    """入住前交换动态床位以减少同宿，保护固定驻员和任务预约。"""
    if not config.conf.dorm_isolation or not plan:
        return plan
    newcomers = {
        name
        for room, row in plan.items()
        if room.startswith("dorm")
        for name in row
        if name in op_data.operators and not op_data.operators[name].is_resting()
    }
    if not newcomers:
        return plan
    projected = op_data.project_arrangements([plan])
    beds = [
        bed
        for bed in projected.ordered_dorms()
        if projected.is_effective_free_slot(bed)
    ]
    first_positions = {}
    for bed in beds:
        first_positions[bed.position[0]] = min(
            first_positions.get(bed.position[0], bed.position), bed.position
        )
    reserved = set(reserved_slots) | set(op_data.reserved_product_beds)
    protected_names = set(reserved_names)
    explicit_names = {name for row in plan.values() for name in row}
    for bed in op_data.dorm:
        op = op_data.operators.get(bed.name)
        if (
            op is not None
            and bed.name not in explicit_names
            and (op.current_room, op.current_index) != bed.position
        ):
            reserved.add(bed.position)
            protected_names.add(bed.name)
    movable = [
        bed
        for bed in beds
        if bed.position not in reserved
        and bed.name not in protected_names
        and (
            not bed.name
            or bed.name in projected.operators
            and not projected.is_free_room_excluded(bed.name)
            and resting_tier(projected, bed.name) != RestingTier.EXCLUDED
        )
        and (bed.position != first_positions[bed.position[0]] or bed.name in newcomers)
    ]
    if len(movable) < 2:
        return plan
    result = copy.deepcopy(plan)

    def room_cost(room):
        row = projected.get_current_room(room, True)
        for bed in beds:
            if bed.position[0] == room:
                row[bed.position[1]] = bed.name
        names = set(row) - {"", "Free", "Current"}
        return sum(
            len(shared := names.intersection(group)) * (len(shared) - 1) // 2
            for group in config.conf.dorm_isolation
        )

    allocation_groups = []
    for bed in beds:
        if (
            allocation_groups
            and bed.position != first_positions[bed.position[0]]
            and allocation_groups[-1][0].position[0] == bed.position[0]
            and allocation_groups[-1][0].position != first_positions[bed.position[0]]
        ):
            allocation_groups[-1].append(bed)
        else:
            allocation_groups.append([bed])
    now = datetime.now()

    def recovery_rank(bed):
        op = projected.operators.get(bed.name)
        if (
            op is None
            or has_resting_mood(op, now)
            and resting_mood(op, now) >= op.upper_limit
        ):
            return int(RestingTier.EXCLUDED) + 1
        return resting_tier(projected, bed.name)

    def recovery_score():
        return tuple(
            rank
            for group in allocation_groups
            for rank in sorted(recovery_rank(bed) for bed in group)
        )

    # 先减少同宿，再按恢复层级选择可行的单回对象；同速普通位不因心情换床。
    # 隔离及层级评分严格下降，单回让位后仍可继续补回更高层级的对象。
    for _ in range(len(movable) ** 2):
        best = None
        best_key = (0, recovery_score(), 0, 0)
        for offset, first in enumerate(movable):
            for second in movable[offset + 1 :]:
                rooms = {first.position[0], second.position[0]}
                target_moves = sum(
                    bed.position == first_positions[bed.position[0]]
                    for bed in (first, second)
                )
                if first.name == second.name or len(rooms) < 2 and not target_moves:
                    continue
                before = sum(room_cost(room) for room in rooms)
                first.name, second.name = second.name, first.name
                gain = before - sum(room_cost(room) for room in rooms)
                rank = recovery_score()
                first.name, second.name = second.name, first.name
                if gain < 0 or gain == 0 and not target_moves:
                    continue
                key = (
                    -gain,
                    rank,
                    target_moves,
                    sum(
                        bool(bed.name) and bed.name not in newcomers
                        for bed in (first, second)
                    ),
                )
                if key < best_key:
                    best, best_key = (first, second), key
        if best is None:
            break
        first, second = best
        first.name, second.name = second.name, first.name
        for bed in best:
            room, index = bed.position
            result.setdefault(room, ["Current"] * len(projected.plan[room]))[index] = (
                bed.name or "Free"
            )
    return result


def try_reorder(op_data, new_plan, *, tasks=()):
    reserved_names, reserved_slots = retained_task_reservations(op_data, tasks)
    # 移除被拉去上班的替班
    assigned_names = {name for names in new_plan.values() for name in names}
    for d in op_data.dorm:
        if (
            d.name in assigned_names
            and d.name not in reserved_names
            and d.position not in reserved_slots
        ):
            d.name = ""
            d.time = None
    # 复制副本，防止原本的dorm错误触发纠错
    dorm = copy.deepcopy(op_data.dorm)
    logger.debug(op_data.dorm)
    vip = sum(1 for key in op_data.plan.keys() if key.startswith("dorm"))
    logger.debug(f"当前vip个数{vip}")
    if vip == 0:
        return

    # self.dorm 是默认排班中的潜在床位池；副表可能把其中一部分 Free
    # 临时覆盖成固定干员。重排只能操作当前有效排班里仍为 Free 的位置。
    protected_indices = {
        index
        for index, bed in enumerate(dorm)
        if bed.position in reserved_slots or bed.name in reserved_names
    }
    transitions = op_data.arrangement_group_transitions(new_plan)
    effective_free_indices = [
        idx
        for idx, room in enumerate(dorm)
        if op_data.is_effective_free_slot(
            room,
            active_groups={g for g, resting in transitions.items() if resting},
            inactive_groups={g for g, resting in transitions.items() if not resting},
        )
        and idx not in protected_indices
    ]
    blocked_indices = (
        set(range(len(dorm))) - set(effective_free_indices) - protected_indices
    )
    for idx in blocked_indices:
        dorm[idx].name = ""
        dorm[idx].time = None
    plan = {}
    logger.debug(f"更新房间信息{dorm}")
    destinations = {bed.position for bed in dorm if bed.name}
    effective_positions = {dorm[idx].position for idx in effective_free_indices}
    for index, room in enumerate(dorm):
        if room.name and index not in protected_indices:
            op = op_data.operators[room.name]
            room_name, idx = room.position
            if not (op.current_room == room_name and op.current_index == idx):
                if room_name not in plan:
                    plan[room_name] = ["Current"] * 5
                plan[room_name][idx] = room.name
                old_position = (op.current_room, op.current_index)
                if (
                    old_position in effective_positions
                    and old_position not in destinations
                ):
                    plan.setdefault(op.current_room, ["Current"] * 5)[
                        op.current_index
                    ] = "Free"
    # 生成移动任务
    return prioritize_new_dorm_recovery(
        op_data,
        plan,
        reserved_slots,
        preceding_plan=new_plan,
        reserved_names=reserved_names,
    )


def next_workshop_task_time(tasks, earliest=None):
    """Keep workshop jobs close together but outside the 1.5-second collision window."""
    candidate = earliest if earliest is not None else datetime.now()
    gap = timedelta(seconds=2)
    for task in sorted(tasks, key=lambda task: task.time):
        if task.time >= candidate + gap:
            break
        if abs(task.time - candidate) < gap:
            candidate = task.time + gap
    return candidate


def try_workshop_tasks(op_data, tasks, *, minimum_mood=22):
    # 如果没有其他任务则进行加工站干员检查
    from arknights_mower.utils.workshop_automation import (
        refresh_workshop_after_inventory_change,
        restore_if_no_plans,
        workshop_task_current,
    )
    from arknights_mower.utils.workshop_limits import (
        workshop_admission_block,
    )
    from arknights_mower.utils.workshop_recommendation import (
        prioritize_workshop_settings,
    )

    if not refresh_workshop_after_inventory_change():
        return
    restore_if_no_plans()
    # 跑单/专精换人可能将加工推迟到五分钟之后，不能把它当作没有待办。
    pending_operators = {
        task.meta_data
        for task in tasks
        if task.type == TaskTypes.WORKSHOP and workshop_task_current(task)
    }
    inventory_data = get_inventory_counts()
    if config.conf.workshop_settings and inventory_data:
        for item in prioritize_workshop_settings(config.conf.workshop_settings):
            if item.operator in pending_operators:
                continue
            if not item.enabled:
                logger.info(f"{item.operator}加工站任务被禁用，跳过")
                continue
            reason = workshop_admission_block(
                op_data, item, inventory_data, tasks, minimum_mood=minimum_mood
            )
            if reason:
                logger.info(f"{item.operator}加工跳过：{reason}")
                continue
            if item.operator not in op_data.operators:
                logger.info(f"自动添加{item.operator}至干员数据列表")
                op_data.add(Operator(item.operator, ""))
            source = "专精备料" if item.source == "mastery" else "手动配置"
            logger.info(f"{item.operator}满足使用条件，生成加工站任务（{source}）")
            task = SchedulerTask(
                time=next_workshop_task_time(tasks),
                task_type=TaskTypes.WORKSHOP,
                meta_data=item.operator,
            )
            from arknights_mower.utils.workshop_automation import (
                stamp_workshop_task,
            )

            stamp_workshop_task(task)
            tasks.append(task)
            pending_operators.add(item.operator)
    else:
        if not config.conf.workshop_settings:
            logger.debug("未配置加工站任务，跳过任务生成")
        else:
            logger.info("尚无仓库读数，无法核验加工原料及成品库存，跳过任务生成")


def try_add_release_dorm(plan, time, op_data, tasks, *, empty_only=False):
    """共用空床与层级接管；不养闲人只控制满心情清退任务创建。"""
    if plan:
        for names in plan.values():
            for name in names:
                if name not in op_data.operators or time is None:
                    continue
                _, bed = op_data.get_dorm_by_name(name)
                if (
                    bed is not None
                    and op_data.is_effective_free_slot(bed)
                    and bed.time is not None
                    and bed.time < time
                ):
                    add_release_dorm(tasks, op_data, name)
        return

    try:
        now = datetime.now()
        reserved_names, reserved_slots = dorm_task_reservations(op_data, tasks)
        vacancies = vacant_dorm_slots(op_data, reserved_slots)
        priority_only = empty_only and not vacancies
        logger.info("检查宿舍空床与恢复接管")
        candidates = dorm_candidates(op_data, reserved_names, now=now)
        recovery_names = sorted(
            candidates.recovering
            + [
                name
                for name in candidates.estimated_recovering
                if name in op_data.operators
                and resting_tier(op_data, name) <= RestingTier.PRIORITY_REPLACEMENT
            ],
            key=lambda name: (
                resting_tier(op_data, name),
                dorm_candidate_mood(op_data, name, now)
                - op_data.operators[name].upper_limit,
            ),
        )
        recovery_names = crafting_rest_order(op_data, recovery_names)
        if priority_only:
            recovery_names = [
                name
                for name in recovery_names
                if resting_tier(op_data, name) <= RestingTier.PRIORITY_REPLACEMENT
            ]
            if not recovery_names:
                return
        recovering = recovery_names.copy()
        waiting = next(iter(recovering), None)
        full = [
            name
            for name in candidates.filling
            if name not in candidates.recovering and name not in candidates.unknown
        ]
        search_unknown = bool(candidates.unknown) and not priority_only
        if waiting is None and not candidates.filling:
            return

        filling_vacancies = bool(vacancies)
        arrangement = {}
        beds_to_visit = op_data.ordered_dorms()
        for bed in beds_to_visit:
            room, index = bed.position
            if room in arrangement and arrangement[room][index] != "Current":
                continue
            if bed.position in reserved_slots or not op_data.is_effective_free_slot(
                bed
            ):
                continue
            if filling_vacancies:
                if bed.position not in vacancies:
                    continue
                occupant = None
                waiting = next(
                    (
                        name
                        for name in recovering
                        if op_data.dorm_capacity_allows(
                            name, bed.position, plan=arrangement
                        )
                    ),
                    None,
                )
            else:
                occupant = op_data.operators.get(bed.name)
                if (
                    occupant is None
                    or (occupant.current_room, occupant.current_index) != bed.position
                    or op_data.is_free_room_excluded(occupant.name)
                ):
                    continue
                waiting = next(
                    (
                        name
                        for name in recovering
                        if bed_takeover_allowed(op_data, name, occupant.name)
                        and op_data._slot_takable(bed, requester=name, plan=arrangement)
                    ),
                    None,
                )
                if waiting is None:
                    continue

            if waiting is not None:
                incoming = waiting
                recovering.remove(incoming)
                waiting = next(iter(recovering), None)
            elif search_unknown:
                # 未知心情统一通过游戏心情升序选人，不能把默认 24 当实读。
                incoming = "Free"
            else:
                incoming = next(
                    (
                        name
                        for name in full
                        if op_data.dorm_capacity_allows(
                            name, bed.position, plan=arrangement
                        )
                    ),
                    None,
                )
                if incoming is None:
                    continue
                full.remove(incoming)
                if incoming in op_data.operators:
                    op_data.operators[incoming].dorm_mood_fallback = bed.position[0]
                else:
                    # 未登记卡片不能成为换班预演的明确姓名；实际选人再登记。
                    incoming = "Free"
            if filling_vacancies and config.conf.dorm_isolation and incoming != "Free":
                available = [
                    candidate
                    for candidate in op_data.dorm
                    if candidate.position in vacancies
                    and arrangement.get(
                        candidate.position[0],
                        ["Current"] * len(op_data.plan[candidate.position[0]]),
                    )[candidate.position[1]]
                    == "Current"
                ]
                selected = min(
                    available,
                    key=lambda candidate: op_data.dorm_isolation_cost(
                        incoming, *candidate.position, plan=arrangement
                    ),
                )
                if selected is not bed:
                    beds_to_visit.append(bed)
                room, index = selected.position
                if incoming not in recovery_names:
                    op_data.operators[incoming].dorm_mood_fallback = room
            arrangement.setdefault(room, ["Current"] * len(op_data.plan[room]))[
                index
            ] = incoming

        if not arrangement:
            return
        task = SchedulerTask(
            time=now,
            task_plan=arrangement,
            task_type=TaskTypes.FILL_DORM
            if filling_vacancies
            else TaskTypes.NOT_SPECIFIC,
        )
        task.dorm_fill_plan = copy.deepcopy(arrangement)
        if filling_vacancies:
            simplify_dorm_fill(task, tasks, now, op_data)
        if not getattr(task, "simple_dorm_fill", False):
            task.plan = prioritize_new_dorm_recovery(op_data, task.plan, reserved_slots)
        isolated = plan_dorm_isolation(
            op_data, task.plan, reserved_slots, reserved_names=reserved_names
        )
        if isolated != task.plan:
            fill_names = {
                name for row in task.dorm_fill_plan.values() for name in row
            } - {"Current", "Free", ""}
            task.dorm_fill_plan = {
                room: [
                    name if name in fill_names or name == "Free" else "Current"
                    for name in row
                ]
                for room, row in isolated.items()
                if room.startswith("dorm")
            }
        task.plan = isolated
        tasks.append(task)
        logger.info(
            "添加%s任务完成：%s",
            "宿舍补位"
            if filling_vacancies
            else "高优恢复"
            if priority_only
            else "宿舍恢复接管",
            task.plan,
        )
    except Exception as ex:
        logger.exception(ex)


def add_release_dorm(tasks, op_data, name):
    if not op_data.config.free_room or op_data.skip_idle_dorm_release(name):
        return
    _idx, __dorm = op_data.get_dorm_by_name(name)
    if (
        __dorm.time > datetime.now()
        and find_next_task(
            tasks,
            task_type=TaskTypes.RELEASE_DORM,
            meta_data=name,
            scope=TaskScope.PENDING,
        )
        is None
    ):
        _free = op_data.operators[name]
        if _free.current_room.startswith("dorm"):
            __plan = {_free.current_room: ["Current"] * 5}
            __plan[_free.current_room][_free.current_index] = "Free"
            task = SchedulerTask(
                time=__dorm.time,
                task_type=TaskTypes.RELEASE_DORM,
                task_plan=__plan,
                meta_data=name,
            )
            tasks.append(task)
            logger.info(name + " 新增释放宿舍任务")
            logger.debug(str(task))


def set_type_enum(value):
    if value is None:
        return TaskTypes.NOT_SPECIFIC
    if isinstance(value, TaskTypes):
        return value
    if isinstance(value, str):
        for task_type in TaskTypes:
            if value.upper() == task_type.display_value.upper():
                return task_type
    return TaskTypes.NOT_SPECIFIC


def merge_release_dorm(tasks, merge_interval, *, previous_tasks=None):
    """同一时间窗口按宿舍合并清退，逐人保留原床位身份。"""

    def summaries(queue):
        result = {}
        for task in sorted(queue, key=lambda task: task.time):
            if getattr(task, "strict_mood_limit", False):
                continue
            for name, (room, index) in task.release_dorm_targets().items():
                result.setdefault(room, {}).setdefault(task.time, []).append(
                    (index, name)
                )
        return {
            room: tuple((time, tuple(sorted(names))) for time, names in batches.items())
            for room, batches in result.items()
        }

    previous = summaries(tasks if previous_tasks is None else previous_tasks)
    tasks.sort(key=lambda task: task.time)
    chunks, rooms = [], {}
    latest = None

    def flush():
        if rooms:
            chunk = [rooms[room] for room in sorted(rooms)]
            for task in chunk:
                task.release_start = getattr(task, "release_start", task.time)
                task.time = latest
            chunks.append(chunk)
            rooms.clear()

    for task in reversed(tasks):
        targets = task.release_dorm_targets()
        ordinary = (
            task.type == TaskTypes.RELEASE_DORM
            and not getattr(task, "strict_mood_limit", False)
            and not getattr(task, "product_shift_locked", False)
            and not task.retains_execution
            and len(task.plan) == 1
            and targets
            and all(
                name in ("Current", "Free")
                for row in task.plan.values()
                for name in row
            )
            and len(targets) == sum(row.count("Free") for row in task.plan.values())
        )
        if not ordinary:
            flush()
            chunks.append([task])
            latest = None
            continue
        start = getattr(task, "release_start", task.time)
        room = next(iter(task.plan))
        batch = rooms.get(room)
        existing = batch.release_dorm_targets() if batch is not None else {}
        if rooms and (
            any(
                getattr(queued, "emergency_recovery_release", False)
                != getattr(task, "emergency_recovery_release", False)
                for queued in rooms.values()
            )
            or (latest != start and latest - start >= timedelta(minutes=merge_interval))
            or existing.keys() & targets.keys()
            or set(existing.values()) & set(targets.values())
        ):
            flush()
            latest = None
            batch = None
        if not rooms:
            latest = task.time
        if batch is None:
            rooms[room] = task
            continue
        for index, name in enumerate(task.plan[room]):
            if name == "Free":
                batch.plan[room][index] = name
        batch.release_targets = targets | existing
        batch.meta_data = ",".join(batch.release_targets)
        batch.release_start = min(start, getattr(batch, "release_start", batch.time))
    flush()
    tasks[:] = [task for chunk in reversed(chunks) for task in chunk]
    for room, batches in summaries(tasks).items():
        if batches != previous.get(room):
            detail = "；".join(
                f"{time:%H:%M:%S}：{'、'.join(name for _, name in names)}"
                for time, names in batches
            )
            logger.info("%s清退任务：%s", room, detail)


class SchedulerTask:
    time = None
    type = ""
    plan = {}
    meta_data = ""

    @property
    def retains_execution(self):
        """失败任务与重新准入的剩余执行均保留原对象、安排和时间。"""
        return bool(
            getattr(self, "execution_failure", None)
            or getattr(self, "execution_retained", False)
        )

    def __init__(
        self,
        time=None,
        task_plan={},
        task_type="",
        meta_data="",
        adjusted=False,
        strict_mood_limit=False,
        mood_limit=None,
        initial_fia=False,
    ):
        if time is None:
            self.time = datetime.now()
        else:
            self.time = time
        self.plan = task_plan
        self.type = set_type_enum(task_type)
        self.meta_data = meta_data
        self.adjusted = adjusted
        self.strict_mood_limit = strict_mood_limit
        self.mood_limit = mood_limit
        self.initial_fia = initial_fia

    def prepare_run_order_restoration(self):
        """载入中断的跑单时，只恢复首次记录的实际原班。"""
        self.plan = copy.deepcopy(self.run_order_original_roster)
        self.meta_data = ""

    def release_dorm_targets(self):
        """返回仍在任务中的姓名与原床位；兼容旧的单人清退任务。"""
        if self.type != TaskTypes.RELEASE_DORM:
            return {}
        targets = getattr(self, "release_targets", None)
        if targets is None:
            slots = [
                (room, index)
                for room, row in self.plan.items()
                for index, name in enumerate(row)
                if name == "Free"
            ]
            if len(slots) != 1 or not self.meta_data or "," in self.meta_data:
                return {}
            targets = {self.meta_data: slots[0]}
        return {
            name: (room, index)
            for name, (room, index) in targets.items()
            if room in self.plan
            and 0 <= index < len(self.plan[room])
            and self.plan[room][index] == "Free"
        }

    def remove_release_dorm_operator(self, name):
        """离宿只撤销本人的清退位置，保留同批其他干员。"""
        targets = self.release_dorm_targets()
        position = targets.pop(name, None)
        if position is not None:
            room, index = position
            self.plan[room][index] = "Current"
            if all(value == "Current" for value in self.plan[room]):
                del self.plan[room]
        self.release_targets = targets
        self.meta_data = ",".join(targets)

    @property
    def display_name(self):
        if self.type == TaskTypes.SELF_CORRECTION and getattr(
            self, "exhaust_support", False
        ):
            return "替班交接"
        if self.type == TaskTypes.REFRESH_TIME:
            rooms = getattr(self, "recovery_observation_rooms", None)
            if rooms:
                targets = getattr(self, "recovery_observation_targets", {})
                descriptions = []
                for room in sorted(rooms):
                    label = room.replace("dormitory_", "宿舍")
                    names = sorted(
                        name for name, target in targets.items() if target == room
                    )
                    if names:
                        label += "（" + "、".join(names) + "）"
                    descriptions.append(label)
                return "复查宿舍心情：" + "、".join(descriptions)
            return "刷新跑单时间"
        if self.type == TaskTypes.EXHAUST_OFF and getattr(
            self, "ordinary_coordination", False
        ):
            return "轮休协调"
        return self.type.display_value

    def format(self, time_offset=0):
        res = copy.deepcopy(self)
        res.time += timedelta(hours=time_offset)
        res.type = self.display_name
        if res.type == "空任务" and res.meta_data:
            res.type = res.meta_data
        return res

    def __str__(self):
        label = self.display_name if isinstance(self.type, TaskTypes) else self.type
        return f"{label}: SchedulerTask(time='{self.time}',task_plan={self.plan},task_type={self.type},meta_data='{self.meta_data}',adjusted={self.adjusted})"

    def __eq__(self, other):
        if isinstance(other, SchedulerTask):
            return (
                self.type == other.type
                and self.plan == other.plan
                and the_same_time(self.time, other.time)
            )
        return False
