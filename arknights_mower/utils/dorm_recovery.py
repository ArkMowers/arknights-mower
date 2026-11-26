"""在目标最终床位建立单回入驻顺序。"""

from dataclasses import dataclass
from datetime import datetime

from arknights_mower.utils import dorm_skills
from arknights_mower.utils.dorm_candidates import (
    dorm_candidates,
    full_dorm_candidate,
)
from arknights_mower.utils.resting_priority import RestingTier, resting_tier


class DormRecoveryPaddingUnavailable(Exception):
    """选人页没有足够的满心情空闲垫位者，继续正常阵容。"""


@dataclass(frozen=True)
class DirectDormArrival:
    observed: list[dict]


def active_recovery_position(data, op, *, names=None, stages=None):
    """床位、同住者和练度仍与实读一致时才保护单回；旧缓存没有这份证据。"""
    room = getattr(op, "dorm_recovery_room", "")
    index = getattr(op, "dorm_recovery_index", -1)
    if (
        room not in data.plan
        or index < 0
        or (op.current_room, op.current_index) != (room, index)
        or not getattr(op, "dorm_recovery_roster", ())
    ):
        return None
    if names is None:
        names = data.get_current_room(room, True)
    if stages is None:
        from arknights_mower.utils.calculated_mood import known_operator_stages

        stages = known_operator_stages(data)
    if op.dorm_recovery_roster != recovery_roster(data, names, stages):
        return None
    managers = recovery_managers(data, room, names, update_cache=False, stages=stages)
    if managers and getattr(op, "dorm_recovery_fixed", ()) == managers:
        return room, index
    return None


def single_recovery_bed_cost(bed, beds):
    """普通床和单 Free 宿舍同价；多 Free 宿舍的首床留给普通恢复者。"""
    peers = [other for other in beds if other.position[0] == bed.position[0]]
    return int(
        len(peers) > 1 and bed.position[1] == min(other.position[1] for other in peers)
    )


def recovery_managers(op_data, room, agents, *, update_cache=True, stages=None):
    """返回最终名单所有可能提供单回的干员及其移动版本，不按位置指定来源。"""
    from arknights_mower.utils.calculated_mood import known_operator_stages

    if len(agents) != len(op_data.plan.get(room, ())):
        return ()
    sources = []
    for index, name in enumerate(agents):
        if not name or name in ("Free", "Current"):
            continue
        op = op_data.operators.get(name)
        single = dorm_skills.is_single_recovery_manager(name)
        if op is not None and update_cache:
            op.single_recovery_manager = single
        if single:
            if stages is None:
                stages = known_operator_stages(op_data)
            if dorm_skills.dorm_skill_effects(name, stages.get(name)).single != {0}:
                sources.append((name, index, getattr(op, "dorm_position_version", 0)))
    return tuple(sources)


def possible_recovery_provider(data, name):
    from arknights_mower.utils.calculated_mood import known_operator_stages

    return dorm_skills.is_single_recovery_manager(
        name
    ) and dorm_skills.dorm_skill_effects(
        name, known_operator_stages(data).get(name)
    ).single != {0}


# 心情条宽 310 像素，允许两像素边缘误差；倒计时按秒显示。
_BAR_WIDTH = 310
_BAR_ERROR_PIXELS = 2
_BAR_ERROR = _BAR_ERROR_PIXELS * 24 / _BAR_WIDTH


def _recipient_from_rates(unfinished, intervals, skill_options):
    """每种可能练度下只比较一对来源和受益者，共同恢复速度须符合所有读数。"""
    from itertools import product

    recipient = None
    for effects in product(*skill_options.values()):
        # 相同受益者和数值只核对一次。同一练度的自回同时用于该来源的测速。
        offers = set()
        bounds = {}
        single_share = 0
        for provider, effect in zip(skill_options, effects, strict=True):
            if provider in intervals:
                start, end = intervals[provider]
                # 中枢对精英干员可能额外提供 0.1 点/小时。
                bounds[provider] = (
                    start - effect.self_rate - 0.1,
                    end - effect.self_rate,
                )
            if any(effect.single):
                for target in unfinished:
                    if target != provider:
                        offers.add((target, effect.single_bonus_for(target)))
            if len(unfinished) == 1:
                single_share = max(single_share, effect.shared_recovery)

        # 无人能给出单回时，读数仍可能来自自回或单人分摊。
        for target, bonus in offers or {(None, 0)}:
            # 单人分摊与普通单回取最高。二者等值时也无法确认是哪种技能生效。
            effective_bonus = max(single_share, bonus)
            low, high = 1.6, 6.0
            for name, (start, end) in bounds.items():
                extra = effective_bonus if name == target else single_share
                low = max(low, start - extra)
                high = min(high, end - extra)
                if low > high:
                    break
            else:
                if bonus <= single_share or recipient not in (None, target):
                    return None
                recipient = target
    return recipient


