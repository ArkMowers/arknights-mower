import copy
from collections import defaultdict
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
    vacant_dorm_slots,
)
from arknights_mower.utils.furniture_task import (
    FURNITURE_EXIT_SECONDS,
    FURNITURE_RUN_SECONDS,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.operation_timing import estimate_dorm_minutes
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.resting_priority import (
    RestingTier,
    busy_resting_names,
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


def find_next_task(
    tasks,
    compare_time: datetime | None = None,
    task_type="",
    compare_type: Literal["<", "=", ">"] = "<",
    meta_data="",
):
    """找符合条件的下一个任务

    Args:
        tasks: 任务列表
        compare_time: 截止时间
    """
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


def scheduling(tasks, run_order_delay=5, execution_time=0.75, time_now=None):
    time_now = time_now or datetime.now()
    merge_release_dorm(tasks, config.conf.merge_interval)
    # 强制上限不参加延期；统一保护会为它预留离宿时间并避开阻塞任务。
    enabled = config.conf.enable_mastery
    fixed = {
        id(t)
        for t in tasks
        if getattr(t, "strict_mood_limit", False)
        or (t.type == TaskTypes.FILL_DORM)
        or enabled
        and t.type == TaskTypes.SWAP_SUPPORT
    }
    ordinary = [t for t in tasks if id(t) not in fixed] if fixed else tasks
    conflict = _schedule_run_orders(ordinary, run_order_delay, execution_time, time_now)
    if fixed:
        ordinary_ids = {id(task) for task in ordinary}
        tasks[:] = [task for task in tasks if id(task) in fixed | ordinary_ids]
    protect_priority_tasks(tasks, run_order_delay, execution_time, time_now)
    if enabled:
        # 临近换人暂停可选无人机调时，关键任务保护决定执行顺序。
        if any(
            t.type == TaskTypes.SWAP_SUPPORT
            and t.time
            <= time_now
            + timedelta(minutes=_ordinary_task_minutes(t, execution_time) + 1)
            for t in tasks
        ):
            return None
    _sort_dispatch_tasks(tasks, time_now)
    return conflict


def protect_priority_tasks(
    tasks, run_order_delay=5, execution_time=0.75, time_now=None
):
    """按操作耗时保护关键任务，跑单冲突时提前专精换人。"""
    now = time_now or datetime.now()
    for task in tasks:
        simplify_dorm_fill(task, tasks, now)
    swaps = sorted(
        (
            t
            for t in tasks
            if config.conf.enable_mastery and t.type == TaskTypes.SWAP_SUPPORT
        ),
        key=lambda t: t.time,
    )
    for swap in swaps:
        _advance_swap_before_orders(tasks, swap, now, execution_time)
        _defer_work_before_swap(tasks, swap, (now, execution_time))
    cursor = now
    for task in sorted(tasks, key=lambda t: t.time):
        if task.type in (TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT):
            continue
        start = max(cursor, task.time)
        minutes = (
            sum(estimate_dorm_minutes(room) for room in task.plan)
            if _is_dorm_only_task(task)
            else _ordinary_task_minutes(task, execution_time)
        )
        deadline = _dorm_deadline(task, tasks, start, minutes, now)
        if deadline is not None:
            task.time = max(now, deadline.time) + timedelta(seconds=1)
            logger.debug(f"宿舍任务时间不足，移至{deadline.type.display_value}之后")
        else:
            cursor = start + timedelta(minutes=minutes)
    _advance_mood_limit_releases(tasks, run_order_delay, execution_time, now)
    _sort_dispatch_tasks(tasks, now)


def _sort_dispatch_tasks(tasks, now):
    # 尚未开始的清退可以提前；关键任务已经到点时，不再被清退抢占。
    due_priority = {id(task) for task in _priority_tasks(tasks) if task.time <= now}
    initial_fia_due = any(
        getattr(task, "initial_fia", False) and task.time <= now for task in tasks
    )
    tasks.sort(
        key=lambda task: (
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
            task.time,
        )
    )


def _advance_mood_limit_releases(tasks, run_order_delay, execution_time, now):
    """上限是离宿截止时间；提前腾出操作窗口，不等阻塞任务结束。"""
    releases = [
        task
        for task in tasks
        if getattr(task, "strict_mood_limit", False) and task.plan
    ]
    if not releases:
        return
    blockers = sorted(
        (
            task
            for task in tasks
            if not getattr(task, "strict_mood_limit", False)
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
            minutes=sum(estimate_dorm_minutes(room) for room in release.plan)
        )
        start = min(
            release.time, min(release.mood_limit_deadline, next_start) - duration
        )
        for task in blockers:
            if (
                task.type in (TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT)
                and task.time <= now
            ):
                # 已到期的关键任务先执行，不再尝试把清退塞到它前面。
                continue
            if task.type == TaskTypes.RUN_ORDER:
                # 跑单时间已扣除进站提前量，还需预留确认、收单和归位。
                minutes = (
                    max(run_order_delay, config.conf.run_order_delay)
                    + 2 * execution_time
                )
            elif task.type == TaskTypes.SWAP_SUPPORT:
                minutes = _ordinary_task_minutes(task, execution_time)
            elif _is_dorm_only_task(task):
                minutes = sum(estimate_dorm_minutes(room) for room in task.plan)
            else:
                minutes = _ordinary_task_minutes(task, execution_time)
            end = max(now, task.time) + timedelta(minutes=minutes)
            if start <= end and max(now, start) + duration >= task.time:
                start = min(start, task.time - duration - timedelta(seconds=1))
        if start < release.time:
            logger.info(
                f"心情上限离宿提前至 {start:%H:%M:%S}，"
                f"截止 {release.mood_limit_deadline:%H:%M:%S}：{release.meta_data}"
            )
            release.time = start
        next_start = start


def _advance_swap_before_orders(tasks, swap, now, execution_time):
    entry_delay = timedelta(minutes=config.conf.run_order_delay)
    order_operations = timedelta(minutes=2 * execution_time)
    swap_duration = timedelta(minutes=_ordinary_task_minutes(swap, execution_time))
    # 从晚到早检查，提前产生的新冲突在同一轮内收敛。
    orders = sorted(
        (t for t in tasks if t.type == TaskTypes.RUN_ORDER and t.meta_data),
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


def _priority_tasks(tasks):
    return sorted(
        (
            task
            for task in tasks
            if task.type == TaskTypes.RUN_ORDER
            or config.conf.enable_mastery
            and task.type == TaskTypes.SWAP_SUPPORT
        ),
        key=lambda task: task.time,
    )


def simplify_dorm_fill(task, tasks, time_now=None):
    """临近关键任务时退回原始补空名单，避免新入住者竞争单回而扩大操作。"""
    if (
        (task.type != TaskTypes.FILL_DORM)
        or getattr(task, "simple_dorm_fill", False)
        or getattr(task, "dorm_recovery_restore", [])
    ):
        return
    now = time_now or datetime.now()
    window_end = now + timedelta(minutes=max(10, config.conf.run_order_delay * 2))
    if not any(
        t.time <= window_end and (task.time <= now or task.time <= t.time)
        for t in _priority_tasks(tasks)
    ):
        return
    original = getattr(task, "dorm_fill_plan", task.plan)
    task.plan = {
        room: names.copy() for room, names in original.items() if room in task.plan
    }
    task.simple_dorm_fill = True


def _dorm_deadline(task, tasks, start, minutes, now):
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
            for deadline in _priority_tasks(tasks)
            if (task.time <= now or task.time <= deadline.time)
            and finish >= deadline.time
        ),
        None,
    )


def defer_dorm_before_priority_task(task, tasks, room, time_now=None):
    """逐房复核剩余时间；不足时保留未完成计划，关键任务结束后续行。"""
    if not room.startswith("dormitory_"):
        return False
    now = time_now or datetime.now()
    deadline = _dorm_deadline(task, tasks, now, estimate_dorm_minutes(room), now)
    if deadline is None:
        return False
    task.time = max(now, deadline.time) + timedelta(seconds=1)
    tasks.sort(key=lambda t: t.time)
    logger.info(
        f"{room} 操作可能挤占{deadline.type.display_value}时间，剩余宿舍安排延后"
    )
    return True


def _defer_work_before_swap(tasks, swap, timing):
    now, execution_time = timing
    cursor = now
    for task in sorted(tasks, key=lambda t: t.time):
        if (
            task.type in (TaskTypes.SWAP_SUPPORT, TaskTypes.RUN_ORDER)
            or getattr(task, "strict_mood_limit", False)
            or task.time > swap.time
        ):
            continue
        if _is_dorm_only_task(task):
            start = max(cursor, task.time)
            minutes = sum(estimate_dorm_minutes(room) for room in task.plan)
            if _dorm_deadline(task, [swap], start, minutes, now) is not None:
                task.time = max(now, swap.time) + timedelta(seconds=1)
            else:
                cursor = start + timedelta(minutes=minutes)
            continue
        finish = max(cursor, task.time) + timedelta(
            minutes=_ordinary_task_minutes(task, execution_time)
        )
        if finish >= swap.time - timedelta(minutes=1):
            task.time = max(now, swap.time) + timedelta(minutes=3)
        else:
            cursor = finish


def _merge_deferred_dorm_schedules(tasks):
    """把同一批延期任务里的宿舍中间态合成一次最终安排。"""
    mergeable_types = {
        TaskTypes.SHIFT_OFF,
        TaskTypes.SHIFT_ON,
        TaskTypes.RE_ORDER,
    }
    mergeable_tasks = [task for task in tasks if task.type in mergeable_types]
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


def _schedule_run_orders(tasks, run_order_delay=5, execution_time=0.75, time_now=None):
    # execution_time per room
    if time_now is None:
        time_now = datetime.now()
    if len(tasks) > 0:
        adjust_run_order_for_maintenance(tasks, run_order_delay)
        tasks.sort(key=lambda x: x.time)

        # 任务间隔最小时间（5分钟）
        min_time_interval = timedelta(minutes=run_order_delay)

        # 初始化变量以跟踪上一个优先级0任务和计划执行时间总和
        last_priority_0_task = None
        total_execution_time = 0

        # 遍历任务列表
        for i, task in enumerate(tasks):
            current_time = time_now
            # 判定任务堆积，如果第一个任务已经超时，则认为任务堆积
            if task.type.priority == 1 and current_time > task.time:
                total_execution_time += (current_time - task.time).total_seconds() / 60

            if task.type.priority == 1:
                if last_priority_0_task is not None:
                    time_difference = task.time - last_priority_0_task.time
                    if (
                        config.conf.run_order_grandet_mode.enable
                        and time_difference < min_time_interval
                        and time_now < last_priority_0_task.time
                    ) and not task.adjusted:
                        logger.info("检测到跑单任务过于接近，准备修正跑单时间")
                        return last_priority_0_task, task
                # 更新上一个优先级0任务和总执行时间
                last_priority_0_task = task
                total_execution_time = 0
            else:
                # 找到下一个优先级0任务的位置
                next_priority_0_index = -1
                for j in range(i + 1, len(tasks)):
                    if tasks[j].type.priority == 1:
                        next_priority_0_index = j
                        break
                # 如果其他任务的总执行时间超过了下一个优先级0任务的执行时间，调整它们的时间
                if next_priority_0_index > -1:
                    for j in range(i, next_priority_0_index):
                        # 菲亚充能/派对内置3分钟，线索购物内置1分钟
                        task_time = (
                            0
                            if len(tasks[j].plan) > 0
                            and tasks[j].type
                            not in [TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY]
                            else (
                                3
                                if tasks[j].type
                                in [TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY]
                                else 1
                            )
                        )
                        # 其他任务按照 每个房间*预设执行时间算 默认 45秒
                        estimate_time = (
                            len(tasks[j].plan) * execution_time
                            if task_time == 0
                            else task_time
                        )
                        if task_time == 0:
                            estimate_time = sum(
                                estimate_dorm_minutes(room, execution_time)
                                if room.startswith("dormitory_")
                                else execution_time
                                for room in tasks[j].plan
                            )
                        if tasks[j].type == TaskTypes.FURNITURE:
                            estimate_time = _ordinary_task_minutes(
                                tasks[j], execution_time
                            )
                        if (
                            timedelta(minutes=total_execution_time + estimate_time)
                            + time_now
                            < tasks[j].time
                        ):
                            total_execution_time = 0
                        else:
                            total_execution_time += estimate_time
                    if (
                        timedelta(minutes=total_execution_time) + time_now
                        > tasks[next_priority_0_index].time
                    ):
                        if (tasks[next_priority_0_index].time - time_now) > timedelta(
                            minutes=10
                        ):
                            break
                        logger.info("检测到任务可能影响到下次跑单修改任务至跑单之后")
                        logger.debug("||".join([str(t) for t in tasks]))
                        next_priority_0_time = tasks[next_priority_0_index].time
                        pending = tasks[i:next_priority_0_index]
                        pending = _merge_deferred_dorm_schedules(pending)
                        tasks[i:next_priority_0_index] = pending
                        for pending_task in pending:
                            if pending_task.adjusted:
                                continue
                            pending_task.time = next_priority_0_time + timedelta(
                                seconds=1
                            )
                            next_priority_0_time = pending_task.time
                        logger.debug("||".join([str(t) for t in tasks]))
                        break
        tasks.sort(key=lambda x: x.time)


def adjust_run_order_for_maintenance(tasks, run_order_delay=5, advance_time=None):
    """
    将维护期附近的 RUN_ORDER 任务提前到维护前，避免维护期冲突。
    :param tasks: 任务列表
    :param st: 维护开始时间（本地时间，datetime）
    :param ed: 维护结束时间（本地时间，datetime）
    :param run_order_delay: 跑单间隔（分钟）
    :param advance_time: 维护副表要求更早执行时使用的截止时间
    """
    time_gap = max(run_order_delay * 2, 10)  # 确保最小间隔为10分钟操作时间
    st, ed = NewsChecker.get_update_time()
    if not st or not ed:
        logger.debug("无法获取维护时间，跳过调整 RUN_ORDER 任务")
        return []
    window_start = st - timedelta(minutes=time_gap)
    window_end = ed + timedelta(minutes=time_gap)
    # 找出需要调整的任务
    run_order_tasks = [
        t
        for t in tasks
        if t.type == TaskTypes.RUN_ORDER
        and (
            window_start < t.time < window_end
            or advance_time is not None
            and getattr(t, "maintenance_start", None) == st
        )
    ]
    # 按原 time 排序
    run_order_tasks.sort(key=lambda t: t.time)
    # 依次调整时间
    for i, t in enumerate(run_order_tasks, 1):
        new_time = min(window_start, advance_time or window_start) - timedelta(
            seconds=i
        )
        logger.info(f"维护期附近的跑单任务已提前到 {new_time}（原定 {t.time}）")
        t.time = new_time
        t.adjusted = True  # 标记为已调整
        t.maintenance_start = st
    return run_order_tasks


def _native_return(op_data, plan, names):
    """把需要结束休息的干员按当前排班写回原岗位。"""
    for name in names:
        op = op_data.operators[name]
        if not op.room or op.room not in op_data.plan:
            continue
        slots = plan.setdefault(op.room, ["Current"] * len(op_data.plan[op.room]))
        if slots[op.index] in ("Current", name):
            slots[op.index] = name


def _active_recovery_room(op_data, name):
    """只有实际床位仍匹配的单回标记参与豁免。"""
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    position = active_recovery_position(op_data.operators[name])
    return position[0] if position else ""


def _recovery_aware_assignments(
    op_data, beds, candidates, *, clear_invalid_recovery=True
):
    """按正常排名选人，保留有效原床位，只迁移床位失效的入住者。

    candidates 的统一布局为 ``(排序键, 原床位顺序, 姓名, 时间, 原位置)``。
    单回目标若原本会因缩容落选，会替换保留区末尾的非单回目标；若目标
    所在宿舍仍有动态床，优先保留原床或同房床。普通床也保留原位，
    不因房间排序或心情变化互换。确实换房/离床时清除旧标记，使后续
    宿舍任务重新执行一次单回入驻。同房换床也不能沿用旧单回标记。
    """
    capacity = len(beds)
    protected = {
        candidate[2]
        for candidate in candidates
        if _active_recovery_room(op_data, candidate[2])
    }
    kept = list(candidates[:capacity])
    kept_names = {candidate[2] for candidate in kept}
    for candidate in candidates[capacity:]:
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
    dropped = [candidate for candidate in candidates if candidate[2] not in kept_names]

    available = list(beds)
    assignments = {}
    assigned_names = set()
    original_positions = {candidate[2]: candidate[4] for candidate in kept}
    # 单回目标先占原宿舍；同房内优先原床，避免无意义地重做单回。
    for candidate in kept:
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
    for candidate in kept:
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
        and op_data.is_auto_free_dorm_slot(room, index)
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
            for bed in op_data.dorm
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
            )
        )
    return tuple(op_data.config.dorm_order), tuple(beds)


