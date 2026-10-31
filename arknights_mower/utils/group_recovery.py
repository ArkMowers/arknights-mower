"""工作主班的回满要求与本轮延迟回班期限。"""

from datetime import datetime, timedelta
from uuid import uuid4

from arknights_mower.utils import config


def recovery_mood_complete(data, operator, now=None):
    """按所选心情来源判断回满，不改写恢复记录。"""
    from arknights_mower.utils.dorm_candidates import dorm_candidate_mood

    if operator is None:
        return False
    mood = (
        data.calculated_mood(operator.name, now)
        if getattr(data, "mood_calculation_enabled", False)
        else dorm_candidate_mood(data, operator.name, now)
    )
    return mood is not None and mood >= operator.upper_limit


def observed_recovery_deadline(data, name, now=None):
    """按模型或宿舍实读倒计时规划恢复，不将固定岗位开放为 Free。"""
    op = data.operators[name]
    if getattr(data, "mood_calculation_enabled", False):
        return data.calculated_mood_deadline(name, op.upper_limit, now)
    _, bed = data.get_dorm_by_name(name)
    if bed is not None:
        return bed.time
    observation = getattr(op, "dorm_recovery_observation", None)
    if (
        observation is not None
        and observation[:2] == ((op.current_room, op.current_index), op.time_stamp)
        and not getattr(op, "mood_is_prediction", False)
    ):
        due = observation[2]
        if op.mood < 24:
            due = op.time_stamp + (due - op.time_stamp) * (
                (op.upper_limit - op.mood) / (24 - op.mood)
            )
        return due
    return None


def observed_full_mood(operator):
    """只有实际采样能确认恢复完成，倒计时推算不构成实读。"""
    return (
        operator is not None
        and operator.time_stamp is not None
        and not getattr(operator, "mood_is_prediction", False)
        and 0 <= operator.mood <= 24
        and operator.mood >= operator.upper_limit
    )


def completed_mood_limit_release(data, operator):
    """已确认的个人上限离宿完成本轮恢复，实际心情仍保留读数。"""
    return (
        not operator.current_room
        and not getattr(operator, "mood_is_prediction", False)
        and getattr(operator, "rest_mood_release_limit", None) == operator.upper_limit
        and data.rest_mood_complete(operator.name)
    )


def group_recovery_workers(data, group):
    """仅工作主班参与组内恢复，候补、宿管和零心情工作者不增加等待。"""
    return [
        op
        for name in data.shift_group_members(group)
        for op in [data.operators[name]]
        if op.is_high()
        and not op.room.startswith("dorm")
        and not op.independent_rest
        and not op.workaholic
        and not data._can_standby(op)
        and (op.is_resting() or not op.current_room)
    ]


