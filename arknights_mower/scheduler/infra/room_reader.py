from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import cv2
import numpy as np

from arknights_mower.scheduler.database.repositories.state import StateRepository
from arknights_mower.scheduler.database.sqlite_storage import SQLiteStorage
from arknights_mower.scheduler.state import SchedulerState
from arknights_mower.utils.image import cropimg
from arknights_mower.utils.log import logger


class RoomReader:
    def __init__(self, device, recognizer, navigator=None) -> None:
        self._device = device
        self._recog = recognizer
        self._navigator = navigator
        self._storage: Optional[StateRepository] = None

    @property
    def storage(self) -> StateRepository:
        if self._storage is None:
            self._storage = StateRepository(SQLiteStorage())
        return self._storage

    def scan_room(self, room: str, state: SchedulerState) -> None:
        plan_room = state.plan.get(room, [])
        if not plan_room:
            return
        length = len(plan_room)

        name_x = (1288, 1869)
        name_y = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        name_crops = [tuple(zip(name_x, y)) for y in name_y]

        mood_x = (1470, 1780)
        mood_y = (219, 428, 637, 615, 823)
        mood_crops = [tuple(zip(mood_x, (y, y + 1))) for y in mood_y]

        time_x = (1650, 1780)
        time_y = [(270, 305), (480, 515), (690, 725), (668, 703), (877, 912)]
        time_crops = [tuple(zip(time_x, y)) for y in time_y]

        self._recog.update()

        swiped = False
        slots = []
        for i in range(length):
            if i >= 3 and not swiped:
                if self._recog.img[930, 1800, 0] > 51:
                    self._device.swipe(0.8, 0.5, 0.8, 0.05, duration=500)
                    if self._navigator:
                        self._navigator.wait_scene_stable(max_duration=0.5, min_stable=2)
                    self._recog.update()
                swiped = True

            gray = self._recog.gray

            if self._is_empty_slot(name_crops[i]):
                slots.append("空")
                continue

            name = self._read_name(cropimg(gray, name_crops[i]))
            if not name:
                slots.append("空")
                continue

            mood = self._read_mood(cropimg(gray, mood_crops[i]))
            update_time = self._read_time(cropimg(self._recog.img, time_crops[i]))
            slots.append(f"{name}({mood:.0f})")

            if name not in state.operators:
                from arknights_mower.scheduler.domain.operators import Operator, OperatorType

                state.operators[name] = Operator(
                    name=name, room=room, index=i, operator_type=OperatorType.LOW
                )

            op = state.operators.get(name)
            if op is not None:
                op.mood = mood
                op.time_stamp = update_time or datetime.now()
                op.current_room = room
                op.current_index = i

        logger.info(f"RoomReader: {room} [{' '.join(slots)}]")

        for op_name in list(state.operators.keys()):
            op = state.operators[op_name]
            if op.current_room == room and (op.current_index < 0 or op.current_index >= length):
                op.current_room = ""
                op.current_index = -1

        self._persist(state)

    def _persist(self, state: SchedulerState) -> None:
        data = state.save_snapshot()
        if data:
            self.storage.save("operator_mood", data)

    def _is_empty_slot(self, crop_box) -> bool:
        return self._recog.find("infra_no_operator", scope=crop_box) is not None

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
        img = img[y : y + h, x : x + w]

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

    def _read_mood(self, img: np.ndarray) -> float:
        img = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY)[1]
        return cv2.countNonZero(img) * 24 / 310

    def _read_time(self, img: np.ndarray) -> datetime | None:
        from arknights_mower.utils import rapidocr

        try:
            ret = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)[0]
            if not ret or not ret[0][0]:
                return None
            time_str = ret[0][0].replace(".", ":")
            h, m, s = time_str.split(":")
            return datetime.now() + timedelta(
                seconds=int(h) * 3600 + int(m) * 60 + int(s)
            )
        except Exception:
            return None
