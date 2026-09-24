import copy
import heapq
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Literal

from arknights_mower.solvers.record import get_inventory_counts
from arknights_mower.utils import config
from arknights_mower.utils.datetime import the_same_time
from arknights_mower.utils.furniture_task import (
    FURNITURE_EXIT_SECONDS,
    FURNITURE_RUN_SECONDS,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.resting_priority import (
    RestingTier,
    busy_resting_names,
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
    # Keep swaps out of the mutable run-order schedule: their deadline cannot move.
    enabled = config.conf.enable_mastery
    fixed = {
        id(t)
        for t in tasks
        if getattr(t, "strict_mood_limit", False)
        or enabled
        and t.type == TaskTypes.SWAP_SUPPORT
    }
    ordinary = [t for t in tasks if id(t) not in fixed] if fixed else tasks
    conflict = _schedule_run_orders(ordinary, run_order_delay, execution_time, time_now)
    if fixed and config.conf.experimental_dorm_logic:
        ordinary_ids = {id(task) for task in ordinary}
        tasks[:] = [task for task in tasks if id(task) in fixed | ordinary_ids]
    if enabled:
        swap_conflict = protect_support_swaps(
            tasks, run_order_delay, execution_time, time_now
        )
        if swap_conflict:
            return swap_conflict
        # Near a handoff, stop optional drone adjustment loops as well as dispatch.
        if any(
            t.type == TaskTypes.SWAP_SUPPORT
            and t.time <= time_now + _support_swap_gap(run_order_delay)
            for t in tasks
        ):
            return None
    tasks.sort(key=lambda t: t.time)
    return conflict


def _support_swap_gap(run_order_delay):
    # The order countdown is offset by the configured entry delay, even when a
    # caller uses scheduling()'s default conflict interval.
    return timedelta(
        minutes=max(10, run_order_delay * 2, config.conf.run_order_delay * 2)
    )


def protect_support_swaps(tasks, run_order_delay=5, execution_time=0.75, time_now=None):
    """Fixed handoff deadlines yield only trade rooms as drone-acceleration targets."""
    if not config.conf.enable_mastery:
        return None
    now = time_now or datetime.now()
    swaps = sorted(
        (t for t in tasks if t.type == TaskTypes.SWAP_SUPPORT), key=lambda t: t.time
    )
    gap = _support_swap_gap(run_order_delay)
    conflict = None
    for swap in swaps:
        order_conflict = _avoid_swap_with_orders(tasks, swap, (now, gap))
        conflict = conflict or order_conflict
        _defer_work_before_swap(tasks, swap, (now, execution_time))
    tasks.sort(key=lambda t: t.time)
    return conflict


def _avoid_swap_with_orders(tasks, swap, timing):
    now, gap = timing
    conflict = None
    for task in tasks:
        if task.type != TaskTypes.RUN_ORDER or not task.meta_data:
            continue
        if max(now, task.time) + gap <= swap.time or task.time > swap.time + gap:
            continue
        if now + gap < swap.time:
            conflict = conflict or (task, swap)
        else:
            task.time = max(now, swap.time) + gap + timedelta(seconds=1)
            logger.warning("跑单来不及提前避开专精换人，先执行换人后再处理跑单")
    return conflict


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
            TaskTypes.NOT_SPECIFIC,
        )
        and bool(task.plan)
        and all(room.startswith("dormitory_") for room in task.plan)
    )


