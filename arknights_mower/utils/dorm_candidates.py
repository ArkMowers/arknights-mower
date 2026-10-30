"""规划与选人共用的宿舍预约和心情候选快照。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from arknights_mower.utils.resting_priority import (
    RestingTier,
    busy_resting_names,
    crafting_rest_order,
    has_resting_mood,
    is_full_dynamic_candidate,
    resting_key,
    resting_mood,
    resting_tier,
    unregistered_idle_candidates,
)


@dataclass
class DormCandidates:
    recovering: list[str]
    full: list[str]
    # 缺少实读且尚需筛选；绿色笑脸观测仍只属于普通补位名单。
    unknown: list[str]
    # 有效低心情卡片仍需实读，但足以触发普通满员住客替换。
    estimated_recovering: list[str]
    # 满员兜底按心情；缺少实读时用卡片预估，不以恢复缺口排序。
    filling: list[str]


def dorm_candidate_mood(op_data, name, now=None, *, estimates=None):
    """调度使用较新的有效心情；卡片预估不生成速率或恢复期限。"""
    observation = scheduling_mood_observation(op_data, name, now, estimates=estimates)
    return observation[0] if observation is not None else None


def scheduling_mood_reaches(op_data, name, limit, now=None):
    """只比较心情，不据此生成恢复计时或速率。"""
    mood = dorm_candidate_mood(op_data, name, now)
    return mood is not None and mood >= limit


def scheduling_mood_observation(op_data, name, now=None, *, estimates=None):
    """返回决策值及来源时间，实读字段和预估缓存分别保留。"""
    now = now or getattr(op_data, "_projection_now", None) or datetime.now()
    if getattr(op_data, "mood_calculation_enabled", False):
        value = op_data.calculated_mood(name, now)
        return (value, now) if value is not None else None
    op = op_data.operators.get(name)
    measured = (
        (op.mood if op.is_resting() else resting_mood(op, now), op.time_stamp)
        if has_resting_mood(op, now)
        and not getattr(op, "mood_is_prediction", False)
        and op.time_stamp <= now
        else None
    )
    mood = card_mood_estimate(op_data, name, now, estimates=estimates)
    if mood is not None:
        values = (
            getattr(op_data, "dorm_mood_estimates", {})
            if estimates is None
            else estimates
        )
        observed_at = values[name][1]
        if measured is None or observed_at > measured[1]:
            return mood, observed_at
    return measured


def card_mood_estimate(op_data, name, now=None, *, estimates=None):
    """返回一小时内的卡牌预估，不创建或修改实读心情。"""
    now = now or getattr(op_data, "_projection_now", None) or datetime.now()
    estimate = (
        getattr(op_data, "dorm_mood_estimates", {}) if estimates is None else estimates
    ).get(name)
    if (
        isinstance(estimate, (tuple, list))
        and len(estimate) >= 2
        and isinstance(estimate[1], datetime)
        and isinstance(estimate[0], (int, float))
        and isfinite(estimate[0])
        and 0 <= estimate[0] <= 24
        and timedelta() <= now - estimate[1] < timedelta(hours=1)
    ):
        return estimate[0]
    return None


def full_dorm_candidate(op_data, name, *, estimates=None, now=None):
    """单回满心情判断使用较新的有效实读、卡片观测或排序推断。"""
    mood = dorm_candidate_mood(op_data, name, now, estimates=estimates)
    return mood is not None and mood >= 24


def unstarted_product_wait(task):
    """仅因切表依赖等待、尚未执行换人或切产物的任务。"""
    return bool(getattr(task, "product_shift_waiting", False)) and not any(
        getattr(task, flag, False)
        for flag in (
            "backup_shift_active",
            "product_shift_locked",
            "product_switched_before_arrangement",
            "derived_correction_started",
            "group_shift_expected",
            "arrangement_retry_room",
        )
    )


def product_wait_resting_replacements(op_data, task):
    """尚未开始换人的切产物预约允许未接岗的普通替班临时恢复。"""
    if not getattr(task, "product_shift_locked", False) or any(
        getattr(task, flag, False)
        for flag in (
            "backup_shift_active",
            "product_switched_before_arrangement",
            "derived_correction_started",
            "group_shift_expected",
            "arrangement_retry_room",
        )
    ):
        return set()
    return {
        name
        for room, row in task.plan.items()
        if not room.startswith("dorm")
        for name in row
        if name in getattr(task, "product_lock_names", ())
        and name not in getattr(task, "urgent_recovery_reserved_names", ())
        and (op := op_data.operators.get(name)) is not None
        and callable(getattr(op, "is_high", None))
        and callable(getattr(op, "is_working", None))
        and not op.is_high()
        and not op.is_working()
    }


def retained_task_reservations(
    op_data, tasks, *, current_task=None, returning_groups=()
):
    """保留执行预约目标、当前驻员和整组成员，规划与纠错共用。"""
    tasks = [task for task in tasks if not unstarted_product_wait(task)]
    if returning_groups:
        from arknights_mower.utils.retained_recovery import retained_recovery_may_return

        names, slots = set(), set()
        for task in tasks:
            if (
                task is None
                or task is current_task
                or getattr(task, "run_order_staffing_wait", False)
                or not getattr(task, "retains_execution", False)
            ):
                continue
            task_names, task_slots = retained_task_reservations(op_data, [task])
            released = {
                name
                for group in returning_groups
                if retained_recovery_may_return(op_data, task, group)
                for name in op_data.shift_group_members(group)
            }
            task_names.difference_update(released)
            task_slots.difference_update(
                position
                for name in released
                for op in (op_data.operators[name],)
                for position in (
                    (op.current_room, op.current_index),
                    (op.room, op.index),
                )
            )
            names.update(task_names)
            slots.update(task_slots)
        return names, slots
    names, slots = set(), set()
    for task in tasks:
        if (
            task is None
            or task is current_task
            or getattr(task, "run_order_staffing_wait", False)
            or not getattr(task, "retains_execution", False)
        ):
            continue
        for room, row in task.plan.items():
            for index, name in enumerate(row):
                if name != "Current":
                    slots.add((room, index))
                if name not in ("", "Current", "Free"):
                    names.add(name)
        for position, name in getattr(task, "group_shift_expected", {}).items():
            if name != "Current":
                slots.add(position)
            if name not in ("", "Current", "Free"):
                names.add(name)
        names.update(task.release_dorm_targets())
    from arknights_mower.utils.urgent_recovery import pending_urgent_reservations

    pending_names, pending_slots = pending_urgent_reservations(tasks, current_task)
    names.update(pending_names)
    slots.update(pending_slots)
    if not names and not slots:
        return names, slots
    names.update(
        name
        for name, op in op_data.operators.items()
        if (op.current_room, op.current_index) in slots
    )
    groups = {
        group
        for name in names
        if (op := op_data.operators.get(name)) is not None
        for group in (
            [getattr(op, "group", "")]
            if not getattr(op, "multi_group", False)
            else [binding["group"] for binding in op.group_bindings]
        )
        if group
    }
    names.update(
        name
        for group in groups
        for name in getattr(op_data, "groups", {}).get(group, ())
    )
    # 目标干员仍在其他工作站时保留姓名和目标岗位，允许源岗位先释放。
    from arknights_mower.utils.scheduler_task import TaskTypes

    restoration_sources = {
        (name, op.current_room, op.current_index)
        for task in tasks
        if task is not current_task
        for room, row in (
            task.plan
            if getattr(task, "product_shift_locked", False)
            or getattr(task, "backup_shift_active", False)
            else getattr(task, "run_order_original_roster", {})
            if getattr(task, "run_order_restore_pending", False)
            else getattr(task, "emergency_original_roster", {})
            if task.type == TaskTypes.RUN_ORDER and not task.meta_data
            else {}
        ).items()
        for name in row
        if (op := op_data.operators.get(name)) is not None
        and op.is_working()
        and op.current_room != room
    }
    slots.update(
        (op.current_room, op.current_index)
        for name in names
        if (op := op_data.operators.get(name)) is not None
        and op.current_room
        and op.current_index >= 0
        and (name, op.current_room, op.current_index) not in restoration_sources
    )
    return names, slots


def dorm_task_reservations(op_data, tasks, excluded=()):
    """规划与执行采用相同预约；待命候补的回班任务不阻止其临时恢复。"""
    tasks = [task for task in tasks if not unstarted_product_wait(task)]
    recovering_tasks = [
        (task, recovering)
        for task in tasks
        if (recovering := product_wait_resting_replacements(op_data, task))
    ]
    recovering_ids = {id(task) for task, _ in recovering_tasks}
    names, retained_slots = retained_task_reservations(
        op_data, [task for task in tasks if id(task) not in recovering_ids]
    )
    for task, recovering in recovering_tasks:
        task_names, task_slots = retained_task_reservations(op_data, [task])
        task_names.difference_update(recovering)
        # 只释放临时恢复者的源床，原任务的目标床和其他任务预约继续生效。
        target_slots = {
            (room, index)
            for room, row in task.plan.items()
            for index, name in enumerate(row)
            if name != "Current"
        }
        task_slots.difference_update(
            (op.current_room, op.current_index)
            for name in recovering
            for op in (op_data.operators[name],)
            if op.current_room.startswith("dorm")
            and (op.current_room, op.current_index) not in target_slots
        )
        names.update(task_names)
        retained_slots.update(task_slots)
    names.update(set(excluded) - {"", "Current", "Free"})
    names.update(getattr(op_data, "emergency_reserved_agents", ()))
    slots = {slot for slot in retained_slots if slot[0].startswith("dorm")}
    for task in tasks:
        if task is None or getattr(task, "run_order_staffing_wait", False):
            continue
        if not (
            getattr(task, "emergency_staffing", False)
            and task.retains_execution
            and not getattr(task, "emergency_recovery_release", False)
        ):
            names.update(getattr(task, "emergency_staffing_members", ()))
        names.update(
            name
            for row in getattr(task, "run_order_original_roster", {}).values()
            for name in row
            if name not in ("", "Current", "Free")
        )
        names.update(
            name
            for row in getattr(task, "emergency_original_roster", {}).values()
            for name in row
            if name not in ("", "Current", "Free")
        )
        task_type = getattr(getattr(task, "type", None), "name", "")
        if (
            task_type == "RELEASE_DORM"
            and task.time
            > (getattr(op_data, "_projection_now", None) or datetime.now())
            and not task.retains_execution
            and not getattr(task, "strict_mood_limit", False)
            and not getattr(task, "product_shift_locked", False)
            and not getattr(task, "emergency_recovery_release", False)
            and len(task.plan) == 1
            and (targets := task.release_dorm_targets())
            and all(
                name in ("Current", "Free")
                for row in task.plan.values()
                for name in row
            )
            and len(targets) == sum(row.count("Free") for row in task.plan.values())
        ):
            # 普通未来清退随换床后的实读重建，不为旧床预约整间宿舍。
            continue
        returning = task_type == "SHIFT_ON"
        recovering = product_wait_resting_replacements(op_data, task)
        for room, row in task.plan.items():
            for index, name in enumerate(row):
                if room.startswith("dorm") and name != "Current":
                    slots.add((room, index))
                if name in ("", "Current", "Free"):
                    continue
                if name not in recovering and not (
                    returning and name in op_data.operators and op_data.is_standby(name)
                ):
                    names.add(name)
    return names, slots


def vacant_dorm_slots(op_data, reserved_slots=()):
    """只认当前已经开放、实际缓存无人且尚未预约的动态床位。"""
    return {
        bed.position
        for bed in op_data.dorm
        if not bed.name
        and bed.position not in reserved_slots
        and op_data.is_effective_free_slot(bed)
        and op_data.get_current_operator(*bed.position) is None
    }


def dorm_candidates(
    op_data, excluded=(), *, include_standby=True, current_residents=(), now=None
):
    now = now or getattr(op_data, "_projection_now", None) or datetime.now()
    excluded = set(excluded) | busy_resting_names() | {op_data.get_train_support()}
    replacement_names = {
        name
        for slots in op_data.plan.values()
        for slot in slots
        if slot.agent != "菲亚梅塔"
        for name in slot.all_replacements
    }
    moods, estimate_keys = {}, {}

    def candidate_mood(name):
        if name not in moods:
            moods[name] = dorm_candidate_mood(op_data, name, now)
        return moods[name]

    recovering, full, unknown = [], [], []
    for name, op in op_data.operators.items():
        if (
            name in excluded
            or op.is_high()
            and not (include_standby and op_data.is_standby(name))
            or op.current_room
            and not (name in current_residents and op.current_room.startswith("dorm"))
            or op_data.rest_mood_complete(name)
            or resting_tier(op_data, name, replacement_names=replacement_names)
            == RestingTier.EXCLUDED
        ):
            continue
        mood = candidate_mood(name)
        if not has_resting_mood(op, now):
            if (mood is not None and mood < op.upper_limit) or (
                not op.is_high() and not op_data.has_rest_mood_limit(name)
            ):
                unknown.append(name)
            continue
        if (
            not op_data.idle_rest_checked(name)
            and mood is not None
            and mood < op.upper_limit
        ):
            recovering.append(name)
        elif not op.is_high() and not op_data.has_rest_mood_limit(name):
            full.append(name)
    recovering.sort(
        key=lambda name: resting_key(
            op_data, name, now, replacement_names=replacement_names
        )
    )
    recovering = crafting_rest_order(
        op_data, recovering, replacement_names=replacement_names
    )

    unknown.extend(unregistered_idle_candidates(op_data, excluded))

    def estimate_key(name):
        if name not in estimate_keys:
            mood = candidate_mood(name)
            estimate_keys[name] = (
                is_full_dynamic_candidate(op_data, name, now),
                24 if mood is None else mood,
                resting_tier(op_data, name, now, replacement_names=replacement_names),
            )
        return estimate_keys[name]

    full.sort(key=estimate_key)
    unknown.sort(key=estimate_key)
    filling = sorted([*recovering, *full, *unknown], key=estimate_key)
    # 绿色笑脸只撤销主动核验；仍可补空床，不进入实读 full 集合。
    unknown = [
        name for name in unknown if (mood := candidate_mood(name)) is None or mood < 24
    ]
    unknown = crafting_rest_order(op_data, unknown, replacement_names=replacement_names)
    filling = crafting_rest_order(op_data, filling, replacement_names=replacement_names)
    estimated_recovering = [
        name
        for name in unknown
        if (mood := candidate_mood(name)) is not None
        and mood < getattr(op_data.operators.get(name), "upper_limit", 24)
    ]
    return DormCandidates(recovering, full, unknown, estimated_recovering, filling)
