from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.infra import InfraKit

logger = logging.getLogger(__name__)


class AbstractExecutor(ABC):
    def __init__(self, infra: InfraKit) -> None:
        self.infra = infra

    @property
    def _device(self):
        return self.infra.device

    @property
    def _pause(self):
        return self.infra.pause

    def safe_execute(self, task: SchedulerTask) -> bool:
        try:
            self.execute(task)
            return True
        except Exception:
            logger.exception(f"executor failed for task: {task}")
            return False

    def check_pause(self) -> None:
        self.infra.pause.wait_if_paused()

    @abstractmethod
    def execute(self, task: SchedulerTask) -> None:
        ...
