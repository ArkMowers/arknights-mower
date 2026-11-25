"""Check a normalized ordinary Copilot script against the instance's local roster."""

from collections import defaultdict, deque

from arknights_mower.utils.growth import growth_data
from arknights_mower.utils.mastery_recommendation import (
    get_cultivate_characters,
    get_skill_data,
)


def _unknown(message, gaps=None):
    return {
        "status": "unknown",
        "gaps": gaps or [],
        "can_borrow": False,
        "message": message,
    }


def _shortfalls(oper, char, definition):
    if char is None:
        return ["未拥有"]

    req = oper.get("requirements") or {}
    elite, level = req.get("elite", -1), req.get("level", 0)
    skill_level, module = req.get("skill_level", 0), req.get("module", -1)
    if not all(type(v) is int for v in (elite, level, skill_level, module)):
        return None
    reasons = []
    if elite > 0 or level > 0:
        phase, rank = char.get("evolvePhase"), char.get("level")
        if (
            type(phase) is not int
            or not 0 <= phase <= 2
            or type(rank) is not int
            or not 1 <= rank <= 90
        ):
            return None
        if (phase, rank) < (elite, level):
            promotion = ("未精英化", "精一", "精二")
            actual = f"{promotion[phase]} {rank} 级"
            expected = f"{level} 级" if phase == elite else promotion[elite]
            if phase != elite and level > 0:
                expected += f" {level} 级"
            reasons.append(f"{actual}，要求 {expected}")

    skill = oper.get("skill", 0)
    if skill > 0 and skill_level > 0:
        base = char.get("mainSkillLevel")
        if type(base) is not int or not 1 <= base <= 7:
            return reasons or None
        actual = base
        if skill_level > 7:
            skills = char.get("skills")
            if not isinstance(skills, list) or len(skills) < skill:
                return reasons or None
            selected = skills[skill - 1]
            mastery = selected.get("level") if isinstance(selected, dict) else None
            if type(mastery) is not int or not 0 <= mastery <= 3:
                return reasons or None
            actual += mastery
        if actual < skill_level:
            reasons.append(f"技能 {skill} 为 {actual} 级，要求 {skill_level} 级")

    # MaaCore checks the equipped branch. Ordinary Copilot ignores module level and potential.
    if module > 0:
        if module > 5:
            return None
        branch = "XYADB"[module - 1]
        modules = definition.get("modules")
        unlocked = char.get("equips")
        if not isinstance(modules, list) or not isinstance(unlocked, list):
            return None
        ids = {m["id"] for m in modules if m["type"].rsplit("-", 1)[-1] == branch}
        if not ids:
            return None
        if any(
            not isinstance(m, dict) or not isinstance(m.get("id"), str)
            for m in unlocked
        ):
            return reasons or None
        levels = [m.get("level") for m in unlocked if m["id"] in ids]
        if not all(type(n) is int and 0 <= n <= 3 for n in levels):
            return None
        if not any(levels):
            reasons.append(f"未解锁 {branch} 模组")
    return reasons


def _match(edges):
    """Add one slot at a time, rearranging earlier choices along an alternating path."""
    assigned = {}
    missing = []
    for start in range(len(edges)):
        queue = deque([start])
        previous = {start: None}
        parent = {}
        while queue:
            slot = queue.popleft()
            for owner in edges[slot]:
                if owner in parent:
                    continue
                parent[owner] = slot
                if owner not in assigned:
                    while owner is not None:
                        slot = parent[owner]
                        assigned[owner] = slot
                        owner = previous[slot]
                    break
                other = assigned[owner]
                if other not in previous:
                    previous[other] = owner
                    queue.append(other)
            else:
                continue
            break
        else:
            missing.append(start)
    return assigned, missing


def _can_borrow(start, edges, borrowable, assigned):
    """An augmenting path may use one borrowed operator with higher progression."""
    queue = deque([(start, False)])
    seen = set(queue)
    while queue:
        slot, borrowed = queue.popleft()
        options = [(edges[slot], borrowed)]
        if not borrowed:
            options.append((borrowable[slot], True))
        for owners, used in options:
            for owner in owners:
                if owner not in assigned:
                    return True
                state = assigned[owner], used
                if state not in seen:
                    seen.add(state)
                    queue.append(state)
    return False


def check_copilot_roster(data):
    slots = [(op["name"], [op]) for op in data.get("opers", [])]
    slots.extend((g["name"], g["opers"]) for g in data.get("groups", []))
    ready = {"status": "ready", "gaps": [], "can_borrow": False}
    if not slots:
        return ready
    roster = get_cultivate_characters()
    if not roster:
        return _unknown("请在「养成规划」中刷新森空岛干员练度后重新检查。")

    definitions = growth_data(get_skill_data())["characters"]
    names = defaultdict(list)
    for cid, definition in definitions.items():
        name = definition["name"].casefold()
        names[name].append(cid)
        owner = definition.get("progression_owner", cid)
        if owner != cid:
            names[f"{name}-{definition['profession'].casefold()}"].append(cid)

    edges, possible, borrowable, reports = [], [], [], []
    for label, members in slots:
        usable, uncertain, borrowed, candidates = set(), set(), set(), []
        for oper in members:
            name = oper["name"]
            role = oper.get("role")
            role = role.casefold() if isinstance(role, str) else ""
            ids = names.get(name.casefold(), [])
            if role:
                ids = [
                    cid
                    for cid in ids
                    if definitions[cid]["profession"].casefold() == role
                ]
            elif len(ids) > 1:
                # The unqualified base form uses the operator's original profession.
                ids = [
                    cid
                    for cid in ids
                    if definitions[cid].get("progression_owner", cid) == cid
                ]
            reasons = None
            owner = name.casefold()
            if len(ids) == 1:
                cid = ids[0]
                definition = definitions[cid]
                owner = definition.get("progression_owner", cid)
                reasons = _shortfalls(oper, roster.get(cid), definition)
            if reasons is None:
                uncertain.add(owner)
                reasons = ["缺少可核对的干员资料"]
            elif not reasons:
                usable.add(owner)
                reasons = ["该干员已被其他位置占用"]
            else:
                borrowed.add(owner)
            candidates.append({"name": name, "reasons": reasons})
        edges.append(usable)
        possible.append(usable | uncertain)
        borrowable.append(borrowed)
        reports.append({"slot": label, "candidates": candidates})

    assigned, missing = _match(edges)
    if not missing:
        return ready
    if possible != edges and len(_match(possible)[1]) < len(missing):
        return _unknown(
            "部分干员资料不足，无法核对全部位置。请刷新森空岛练度和游戏资源。",
            [report for report, options in zip(reports, possible) if not options],
        )
    return {
        "status": "shortfall",
        "gaps": [reports[i] for i in missing],
        "can_borrow": len(missing) == 1
        and _can_borrow(missing[0], edges, borrowable, assigned),
    }