def observed_recovery_recipient(observed, stages):
    """从五床实读和已知或可能解锁的技能判定普通单回的受益者。"""
    if not observed or len(observed) != 5:
        return None
    if any(
        not isinstance(row, dict)
        or not row.get("observed", True)
        or not isinstance(row.get("agent"), str)
        for row in observed
    ):
        return None
    occupied = {row["agent"]: row for row in observed if row["agent"]}
    if len(occupied) != sum(bool(row["agent"]) for row in observed):
        return None
    skill_options = {
        name: dorm_skills.dorm_skill_options(name, stages.get(name))
        for name in occupied
        if name != "菲亚梅塔"
    }
    if any(not e.comparable for options in skill_options.values() for e in options):
        return None
    sources = {
        name
        for name, options in skill_options.items()
        if any(any(e.single) for e in options)
    }
    if not sources:
        return None
    sharing = {
        name
        for name, options in skill_options.items()
        if any(e.shares_recovery for e in options)
    }
    unfinished = []
    intervals = {}
    for name in skill_options:
        row = occupied[name]
        mood = row.get("measured_mood")
        seconds = row.get("recovery_seconds")
        sole_source = len(sources) == 1 and name in sources and not sharing
        if type(mood) not in (int, float) or not 0 <= mood <= 24:
            if sole_source:
                continue
            return None
        if mood == 24 and seconds is None:
            continue
        interior_bar = _BAR_ERROR < mood < 24 - _BAR_ERROR
        if seconds is None:
            if not interior_bar:
                if sole_source:
                    continue
                return None
            # 中段条足以确认未满。没有倒计时仍可能受益，只是不提供速度。
            unfinished.append(name)
            continue
        if type(seconds) is not int or seconds <= 0:
            return None
        if seconds == 1 and mood < 24 - _BAR_ERROR:
            return None
        unfinished.append(name)
        if interior_bar:
            missing = 24 - mood
            intervals[name] = (
                (missing - _BAR_ERROR) * 3600 / (seconds + 1),
                (missing + _BAR_ERROR) * 3600 / (seconds - 1),
            )

    candidates = [name for name in unfinished if sources - {name}]
    if not candidates:
        return None
    sole_unlocked = len(candidates) == 1 and any(
        all(any(e.single) for e in skill_options[n]) for n in sources - {candidates[0]}
    )
    if not sole_unlocked and len(intervals) < 2:
        return None
    if sharing and len(unfinished) > 1:
        # 多人均分时，分摊量在室友的速度差中抵消。唯一可得者不必靠速度区分。
        if not sole_unlocked and (
            len(sharing) != 1 or any(n in sources or n in sharing for n in unfinished)
        ):
            return None
        fia = occupied.get("菲亚梅塔")
        if fia and (
            fia.get("measured_mood") != 24 or fia.get("recovery_seconds") is not None
        ):
            return None
    return _recipient_from_rates(unfinished, intervals, skill_options)


def dorm_departures_sampled(observed, remaining):
    """这次读房已记录所有将离宿住客的实测心情。"""
    return all(
        row.get("observed", True)
        and (not row["agent"] or row["agent"] in remaining or row.get("mood_sampled"))
        for row in observed
    )


