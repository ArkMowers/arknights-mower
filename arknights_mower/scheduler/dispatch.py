from __future__ import annotations

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.errors import DeviceError, SchedulerError
from arknights_mower.scheduler.infra import InfraKit
from arknights_mower.utils.log import logger


class TaskDispatch:

    def __init__(self) -> None:
        self._executors: dict[TaskTypes, type] = {}
        self._executor_kwargs: dict[TaskTypes, dict] = {}

    def register(self, task_type: TaskTypes, executor: type, **kwargs) -> None:
        self._executors[task_type] = executor
        self._executor_kwargs[task_type] = kwargs

    def get(self, task_type: TaskTypes) -> type | None:
        return self._executors.get(task_type)

    def resolve(self, task_type: TaskTypes) -> type:
        executor = self.get(task_type)
        if executor is None:
            raise SchedulerError(f"no executor for {task_type}")
        return executor

    def execute(self, task: SchedulerTask, infra: InfraKit) -> bool:
        executor_cls = self.resolve(task.type)
        kwargs = self._executor_kwargs.get(task.type, {})
        executor = executor_cls(infra, **kwargs)

        while True:
            try:
                executor.execute(task)
                return True
            except DeviceError:
                logger.warning("DeviceError, reconnecting...")
                infra.device.reconnect()
                continue
            except Exception:
                logger.exception(f"executor failed for task: {task}")
                return False
