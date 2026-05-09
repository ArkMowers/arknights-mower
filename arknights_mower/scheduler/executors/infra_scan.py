from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger


class InfraScanExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=15)

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._rooms: deque[str] = deque()
        self._current_room = ""

    def execute(self, task: SchedulerTask) -> None:
        rooms = [r.strip() for r in task.meta_data.split(",") if r.strip()]
        self._rooms = deque(rooms)
        start = datetime.now()

        while self._rooms:
            self.check_pause()
            if datetime.now() - start > self.MAX_DURATION:
                raise TimeoutError("infra scan timed out")

            room = self._rooms[0]
            self._current_room = room
            self._scan_single_room(room, start)
            self._rooms.popleft()

    def _scan_single_room(self, room: str, start: datetime) -> None:
        from arknights_mower.scheduler.scene import Scene as V2Scene

        if not self._at_infra_main():
            self.infra.navigator.navigate(V2Scene.INFRA_MAIN)
            self.infra.navigator.wait_scene_stable()

        self._enter_room_with_retry(room)

    def _at_infra_main(self) -> bool:
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        recog.update()
        from arknights_mower.utils.scene import Scene

        return recog.get_scene() == Scene.INFRA_MAIN

    def _enter_room(self, room: str) -> None:
        if self.infra.navigator.enter_room(room):
            self._read_room_data(room)

    def _wait_room_ready(self) -> bool:
        self.infra.navigator.wait_scene_stable()
        for _ in range(10):
            self.check_pause()
            self._get_scene()
            if self._detect_room_view():
                return True
        return False

    def _detect_room_view(self) -> bool:
        from arknights_mower.utils.scene import Scene

        s = self._get_scene()
        return s in (Scene.INFRA_DETAILS, Scene.INFRA_ARRANGE)

    def _get_scene(self):
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        recog.update()
        return recog.get_scene()

    def _read_room_data(self, room: str) -> None:
        from arknights_mower.scheduler.infra.room_reader import RoomReader
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        RoomReader(self.infra.device, recog).scan_room(room, self.infra.state)
