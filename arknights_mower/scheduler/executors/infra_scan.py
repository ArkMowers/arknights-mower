from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger

from arknights_mower.scheduler.scene import Scene as V2Scene

class InfraScanExecutor(AbstractExecutor):
    _timeout = timedelta(minutes=5)
    SCENE_WHITELIST = (
        V2Scene.CONNECTING,
        V2Scene.LOADING,
        V2Scene.INFRA_MAIN,
        V2Scene.INFRA_DETAILS,
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
        self._current_room = ""
        self._timeout = timeout

    def execute(self, task: SchedulerTask) -> None:        
        rooms = [r.strip() for r in task.meta_data.split(",") if r.strip()]
        self._rooms = deque(rooms)

        while self._rooms:
            self.guard()

            room = self._rooms[0]
            self._current_room = room
            self._scan_single_room(room)
            self._rooms.popleft()

            if self._get_scene() != V2Scene.INFRA_MAIN:
                self.infra.navigator.navigate(V2Scene.INFRA_MAIN)

    def _scan_single_room(self, room: str) -> None:
        while True:
            self.guard()

            scene = self._get_scene()
            if scene == V2Scene.INFRA_MAIN:
                self.infra.navigator.enter_room(room)
            elif scene == V2Scene.INFRA_DETAILS_OPEN:
                self._read_room_data(room)
                return
            elif scene == V2Scene.INFRA_DETAILS or scene == V2Scene.CTRLCENTER_ASSISTANT:
                self.infra.navigator._wait_room_detail()
                continue
            elif scene in (V2Scene.LOADING, V2Scene.CONNECTING):
                pass
            else:
                self.infra.navigator.navigate(V2Scene.INFRA_MAIN)    

    def _tap_at(self, pos) -> None:
        box = pos[0] if isinstance(pos, tuple) else pos
        cx = (box[0][0] + box[1][0]) // 2  
        cy = (box[0][1] + box[1][1]) // 2
        self.infra.device.tap(cx / 1920, cy / 1080)

    def _read_room_data(self, room: str) -> None:
        from arknights_mower.scheduler.infra.room_reader import RoomReader

        RoomReader(self.infra.device, self._recog).scan_room(room, self.infra.state)