def rebalance_plan_swap_dorms(
    op_data, previous_dorms=None, reserved_names: set[str] | None = None
):
    """主副表切换后，仅迁移失去有效原床位的入住者。

    previous_dorms 保留切表前的床位位置和恢复计时。单独改变房间优先级
    不移动已入住者；新顺序仅用于分配确实需要迁移的干员。
    """
    reserved_names = reserved_names or set()
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
    beds = [bed for bed in op_data.dorm if op_data.is_effective_free_slot(bed)]
    assignments, dropped = _recovery_aware_assignments(op_data, beds, candidates)
    plan = {}
    for _key, _order, name, _time, _position in dropped:
        op = op_data.operators[name]
        if op.is_high():
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
        bed.time = saved_time

    effective_positions = {bed.position for bed in beds}
    for _key, _order, _name, _time, position in candidates:
        if position in destinations:
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
        if bed.position not in destinations:
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
    tasks, op_data, existing_targets=None, release_tasks=None, pending_arrangements=()
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
    batches = copy.deepcopy(batches)
    ordered = sorted(batches, key=lambda batch: batch[0])
    result = []
    planned = set()
    current_time = datetime.now()
    pending_resources = [
        (task.time, *_arrangement_resources(task.plan)) for task in pending_arrangements
    ]
    for time, (dorms, rest_in_full) in ordered:
        logger.debug(f"{time},{dorms},{rest_in_full}")
        plan = {}
        exhaust_exist = False
        for room in dorms:
            if not room.name or room.name not in op_data.operators:
                logger.debug(f"跳过已失效的宿舍回班项：{room}")
                continue
            if room.name in planned:
                continue
            op = op_data.operators[room.name]
            if op.exhaust_require:
                exhaust_exist = True
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
                if projected_bed is None:
                    continue
                target_room, target_index = projected_bed.position
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
                agents = op_data.groups[op.group] if op.group != "" else [op.name]
                for agent in agents:
                    o = op_data.operators[agent]
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
            planned.update(rebalance_closing_dorm_slots(op_data, plan, planned))
        earliest = _after_pending_arrangements(plan, pending_resources)
        if rest_in_full:
            if exhaust_exist:
                time = max(time, current_time, earliest)
            else:
                time = max(time - timedelta(minutes=8), current_time, earliest)
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


