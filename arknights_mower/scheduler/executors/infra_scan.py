from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor, Step, StepRestart, StepRetry
from arknights_mower.utils.log import logger
from arknights_mower.utils.log import logger

from arknights_mower.scheduler.scene import Scene as V2Scene


class InfraScanExecutor(AbstractExecutor):
    _timeout = timedelta(minutes=5)
    SCENE_WHITELIST = (
        V2Scene.CONNECTING,
        V2Scene.LOADING,
        V2Scene.INFRA_MAIN,
        V2Scene.INFRA_DETAILS,
        V2Scene.INFRA_DETAILS_OPEN,
        V2Scene.INFRA_ROOM_GAP,
        V2Scene.INFRA_ARRANGE,
        V2Scene.INFRA_ARRANGE_CONFIRM,
        V2Scene.INFRA_ARRANGE_ORDER,
        V2Scene.RIIC_OPERATOR_SELECT,
        V2Scene.CTRLCENTER_ASSISTANT,
    )

    def __init__(self, infra, timeout: timedelta = _timeout) -> None:
        super().__init__(infra)
        self._rooms: deque[str] = deque()
        self._timeout = timeout

    def execute(self, task: SchedulerTask) -> None:
        rooms = [r.strip() for r in task.meta_data.split(",") if r.strip()]
        self._rooms = deque(rooms)

        while self._rooms:
            self.guard()
            self._room = self._rooms[0]
            try:
                self._run_scan(self._room)
                self._rooms.popleft()
            except (StepRetry, StepRestart):
                logger.info(f"scan room {self._room}: retry")
                continue
            finally:
                if self._get_scene() != V2Scene.INFRA_MAIN:
                    self.infra.navigator.navigate(V2Scene.INFRA_MAIN)

    def _run_scan(self, room: str) -> None:
        self._room = room
        self.run_steps([
            Step("enter",   self._scan_enter,   self._do_scan_enter,   start=V2Scene.INFRA_MAIN),
            Step("arrange", self._scan_arrange, self._do_scan_arrange),
            Step("read",    self._scan_read,    self._do_scan_read),
        ])

    def _scan_enter(self, scene: int) -> bool:
        return scene == V2Scene.INFRA_MAIN

    def _do_scan_enter(self) -> list[Step] | None:
        if not self.infra.navigator.enter_room(self._room):
            raise StepRestart
        return None

    def _scan_arrange(self, scene: int) -> bool:
        if not scene in (V2Scene.INFRA_DETAILS, V2Scene.INFRA_DETAILS_OPEN):
            raise StepRestart
        return True

    def _do_scan_arrange(self) -> list[Step] | None:
        if not self.infra.navigator._wait_room_detail():
            raise StepRestart
        return None

    def _scan_read(self, scene: int) -> bool:        
        if not scene in (V2Scene.INFRA_DETAILS_OPEN, V2Scene.CTRLCENTER_ASSISTANT):
            raise StepRestart
        return True

    def _do_scan_read(self) -> list[Step] | None:
        from arknights_mower.scheduler.infra.room_reader import RoomReader

        RoomReader(self.infra.device, self._recog, self.infra.navigator).scan_room(self._room, self.infra.state)
        return None