def _is_dorm_only_batch(tasks):
    # 宿舍重排附带的空唤醒任务不涉及工作站，但不能让任意空批次绕过保护。
    return any(_is_dorm_only_task(task) for task in tasks) and all(
        _is_dorm_only_task(task)
        or (
            task.type in (TaskTypes.NOT_SPECIFIC, TaskTypes.RE_ORDER)
            and not task.plan
            and not task.meta_data
        )
        for task in tasks
    )


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
    redundant_followup_ids = set()
    for index, task in enumerate(tasks[:-1]):
        if (
            id(task) in dorm_ids
            and task.type == TaskTypes.RE_ORDER
            and id(tasks[index + 1]) not in dorm_ids
            and tasks[index + 1].type == TaskTypes.NOT_SPECIFIC
            and not tasks[index + 1].plan
            and tasks[index + 1].time == task.time
        ):
            redundant_followup_ids.add(id(tasks[index + 1]))
    redundant_followup_ids.difference_update(dorm_ids)
    for task in dorm_tasks:
        for room in list(task.plan):
            if room.startswith("dormitory_"):
                del task.plan[room]
    anchor.plan.update(merged)

    result = []
    for task in tasks:
        if (
            task is not anchor
            and id(task) in dorm_ids
            and task.type != TaskTypes.SHIFT_OFF
            and not task.plan
        ):
            continue
        # RE_ORDER 后的空任务只是为了唤醒下一轮；RE_ORDER 已合并时不再需要。
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
                        if config.conf.experimental_dorm_logic:
                            if _is_dorm_only_batch(pending):
                                logger.info(
                                    "实验宿舍逻辑下待处理任务仅涉及宿舍，保留原定时间"
                                )
                                break
                            pending = _merge_deferred_dorm_schedules(pending)
                        tasks[i:next_priority_0_index] = pending
                        for pending_task in pending:
                            if pending_task.adjusted:
                                continue
                            pending_task.deferred_by_run_order = True
                            pending_task.time = next_priority_0_time + timedelta(
                                seconds=1
                            )
                            next_priority_0_time = pending_task.time
                        logger.debug("||".join([str(t) for t in tasks]))
                        break
        tasks.sort(key=lambda x: x.time)


def adjust_run_order_for_maintenance(tasks, run_order_delay=5):
    """
    将维护期附近的 RUN_ORDER 任务提前到维护前，避免维护期冲突。
    :param tasks: 任务列表
    :param st: 维护开始时间（本地时间，datetime）
    :param ed: 维护结束时间（本地时间，datetime）
    :param run_order_delay: 跑单间隔（分钟）
    """
    time_gap = max(run_order_delay * 2, 10)  # 确保最小间隔为10分钟操作时间
    st, ed = NewsChecker.get_update_time()
    if not st or not ed:
        logger.debug("无法获取维护时间，跳过调整 RUN_ORDER 任务")
        return
    window_start = st - timedelta(minutes=time_gap)
    window_end = ed + timedelta(minutes=time_gap)
    # 找出需要调整的任务
    run_order_tasks = [
        t
        for t in tasks
        if t.type == TaskTypes.RUN_ORDER and window_start < t.time < window_end
    ]
    # 按原 time 排序
    run_order_tasks.sort(key=lambda t: t.time)
    # 依次调整时间
    for i, t in enumerate(run_order_tasks, 1):
        new_time = window_start - timedelta(seconds=i)
        logger.info(f"维护期附近的跑单任务已提前到 {new_time}（原定 {t.time}）")
        t.time = new_time
        t.adjusted = True  # 标记为已调整


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
    """返回仍有效的单回宿舍标记；离开过该宿舍的旧标记不参与豁免。"""
    op = op_data.operators[name]
    room = getattr(op, "dorm_recovery_room", "")
    return room if room and op.current_room == room else ""


