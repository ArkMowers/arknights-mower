from __future__ import annotations

import time
from datetime import datetime

from arknights_mower.scheduler.dispatch import TaskDispatch
from arknights_mower.scheduler.errors import TaskNotFoundError
from arknights_mower.scheduler.infra import InfraKit
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState
from arknights_mower.utils.log import logger


class MainLoop:
    IDLE_INTERVAL = 30
    PLANNER_INTERVAL = 60

    def __init__(
        self,
        state: SchedulerState,
        planners: list[AbstractPlanner],
        dispatch: TaskDispatch,
        infra: InfraKit,
    ) -> None:
        self.state = state
        self.planners = planners
        self.dispatch = dispatch
        self._infra = infra
        self._last_plan_time = 0.0

    def _run_planners(self) -> None:
        now_ts = time.time()
        if now_ts - self._last_plan_time < self.PLANNER_INTERVAL:
            return
        self._last_plan_time = now_ts

        for planner in self.planners:
            try:
                task = planner.plan(self.state)
                if task is not None:
                    self.state.task_queue.push(task)
                    logger.debug(f"planner {planner.__class__.__name__} -> {task}")
            except Exception:
                logger.exception(f"planner {planner.__class__.__name__} failed")

    def run_forever(self) -> None:
        _idle_log = 0.0
        while True:
            self._infra.pause.wait_if_paused()
            if self._infra.pause.is_stopped:
                logger.info("MainLoop stopped")
                break

            self._run_planners()

            task = self.state.task_queue.peek()
            if task is None:
                now = time.time()
                if now - _idle_log > self.IDLE_INTERVAL:
                    logger.info("no pending tasks, idling...")
                    _idle_log = now
                time.sleep(1)
                continue

            if task.time > datetime.now():
                time.sleep(1)
                continue

            ok = self.dispatch.execute(task, self._infra)
            try:
                self.state.task_queue.pop()
            except TaskNotFoundError:
                pass

            self.state.error = not ok
            if not ok:
                logger.warning(f"task failed: {task}")
