from __future__ import annotations

import time
from typing import Optional

from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.errors import DeviceError, SchedulerError
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.utils.log import logger


class TaskDispatch:
    MAX_RETRY = 3

    def __init__(self) -> None:
        self._executors: dict[TaskTypes, type] = {}

    def register(self, task_type: TaskTypes, executor: type) -> None:
        self._executors[task_type] = executor

    def get(self, task_type: TaskTypes) -> Optional[type]:
        return self._executors.get(task_type)

    def resolve(self, task_type: TaskTypes) -> type:
        executor = self.get(task_type)
        if executor is None:
            raise SchedulerError(f"no executor for {task_type}")
        return executor

    def _reconnect(self, device: DevicePort) -> None:
        logger.info("dispatching reconnect")
        device.reconnect()

    def execute(
        self,
        task: SchedulerTask,
        device: DevicePort,
        pause_controller: Optional[PauseController] = None,
    ) -> bool:
        executor_cls = self.resolve(task.type)
        executor = executor_cls(device, pause_controller)

        for attempt in range(1, self.MAX_RETRY + 1):
            try:
                executor.execute(task)
                return True
            except DeviceError:
                logger.warning(
                    f"DeviceError on attempt {attempt}/{self.MAX_RETRY}, reconnecting..."
                )
                self._reconnect(device)
                continue
            except Exception:
                logger.exception(f"executor failed for task: {task}")
                return False

        logger.error(f"executor failed after {self.MAX_RETRY} retries: {task}")
        return False