def _recovery_aware_assignments(
    op_data, beds, candidates, *, clear_invalid_recovery=True
):
    """按正常排名选人，保留有效原床位，只迁移床位失效的入住者。

    candidates 的统一布局为 ``(排序键, 原床位顺序, 姓名, 时间, 原位置)``。
    单回目标若原本会因缩容落选，会替换保留区末尾的非单回目标；若目标
    所在宿舍仍有动态床，优先保留原床或同房床。普通床也保留原位，
    不因房间排序或心情变化互换。确实换房/离床时清除旧标记，使后续
    宿舍任务重新执行一次单回入驻。
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

    assigned_rooms = {
        candidate[2]: position[0] for position, candidate in assignments.items()
    }
    if clear_invalid_recovery:
        for name in protected:
            recovery_room = _active_recovery_room(op_data, name)
            if assigned_rooms.get(name) != recovery_room:
                op_data.operators[name].clear_dorm_recovery()
    return assignments, dropped


def rebalance_closing_dorm_slots(op_data, plan, recalled):
    """固定宿舍成员回班前，统一重排仍在恢复中的动态床位。

    关闭临时 Free 位时，被挤出者和其他动态床位入住者使用同一套
    “休息层级、当前心情、原床位次序”排序。容量不足时只淘汰排序
    最后的成员；如果该成员属于主班，则其整组一并回班并再次计算，
    避免留下无岗位、无床位的半组状态。
    """
    if not getattr(op_data, "experimental_dorm_logic", False):
        return set(recalled)
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
    if not getattr(op_data, "experimental_dorm_logic", False):
        return None
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
    if not getattr(op_data, "experimental_dorm_logic", False):
        return {}
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


def generate_plan_by_drom(
    tasks, op_data, existing_targets=None, release_tasks=None, pending_arrangements=()
):
    # 同时刻的回班与释放床位必须分别保留类型，并共用一次未来状态演算。
    batches = list(tasks.items()) + list((release_tasks or {}).items())
    if not batches:
        return []
    experimental = bool(getattr(op_data, "experimental_dorm_logic", False))
    if experimental:
        # 未来回班只能修改演算快照，不能提前释放正在休息的真实床位。
        # 批次另行复制，避免床位换人后把原入住者的时间套给新入住者。
        op_data = copy.copy(op_data)
        op_data.dorm = copy.deepcopy(op_data.dorm)
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
            if not op.is_high():
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
                if experimental:
                    projected_bed = next(
                        (bed for bed in op_data.dorm if bed.name == op.name), None
                    )
                    if projected_bed is None:
                        continue
                    target_room, target_index = projected_bed.position
                    projected_bed.reset()
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
        names, slots = _arrangement_resources(plan)
        # 从迁移后的床位派生的任务必须晚于迁移本身；不拖延无关房间的回班。
        earliest = max(
            (
                ready + timedelta(seconds=1)
                for ready, moving, changed in pending_resources
                if names & moving or slots & changed
            ),
            default=datetime.min,
        )
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
            if rest_in_full is None and not op_data.config.free_room:
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
    interval = config.conf.merge_interval
    if pending_arrangements:
        # 依赖安排可能使原本较早的释放批次延后；合并器按执行时间遍历。
        result.sort(key=lambda task: task.time)
    merge_release_dorm(result, interval)
    logger.debug("生成任务: " + ("||".join([str(t) for t in result])))
    return result


def plan_metadata(op_data, tasks):
    locked_tasks = [
        task
        for task in tasks
        if op_data.experimental_dorm_logic
        and getattr(task, "product_shift_locked", False)
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
    # 切产物延期任务保留原对象、重试时间与资源锁，只重算其他回班/释放任务。
    tasks = [
        t
        for t in tasks
        if t.type not in [TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM]
        or id(t) in locked_ids
    ]
    pending_arrangements = []
    # 按实际床位定时；迁移完成读房后会重建，避免清理尚未发生的未来位置。
    limited_releases = plan_mood_limit_releases(op_data)
    if op_data.experimental_dorm_logic:
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
        op_data = op_data.project_arrangements(
            task.plan for task in pending_arrangements
        )
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
            if not operator.is_high() and not op_data.is_ling_xi_limited(dorm.name):
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
            # 如果与第一个差值过大，
            base_time = high_dorms[0].time
            need_early = not op_data.operators[high_dorms[0].name].exhaust_require
            if base_time is not None and not rest_in_full_dorms:
                for dorm in high_dorms[1:]:
                    # 三电站限制为1小时，2电站限制为1.5小时
                    limit = 5400 if op_data.power_plant_count == 2 else 3600
                    if dorm.time and (base_time - dorm.time).total_seconds() > limit:
                        logger.debug(
                            f"{high_dorms[0].name} 的时间 {base_time} 被调整为 {dorm.time}，因为时间差超过{limit / 3600}小时"
                        )
                        max_rest_in_full_time = base_time
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
            # 防止时间和前面重复
            if min_resting_time != datetime.max:
                min_resting_time += timedelta(seconds=10)
            if room.time and room.name:
                task_time = min(room.time, min_resting_time)
                if task_time < datetime.now():
                    # 如果干员休息完毕，则不再生成
                    continue
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
    tasks.extend(limited_releases)
    return tasks


def plan_mood_limit_releases(op_data):
    now = datetime.now()
    result = []
    for bed in op_data.all_dorms():
        if not op_data.is_ling_xi_limited(bed.name):
            continue
        op = op_data.operators.get(bed.name)
        if op is None or (op.current_room, op.current_index) != bed.position:
            continue
        if not op_data.is_recovery_dorm(bed, op.name):
            continue
        if op_data.ling_xi_rest_complete(op.name):
            due = now
        elif bed.time is not None:
            due = max(now, bed.time)
        else:
            # 未读到恢复时间时不能凭默认心情提前释放。
            continue
        room, index = bed.position
        names = ["Current"] * len(op_data.plan[room])
        names[index] = "Free"
        result.append(
            SchedulerTask(
                time=due,
                task_plan={room: names},
                task_type=TaskTypes.RELEASE_DORM,
                meta_data=op.name,
                strict_mood_limit=True,
            )
        )
    return result


def prioritize_new_dorm_recovery(op_data, plan, reserved_slots=(), preceding_plan=None):
    """新入住者优先竞争单回位，其余入住者保留已选床位。

    先投影完整入住计划，再按宿舍顺序比较每房首个动态位。仅让排名
    更高的新入住者与目标交换床位，被替换者继续竞争后面的单回位。
    不增加/淘汰休息者，也不因已有入住者心情交叉而搬床。返回计划
    副本，不提前改变真实位置或单回标记。
    """
    if not op_data.experimental_dorm_logic or not plan:
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
        if (
            op is not None
            and bed.name not in explicit_names
            and (op.current_room, op.current_index) != bed.position
        ):
            locked_rooms.add(bed.position[0])
    beds = [bed for bed in beds if bed.position[0] not in locked_rooms]
    arrivals = []
    for bed in beds:
        op = op_data.operators.get(bed.name)
        if (
            op is not None
            and op.name in explicit_names
            and not op_data.is_dynamic_dorm_position(
                op.current_room, op.current_index, op.name
            )
        ):
            arrivals.append(op.name)
    if not arrivals:
        return plan
    now = datetime.now()
    arrivals.sort(key=lambda name: resting_key(op_data, name, now))
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
            if not target.name or resting_key(op_data, source.name, now) >= resting_key(
                op_data, target.name, now
            ):
                continue
            source.name, target.name = target.name, source.name
            for bed in (source, target):
                room, index = bed.position
                result.setdefault(room, ["Current"] * len(op_data.plan[room]))[
                    index
                ] = bed.name or "Free"
    return result


def try_reorder(op_data, new_plan):
    experimental = bool(getattr(op_data, "experimental_dorm_logic", False))
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
    effective_free_indices = [
        idx for idx, room in enumerate(dorm) if op_data.is_effective_free_slot(room)
    ]
    blocked_indices = set(range(len(dorm))) - set(effective_free_indices)
    for idx in blocked_indices:
        dorm[idx].name = ""
        dorm[idx].time = None
    # 测试逻辑的 assign_dorm/group 已经为本轮新休息者选择了床位。这里若
    # 再按实时心情全量映射所有入住者，不同宿舍的恢复速度会改变心情顺序，
    # 下一轮又得到相反映射，最终造成宿舍间反复搬动。先落实已选床位，
    # 再让本轮新入住者竞争单回位；副表切换和临时床关闭单独演算。
    if not experimental:
        dorm_info = [
            {
                "name": dorm[idx].name,
                "index": idx,
                "time": dorm[idx].time,
                "priority": get_ranking(dorm[idx].name),
            }
            for idx in effective_free_indices
        ]
        priority_list = op_data.config.ope_resting_priority
        priority_order = {
            "high": len(priority_list),
            "normal": len(priority_list) + 1,
            "standby": len(priority_list) + 2,
            "low": len(priority_list) + 3,
        }
        dorm_info.sort(
            key=lambda item: (
                priority_list.index(item["name"])
                if item["name"] in priority_list and item["name"]
                else priority_order[item["priority"]],
                item["index"],
            )
        )
        for target_idx, info in zip(effective_free_indices, dorm_info):
            dorm[target_idx].name = info["name"]
            dorm[target_idx].time = info["time"]
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
                if experimental and (
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
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.workshop_automation import (
        restore_if_no_plans,
        workshop_task_current,
    )
    from arknights_mower.utils.workshop_limits import batch_limit
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
            valid = False
            if item.operator in op_data.operators.keys():
                agent = op_data.operators[item.operator]
                valid = agent.mood > 22
            else:
                logger.info(f"自动添加{item.operator}至干员数据列表")
                valid = True
                op_data.add(Operator(item.operator, ""))
            match = False
            base_material_match = False
            non_base_material_match = False
            if item.operator == "九色鹿":
                base_material_match = False
                non_base_material_match = False
                for material in item.items:
                    for name in material.item_names:
                        metadata = workshop_formula[name]
                        if batch_limit(name, metadata, material, inventory_data) > 0:
                            if metadata["apCost"] < 4 or metadata["tab"] == "基建材料":
                                base_material_match = True
                            elif (
                                metadata["apCost"] == 4
                                and metadata["tab"] != "基建材料"
                            ):
                                non_base_material_match = True
                match = base_material_match and non_base_material_match
                if not match:
                    logger.info(
                        f"{item.operator}材料设置不符合要求：请检查合成数量，并确认至少要有一个小于4心情垫刀材料和一个4心情精英材料"
                    )
            else:
                for material in item.items:
                    for name in material.item_names:
                        metadata = workshop_formula[name]
                        if batch_limit(name, metadata, material, inventory_data) > 0:
                            match = True
                            break
                if not match:
                    logger.info(f"{item.operator}材料设置不符合要求: 请检查合成数量")
            if match and valid:
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
                logger.debug("数据不满足条件，跳过加工站任务生成")
    else:
        logger.debug("没有加工站配置或仓库数据，跳过加工站任务生成")


def try_add_release_dorm(plan, time, op_data, tasks):
    if not op_data.config.free_room:
        return
    if not getattr(op_data, "experimental_dorm_logic", False):
        return _try_add_release_dorm_legacy(plan, time, op_data, tasks)
    # 有plan 的情况
    for k, v in plan.items():
        for name in v:
            if name in op_data.operators and time is not None:
                _idx, __dorm = op_data.get_dorm_by_name(name)
                if (
                    __dorm
                    and op_data.is_effective_free_slot(__dorm)
                    and __dorm.time is not None
                    and __dorm.time < time
                ):
                    add_release_dorm(tasks, op_data, name)
    # 普通情况
    if not plan:
        try:
            # 查看是否有未满心情的人
            logger.info("启动不养闲人安排空余宿舍位")
            now = datetime.now()
            standby_waiting = {
                op.name
                for op in op_data.operators.values()
                if op_data.is_standby(op.name)
            }
            reserved = {
                name
                for task in tasks
                for names in task.plan.values()
                for name in names
                if name not in ("", "Current", "Free")
                and not (name in standby_waiting and task.type == TaskTypes.SHIFT_ON)
            }
            reserved_slots = {
                (room, index)
                for task in tasks
                for room, names in task.plan.items()
                for index, name in enumerate(names)
                if name != "Current"
            }
            waiting_list = [
                op
                for op in op_data.operators.values()
                if (not op.is_high() or op.name in standby_waiting)
                and not op.current_room
                and not op_data.ling_xi_rest_complete(op.name)
                and op.name not in reserved
                and resting_tier(op_data, op.name) != RestingTier.EXCLUDED
                and (
                    op.name in standby_waiting
                    or resting_mood(op, now) < op.upper_limit
                    or (
                        resting_tier(op_data, op.name) == RestingTier.REPLACEMENT
                        and resting_mood(op, now) == float("inf")
                    )
                )
            ]
            busy = busy_resting_names()
            waiting_list = [op for op in waiting_list if op.name not in busy]
            waiting_list.sort(key=lambda op: resting_key(op_data, op.name, now))
            if not waiting_list:
                return
            logger.debug(f"有{len(waiting_list)}个干员心情未满")
            plan = {}
            for value in op_data.dorm:
                if not waiting_list:
                    break
                room, index = value.position
                if (
                    value.position in reserved_slots
                    or not op_data.is_effective_free_slot(value)
                ):
                    continue
                agent = op_data.operators.get(value.name)
                if agent is not None:
                    if (agent.current_room, agent.current_index) != value.position:
                        continue
                    mood = resting_mood(agent, now)
                    full = (mood != float("inf") and mood >= agent.upper_limit) or (
                        value.time is not None and value.time <= now
                    )
                    # 候补及以上在恢复期间受保护；休息完成后由不养闲人统一腾床。
                    if not full and not op_data._slot_takable(
                        value, protect_resting=True, requester=waiting_list[0].name
                    ):
                        continue
                elif value.name:
                    continue
                rest = waiting_list.pop(0)
                plan.setdefault(room, ["Current"] * len(op_data.plan[room]))[index] = (
                    rest.name
                )
            if plan:
                plan = prioritize_new_dorm_recovery(op_data, plan, reserved_slots)
                logger.debug(f"不养闲人任务：{plan}")
                logger.info("添加不养闲人任务完成")
                task = SchedulerTask(task_plan=plan)
                tasks.append(task)
        except Exception as ex:
            logger.exception(ex)


def _try_add_release_dorm_legacy(plan, time, op_data, tasks):
    """稳定宿舍不养闲人：普通空闲者及已随组下班的待命候补补床。"""
    for names in plan.values():
        for name in names:
            if name != "Current":
                _, dorm = op_data.get_dorm_by_name(name)
                if dorm and op_data.is_effective_free_slot(dorm) and dorm.time < time:
                    add_release_dorm(tasks, op_data, name)
    if plan:
        return
    try:
        logger.info("启动不养闲人安排空余宿舍位")
        waiting_list = []
        for name, op in op_data.operators.items():
            if (
                (not op.is_high() or op_data.is_standby(name))
                and op.current_mood() < op.upper_limit
                and op.current_room == ""
                and op.name not in op_data.config.free_blacklist
            ):
                heapq.heappush(
                    waiting_list,
                    (
                        1 if name in ["九色鹿", "年"] else 0,
                        (op.current_mood() - op.lower_limit)
                        / (op.upper_limit - op.lower_limit),
                        name,
                    ),
                )
                logger.debug(f"{name}:心情：{op.current_mood()}")
        if not waiting_list:
            return
        logger.debug(f"有{len(waiting_list)}个干员心情未满")
        release_plan = {}
        for dorm in op_data.dorm:
            if not op_data.is_effective_free_slot(dorm):
                continue
            if not waiting_list:
                break
            if not dorm.name:
                replacement = heapq.heappop(waiting_list)
                release_plan.setdefault(
                    dorm.position[0],
                    ["Current"] * len(op_data.plan[dorm.position[0]]),
                )[dorm.position[1]] = replacement[2]
                continue
            if dorm.name in op_data.operators:
                occupant = op_data.operators[dorm.name]
                logger.debug(str(dorm))
                if (not occupant.is_high() or op_data._can_standby(occupant)) and (
                    occupant.current_mood() >= occupant.upper_limit
                    or (dorm.time is not None and dorm.time < datetime.now())
                ):
                    replacement = heapq.heappop(waiting_list)
                    release_plan.setdefault(dorm.position[0], ["Current"] * 5)[
                        dorm.position[1]
                    ] = replacement[2]
        if release_plan:
            logger.debug(f"不养闲人任务：{release_plan}")
            logger.info("添加不养闲人任务完成")
            tasks.append(SchedulerTask(task_plan=release_plan))
    except Exception as ex:
        logger.exception(ex)


def add_release_dorm(tasks, op_data, name):
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


def merge_release_dorm(tasks, merge_interval):
    for idx in range(1, len(tasks) + 1):
        if idx == 1:
            continue
        task = tasks[-idx]
        last_not_release = None
        if task.type != TaskTypes.RELEASE_DORM or getattr(
            task, "strict_mood_limit", False
        ):
            continue
        for index_last_not_release in range(idx + 1, len(tasks) + 1):
            if tasks[-index_last_not_release].type != TaskTypes.RELEASE_DORM and tasks[
                -index_last_not_release
            ].time > task.time - timedelta(minutes=1):
                last_not_release = tasks[-index_last_not_release]
        if last_not_release is not None:
            continue
        elif task.time + timedelta(minutes=merge_interval) > tasks[-idx + 1].time:
            tasks[-idx].time = tasks[-idx + 1].time + timedelta(seconds=1)
            tasks[-idx], tasks[-idx + 1] = (
                tasks[-idx + 1],
                tasks[-idx],
            )
            logger.info(f"自动合并{merge_interval}分钟以内任务")


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
    ):
        if time is None:
            self.time = datetime.now()
        else:
            self.time = time
        self.plan = task_plan
        self.type = set_type_enum(task_type)
        self.meta_data = meta_data
        self.adjusted = adjusted
        self.deferred_by_run_order = False
        self.strict_mood_limit = strict_mood_limit

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
