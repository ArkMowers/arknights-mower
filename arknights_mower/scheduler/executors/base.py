from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController

logger = logging.getLogger(__name__)


class AbstractExecutor(ABC):
    def __init__(
        self, device: DevicePort, pause_controller: Optional[PauseController] = None
    ) -> None:
        self._device = device
        self._pause = pause_controller or ThreadPauseController()

    def safe_execute(self, task: SchedulerTask) -> bool:
        try:
            self.execute(task)
            return True
        except Exception:
            logger.exception(f"executor failed for task: {task}")
            return False

    def check_pause(self) -> None:
        self._pause.wait_if_paused()

    @abstractmethod
    def execute(self, task: SchedulerTask) -> None:
        ...
