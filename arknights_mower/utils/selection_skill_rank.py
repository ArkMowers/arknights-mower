"""Rank unselected operators with an unlocked skill for the current facility."""

from arknights_mower.utils.building_skill_data import BUILDING_ROOM_NAMES
from arknights_mower.utils.building_skills import skill_index, skill_statuses
from arknights_mower.utils.mastery_recommendation import (
    PROF_MAP,
    get_cultivate_snapshot,
    get_skill_data,
)

_EFFICIENCY_PRODUCTS = {
    BUILDING_ROOM_NAMES["MANUFACTURE"]: {"gold": "F_GOLD", "exp3": "F_EXP"},
    BUILDING_ROOM_NAMES["TRADING"]: {"lmd": None},
}


def _record_efficiency(products, skill, scores):
    targets, value = skill.get("targets"), skill.get("efficiency")
    known = isinstance(targets, list) and all(isinstance(t, str) for t in targets)
    for product, recipe in products.items():
        if known and recipe is not None and recipe not in targets:
            continue
        # Trade buffs in the verified LMD order use an explicit empty target list.
        if not known or (recipe is None and targets) or type(value) is not int:
            scores[product] = None
        elif product not in scores or (
            scores[product] is not None and value > scores[product]
        ):
            scores[product] = value


def _room_scores(skills, growth):
    if not skills:
        raise ValueError("missing building skills")
    active = {}
    efficiencies = {}
    for skill, status in skill_statuses(skills, growth):
        slot = skill["skill_key"]
        if (
            status == "unknown"
            or type(slot) is not int
            or type(skill["skill_level"]) is not int
        ):
            raise ValueError("invalid building skill")
        if status == "active":
            room, score = skill["roomType"], skill.get("sortId")
            if not isinstance(room, str) or not room or type(score) is not int:
                raise ValueError("missing building skill room or sortId")
            if room not in active or slot > active[room][0]:
                active[room] = (slot, score)
            if products := _EFFICIENCY_PRODUCTS.get(room):
                _record_efficiency(products, skill, efficiencies)
    return {room: score for room, (_, score) in active.items()} | efficiencies


def _owned_skills(roster, catalog, operators):
    owned = {}
    ids = set()
    for char in roster:
        char_id = char["id"]
        info = operators[char_id]
        name, profession = info["name"], info["profession"]
        phase, level = char.get("evolvePhase"), char.get("level")
        if (
            char_id in ids
            or not isinstance(name, str)
            or not name
            or profession not in PROF_MAP
            or type(phase) is not int
            or not 0 <= phase <= 2
            or type(level) is not int
            or not 1 <= level <= 90
        ):
            raise ValueError("invalid operator progress")
        ids.add(char_id)
        scores = _room_scores(catalog[name], (phase, level))
        roles, previous = owned.setdefault(name, (set(), scores))
        if previous != scores:
            for key in previous.keys() | scores.keys():
                if (
                    key not in previous
                    or key not in scores
                    or previous[key] != scores[key]
                ):
                    if key in BUILDING_ROOM_NAMES.values():
                        raise ValueError(
                            "conflicting building skills for operator forms"
                        )
                    previous[key] = None
        roles.add(profession)
    return owned


# Snapshot and resource readers replace these objects when their source changes.
_cached = None


def _current_index():
    global _cached
    snapshot = get_cultivate_snapshot()
    if not snapshot:
        _cached = None
        return None
    try:
        catalog = skill_index()
        training = get_skill_data()["training"]
        if training.get("version") != 1:
            return None
        operators = training["operators"]
        cached = _cached
        if (
            cached is not None
            and cached[0] is snapshot
            and cached[1] is catalog
            and cached[2] is operators
        ):
            return cached[3]
        try:
            index = _owned_skills(snapshot["data"]["characters"], catalog, operators)
        except (AttributeError, KeyError, TypeError, ValueError):
            index = None
        _cached = snapshot, catalog, operators, index
        return index
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return None


def selection_skill_rank(
    room_type: str, profession: str, target: str, selected
) -> dict[bool, tuple[int, int]] | None:
    """Return one-based descending/ascending rank ranges after the selected prefix."""
    if not isinstance(room_type, str):
        return None
    return _selection_rank(
        BUILDING_ROOM_NAMES.get(room_type), profession, target, selected
    )


def selection_efficiency_rank(
    room_type: str, profession: str, target: str, selected, *, product: str
) -> dict[bool, tuple[int, int]] | None:
    """Return rank ranges for the observed product, keeping equal efficiencies tied."""
    if not isinstance(room_type, str) or not isinstance(product, str):
        return None
    if product not in _EFFICIENCY_PRODUCTS.get(BUILDING_ROOM_NAMES.get(room_type), {}):
        return None
    return _selection_rank(product, profession, target, selected)


def _selection_rank(key, profession, target, selected):
    if not key or not isinstance(profession, str) or not isinstance(target, str):
        return None
    if not isinstance(selected, (list, tuple, set, frozenset)):
        return None
    if not all(isinstance(name, str) for name in selected):
        return None
    prefix = set(selected)
    owned = _current_index()
    if (
        not owned
        or target not in owned
        or target in prefix
        or len(prefix) != len(selected)
        or not prefix.issubset(owned)
    ):
        return None

    target_roles, scores = owned[target]
    score = scores.get(key)
    if score is None or (profession != "ALL" and target_roles != {profession}):
        return None
    lower = higher = tied = 0
    for name, (roles, rooms) in owned.items():
        if name in prefix or key not in rooms:
            continue
        if profession != "ALL":
            if profession not in roles:
                continue
            if len(roles) != 1:
                # The snapshot contains all unlocked forms but not the active one.
                return None
        value = rooms[key]
        if value is None:
            return None
        lower += value < score
        higher += value > score
        tied += value == score
    return {False: (higher + 1, higher + tied), True: (lower + 1, lower + tied)}
