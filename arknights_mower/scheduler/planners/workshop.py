from __future__ import annotations

from datetime import datetime, timedelta

from arknights_mower.scheduler.constants import (
    WORKSHOP_AGENT_JIUSE,
    WORKSHOP_FURNITURE_PREFIX,
    WORKSHOP_MOOD_MIN,
)
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner


class WorkshopPlanner(AbstractPlanner):
    frequency = timedelta(minutes=30)

    def condition(self, state) -> bool:
        from arknights_mower.utils import config

        return bool(config.conf.workshop_settings)

    def make_task(self, state) -> SchedulerTask | None:
        from arknights_mower.data import workshop_formula
        from arknights_mower.solvers.record import get_inventory_counts

        inventory_data = get_inventory_counts()
        if not inventory_data:
            return None

        from arknights_mower.utils import config

        for item in config.conf.workshop_settings:
            if not item.enabled:
                continue

            agent = state.operators.get(item.operator)
            if agent is not None and agent.mood <= WORKSHOP_MOOD_MIN:
                continue

            match = False
            if item.operator == WORKSHOP_AGENT_JIUSE:
                match = self._check_jiuselu(item, inventory_data, workshop_formula)
            else:
                match = self._check_material(item, inventory_data, workshop_formula)

            if match:
                return SchedulerTask(
                    time=datetime.now(),
                    type=TaskTypes.WORKSHOP,
                    meta_data=item.operator,
                )

        return None

    def _check_material(self, item, inventory_data, workshop_formula) -> bool:
        for material in item.items:
            for name in material.item_names:
                metadata = workshop_formula[name]
                if name.startswith(WORKSHOP_FURNITURE_PREFIX):
                    name = WORKSHOP_FURNITURE_PREFIX
                if (
                    name in inventory_data
                    and inventory_data[name] < material.self_upper_limit
                    and all(
                        child_name in inventory_data
                        and inventory_data[child_name]
                        > material.children_lower_limit
                        for child_name in metadata["items"]
                    )
                ):
                    return True
        return False

    def _check_jiuselu(self, item, inventory_data, workshop_formula) -> bool:
        from arknights_mower.scheduler.constants import WORKSHOP_TABS

        base_match = False
        non_base_match = False
        for material in item.items:
            for name in material.item_names:
                metadata = workshop_formula[name]
                if name.startswith(WORKSHOP_FURNITURE_PREFIX):
                    name = WORKSHOP_FURNITURE_PREFIX
                if (
                    name in inventory_data
                    and inventory_data[name] < material.self_upper_limit
                    and all(
                        child_name in inventory_data
                        and inventory_data[child_name]
                        > material.children_lower_limit
                        for child_name in metadata["items"]
                    )
                ):
                    if metadata["apCost"] < 4 or metadata["tab"] == WORKSHOP_TABS[0]:
                        base_match = True
                    elif metadata["apCost"] == 4 and metadata["tab"] != WORKSHOP_TABS[0]:
                        non_base_match = True
        return base_match and non_base_match
