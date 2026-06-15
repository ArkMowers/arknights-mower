from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from arknights_mower.scheduler.constants import (
    WORKSHOP_FURNITURE_PREFIX,
    WORKSHOP_JIUSE_CRIT_GAP,
    WORKSHOP_JIUSE_MAX_AP,
    WORKSHOP_JIUSE_SKILL_TARGET,
    WORKSHOP_MOOD_CRIT,
    WORKSHOP_TABS,
)


@dataclass(frozen=True)
class WorkshopCandidate:
    formula_name: str
    inventory_name: str
    tab: str
    ap_cost: float
    item_config: object


def workshop_inventory_name(formula_name: str) -> str:
    if formula_name.startswith(WORKSHOP_FURNITURE_PREFIX):
        return WORKSHOP_FURNITURE_PREFIX
    return formula_name


def is_jiuselu_crit_candidate(candidate: WorkshopCandidate) -> bool:
    return (
        candidate.ap_cost == WORKSHOP_JIUSE_MAX_AP
        and candidate.tab != WORKSHOP_TABS[0]
    )


def is_jiuselu_padding_candidate(candidate: WorkshopCandidate) -> bool:
    return (
        0 < candidate.ap_cost < WORKSHOP_JIUSE_MAX_AP
        or candidate.tab == WORKSHOP_TABS[0]
    )


def jiuselu_candidate_matches_gap(candidate: WorkshopCandidate, gap: int) -> bool:
    if 0 < gap < WORKSHOP_JIUSE_CRIT_GAP:
        return is_jiuselu_crit_candidate(candidate)
    return is_jiuselu_padding_candidate(candidate)


def jiuselu_should_switch_candidate(
    candidate: WorkshopCandidate,
    gap: int,
    mood: float,
) -> bool:
    if 0 < gap < WORKSHOP_JIUSE_CRIT_GAP:
        return mood >= WORKSHOP_MOOD_CRIT and not is_jiuselu_crit_candidate(candidate)
    if gap >= WORKSHOP_JIUSE_CRIT_GAP:
        return is_jiuselu_crit_candidate(candidate)
    return False


@dataclass(frozen=True)
class WorkshopProductionPlan:
    add_taps: int = 0
    use_max: bool = False
    estimated_mood_cost: float = 0


def make_jiuselu_production_plan(
    *,
    gap: int,
    mood: float,
    ap_cost: float,
) -> WorkshopProductionPlan | None:
    if gap <= 0:
        return WorkshopProductionPlan(estimated_mood_cost=ap_cost)
    if gap > WORKSHOP_JIUSE_SKILL_TARGET:
        return None
    if 0 < gap < WORKSHOP_JIUSE_CRIT_GAP and mood < WORKSHOP_MOOD_CRIT:
        return None
    if ap_cost <= 0:
        return None
    if gap <= mood:
        add_taps = max(ceil(gap / ap_cost) - 2, 0)
        taps = add_taps + 1
        return WorkshopProductionPlan(
            add_taps=add_taps,
            use_max=False,
            estimated_mood_cost=taps * ap_cost,
        )
    return WorkshopProductionPlan(use_max=True, estimated_mood_cost=24)


def first_matching_candidate(
    candidates: Iterable[WorkshopCandidate],
    *,
    is_jiuselu: bool,
    gap: int,
) -> WorkshopCandidate | None:
    for candidate in candidates:
        if not is_jiuselu or jiuselu_candidate_matches_gap(candidate, gap):
            return candidate
    return None


def build_workshop_candidates(
    agent: str,
    *,
    is_jiuselu: bool,
) -> dict[str, dict[str, WorkshopCandidate]]:
    from arknights_mower.data import workshop_formula
    from arknights_mower.solvers.record import get_inventory_counts
    from arknights_mower.utils import config
    from arknights_mower.utils.log import logger

    inventory = get_inventory_counts()
    if not inventory:
        return {}

    item_list = next(
        (s.items for s in config.conf.workshop_settings if s.operator == agent),
        [],
    )
    seen: set[str] = set()
    group: dict[str, dict[str, WorkshopCandidate]] = {}
    for item in item_list:
        for formula_name in item.item_names:
            if formula_name in seen:
                logger.warning("duplicate workshop material ignored: %s", formula_name)
                continue
            seen.add(formula_name)
            metadata = workshop_formula.get(formula_name)
            if metadata is None:
                logger.warning("unknown workshop material ignored: %s", formula_name)
                continue
            inventory_name = workshop_inventory_name(formula_name)
            if not _inventory_match(inventory, inventory_name, item, metadata):
                logger.debug("workshop material not ready: %s", formula_name)
                continue
            ap_cost = float(metadata["apCost"])
            if is_jiuselu and ap_cost > WORKSHOP_JIUSE_MAX_AP:
                logger.warning("skip >4 mood material for jiuselu: %s", formula_name)
                continue
            tab = metadata["tab"]
            group.setdefault(tab, {})[formula_name] = WorkshopCandidate(
                formula_name=formula_name,
                inventory_name=inventory_name,
                tab=tab,
                ap_cost=ap_cost,
                item_config=item,
            )
    return group


def _inventory_match(inventory, inventory_name: str, item, metadata) -> bool:
    return (
        inventory_name in inventory
        and inventory[inventory_name] < item.self_upper_limit
        and all(
            child in inventory and inventory[child] > item.children_lower_limit
            for child in metadata["items"]
        )
    )
