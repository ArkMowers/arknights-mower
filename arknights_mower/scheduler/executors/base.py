from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional, Sequence

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.infra import InfraKit

logger = logging.getLogger(__name__)


class StepRetry(Exception):
    pass


class StepRestart(Exception):
    pass


@dataclass
class Step:
    name: str
    enter: Callable[[int], bool]
    act: Callable[[], Optional[list[Step]]] = field(default=lambda: None)
    start: int | None = None


class AbstractExecutor(ABC):
    _recog = None
    SCENE_WHITELIST: Optional[Sequence[int]] = None
    _timeout: timedelta = timedelta(hours=1)

    def __init__(self, infra: InfraKit) -> None:
        self.infra = infra
        AbstractExecutor._recog = infra.navigator._recognizer
        self._timeout_start: Optional[datetime] = None

    @property
    def _device(self):
        return self.infra.device

    @property
    def _pause(self):
        return self.infra.pause

    def _update_scene(self):
        AbstractExecutor._recog.update()
        return AbstractExecutor._recog.get_scene()

    def _get_scene(self) -> int:
        recog = AbstractExecutor._recog
        recog.update()
        wl = self.SCENE_WHITELIST
        if wl:
            recog.set_scene_whitelist(wl)
        try:
            return recog.get_scene()
        finally:
            if wl:
                recog.set_scene_whitelist(None)

    def wait_scene_stable(self, **kwargs):
        self.infra.navigator.wait_scene_stable(**kwargs)

    def safe_execute(self, task: SchedulerTask) -> bool:
        try:
            self.execute(task)            
            return True
        except Exception:
            logger.exception(f"executor failed for task: {task}")
            return False

    def guard(self) -> None:
        self.infra.pause.wait_if_paused()
        if self._timeout_start and datetime.now() - self._timeout_start > self._timeout:
            raise TimeoutError(f"{type(self).__name__} timeout after {self._timeout}")

    def run_steps(self, steps: list[Step]) -> None:
        from collections import deque
        from arknights_mower.scheduler.scene import Scene

        initial = list(steps)
        queue = deque(steps)
        logger.info(f"run_steps: start {' -> '.join(s.name for s in steps)}")
        while queue:
            self.guard()
            scene = self._get_scene()
            if scene in (Scene.LOADING, Scene.CONNECTING):
                continue
            if scene == Scene.LEAVE_INFRASTRUCTURE:
                self.infra.device.tap(670 / 1920, 750 / 1080)
                continue
            step = queue[0]
            if step.start is not None and scene != step.start:
                self.infra.navigator.navigate(step.start)
                continue
            if step.enter(scene):
                try:
                    extra = step.act() if step.act else None
                    queue.popleft()
                    if extra:
                        queue = deque(extra) + queue
                except StepRetry:
                    logger.info(f"step {step.name}: retry")
                    continue
                except StepRestart:
                    logger.info(f"step {step.name}: restart queue")
                    queue = deque(initial)
                except Exception:
                    logger.exception(f"step {step.name}: unhandled error")
                    raise
        logger.info("run_steps: done")

    @abstractmethod
    def execute(self, task: SchedulerTask) -> None:
        ...
