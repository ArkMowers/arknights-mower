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
    ENTER_ROOM = auto()
    READ_DATA = auto()
    BACK_OUT = auto()
    DONE = auto()


class InfraScanExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=15)

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._rooms: deque[str] = deque()
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
            return

        logger.warning("navigator failed, tapping to dismiss login")
        self.infra.device.tap(0.5, 0.5)
        self._state = InfraScanState.NEXT_ROOM

    def _state_next_room(self) -> None:
        if not self._rooms:
            self._state = InfraScanState.DONE
            return
        self._state = InfraScanState.ENTER_ROOM

    def _state_enter_room(self) -> None:
        room = self._rooms[0]
        logger.info(f"entering room: {room}")

        from arknights_mower.scheduler.scene import Scene
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        recog.update()
        recog.get_scene()

        tap_pos = self._find_room_tab(room, recog)
        if tap_pos is not None:
            self.infra.device.tap(*tap_pos)

        self._state = InfraScanState.READ_DATA

    def _state_read_data(self) -> None:
        room = self._rooms[0]
        logger.info(f"reading data for room: {room}")

        from arknights_mower.scheduler.infra.room_reader import RoomReader
        from arknights_mower.utils.recognize import Recognizer

        recog = Recognizer(self.infra.device._device)
        RoomReader(self.infra.device, recog).scan_room(room, self.infra.state)

        self._state = InfraScanState.BACK_OUT

    def _state_back_out(self) -> None:
        self.infra.device.back()
        self._rooms.popleft()
        self._state = InfraScanState.NEXT_ROOM

    def _find_room_tab(self, room: str, recog) -> tuple | None:
        tap = recog.find(f"infra_{room}")
        if tap is not None:
            center = (
                (tap[0][0] + tap[1][0]) / 2 / 1920,
                (tap[0][1] + tap[1][1]) / 2 / 1080,
            )
            return center
        logger.warning(f"could not find room tab: {room}")
        return None
