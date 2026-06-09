from __future__ import annotations

from collections import deque
from datetime import timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor, Step, StepRestart, StepRetry
from arknights_mower.scheduler.infra.room_reader import RoomReader
from arknights_mower.scheduler.scene import Scene as V2Scene
from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
from arknights_mower.scheduler.services.operator_service import current_operators_in_room
from arknights_mower.utils.log import logger


class ShiftExecutor(AbstractExecutor):
    _timeout = timedelta(minutes=10)
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
        V2Scene.RIIC_OPERATOR_SELECT
    )

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._swap: AgentSwapService | None = None
        self._pending: deque = deque()
        self._room = ""
        self._agents: list[str] = []

    @property
    def swap_service(self) -> AgentSwapService:
        if self._swap is None:
            self._swap = AgentSwapService(
                self.infra.device, self._recog,
                self.infra.navigator._get_scene, self.infra.pause,
            )
        return self._swap

    def execute(self, task: SchedulerTask) -> None:
        rooms = list(task.plan.items())
        if not rooms:
            return
        self._pending = deque(rooms)
        self._advance()
        while self._room:
            self._run_room()

    def _run_room(self) -> None:
        self.run_steps([
            Step("enter",   self._enter_step,   self._do_enter,       start=V2Scene.INFRA_MAIN),
            Step("detail",  self._detail_step,  self._do_detail),
            Step("wait",    self._wait_step,    self._do_wait),
            Step("arrange", self._arrange_step, self._do_arrange),
            Step("swap",    self._swap_step,    self._do_swap),
            Step("done",    self._done_step,    self._do_confirm),
        ])
        self._advance()

    def _enter_step(self, scene: int) -> bool:
        if scene != V2Scene.INFRA_MAIN:
            raise StepRestart
        return True

    def _do_enter(self) -> list[Step] | None:
        if not self.infra.navigator.enter_room(self._room):
            raise StepRetry
        return None

    def _wait_step(self, scene: int) -> bool:
        if scene not in (V2Scene.INFRA_DETAILS, V2Scene.INFRA_DETAILS_OPEN):
            raise StepRestart
        return True

    def _do_wait(self) -> list[Step] | None:
        RoomReader(self.infra.device, self._recog, self.infra.navigator).scan_room(self._room, self.infra.state)
        return None

    def _detail_step(self, scene: int) -> bool:
        if scene not in (V2Scene.INFRA_DETAILS, V2Scene.INFRA_DETAILS_OPEN):
            raise StepRestart
        return True

    def _do_detail(self) -> list[Step] | None:
        if self._get_scene() == V2Scene.INFRA_DETAILS:
            if not self.infra.navigator._wait_room_detail():
                raise StepRestart
        return None

    def _arrange_step(self, scene: int) -> bool:
        if scene not in (V2Scene.INFRA_DETAILS, V2Scene.INFRA_DETAILS_OPEN):
            raise StepRestart
        return True

    def _do_arrange(self) -> list[Step] | None:
        self.infra.device.tap(0.82, 0.2)
        self.infra.navigator.wait_scene_stable(max_duration=0.5, min_stable=2)
        self._recog.update()
        if self._recog.find("confirm_blue"):
            logger.info("_do_arrange: confirm_blue found, proceed")
            return None
        logger.info("_do_arrange: confirm_blue not found, restart")
        raise StepRestart        

    def _swap_step(self, scene: int) -> bool:
        if scene != V2Scene.INFRA_ARRANGE_ORDER:
            logger.info(f"_swap_step: scene {scene} != INFRA_ARRANGE_ORDER, restart")
            raise StepRestart
        return True

    def _do_swap(self) -> list[Step] | None:
        current = current_operators_in_room(self.infra.state, self._room)
        logger.info(f"_do_swap: current={current} agents={self._agents}")
        ok = self.swap_service.run(
            self._room, self._agents,
            current_operators=current if len(current) == len(self._agents) else None,
        )
        if not ok:
            logger.info("_do_swap: swap_service failed, restart")
            raise StepRestart
        return None

    def _done_step(self, scene: int) -> bool:
        if scene not in (V2Scene.INFRA_DETAILS, V2Scene.INFRA_DETAILS_OPEN):
            raise StepRestart
        self._recog.update()
        return not self._recog.find("confirm_blue")

    def _do_confirm(self) -> list[Step] | None:
        for btn in ("confirm_blue", "confirm_train", "arrange_confirm"):
            pos = self._recog.find(btn)
            if pos:
                box = pos[0] if isinstance(pos, tuple) else pos
                self._tap_center(box)
                return None
        return None

    def _advance(self) -> None:
        if self._pending:
            self._room, self._agents = self._pending.popleft()
            logger.info(f"ShiftExecutor: room={self._room} agents={self._agents}")
        else:
            self._room = ""

    def _tap_center(self, box) -> None:
        if isinstance(box, (list, tuple)) and len(box) == 2:
            if isinstance(box[0], (list, tuple)):
                x1, y1 = box[0]
                x2, y2 = box[1]
                self.infra.device.tap((x1 + x2) / 2 / 1920, (y1 + y2) / 2 / 1080)
            else:
                self.infra.device.tap(box[0] / 1920, box[1] / 1080)