def _ordinary_roommate_change(names, agents, target, stages, *, allow_vacancy=False):
    """目标和唯一来源留在原床，只有普通室友在原槽换人。"""
    if (
        len(names) != 5
        or len(agents) != 5
        or not target
        or target not in names
        or agents[names.index(target)] != target
        or any(n in ("Current", "Free", "菲亚梅塔") for n in (*names, *agents))
    ):
        return False
    changes = [(a, b) for a, b in zip(names, agents) if a != b]
    if not changes or (not allow_vacancy and any(not a for a, _ in changes)):
        return False
    effects = {
        n: dorm_skills.dorm_skill_effects(n, stages.get(n))
        for n in set(names).union(agents) - {""}
    }
    if any(
        not e.comparable or e.extra_target or e.shares_recovery
        for e in effects.values()
    ):
        return False
    providers = [n for n, e in effects.items() if any(e.single)]
    changed = {n for pair in changes for n in pair if n}
    return (
        len(providers) == 1
        and providers[0] not in changed | {target}
        and not effects[target].affects_self
        and all(
            not effects[n].affects_self and not dorm_skills.is_group_recovery_manager(n)
            for n in changed
        )
    )


def direct_recovery_arrival(
    agents, target, observed, stages, recipient, *, continued=None
):
    """根据换班前的实读决定能否一次提交最终名单，确认后再核对受益者。"""
    names = [row["agent"] for row in observed]
    if (
        len(names) != 5
        or len(agents) != 5
        or any(n in ("Current", "Free") for n in agents)
        or any(not row.get("observed", True) for row in observed)
    ):
        return False
    effects = {
        n: dorm_skills.dorm_skill_effects(n, stages.get(n))
        for n in set(names + agents)
        if n and n != "菲亚梅塔"
    }
    if any(not e.comparable or e.extra_target for e in effects.values()):
        return False
    sources = [n for n, e in effects.items() if any(e.single)]
    if len(sources) != 1:
        return False
    (provider,) = sources
    if (
        provider not in names
        or provider not in agents
        or names.index(provider) != agents.index(provider)
    ):
        return False
    unfinished = {
        row["agent"]
        for row in observed
        if row["agent"]
        and (row.get("measured_mood") != 24 or row.get("recovery_seconds") is not None)
    }
    sharing = {n for n, effect in effects.items() if effect.shares_recovery}
    if sharing or "菲亚梅塔" in names + agents:
        # 满房中三名原住客均不动，菲亚梅塔前一位已满，两名普通新人只换最后两床。
        return (
            names[:3] == agents[:3]
            and sharing == {names[0]}
            and names[1:3] == [provider, "菲亚梅塔"]
            and all(names)
            and not unfinished
            and agents[3] == target
            and all(
                n and n not in names and not effects[n].affects_self for n in agents[3:]
            )
        )
    if recipient == target and names.index(target) == agents.index(target):
        return True
    if recipient is None and _ordinary_roommate_change(
        names, agents, target, stages, allow_vacancy=continued == target
    ):
        # 只换室友时，旧房读不清也先完成换班。新房读明确给错再纠正。
        return True
    changes = [(a, b) for a, b in zip(names, agents) if a != b]
    if recipient and recipient != target:
        # 仅两名未满住客互换，目标换到原受益者的前床。结果仍须确认后实读。
        if changes == [(recipient, target), (target, recipient)]:
            return unfinished == {recipient, target}
    arrivals = [n for n in agents if n and n not in names]
    if not arrivals or arrivals[0] != target:
        return False
    if not unfinished:
        return True
    # 唯一未满的普通住客离开，目标接原床，第二位新人住进后方空床。
    index = agents.index(target)
    leaving = names[index]
    mood = observed[index].get("measured_mood")
    seconds = observed[index].get("recovery_seconds")
    return (
        unfinished == {leaving}
        and leaving not in agents
        and len(arrivals) == 2
        and changes == [(leaving, target), ("", arrivals[1])]
        and type(mood) in (int, float)
        and _BAR_ERROR < mood < 24 - _BAR_ERROR
        and type(seconds) is int
        and seconds > 1
        and not any(effects[n].affects_self for n in (leaving, *arrivals))
    )


