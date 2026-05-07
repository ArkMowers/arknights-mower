from __future__ import annotations

import heapq
from datetime import datetime
from typing import Callable, Optional

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.errors import TaskNotFoundError


class TaskQueue:
    def __init__(self) -> None:
        self._tasks: list[SchedulerTask] = []

    def push(self, task: SchedulerTask) -> None:
        heapq.heappush(self._tasks, (task.time, id(task), task))

    def pop(self) -> SchedulerTask:
        if not self._tasks:
            raise TaskNotFoundError("pop from empty queue")
        _, _, task = heapq.heappop(self._tasks)
        return task

    def peek(self) -> Optional[SchedulerTask]:
        if not self._tasks:
            return None
        return self._tasks[0][2]

    def find(
        self,
        task_type: Optional[TaskTypes] = None,
        meta_data: str = "",
        predicate: Optional[Callable[[SchedulerTask], bool]] = None,
    ) -> Optional[SchedulerTask]:
        for _, _, task in self._tasks:
            if predicate is not None and predicate(task):
                return task
            if task_type is not None and task.type == task_type:
                if not meta_data or meta_data in task.meta_data:
                    return task
        return None

    def remove(self, task: SchedulerTask) -> None:
        for i, (_, _, t) in enumerate(self._tasks):
            if t is task:
                self._tasks.pop(i)
                heapq.heapify(self._tasks)
                return
        raise TaskNotFoundError(f"task {task} not found")

    def __len__(self) -> int:
        return len(self._tasks)

    def __bool__(self) -> bool:
        return len(self._tasks) > 0

    def all_tasks(self) -> list[SchedulerTask]:
        return [t[2] for t in self._tasks]