def group_recovery_deadline(data, group, *, now=None):
    """额外等待仅限制组内时间差等待，明确回满要求始终生效。"""
    now = now or getattr(data, "_projection_now", None) or datetime.now()
    conf = getattr(data, "runtime_conf", None) or config.conf
    workers = group_recovery_workers(data, group)
    gap_workers = [op for op in workers if not op.multi_group]
    latches = getattr(data, "group_recovery_full_members", None)
    if latches is None:
        latches = data.group_recovery_full_members = {}
    anchors = getattr(data, "group_recovery_return_time", None)
    if anchors is None:
        anchors = data.group_recovery_return_time = {}

    def completed_at(op):
        if recovery_mood_complete(data, op, now) or completed_mood_limit_release(
            data, op
        ):
            return now
        return observed_recovery_deadline(data, op.name, now)

    if group in conf.group_mood_gap_exclusions:
        latches.pop(group, None)
        anchors.pop(group, None)
    elif group in latches:
        latches[group] = [
            op.name
            for op in gap_workers
            if op.is_resting() or op.name in latches[group]
        ]
    elif conf.group_rest_in_full_on_mood_gap:
        times = [at for op in gap_workers if (at := completed_at(op)) is not None]
        threshold = conf.group_mood_gap_threshold_minutes
        if threshold is None:
            threshold = 90 if data.power_plant_count == 2 else 60
        limit = timedelta(minutes=threshold)
        if len(times) > 1 and max(times) - min(times) > limit:
            latches[group] = [op.name for op in gap_workers]
    gap_names = latches.get(group, [])
    if gap_names and group not in anchors:
        residents = [op for op in gap_workers if op.is_resting()]
        high = [op for op in residents if op.resting_priority == "high"]
        times = [
            at
            for op in high or residents or gap_workers
            if (at := completed_at(op)) is not None
        ]
        if times:
            anchors[group] = max(now, min(times) - timedelta(minutes=8))
    max_wait = conf.group_mood_gap_max_extra_wait_hours
    cap = (
        anchors[group] + timedelta(hours=max_wait)
        if gap_names and max_wait > 0 and group in anchors
        else None
    )
    explicit = [op.name for op in workers if op.rest_in_full]
    required = list(
        dict.fromkeys(explicit + (gap_names if cap is None or now < cap else []))
    )
    explicit_times = [completed_at(data.operators[name]) for name in explicit]
    # 缺少个别读数时沿用可用期限，不把补读变成整组回班的前置条件。
    deadlines = [at for at in explicit_times if at is not None]
    if gap_names:
        times = [completed_at(data.operators[name]) for name in gap_names]
        known = [at for at in times if at is not None]
        if len(known) != len(times) and cap is not None:
            deadlines.append(cap)
        elif known:
            latest = max(known)
            deadlines.append(min(latest, cap) if cap is not None else latest)
    return required, max(now, *deadlines) if deadlines else None


def _returning_mood(data, op, now):
    """仅为回班门槛推算已恢复心情，不写入实读或回满证据。"""
    from arknights_mower.utils.dorm_candidates import scheduling_mood_observation

    observation = scheduling_mood_observation(data, op.name, now)
    if observation is None:
        return None
    mood, observed_at = observation
    if (
        getattr(data, "mood_calculation_enabled", False)
        or not op.is_resting()
        or observed_at != op.time_stamp
        or mood >= op.upper_limit
    ):
        return mood
    due = observed_recovery_deadline(data, op.name, now)
    if due is None or due <= observed_at:
        return mood
    return min(
        op.upper_limit,
        mood + (op.upper_limit - mood) * (now - observed_at) / (due - observed_at),
    )


def mood_limit_release_yields(data, release, returning, *, now=None):
    """获准回班只越过配对清退，逐房复核本人离宿所需的剩余时间。"""
    from arknights_mower.utils.operation_timing import estimate_work_minutes
    from arknights_mower.utils.scheduler_task import TaskTypes

    pair = getattr(returning, "mood_limit_return_pair", None)
    name = getattr(returning, "mood_limit_return_name", None)
    if (
        data is None
        or not pair
        or pair != getattr(release, "mood_limit_return_pair", None)
        or returning.type != TaskTypes.SHIFT_ON
        or getattr(returning, "execution_failure", None)
        or release.type != TaskTypes.RELEASE_DORM
        or not getattr(release, "strict_mood_limit", False)
        or not getattr(release, "mood_limit_return_attempted", False)
        or release.meta_data != name
    ):
        return False
    op = data.operators.get(name)
    targets = release.release_dorm_targets()
    if (
        op is None
        or op.room.startswith("dorm")
        or set(targets) != {name}
        or getattr(release, "mood_limit", None) not in (None, op.upper_limit)
    ):
        return False
    if (op.current_room, op.current_index) == (op.room, op.index):
        return True
    if targets[name] != (op.current_room, op.current_index) or returning.plan.get(
        op.room, []
    )[op.index : op.index + 1] != [name]:
        return False
    rooms = [room for room in returning.plan if not room.startswith("dorm")]
    seconds = sum(
        estimate_work_minutes(room) * 60 for room in rooms[: rooms.index(op.room) + 1]
    )
    return (now or datetime.now()) + timedelta(seconds=seconds) <= getattr(
        release, "mood_limit_deadline", release.time
    )


