from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

from arknights_mower.scheduler.domain.task import SchedulerTask


class AbstractPlanner(ABC):
    frequency: timedelta | None = None

    def __init__(self) -> None:
        self.last_run: Optional[datetime] = None

    def should_run(self) -> bool:
        if self.frequency is not None and self.last_run is not None:
            if datetime.now() - self.last_run < self.frequency:
                return False
        return True

    def plan(self, state) -> Optional[SchedulerTask]:
        if not self.should_run():
            return None
        if not self.condition(state):
            return None
        task = self.make_task(state)
        if task is not None:
            self.last_run = datetime.now()
        return task

    @abstractmethod
    def condition(self, state) -> bool:
        ...

    @abstractmethod
    def make_task(self, state) -> Optional[SchedulerTask]:
        ...


class LegacyPlannerAdapter(AbstractPlanner):
    """Wrap old-style planners (no AbstractPlanner inheritance) into new interface."""

    def __init__(self, planner: Any) -> None:
        super().__init__()
        self._inner = planner

    def condition(self, state) -> bool:
        return True

    def make_task(self, state) -> Optional[SchedulerTask]:
        return self._inner.plan(state)