def fourth_bed_removals(agents, target, observed, recipient, stages) -> tuple[int, ...]:
    """返回依次移出住客的床位下标。空元组表示继续常规排班。"""
    names = [row["agent"] for row in observed]
    if (
        len(names) != 5
        or len(agents) != 5
        or not recipient
        or not names[2]
        or names[3] != recipient
        or agents[:4] != [*names[:2], target, recipient]
        or (names[4] and names[4] != agents[4])
        or not observed[3].get("mood_sampled")
        or not dorm_departures_sampled(observed, agents)
        or any(
            row.get("measured_mood") != 24 or row.get("recovery_seconds") is not None
            for row in observed[:2]
        )
        or "菲亚梅塔" in names
    ):
        return ()
    for name in set(filter(None, (*names, *agents))):
        effect = dorm_skills.dorm_skill_effects(name, stages.get(name))
        if (
            not effect.comparable
            or effect.affects_self
            or effect.shares_recovery
            or effect.extra_target
            or name not in names[:2]
            and any(effect.single)
        ):
            return ()
    if not names[4]:
        newcomer = agents[4]
        if target in names or newcomer and (newcomer in names or newcomer == target):
            return ()
        return (3,)
    if target != names[2]:
        return ()
    if (
        observed[4].get("measured_mood") == 24
        and observed[4].get("recovery_seconds") is None
    ):
        return (3,)
    for row in (observed[2], observed[4]):
        mood = row.get("measured_mood")
        seconds = row.get("recovery_seconds")
        if not (
            type(mood) in (int, float)
            and 0 < mood < 24 - _BAR_ERROR
            and type(seconds) is int
            and seconds > 1
        ):
            return ()
    difference = round(
        (observed[2]["measured_mood"] - observed[4]["measured_mood"]) * _BAR_WIDTH / 24
    )
    if difference < -2 * _BAR_ERROR_PIXELS:
        return (3,)
    # 第 3 床未明显更低时，先移走第 5 人，原受益者离开后只剩目标可接手。
    return (4, 3) if observed[4].get("mood_sampled") else ()


def recovery_attempt_signature(data, names, recipient, stages, observed):
    """第 4 人受益的满房里，第 5 人自然回满后不再竞争单回。"""
    fifth_full = (
        len(names) == 5
        and names[3] == recipient
        and bool(names[4])
        and observed[4].get("measured_mood") == 24
        and observed[4].get("recovery_seconds") is None
    )
    return recipient, recovery_roster(data, names, stages), fifth_full


def already_attempted_recovery(target, signature):
    previous = getattr(target, "dorm_recovery_attempt", None)
    # 旧缓存没有末床状态。已满床再出现计时也不能重复触发同一轮纠正。
    room_state = signature[:2]
    return previous in (signature, room_state, (*room_state, True))


def recovery_roster(data, names, stages):
    return tuple(
        (n, getattr(data.operators.get(n), "dorm_position_version", 0), stages.get(n))
        for n in names
    )


def _read_room_recipient(data, room, names, observed, stages, *, final=False):
    """记录实读受益者供心情计算使用。是否保护床位由排班决定。"""
    recipient = observed_recovery_recipient(observed, stages)
    for index, row in enumerate(observed):
        op = data.operators.get(row["agent"])
        if op is None or (op.current_room, op.current_index) != (room, index):
            continue
        if final:
            op.clear_dorm_recovery_target()
        if row["agent"] == recipient:
            op.dorm_recipient_roster = recovery_roster(data, names, stages)
        elif (
            recipient is not None
            or final
            or (
                row.get("observed", True)
                and row.get("measured_mood") == 24
                and row.get("recovery_seconds") is None
            )
        ):
            op.dorm_recipient_roster = ()
    return recipient


def reconcile_recovery_marker(data, room, observed):
    """普通读房中，实际名单或读数推翻旧标记时作废，不为核验另开房间。"""
    from arknights_mower.utils.calculated_mood import known_operator_stages

    names = [row["agent"] for row in observed]
    marked = [
        (op, row)
        for row in observed
        if (op := data.operators.get(row["agent"])) is not None
        and (
            getattr(op, "dorm_recovery_room", "") == room
            or getattr(op, "dorm_roommate_roster", ())
        )
    ]
    if not marked and not any("measured_mood" in row for row in observed):
        return
    stages = known_operator_stages(data)
    recipient = _read_room_recipient(data, room, names, observed, stages)
    for op, row in marked:
        if (
            row.get("observed", True)
            and row.get("measured_mood") == 24
            and row.get("recovery_seconds") is None
        ):
            op.clear_dorm_recovery_target()
            continue
        seating = getattr(op, "dorm_roommate_roster", ())
        if seating and seating == recovery_roster(data, names, stages):
            if recipient is None:
                continue
            if recipient == op.name:
                managers = recovery_managers(
                    data, room, names, update_cache=False, stages=stages
                )
                record_recovery_target(
                    data, room, op, names.index(op.name), managers, names, stages
                )
                continue
        if not active_recovery_position(data, op, names=names, stages=stages) or (
            recipient is not None and recipient != op.name
        ):
            op.clear_dorm_recovery_target()