def mood_limit_group_return(data, release, tasks, *, now=None):
    """上限离宿先尝试已有整组回班，原清退保留期限及失败后的执行责任。"""
    from arknights_mower.utils.dorm_candidates import retained_task_reservations
    from arknights_mower.utils.operation_timing import estimate_work_minutes
    from arknights_mower.utils.scheduler_task import TaskTypes, generate_plan_by_drom

    now = now or datetime.now()
    from arknights_mower.utils.backup_group_tasks import held_rest_groups

    def untouched(task):
        return not (
            task.retains_execution
            or getattr(task, "backup_shift_active", False)
            or getattr(task, "product_shift_locked", False)
            or getattr(task, "group_shift_expected", {})
            or getattr(task, "backup_explicit_slots", ())
            or getattr(task, "mood_physical_started", False)
            or getattr(task, "dorm_recovery_restore", ())
        )

    if (
        release.type != TaskTypes.RELEASE_DORM
        or not getattr(release, "strict_mood_limit", False)
        or release.time > now
        or not any(task is release for task in tasks)
        or not untouched(release)
        or getattr(release, "mood_limit_return_attempted", False)
    ):
        return None
    op = data.operators.get(release.meta_data)
    if (
        op is None
        or not op.is_high()
        or not op.group
        or op.room.startswith("dorm")
        or op.workaholic
        or data._can_standby(op)
        or op.multi_group
        or op.independent_rest
        or not data.group_is_resting(op.group)
        or op.group in held_rest_groups(data)
        or not data.has_rest_mood_limit(op.name)
        or data.is_free_room_excluded(op.name)
        or release.release_dorm_targets().get(op.name)
        != (op.current_room, op.current_index)
        or getattr(release, "mood_limit", None) not in (None, op.upper_limit)
    ):
        return None
    for task in tasks:
        if task.type != TaskTypes.SHIFT_ON or not untouched(task):
            continue
        if task.plan.get(op.room, [])[op.index : op.index + 1] != [op.name]:
            continue
        # 只提取本组正常回班，不能把同批其他组的回班一并提前。
        _, bed = data.get_dorm_by_name(op.name)
        if bed is None:
            continue
        candidates = generate_plan_by_drom({now: ([bed], False)}, data, now=now)
        task = next(
            (
                candidate
                for candidate in candidates
                if candidate.plan.get(op.room, [])[op.index : op.index + 1] == [op.name]
            ),
            None,
        )
        if task is None:
            continue
        names, slots = retained_task_reservations(
            data, tasks, returning_groups=[op.group]
        )
        if any(
            name != "Current" and ((room, index) in slots or name in names)
            for room, row in task.plan.items()
            for index, name in enumerate(row)
        ):
            continue
        # 工作站先执行；必须给清退对象所在房间及之前的工作站留足操作时间。
        rooms = [room for room in task.plan if not room.startswith("dorm")]
        if op.room not in rooms:
            continue
        seconds = sum(
            estimate_work_minutes(room) * 60
            for room in rooms[: rooms.index(op.room) + 1]
        )
        deadline = getattr(release, "mood_limit_deadline", release.time)
        if now + timedelta(seconds=seconds) > deadline:
            continue
        returning = [
            member
            for room, row in task.plan.items()
            if not room.startswith("dorm")
            for index, name in enumerate(row)
            if (member := data.operators.get(name)) is not None
            and (member.room, member.index) == (room, index)
        ]
        groups = {member.group for member in returning if member.group}
        if any(
            required or due is not None
            for required, due in (
                group_recovery_deadline(data, group, now=now) for group in groups
            )
        ):
            continue
        if any(
            member.rest_in_full
            or not member.workaholic
            and not data._can_standby(member)
            and (
                (mood := _returning_mood(data, member, now)) is None
                or mood <= data.resting_mood_threshold(member)
            )
            for member in returning
        ):
            continue
        release.mood_limit_return_attempted = True
        task.mood_limit_return_name = op.name
        task.mood_limit_return_pair = release.mood_limit_return_pair = uuid4().hex
        tasks.append(task)
        return task
    return None