def plan_metadata(op_data, tasks):
    op_data.refresh_idle_dorm_search()
    locked_tasks = [
        task for task in tasks if (getattr(task, "product_shift_locked", False))
    ]
    locked_names = {name for task in locked_tasks for name in task.product_lock_names}
    locked_groups = {
        op_data.operators[name].group
        for name in locked_names
        if name in op_data.operators and op_data.operators[name].group
    }
    locked_slots = {slot for task in locked_tasks for slot in task.product_lock_slots}
    locked_ids = {id(task) for task in locked_tasks}
    # 仅当副表处于激活状态时，保留既有回班任务中的工位快照，避免副表临时调整工位覆盖回班目标；
    # 当所有副表均已失效（恢复纯主表）时，所有干员统一按主表规划回班，避免副表工位粘滞。
    existing_targets = {}
    if any(getattr(op_data, "plan_condition", [])):
        for t in tasks:
            if t.type == TaskTypes.SHIFT_ON and t.plan:
                for room, agents in t.plan.items():
                    for idx, name in enumerate(agents):
                        if name not in ("Current", "Free", ""):
                            existing_targets[name] = (room, idx)
    previous_releases = [t for t in tasks if getattr(t, "strict_mood_limit", False)]
    # 切产物延期任务保留原对象、重试时间与资源锁，只重算其他回班/释放任务。
    tasks = [
        t
        for t in tasks
        if t.type not in [TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM]
        or id(t) in locked_ids
    ]
    _, reserved_slots = dorm_task_reservations(
        op_data, [task for task in tasks if task.type != TaskTypes.FILL_DORM]
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
            and not v.room.startswith("dorm")
            and not v.is_resting()
            and not op_data.is_standby(v.name)
        ),
        key=lambda x: x.current_mood() - x.lower_limit,
    )

    # 计算最低休息时间
    for agent in total_agent:
        # 如果全红脸，使用急救模式
        predicted_rest_time = max(
            agent.predict_exhaust(), datetime.now() + timedelta(minutes=30)
        )
        min_resting_time = min(min_resting_time, predicted_rest_time)

    logger.debug(f"预测最低休息时间为: {min_resting_time}")
    grouped_dorms = defaultdict(list)
    free_rooms = []
    # 固定宿舍恢复位始终参与回班计时；动态床位只处理当前排班仍为 Free 的位置。
    for dorm in op_data.all_dorms():
        if dorm in op_data.dorm and not op_data.is_effective_free_slot(dorm):
            continue
        if dorm.name and dorm.name in op_data.operators:
            operator = op_data.operators[dorm.name]
            if (
                dorm.name in locked_names
                or operator.group in locked_groups
                or dorm.position in locked_slots
            ):
                continue
            grouped_dorms[operator.group].append(dorm)
            if (
                dorm in op_data.dorm
                and not op_data.has_rest_mood_limit(dorm.name)
                and not op_data.skip_idle_dorm_release(dorm.name)
            ):
                free_rooms.append(dorm)
    new_task = {}
    for group_name, dorms in grouped_dorms.items():
        logger.debug(f"开始计算:{group_name}")
        logger.debug(f"开始计算:{dorms}")
        max_rest_in_full_time = None
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
        rest_in_full_dorms = [
            dorm for dorm in high_dorms if op_data.operators[dorm.name].rest_in_full
        ]
        if high_dorms and group_name:
            # 高优先干员恢复时间差过大时，可延后整组回班。
            base_time = high_dorms[0].time
            need_early = not op_data.operators[high_dorms[0].name].exhaust_require
            mood_gap_full_rest = False
            if (
                config.conf.group_rest_in_full_on_mood_gap
                and base_time is not None
                and not rest_in_full_dorms
            ):
                for dorm in high_dorms[1:]:
                    # 三电站限制为1小时，2电站限制为1.5小时
                    limit = 5400 if op_data.power_plant_count == 2 else 3600
                    if dorm.time and (base_time - dorm.time).total_seconds() > limit:
                        logger.debug(
                            f"{high_dorms[0].name} 的时间 {base_time} 被调整为 {dorm.time}，因为时间差超过{limit / 3600}小时"
                        )
                        max_rest_in_full_time = base_time
                        mood_gap_full_rest = True
                    if op_data.operators[high_dorms[0].name].exhaust_require:
                        need_early = False
            if rest_in_full_dorms:
                max_rest_in_full_time = max(
                    (dorm.time for dorm in rest_in_full_dorms if dorm.time is not None),
                    default=None,
                )
            nearest_dorm = min(
                (dorm for dorm in high_dorms if dorm.time is not None),
                key=lambda d: d.time,
                default=None,
            )
            logger.debug(f"最前上班时间为{nearest_dorm}")
            logger.debug({max_rest_in_full_time})
            if max_rest_in_full_time:
                # 处理回满逻辑
                task_time = max_rest_in_full_time - (
                    timedelta(minutes=0.4 * len(high_dorms))
                    if need_early
                    else timedelta(seconds=0)
                )
                max_extra_wait = config.conf.group_mood_gap_max_extra_wait_hours
                if mood_gap_full_rest and max_extra_wait > 0 and nearest_dorm:
                    normal_return_time = min(nearest_dorm.time, min_resting_time)
                    task_time = max(
                        normal_return_time,
                        min(
                            task_time,
                            normal_return_time + timedelta(hours=max_extra_wait),
                        ),
                    )
            elif nearest_dorm:
                task_time = min(nearest_dorm.time, min_resting_time)
            else:
                continue
            if task_time not in new_task:
                new_task[task_time] = (high_dorms, len(rest_in_full_dorms) > 0)
            else:
                combined = new_task[task_time][0] + high_dorms
                type = new_task[task_time][1] or len(rest_in_full_dorms) > 0
                new_task[task_time] = (combined, type)
        if high_dorms and not group_name:
            # 单独添加，最后合并
            # high_droms 如果触发急救模式，后面的移送到急救前
            for room in high_dorms:
                if room.time and room.name:
                    rest_in_full = op_data.operators[room.name].rest_in_full
                    task_time = (
                        min(room.time, min_resting_time)
                        if not rest_in_full
                        else room.time
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
    )
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
            or op.room.startswith("dorm")
            or op.current_room
            or not op_data.rest_mood_complete(op.name)
        ):
            continue
        members = set(op_data.groups[op.group]) if op.group else {op.name}
        if members & (returning | locked_names | busy) or op.group in locked_groups:
            continue
        workers = [
            op_data.operators[name]
            for name in members
            if not op_data.operators[name].room.startswith("dorm")
            and not op_data.operators[name].workaholic
        ]
        if not all(
            not worker.current_room
            and (
                op_data._can_standby(worker)
                or (
                    has_resting_mood(worker)
                    and worker.current_mood() >= worker.upper_limit
                )
            )
            for worker in workers
        ):
            continue
        plan = {}
        _native_return(op_data, plan, members)
        recalled = rebalance_closing_dorm_slots(
            op_data.project_arrangements([]), plan, members
        )
        if recalled & (locked_names | busy) or any(
            (room, index) in locked_slots
            for room, names in plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        ):
            continue
        tasks.append(
            SchedulerTask(
                task_plan=plan,
                time=max(
                    datetime.now(), _after_pending_arrangements(plan, pending_resources)
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
            or (op.room, op.index) in locked_slots
            or not op_data.is_standby(op.name)
        ):
            continue
        return_plan = {}
        _native_return(op_data, return_plan, [op.name])
        earliest = _after_pending_arrangements(return_plan, pending_resources)
        for task in return_tasks:
            slots = task.plan.get(op.room, ["Current"] * len(op_data.plan[op.room]))
            if task.time < earliest or slots[op.index] != "Current":
                continue
            _native_return(op_data, task.plan, [op.name])
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
    result = []
    for bed in op_data.all_dorms():
        op = op_data.operators.get(bed.name)
        if op is None or (op.current_room, op.current_index) != bed.position:
            continue
        if not op_data.is_recovery_dorm(bed, op.name):
            continue
        target = (recovery_targets or {}).get(op.name)
        if (
            target is not None
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
        if not op_data.has_rest_mood_limit(bed.name):
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
    op_data, plan, reserved_slots=(), preceding_plan=None, *, reserved_names=()
):
    """新入住者竞争单回位；单 Free 宿舍离宿时跨宿舍分配一次。

    先投影完整入住计划，再按宿舍顺序比较每房首个动态位。新入住者
    可填空位（含本轮替班腾出的位），或与排名更低的目标交换床位；
    被替换者继续竞争后面的单回位，填入空位后结束本次交换。
    单 Free 宿舍原住客离宿时，已有休息者也参与本次竞争。
    不增加/淘汰休息者，也不因已有入住者心情交叉而搬床。返回计划
    副本，不提前改变真实位置或单回标记。
    """
    if not plan and not preceding_plan:
        return plan
    projected = op_data.project_arrangements([preceding_plan or {}, plan])
    beds = [bed for bed in projected.dorm if projected.is_effective_free_slot(bed)]
    explicit_names = {name for names in plan.values() for name in names}
    locked_rooms = {
        room for room, _ in set(reserved_slots) | set(op_data.reserved_product_beds)
    }
    # 其他任务已选好但尚未实际入住的床位，不参与本轮交换。
    for bed in op_data.dorm:
        op = op_data.operators.get(bed.name)
        if op is not None and (
            bed.name not in explicit_names
            and (op.current_room, op.current_index) != bed.position
        ):
            locked_rooms.add(bed.position[0])
    room_beds = defaultdict(list)
    for bed in beds:
        room_beds[bed.position[0]].append(bed)
        if bed.name and (
            bed.name not in op_data.operators
            or bed.name in reserved_names
            or op_data.is_free_room_excluded(bed.name)
            or projected.rest_mood_complete(bed.name)
            or resting_tier(projected, bed.name) == RestingTier.EXCLUDED
        ):
            locked_rooms.add(bed.position[0])
    beds = [bed for bed in beds if bed.position[0] not in locked_rooms]
    departed_single = any(
        len(room_beds[bed.position[0]]) == 1
        and (old := op_data.get_current_operator(*bed.position)) is not None
        and op_data.is_dynamic_dorm_position(*bed.position, old.name)
        and not projected.is_dynamic_dorm_position(
            projected.operators[old.name].current_room,
            projected.operators[old.name].current_index,
            old.name,
        )
        for bed in beds
    )
    now = datetime.now()
    arrivals = []
    for bed in beds:
        op = op_data.operators.get(bed.name)
        if op is not None and (
            departed_single
            and not (
                has_resting_mood(op, now) and resting_mood(op, now) >= op.upper_limit
            )
            or op.name in explicit_names
            and not op_data.is_dynamic_dorm_position(
                op.current_room, op.current_index, op.name
            )
        ):
            arrivals.append(op.name)
    if not arrivals:
        return plan

    def ranking(name):
        op = op_data.operators[name]
        complete = departed_single and (
            has_resting_mood(op, now) and resting_mood(op, now) >= op.upper_limit
        )
        return complete, resting_key(op_data, name, now)

    arrivals.sort(key=ranking)
    targets = {}
    for bed in beds:
        targets.setdefault(bed.position[0], bed)
    result = copy.deepcopy(plan)
    for name in arrivals:
        source = next(bed for bed in beds if bed.name == name)
        for target in targets.values():
            if target is source:
                # 已获得本房单回位，不为更低顺序的宿舍继续搬动。
                break
            if target.name and ranking(source.name) >= ranking(target.name):
                continue
            source.name, target.name = target.name, source.name
            for bed in (source, target):
                room, index = bed.position
                result.setdefault(room, ["Current"] * len(op_data.plan[room]))[
                    index
                ] = bed.name or "Free"
            if not source.name:
                # 空单回位已接住入住者，没有被挤出者需要继续分配。
                break
    return result


def plan_dorm_isolation(op_data, plan, reserved_slots=()):
    """入住前演算分散新入住者；保留单回位、原入住者和其他任务预约。"""
    if not config.conf.dorm_isolation or not plan:
        return plan
    projected = op_data.project_arrangements([plan])
    beds = [bed for bed in projected.dorm if projected.is_effective_free_slot(bed)]
    first_positions = {}
    for bed in beds:
        first_positions.setdefault(bed.position[0], bed.position)
    reserved = set(reserved_slots) | set(op_data.reserved_product_beds)
    newcomers = {
        name
        for row in plan.values()
        for name in row
        if name in op_data.operators and not op_data.operators[name].is_resting()
    }
    movable = [
        bed
        for bed in beds
        if bed.position not in reserved
        and bed.position != first_positions[bed.position[0]]
        and (not bed.name or bed.name in newcomers)
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

    # 只接受减少同住对数的交换，有限床位内不出现来回搬动。
    for _ in range(len(movable) ** 2):
        best = None
        improvement = 0
        for offset, first in enumerate(movable):
            for second in movable[offset + 1 :]:
                rooms = {first.position[0], second.position[0]}
                if len(rooms) < 2 or first.name == second.name:
                    continue
                before = sum(room_cost(room) for room in rooms)
                first.name, second.name = second.name, first.name
                gain = before - sum(room_cost(room) for room in rooms)
                first.name, second.name = second.name, first.name
                if gain > improvement:
                    best, improvement = (first, second), gain
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


def try_reorder(op_data, new_plan):
    # 移除被拉去上班的替班
    assigned_names = {name for names in new_plan.values() for name in names}
    for d in op_data.dorm:
        if d.name in assigned_names:
            d.name = ""
            d.time = None
    # 复制副本，防止原本的dorm错误触发纠错
    dorm = copy.deepcopy(op_data.dorm)
    logger.debug(op_data.dorm)
    vip = sum(1 for key in op_data.plan.keys() if key.startswith("dorm"))
    logger.debug(f"当前vip个数{vip}")
    if vip == 0:
        return

    def get_ranking(name):
        if name in op_data.operators:
            op = op_data.operators[name]
            if op.operator_type == "high" and op.resting_priority == "high":
                return "high"
            if op.operator_type == "high" and op.resting_priority == "standby":
                return "standby"
            if op.operator_type == "high":
                return "normal"
        return "low"

    # self.dorm 是默认排班中的潜在床位池；副表可能把其中一部分 Free
    # 临时覆盖成固定干员。重排只能操作当前有效排班里仍为 Free 的位置。
    protected_indices = set()
    effective_free_indices = [
        idx
        for idx, room in enumerate(dorm)
        if op_data.is_effective_free_slot(room) and idx not in protected_indices
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
    for room in dorm:
        if room.name:
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
    return prioritize_new_dorm_recovery(op_data, plan, preceding_plan=new_plan)


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


def try_workshop_tasks(op_data, tasks):
    # 如果没有其他任务则进行加工站干员检查
    from arknights_mower.utils.workshop_automation import (
        restore_if_no_plans,
        workshop_task_current,
    )
    from arknights_mower.utils.workshop_limits import (
        workshop_material_block_reason,
        workshop_operator_block_reason,
    )
    from arknights_mower.utils.workshop_recommendation import (
        prioritize_workshop_settings,
    )

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
            reason = workshop_operator_block_reason(
                op_data, item.operator, tasks, minimum_mood=22
            ) or workshop_material_block_reason(
                item.operator, item.items, inventory_data
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


def dorm_residents(op_data):
    """床位缓存缺名时用实际驻员补齐，让床补偿与接管判定使用同一身份。"""
    return {
        bed.position: bed.name
        or (
            resident.name
            if (resident := op_data.get_current_operator(*bed.position)) is not None
            and op_data.is_recovery_dorm(bed, resident.name)
            else ""
        )
        for bed in op_data.dorm
    }


def restore_displaced_resting(op_data, previous, plan, tasks):
    """接管保留候补的回班来源；必需组员失床时显式召回整组。"""
    current = dorm_residents(op_data)
    for bed in op_data.dorm:
        names = plan.get(bed.position[0], [])
        index = bed.position[1]
        if (
            index < len(names)
            and names[index] != "Current"
            and not (
                names[index] in ("Free", "")
                and bed.name != previous.get(bed.position, "")
                and bed.name
            )
        ):
            current[bed.position] = "" if names[index] in ("Free", "") else names[index]
    retained = set(current.values())
    displaced = {
        name
        for position, name in previous.items()
        if name and name != current.get(position) and name not in retained
    }
    recalled = set()
    for name in displaced:
        op = op_data.operators.get(name)
        if op is None or not op.is_high() or op.room not in op_data.plan:
            continue
        members = op_data.groups[op.group] if op.group else [name]
        if op_data._can_standby(op) and any(
            anchor.name in retained
            and anchor.is_high()
            and not op_data._can_standby(anchor)
            and not anchor.room.startswith("dorm")
            and not anchor.workaholic
            and not op_data.rest_mood_complete(anchor.name)
            and (not op.group or anchor.group == op.group)
            for anchor in op_data.operators.values()
        ):
            logger.info(f"{name}的候补床位被接管，随组待命")
            continue
        recalled.update(members)
    for name in recalled:
        op = op_data.operators[name]
        plan.setdefault(op.room, ["Current"] * len(op_data.plan[op.room]))[op.index] = (
            name
        )
    if recalled:
        logger.info(f"休息床位被更高优先级接管，安排整组回班：{sorted(recalled)}")
        for bed in op_data.dorm:
            if bed.name in recalled:
                room, index = bed.position
                if current.get(bed.position) in recalled:
                    plan.setdefault(room, ["Current"] * len(op_data.plan[room]))[
                        index
                    ] = "Free"
                bed.reset()
    changed_slots = {
        bed.position
        for bed in op_data.dorm
        if previous.get(bed.position) != current.get(bed.position)
    }
    # 已接管床位不能继续执行旧的释放任务；已召回成员也不重复预约回班。
    for task in tasks[:]:
        if task.plan is plan or task.type not in (
            TaskTypes.SHIFT_ON,
            TaskTypes.RELEASE_DORM,
        ):
            continue
        for room, names in list(task.plan.items()):
            for index, name in enumerate(names):
                if (task.type == TaskTypes.SHIFT_ON and name in recalled) or (
                    task.type == TaskTypes.RELEASE_DORM
                    and (room, index) in changed_slots
                ):
                    names[index] = "Current"
            if all(name == "Current" for name in names):
                del task.plan[room]
        if not task.plan:
            tasks.remove(task)


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
        if priority_only:
            recovery_names = [
                name
                for name in recovery_names
                if resting_tier(op_data, name) <= RestingTier.PRIORITY_REPLACEMENT
            ]
            if not recovery_names:
                return
        recovering = iter(recovery_names)
        waiting = next(recovering, None)
        full = iter(
            name
            for name in candidates.filling
            if name not in candidates.recovering and name not in candidates.unknown
        )
        search_unknown = bool(candidates.unknown) and not priority_only
        estimated_recovery = bool(candidates.estimated_recovering)
        replacement_search = estimated_recovery or (
            search_unknown and not op_data.idle_dorm_search_exhausted
        )
        if waiting is None and not candidates.filling:
            return

        filling_vacancies = bool(vacancies)
        arrangement = {}
        residents = []
        beds_to_visit = list(op_data.dorm)
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
            else:
                occupant = op_data.operators.get(bed.name)
                if (
                    occupant is None
                    or (occupant.current_room, occupant.current_index) != bed.position
                    or op_data.is_free_room_excluded(occupant.name)
                ):
                    continue
                complete = (
                    has_resting_mood(occupant, now)
                    and resting_mood(occupant, now) >= occupant.upper_limit
                ) or (bed.time is not None and bed.time <= now)
                if priority_only or not complete:
                    if waiting is None or not op_data._slot_takable(
                        bed, requester=waiting
                    ):
                        continue
                elif waiting is None and (
                    not replacement_search
                    or op_data.is_full_dorm_fallback(occupant.name)
                    and not estimated_recovery
                    or op_data.has_rest_mood_limit(occupant.name)
                ):
                    continue

            if waiting is not None:
                incoming = waiting
                waiting = next(recovering, None)
            elif search_unknown:
                # 未知心情统一通过游戏心情升序选人，不能把默认 24 当实读。
                incoming = "Free"
                if occupant is not None:
                    residents.append(occupant.name)
            else:
                incoming = next(full, None)
                if incoming is None:
                    break
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
        previous = dorm_residents(op_data)
        restore_displaced_resting(op_data, previous, arrangement, tasks)
        task = SchedulerTask(
            time=now,
            task_plan=arrangement,
            task_type=TaskTypes.FILL_DORM
            if filling_vacancies
            else TaskTypes.NOT_SPECIFIC,
        )
        if residents:
            task.dorm_mood_residents = residents
        task.dorm_fill_plan = copy.deepcopy(arrangement)
        if filling_vacancies:
            simplify_dorm_fill(task, tasks, now)
        if not getattr(task, "simple_dorm_fill", False):
            task.plan = prioritize_new_dorm_recovery(op_data, task.plan, reserved_slots)
        isolated = plan_dorm_isolation(op_data, task.plan, reserved_slots)
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
        and find_next_task(tasks, task_type=TaskTypes.RELEASE_DORM, meta_data=name)
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

    def format(self, time_offset=0):
        res = copy.deepcopy(self)
        res.time += timedelta(hours=time_offset)
        res.type = res.type.display_value
        if res.type == "空任务" and res.meta_data:
            res.type = res.meta_data
        return res

    def __str__(self):
        return f"SchedulerTask(time='{self.time}',task_plan={self.plan},task_type={self.type},meta_data='{self.meta_data}',adjusted={self.adjusted})"

    def __eq__(self, other):
        if isinstance(other, SchedulerTask):
            return (
                self.type == other.type
                and self.plan == other.plan
                and the_same_time(self.time, other.time)
            )
        return False
