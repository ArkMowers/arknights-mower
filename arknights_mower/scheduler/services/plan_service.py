from __future__ import annotations

from copy import deepcopy

from arknights_mower.scheduler.domain.plan import PlanConfig


def is_refresh_trading(config: PlanConfig, agent_name: str) -> list:
    match = next(
        (e for e in config.refresh_trading_config if agent_name in e.lower()),
        None,
    )
    if match is not None:
        rest = match.replace(agent_name, "")
        if rest:
            return [True, rest.split(",")]
        return [True, []]
    return [False, []]


def merge_config(base: PlanConfig, target: PlanConfig) -> PlanConfig:
    result = deepcopy(base)
    for attr in [
        "rest_in_full",
        "exhaust_require",
        "workaholic",
        "resting_priority",
        "free_blacklist",
        "refresh_trading_config",
        "refresh_drained",
        "ope_resting_priority",
    ]:
        merged = getattr(result, attr) + [
            x for x in getattr(target, attr) if x not in getattr(result, attr)
        ]
        setattr(result, attr, merged)
    return result