def record_recovery_target(data, room, target, index, managers, names, stages):
    if not managers or (target.current_room, target.current_index) != (room, index):
        return
    for op in data.operators.values():
        if op is not target and op.current_room == room:
            op.dorm_recipient_roster = ()
        if op is not target and (
            getattr(op, "dorm_recovery_room", "") == room
            or op.current_room == room
            and getattr(op, "dorm_roommate_roster", ())
        ):
            op.clear_dorm_recovery_target()
    target.dorm_recovery_room, target.dorm_recovery_index = room, index
    target.dorm_recovery_fixed = managers
    target.dorm_recovery_roster = recovery_roster(data, names, stages)
    target.dorm_recipient_roster = target.dorm_recovery_roster
    target.dorm_roommate_roster = ()
    target.dorm_recovery_attempt = None


def recovery_target(
    op_data, room, agents, manager_names=None, *, group_transitions=None, continued=None
):
    slots = op_data.plan.get(room, [])
    if not room.startswith("dorm") or len(agents) != len(slots):
        return None
    if manager_names is None:
        managers = recovery_managers(op_data, room, agents)
        if len(managers) != 1:
            return None
        manager_names = {managers[0][0]}
    # 唯一来源不能给自己。多个来源同住时，核对对象自己也可能有单回技能。
    excluded = manager_names if len(manager_names) == 1 else ()
    index = next(
        (
            i
            for i, name in enumerate(agents)
            if name not in excluded
            and (
                op_data.is_dynamic_dorm_position(
                    room, i, name, group_transitions=group_transitions
                )
                or (bed := op_data.get_group_dorm(room, i)) is not None
                and op_data.is_recovery_dorm(
                    bed, name, group_transitions=group_transitions
                )
            )
        ),
        None,
    )
    if index is None:
        return None
    if (
        continued
        and continued in agents
        and slots[agents.index(continued)].agent == "Free"
    ):
        index = agents.index(continued)
    target = op_data.operators.get(agents[index])
    if (
        target is None
        or (
            full_dorm_candidate(op_data, target.name)
            if getattr(op_data, "mood_calculation_enabled", False)
            else target.mood >= 24 and target.time_stamp is not None
        )
        or target.room.startswith("dorm")
        or target.name == "菲亚梅塔"
        or target.name in excluded
    ):
        return None
    return target


def protected_recovery_target(
    op_data, room, agents, managers, group_transitions, *, continued=None
):
    if not managers:
        return None
    manager_names = {name for name, _, _ in managers}
    target = recovery_target(
        op_data,
        room,
        agents,
        manager_names,
        group_transitions=group_transitions,
        continued=continued,
    )
    if (
        target is None
        or target.name in op_data.config.free_room_exclusions
        or resting_tier(op_data, target.name) > RestingTier.PRIORITY_REPLACEMENT
    ):
        return None
    return target


def recovery_order_target(
    op_data, room, agents, *, group_transitions=None, continued=None
):
    """只读判断完整单回排序目标，准入和执行共用相同床位有效性检查。"""
    managers = recovery_managers(op_data, room, agents, update_cache=False)
    if len(managers) != 1:
        return None
    target = protected_recovery_target(
        op_data, room, agents, managers, group_transitions, continued=continued
    )
    if target is None:
        return None
    target_index = agents.index(target.name)
    if (
        active_recovery_position(op_data, target) == (room, target_index)
        and getattr(target, "dorm_recovery_fixed", ()) == managers
        and all(
            (
                op_data.operators[name].current_room,
                op_data.operators[name].current_index,
            )
            == (room, index)
            for name, index, _ in managers
        )
    ):
        return None
    return target


def has_pending_roommate_readback(task):
    targets = getattr(task, "dorm_roommate_targets", None)
    return bool(targets and not task.plan.keys().isdisjoint(targets))


def remember_roommate_target(task, room, agents=(), target=None):
    if target:
        targets = vars(task).setdefault("dorm_roommate_targets", {})
        targets[room] = (tuple(agents), target)
    else:
        targets = getattr(task, "dorm_roommate_targets", None)
        if targets is not None:
            targets.pop(room, None)
            if not targets:
                del task.dorm_roommate_targets


