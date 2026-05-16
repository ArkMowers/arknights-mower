from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger
from arknights_mower.scheduler.scene import Scene as V2Scene

class InfraScanExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=5)
    SCENE_WHITELIST = (
        V2Scene.CONNECTING,
        V2Scene.LOADING,
        V2Scene.INFRA_MAIN,
        V2Scene.INFRA_DETAILS,
        V2Scene.INFRA_ARRANGE,
        V2Scene.INFRA_ARRANGE_CONFIRM,
        V2Scene.INFRA_ARRANGE_ORDER,
        V2Scene.RIIC_OPERATOR_SELECT,
    )

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._rooms: deque[str] = deque()
        self._current_room = ""

    def execute(self, task: SchedulerTask) -> None:
        # --- TEST: wait_scene_stable infinite loop ---
        import time
        t0 = time.time()
        while True:
            self.check_pause()
            logger.info(f"[TEST] wait_scene_stable loop: {time.time()-t0:.1f}s")
            from arknights_mower.scheduler.scene import Scene
            self.infra.navigator.wait_scene_stable(max_checks=10, min_stable=1)
            logger.info(f"[TEST] wait_scene_stable returned")
            scene = self._get_scene()
            logger.info(f"[TEST] scene={scene}")
        # --- END TEST ---

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
            logger.info(f"Finished scanning room {room}, {len(self._rooms)} rooms left")

            if self._get_scene() != V2Scene.INFRA_MAIN:
                logger.info(f"Navigating back to INFRA_MAIN...")
                nav_ret = self.infra.navigator.navigate(V2Scene.INFRA_MAIN)
                logger.info(f"Navigate to INFRA_MAIN returned {nav_ret}")

    def _scan_single_room(self, room: str, start: datetime) -> None:

        detail_open = False
        while True:
            self.check_pause()
            if datetime.now() - start > self.MAX_DURATION:
                raise TimeoutError("infra scan timed out")

            scene = self._get_scene()
            logger.info(f"scan loop: room={room} scene={scene} detail_open={detail_open}")
            if scene == V2Scene.INFRA_MAIN:
                logger.info(f"scan loop: enter_room({room})")
                ret = self.infra.navigator.enter_room(room)
                logger.info(f"scan loop: enter_room returned {ret}")
            elif scene == V2Scene.INFRA_DETAILS:
                if self.infra.navigator._wait_room_detail():
                    AbstractExecutor._recog.update()
                    self._read_room_data(room)
                    return
            elif scene in (V2Scene.LOADING, V2Scene.CONNECTING):
                logger.info(f"scan loop: waiting for scene")
                pass       
            else:
                logger.info(f"scan loop: unexpected scene {scene}, navigate to INFRA_MAIN")
                self.infra.navigator.navigate(V2Scene.INFRA_MAIN)    

    def _tap_at(self, pos) -> None:
        box = pos[0] if isinstance(pos, tuple) else pos
        cx = (box[0][0] + box[1][0]) // 2  
        cy = (box[0][1] + box[1][1]) // 2
        self.infra.device.tap(cx / 1920, cy / 1080)

    def _read_room_data(self, room: str) -> None:
        from arknights_mower.scheduler.infra.room_reader import RoomReader

        RoomReader(self.infra.device, self._recog).scan_room(room, self.infra.state)
