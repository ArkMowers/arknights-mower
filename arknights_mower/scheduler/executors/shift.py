from __future__ import annotations

from collections import deque
from datetime import timedelta

import cv2
import numpy as np

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor, Step, StepRestart, StepRetry
from arknights_mower.scheduler.scene import Scene as V2Scene
from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
from arknights_mower.utils.log import logger


class ShiftExecutor(AbstractExecutor):
    _timeout = timedelta(minutes=10)

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
            Step("detail",  self._detail_step,  self._do_detail,      start=V2Scene.INFRA_DETAILS),
            Step("arrange", self._arrange_step, self._do_arrange,     start=V2Scene.INFRA_DETAILS),
            Step("swap",    self._swap_step,    self._do_swap,        start=V2Scene.RIIC_OPERATOR_SELECT),
            Step("done",    self._done_step,    self._do_confirm,     start=V2Scene.INFRA_DETAILS),
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
        self._recog.update()
        if self._recog.find("confirm_blue"):
            return None
        self.infra.device.tap(0.82, 0.2)
        self.infra.navigator.wait_scene_stable(max_duration=1.0, min_stable=1)
        return None

    def _swap_step(self, scene: int) -> bool:
        if scene != V2Scene.RIIC_OPERATOR_SELECT:
            raise StepRestart
        return True

    def _do_swap(self) -> list[Step] | None:
        current = self._read_current()
        ok = self.swap_service.run(
            self._room, self._agents,
            current_operators=current if len(current) == len(self._agents) else None,
        )
        if not ok:
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

    def _read_current(self, slot_count: int = 5) -> list[str]:
        self._recog.update()
        names = []
        name_x = (1288, 1869)
        name_y = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        for idx in range(slot_count):
            y = name_y[idx]
            crop_box = tuple(zip(name_x, y))
            if self._recog.find("infra_no_operator", scope=crop_box) is None:
                gray_crop = (
                    cv2.cvtColor(self._recog.img[y[0]:y[1], name_x[0]:name_x[1]], cv2.COLOR_RGB2GRAY)
                    if len(self._recog.img.shape) == 3
                    else self._recog.img[y[0]:y[1], name_x[0]:name_x[1]]
                )
                name = self._read_name(gray_crop)
                names.append(name or "")
            else:
                names.append("")
        return names

    def _read_name(self, img: np.ndarray) -> str:
        from arknights_mower.solvers.base_mixin import OP_ROOM
        from arknights_mower.utils.image import cropimg

        img = cropimg(img, ((169, 22), (513, 80)))
        img = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY)[1]
        img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        kernel = np.ones((12, 12), np.uint8)
        dilation = cv2.dilate(img, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return ""
        rect = sorted((cv2.boundingRect(c) for c in contours), key=lambda r: r[0])
        x, y, w, h = rect[0]
        img = img[y:y + h, x:x + w]
        h, w = min(img.shape[0], 46), min(img.shape[1], 265)
        tpl = np.zeros((46, 265), dtype=np.uint8)
        tpl[:h, :w] = img[:h, :w]
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        best, best_score = None, 0
        for operator, template in OP_ROOM.items():
            _, max_val, _, _ = cv2.minMaxLoc(
                cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
            )
            if max_val > best_score:
                best_score = max_val
                best = operator
        return best or ""

    def _tap_center(self, box) -> None:
        if isinstance(box, (list, tuple)) and len(box) == 2:
            if isinstance(box[0], (list, tuple)):
                x1, y1 = box[0]
                x2, y2 = box[1]
                self.infra.device.tap((x1 + x2) / 2 / 1920, (y1 + y2) / 2 / 1080)
            else:
                self.infra.device.tap(box[0] / 1920, box[1] / 1080)
