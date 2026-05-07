from __future__ import annotations

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.errors import DeviceError, SchedulerError
from arknights_mower.scheduler.infra import InfraKit
from arknights_mower.utils.log import logger


class TaskDispatch:
    MAX_RETRY = 3

    def __init__(self) -> None:
        self._executors: dict[TaskTypes, type] = {}

    def register(self, task_type: TaskTypes, executor: type) -> None:
        self._executors[task_type] = executor

    def get(self, task_type: TaskTypes) -> type | None:
        return self._executors.get(task_type)

    def resolve(self, task_type: TaskTypes) -> type:
        executor = self.get(task_type)
        if executor is None:
            raise SchedulerError(f"no executor for {task_type}")
        return executor

    def execute(self, task: SchedulerTask, infra: InfraKit) -> bool:
        executor_cls = self.resolve(task.type)
        executor = executor_cls(infra)

        for attempt in range(1, self.MAX_RETRY + 1):
            try:
                executor.execute(task)
                return True
            except DeviceError:
                logger.warning(
                    f"DeviceError on attempt {attempt}/{self.MAX_RETRY}, reconnecting..."
                )
                infra.device.reconnect()
                continue
            except Exception:
                logger.exception(f"executor failed for task: {task}")
                return False

        logger.error(f"executor failed after {self.MAX_RETRY} retries: {task}")
        return False
