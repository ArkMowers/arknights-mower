from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from enum import Enum, auto

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger


class InfraScanState(Enum):
    NAVIGATE = auto()
    NEXT_ROOM = auto()
    FIND_ROOM = auto()
    ENTER_ROOM = auto()
    ROOM_DETAIL = auto()
    READ_DATA = auto()
    BACK_OUT = auto()
    DONE = auto()


class InfraScanExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=15)
    MAX_ENTER_RETRY = 3

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._rooms: deque[str] = deque()
        self._enter_attempts = 0
        self._state = InfraScanState.DONE

    def execute(self, task: SchedulerTask) -> None:
        rooms = [r.strip() for r in task.meta_data.split(",") if r.strip()]
        self._rooms = deque(rooms)
        self._state = InfraScanState.NAVIGATE
        start = datetime.now()

        while self._state != InfraScanState.DONE:
            self.check_pause()
            if datetime.now() - start > self.MAX_DURATION:
                raise TimeoutError("infra scan timed out")
            getattr(self, f"_state_{self._state.name.lower()}")()
            self.infra.device.screencap()

    def _state_navigate(self) -> None:
        from arknights_mower.scheduler.scene import Scene

        if self.infra.navigator.navigate(Scene.INFRA_MAIN):
            self._state = InfraScanState.NEXT_ROOM
        else:
            self.infra.device.tap(0.5, 0.5)
            self._state = InfraScanState.NEXT_ROOM

    def _state_next_room(self) -> None:
        if not self._rooms:
            self._state = InfraScanState.DONE
            return
        self._enter_attempts = 0
        self._state = InfraScanState.FIND_ROOM

    def _state_find_room(self) -> None:
        room = self._rooms[0]
        self._get_scene()

        central = self._recognizer.find("control_central") if self._recognizer else None
        if central is None:
            self._enter_attempts += 1
            if self._enter_attempts >= self.MAX_ENTER_RETRY:
                logger.warning(f"failed to find control_central for {room}, skip")
                self._state = InfraScanState.BACK_OUT
            return

        from arknights_mower.utils.segment import base as segment_base

        rooms_map = segment_base(self._recognizer.img, central)
        target = rooms_map.get(room)
        if target is None:
            self._enter_attempts += 1
            if self._enter_attempts >= self.MAX_ENTER_RETRY:
                logger.warning(f"room {room} not in segment map, skip")
                self._state = InfraScanState.BACK_OUT
            return

        self._room_center = (
            int((target[0][0] + target[2][0]) / 2),
            int((target[1][1] + target[3][1]) / 2),
        )
        self._state = InfraScanState.ENTER_ROOM

    def _state_enter_room(self) -> None:
        cx, cy = self._room_center
        self.infra.device.tap(cx / 1920, cy / 1080)
        self._state = InfraScanState.ROOM_DETAIL

    def _state_room_detail(self) -> None:
        if self.infra.navigator.turn_on_room_detail():
            self._state = InfraScanState.READ_DATA
        else:
            logger.warning("failed to turn on room detail")
            self._state = InfraScanState.BACK_OUT

    def _state_read_data(self) -> None:
        room = self._rooms[0]

        from arknights_mower.scheduler.infra.room_reader import RoomReader
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        RoomReader(self.infra.device, recog).scan_room(room, self.infra.state)

        self._state = InfraScanState.BACK_OUT

    def _state_back_out(self) -> None:
        from arknights_mower.scheduler.scene import Scene

        self.infra.navigator.navigate(Scene.INFRA_MAIN)
        self._rooms.popleft()
        self._state = InfraScanState.NEXT_ROOM

    def _get_scene(self) -> None:
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        recog.update()
        self._recognizer = recog