def continuing_roommate(data, room, agents, *, previous=None):
    """只有普通室友换人时，找出仍应留在原床核对的目标。"""
    from arknights_mower.utils.calculated_mood import known_operator_stages
    from arknights_mower.utils.resting_priority import resting_key

    if len(agents) != 5:
        return None
    slots = data.plan.get(room, ())
    if len(slots) != len(agents):
        return None
    saved = previous[1] if previous and previous[0] == tuple(agents) else None
    if saved:
        marked = data.operators.get(saved)
    else:
        marked = next(
            (
                op
                for n in agents
                if (op := data.operators.get(n)) is not None
                and op.current_room == room
                and (
                    getattr(op, "dorm_recovery_room", "") == room
                    or getattr(op, "dorm_roommate_roster", ())
                )
            ),
            None,
        )
    if marked is None or marked.name not in agents:
        return None
    index = agents.index(marked.name)
    free = [i for i, slot in enumerate(slots) if slot.agent == "Free"]
    if (
        index not in free[1:]
        or any(option.endswith("_low") for option in data.config.dorm_order)
        or marked.name in data.config.free_room_exclusions
    ):
        return None
    current = data.get_current_room(room, True)
    if not saved:
        if any(current[i] != name and i not in free for i, name in enumerate(agents)):
            return None
        stages = known_operator_stages(data)
        if not _ordinary_roommate_change(
            current, agents, marked.name, stages, allow_vacancy=True
        ):
            return None
        if getattr(marked, "dorm_roommate_roster", ()) != recovery_roster(
            data, current, stages
        ) and active_recovery_position(data, marked, names=current, stages=stages) != (
            room,
            index,
        ):
            return None
    now = getattr(data, "_projection_now", None) or datetime.now()
    rank = resting_key(data, marked.name, now)
    if rank[0] > RestingTier.PRIORITY_REPLACEMENT:
        return None
    for i in free:
        other = agents[i]
        if not other or other == marked.name:
            continue
        other_rank = resting_key(data, other, now)
        if saved:
            # 续做时服从当前层级和显式优先顺序。入住后的心情变化不重开同一次分床。
            if other_rank[:2] < rank[:2]:
                return None
        elif other_rank <= rank or (
            i == free[0] and current[i] == other and other_rank[:2] == rank[:2]
        ):
            return None
    return marked.name


def keep_measured_dorm_swap(data, room, plan, observed=None):
    """只需对调两张普通 Free 床时，按本次读数或仍有效的实读记录保留受益者。"""
    from arknights_mower.utils.calculated_mood import known_operator_stages

    if len(plan) != 5 or any(opt.endswith("_low") for opt in data.config.dorm_order):
        return False
    current = data.get_current_room(room, True)
    if len(current) != 5 or (
        observed is not None and [row["agent"] for row in observed] != current
    ):
        return False
    final = [old if name == "Current" else name for old, name in zip(current, plan)]
    changes = [i for i in range(5) if final[i] != current[i]]
    if len(changes) != 2:
        return False
    front, other = changes
    if (
        not current[front]
        or not current[other]
        or (final[front], final[other]) != (current[other], current[front])
        or any(data.plan[room][i].agent != "Free" for i in changes)
        or "菲亚梅塔" in (current[front], current[other])
    ):
        return False
    stages = known_operator_stages(data)
    managers = recovery_managers(data, room, current, update_cache=False, stages=stages)
    target = protected_recovery_target(data, room, final, managers, {})
    if target is None or target.name != final[front]:
        return False
    if observed is None:
        return active_recovery_position(data, target, names=current, stages=stages) == (
            room,
            other,
        )
    if observed_recovery_recipient(observed, stages) != target.name:
        return False
    record_recovery_target(data, room, target, other, managers, current, stages)
    return True


