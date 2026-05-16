from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Sequence

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.infra import InfraKit

logger = logging.getLogger(__name__)


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

    @abstractmethod
    def execute(self, task: SchedulerTask) -> None:
        ...
