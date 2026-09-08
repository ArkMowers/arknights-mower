"""Public mastery planning entry points and profession-wide recommendations."""

from . import mastery_support_data as data
from .mastery_optimizer import optimize_supports
from .mastery_optimizer import stage_route as stage_route
from .mastery_support_data import (
    candidates as candidates,
)
from .mastery_support_data import (
    check_schedule_name as check_schedule_name,
)
from .mastery_support_data import (
    rate as rate,
)
from .mastery_support_data import (
    trainer_stats as trainer_stats,
)
from .mastery_support_data import (
    unlocked as unlocked,
)
from .mastery_support_edits import edit_supports as edit_supports
from .mastery_support_types import (
    BASE_HOURS,
)
from .mastery_support_types import (
    CONTROL_TRAINERS as CONTROL_TRAINERS,
)
from .mastery_support_types import (
    REDUCERS as REDUCERS,
)
from .mastery_support_types import (
    RosterUnavailableError as RosterUnavailableError,
)
from .mastery_support_types import (
    StageSpec as StageSpec,
)
from .mastery_support_types import (
    SupportPlanError as SupportPlanError,
)
from .mastery_support_types import (
    TrainingInputs as TrainingInputs,
)
from .mastery_support_types import (
    decode_json as decode_json,
)
from .mastery_support_types import (
    decode_supports as decode_supports,
)
from .mastery_support_types import (
    editable_after as editable_after,
)
from .mastery_support_types import (
    encode_supports as encode_supports,
)
from .mastery_support_types import (
    stage_for as stage_for,
)


def owned_roster():
    return data.owned_roster()


def training_data():
    return data.training_data()


def schedule_context(plan=None):
    return data.schedule_context(plan)


def plan_supports(char_id, current, target, inputs=None):
    inputs = inputs or TrainingInputs()
    options, central = candidates(char_id, inputs)
    return optimize_supports(options, current, target, (central, inputs.buffer))


def profession_training_routes(professions, inputs=None):
    """Preview owned, unlocked trainers; do not assume a target branch."""
    inputs = data.resolve_inputs(inputs)
    roster, metadata = inputs.roster, inputs.metadata
    blocked, central = inputs.schedule
    buffer = inputs.buffer
    eligible = []
    for char in roster:
        meta = metadata.get(char["id"])
        if not meta or meta["name"] in blocked:
            continue
        effects = unlocked(meta, char)
        if not any(r["kind"] in {"speed", "halve"} for r in effects):
            continue  # A control-room bonus alone is not a training skill.
        if any(r["kind"] in {"environment", "unsupported"} for r in effects):
            continue
        eligible.append((meta, char))

    defaults = {}
    for profession, label in professions.items():
        target = {"profession": profession}  # Branch-specific extras never match.
        options = {
            meta["name"]: {
                level: trainer_stats(meta, char, target, level) for level in BASE_HOURS
            }
            for meta, char in eligible
        }
        if not options:
            defaults[label] = {"supports": [], "half_off": False}
            continue
        plan = optimize_supports(options, 0, 3, (central, buffer))
        defaults[label] = {
            "supports": [
                {
                    "name": stage["operator"],
                    "skill_level": stage["level"],
                    "efficiency": stage["efficiency"],
                    "swap": bool(stage["swap_target"]),
                    "swap_name": stage["swap_target"] or "",
                    "match": stage["swap_efficiency"] > 0,
                }
                for stage in plan["stages"]
            ],
            "half_off": any(stage["half_inherited"] for stage in plan["stages"]),
        }
    return {"defaults": defaults}


def profession_reference_trainers(routes, professions, *, roster, metadata):
    """Display the original default trainers independently of personal availability.

    A missing roster/rule is unknown, not evidence that an operator is unowned or
    locked. Unlock status refers to the displayed bonus, including skill upgrades.
    """
    owned = None if roster is None else {c["id"]: c for c in roster}
    by_name = {m["name"]: (cid, m) for cid, m in metadata.items()}
    result = {}
    for profession, label in professions.items():
        result[label] = {}
        for level in BASE_HOURS:
            entry = routes.get(label, {}).get(f"level_{level}")
            if not entry:
                continue
            name, efficiency = entry["operator"], entry["efficiency"]
            cid, meta = by_name.get(name, (None, None))
            has_operator = cid in owned if owned is not None and cid else None
            has_skill = None
            if has_operator and meta:
                stats = trainer_stats(
                    meta, owned[cid], {"profession": profession}, level
                )
                has_skill = stats["efficiency"] >= efficiency
            result[label][level] = {
                "name": name,
                "efficiency": efficiency,
                "owned": has_operator,
                "unlocked": has_skill,
            }
    return result


def legacy_profession_routes(routes):
    """Use the original complete profession routes when BOX is unavailable."""
    return {
        "defaults": {
            profession: {
                "supports": [
                    {
                        "name": entry["operator"],
                        "skill_level": level,
                        "efficiency": entry["efficiency"],
                        "swap": bool(entry.get("swap_target")),
                        "swap_name": entry.get("swap_target") or "",
                        "match": bool(entry.get("job_match")),
                    }
                    for level in BASE_HOURS
                    if (entry := stages.get(f"level_{level}"))
                ],
                "half_off": any(entry.get("swap_target") for entry in stages.values()),
            }
            for profession, stages in routes.items()
        }
    }
