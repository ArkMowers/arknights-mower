from __future__ import annotations

from datetime import datetime
from typing import Optional

from arknights_mower.scheduler.dispatch import TaskDispatch
from arknights_mower.scheduler.errors import TaskNotFoundError
from arknights_mower.scheduler.infra import InfraKit
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger


class MainLoop:
    IDLE_INTERVAL = 30
    PLANNER_INTERVAL = 60
    IDLE_POLL = 1

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
        self._last_plan_time: Optional[datetime] = None

    def _run_planners(self) -> None:
        now = datetime.now()
        if self._last_plan_time is not None:
            elapsed = (now - self._last_plan_time).total_seconds()
            if elapsed < self.PLANNER_INTERVAL:
                return
        self._last_plan_time = now

        for planner in self.planners:
            try:
                task = planner.plan(self.state)
                if task is not None:
                    self.state.task_queue.push(task)
                    logger.debug(f"planner {planner.__class__.__name__} -> {task}")
            except Exception:
                logger.exception(f"planner {planner.__class__.__name__} failed")

    def run_forever(self) -> None:
        last_idle_log: Optional[datetime] = None
        logger.info("MainLoop: enter run_forever")
        while True:
            self._infra.pause.wait_if_paused()
            if self._infra.pause.is_stopped:
                logger.info("MainLoop stopped (is_stopped)")
                break

            self._run_planners()

            task = self.state.task_queue.peek()
            logger.debug(f"MainLoop: task={task}")
            if task is None:
                now = datetime.now()
                if last_idle_log is None or (
                    now - last_idle_log
                ).total_seconds() > self.IDLE_INTERVAL:
                    logger.info("no pending tasks, idling...")
                    last_idle_log = now
                self._infra.pause.wait(self.IDLE_POLL)
                continue

            if task.time > datetime.now():
                self._infra.pause.wait(self.IDLE_POLL)
                continue

            try:
                ok = self.dispatch.execute(task, self._infra)
            except MowerExit:
                logger.info("mower exiting, stopping main loop (MowerExit)")
                break
            except Exception:
                logger.exception("MainLoop: unhandled error from dispatch")
                break

            try:
                self.state.task_queue.pop()
            except TaskNotFoundError:
                pass

            self.state.error = not ok
            if not ok:
                logger.warning(f"task failed: {task}")
