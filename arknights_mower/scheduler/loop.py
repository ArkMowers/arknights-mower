from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.dispatch import TaskDispatch
from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.errors import DeviceError, TaskNotFoundError
from arknights_mower.scheduler.infra.pause_controller import PauseController
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
        device: DevicePort,
        pause_controller: PauseController,
    ) -> None:
        self.state = state
        self.planners = planners
        self.dispatch = dispatch
        self._device = device
        self._pause = pause_controller
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
            self._pause.wait_if_paused()
            if self._pause.is_stopped:
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

            ok = self.dispatch.execute(task, self._device, self._pause)
            try:
                self.state.task_queue.pop()
            except TaskNotFoundError:
                pass

            self.state.error = not ok
            if not ok:
                logger.warning(f"task failed: {task}")