def verify_final_recovery(
    data,
    room,
    agents,
    observed,
    *,
    group_transitions,
    can_repair,
    attempted=True,
    continued=None,
):
    """核对最终阵容的受益者。只在读数证明给错人且尚未调整时要求原任务修复。"""
    from arknights_mower.utils.calculated_mood import known_operator_stages

    if [row["agent"] for row in observed] != agents:
        return False
    stages = known_operator_stages(data)
    managers = recovery_managers(data, room, agents, update_cache=False, stages=stages)
    recipient = _read_room_recipient(data, room, agents, observed, stages, final=True)
    target = protected_recovery_target(
        data, room, agents, managers, group_transitions, continued=continued
    )
    if target is None:
        return False
    if recipient == target.name:
        record_recovery_target(
            data, room, target, agents.index(target.name), managers, agents, stages
        )
    else:
        target.clear_dorm_recovery_target()
        if len(managers) != 1:
            return False
        if (
            recipient is None
            and continued == target.name
            and all(row.get("observed", True) for row in observed)
            and (target.current_room, target.current_index)
            == (room, agents.index(continued))
        ):
            # 已核对新名单，但读数不足。只沿用排班座次，实测归属和回满速度保持未知。
            target.dorm_roommate_roster = recovery_roster(data, agents, stages)
        if recipient is not None:
            signature = recovery_attempt_signature(
                data, agents, recipient, stages, observed
            )
            if not already_attempted_recovery(target, signature):
                if can_repair:
                    return True
                if attempted:
                    target.dorm_recovery_attempt = signature
    return False


def recovery_order_plan(
    op_data, room, agents, reserved_names=(), *, group_transitions=None, continued=None
):
    """建立单回时就占住最终床位，补回其他人后目标仍在原位。

    目标前方保留单回宿管、菲亚梅塔与已满心情的入住者；其他位置使用
    无单回技能的满心情空闲者垫位，不能留空让游戏压缩名单。
    没有足够合格垫位者时不执行这次单回确认。
    """
    managers = recovery_managers(op_data, room, agents)
    target = recovery_order_target(
        op_data, room, agents, group_transitions=group_transitions, continued=continued
    )
    if target is None:
        return None
    manager_names = {name for name, _, _ in managers}
    target_index = agents.index(target.name)
    retained = []
    for index, name in enumerate(agents):
        if name in (target.name, "菲亚梅塔") or name in manager_names:
            retained.append(name)
            continue
        if index < target_index:
            retained.append(name if full_dorm_candidate(op_data, name) else "")
            continue
        if op_data.is_dynamic_dorm_position(
            room, index, name, group_transitions=group_transitions
        ):
            retained.append("")
            continue
        op = op_data.operators.get(name)
        if op_data.is_dorm_replacement_for_slot(
            name, room, index, group_transitions=group_transitions
        ) and (
            not full_dorm_candidate(op_data, name)
            if getattr(op_data, "mood_calculation_enabled", False)
            else op is None or op.time_stamp is None or op.mood < 24
        ):
            retained.append("")
            continue
        if name in ("", "Free", "Current"):
            # 未解析的固定位置不能据此清房。
            return None
        retained.append(name)
    while retained and not retained[-1]:
        retained.pop()
    if "" in retained:
        current = op_data.get_current_room(room, True)
        candidates = dorm_candidates(
            op_data,
            set(agents) | set(reserved_names),
            current_residents=current,
        )
        for index, name in enumerate(retained):
            if not name:
                # 重试保留原位垫位者；新垫位在选人页按心情降序实际选择。
                previous = current[index]
                retained[index] = (
                    previous
                    if (target.current_room, target.current_index)
                    == (room, target_index)
                    and previous in candidates.filling
                    and full_dorm_candidate(op_data, previous)
                    and not dorm_skills.is_single_recovery_manager(previous)
                    else "Free"
                )
    return retained


def compact_dorm_vacancies(data, plan):
    """显式空床放到末尾；菲亚位置之前的空缺交由普通补位填充。"""
    for room, row in plan.items():
        if not room.startswith("dorm") or "" not in row:
            continue
        current = data.get_current_room(room, True)
        resolved = [
            current[index] if name == "Current" else name
            for index, name in enumerate(row)
        ]
        occupants = [name for name in resolved if name]
        if "菲亚梅塔" in resolved:
            fixed = resolved.index("菲亚梅塔")
            missing = fixed - occupants.index("菲亚梅塔")
            occupants[fixed - missing : fixed - missing] = ["Free"] * missing
        compacted = occupants + [""] * (len(row) - len(occupants))
        if compacted != resolved:
            plan[room] = compacted
    return plan
