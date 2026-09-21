"""Pure duration calculation and bounded search for consecutive mastery stages."""

import math
from dataclasses import dataclass, replace
from itertools import product

from .mastery_support_data import rate
from .mastery_support_types import (
    BASE_HOURS,
    StageSpec,
    SupportPlanError,
    swap_buffer_minutes,
)


def _duration(first, reducer, spec):
    speed = rate(first["efficiency"], spec.central)
    if not reducer or reducer["name"] == first["name"]:
        return spec.work / speed, None
    tail = (300 + max(1, spec.buffer)) / 60
    tail_speed = rate(reducer["efficiency"], spec.central)
    # Match runtime handoff timing: central counts on the destination only.
    # Overall duration still uses nominal speeds on both legs.
    remaining_work = spec.work - tail * tail_speed * speed / rate(first["efficiency"])
    if not spec.manual and (
        remaining_work <= 0 or first["efficiency"] <= reducer["efficiency"]
    ):
        return None
    switch = max(0, math.floor(remaining_work / speed * 3600) / 3600)
    return switch + (spec.work - switch * speed) / tail_speed, switch


def stage_route(first, reducer, spec):
    configured_buffer = spec.buffer
    inherited = spec.work <= BASE_HOURS[spec.level] / 2
    spec = replace(
        spec,
        buffer=swap_buffer_minutes(
            spec.level, spec.buffer, central=spec.central, inherited=inherited
        ),
    )
    duration = _duration(first, reducer, spec)
    if duration is None:
        return None
    hours, switch_after = duration
    return {
        "operator": first["name"],
        "efficiency": first["efficiency"],
        "level": spec.level,
        "swap_target": reducer["name"]
        if reducer and switch_after is not None
        else None,
        "swap_efficiency": reducer["efficiency"] if reducer else 0,
        "central_bonus": spec.central,
        "mastery_swap_buffer": max(1, spec.buffer),
        "configured_swap_buffer": configured_buffer,
        "half_inherited": inherited,
        "hours": hours,
        "switch_after": switch_after,
    }


@dataclass(frozen=True)
class SearchStep:
    level: int
    target: int
    settings: tuple

    @property
    def central(self):
        return self.settings[0]

    @property
    def buffer(self):
        return self.settings[1]


def _useful_trainers(options, level):
    stats = [levels[level] for levels in options.values()]
    fastest = max(t["efficiency"] for t in stats)
    ordinary = sorted(
        (t for t in stats if not t["halves"] and t["efficiency"] == fastest),
        key=lambda t: t["name"],
    )
    return [t for t in stats if t["halves"]] + ordinary[:1]


def _mark_carry(route, last, carry, step):
    last_hours = route["hours"] - (route["switch_after"] or 0)
    earned = (
        step.level < step.target
        and last["halves"]
        and last_hours >= (300 + route["mastery_swap_buffer"]) / 60
    )
    route.update(
        activate_with=carry,
        half_inherited=bool(carry),
        next_carry=last["name"] if earned else None,
        manual=False,
    )


def _switches(route, previous):
    names = [route["activate_with"], route["operator"], route["swap_target"]]
    changes = 0
    for name in filter(None, names):
        changes += int(previous is not None and name != previous)
        previous = name
    return changes


def _candidate_routes(carry, trainers, step):
    reducers = [t for t in trainers if t["halves"]] if step.level < step.target else []
    spec = StageSpec(
        step.level,
        BASE_HOURS[step.level] * (0.5 if carry else 1),
        step.central,
        step.buffer,
    )
    for first, reducer in product(trainers, [None, *reducers]):
        route = stage_route(first, reducer, spec)
        if route is None:
            continue
        last = reducer if route["swap_target"] else first
        _mark_carry(route, last, carry, step)
        yield (route["next_carry"], last["name"]), route


def _advance_paths(paths, options, step):
    best = {}
    trainers = _useful_trainers(options, step.level)
    for (carry, previous), (elapsed, switches, routes) in paths.items():
        for key, route in _candidate_routes(carry, trainers, step):
            value = (
                elapsed + route["hours"],
                switches + _switches(route, previous),
                routes + [route],
            )
            if key not in best or value[:2] < best[key][:2]:
                best[key] = value
    return best


def optimize_supports(options, current, target, settings):
    if not options:
        raise SupportPlanError("没有可用的协助干员（非训练室排班中的干员已排除）")
    paths = {(None, None): (0, 0, [])}
    for level in range(current + 1, target + 1):
        paths = _advance_paths(paths, options, SearchStep(level, target, settings))
    elapsed, switches, routes = min(paths.values(), key=lambda v: v[:2])
    return {
        "version": 1,
        "stages": routes,
        "hours": elapsed,
        "switches": switches,
        "central_bonus": settings[0],
        "current": current,
        "target": target,
    }
