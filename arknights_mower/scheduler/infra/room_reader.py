from __future__ import annotations

from datetime import datetime

import cv2
import numpy as np

from arknights_mower.scheduler.state import SchedulerState
from arknights_mower.utils.image import cropimg
from arknights_mower.utils.log import logger


class RoomReader:
    def __init__(self, device, recognizer) -> None:
        self._device = device
        self._recog = recognizer

    def scan_room(self, room: str, state: SchedulerState) -> None:
        plan_room = state.plan.get(room, [])
        if not plan_room:
            return
        length = len(plan_room)

        self._recog.update()
        self._device.tap(0.5, 0.5)

        pos_x = (1288, 1869)
        pos_y_list = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        name_crops = [tuple(zip(pos_x, y)) for y in pos_y_list]

        mood_x = (1470, 1780)
        mood_y_coords = (219, 428, 637, 615, 823)
        mood_crops = [tuple(zip(mood_x, (y, y + 1))) for y in mood_y_coords]

        for i in range(length):
            self._recog.update()
            gray = self._recog.gray

            name_img = cropimg(gray, name_crops[i])
            if self._is_empty_slot(name_crops[i]):
                continue
            name = self._read_name(name_img)
            if not name:
                continue

            mood_img = cropimg(gray, mood_crops[i])
            mood = self._read_mood(mood_img)
            if name not in state.operators:
                from arknights_mower.scheduler.domain.operators import Operator, OperatorType

                op = Operator(name=name, room=room, index=i, operator_type=OperatorType.LOW)
                state.operators[name] = op

            op = state.operators.get(name)
            if op is not None:
                op.mood = mood
                op.time_stamp = datetime.now()
                op.current_room = room
                op.current_index = i

        for op_name in list(state.operators.keys()):
            op = state.operators[op_name]
            if op.current_room == room and (op.current_index < 0 or op.current_index >= length):
                op.current_room = ""
                op.current_index = -1

    def _is_empty_slot(self, crop_box) -> bool:
        from arknights_mower.utils.recognize import Recognizer

        return self._recog.find("infra_no_operator", scope=crop_box) is not None

    def _read_name(self, img: np.ndarray) -> str:
        from arknights_mower.solvers.base_mixin import OP_ROOM

        img = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY)[1]
        img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilation = cv2.dilate(img, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return ""
        rect = [cv2.boundingRect(c) for c in contours]
        rect.sort(key=lambda r: r[0])
        x, y, w, h = rect[0]
        img = img[y : y + h, x : x + w]
        tpl = np.zeros((46, 265), dtype=np.uint8)
        tpl[: img.shape[0], : img.shape[1]] = img
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        best = None
        best_score = 0
        for operator, template in OP_ROOM.items():
            result = cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = max_val
                best = operator
        return best or ""

    def _read_mood(self, img: np.ndarray) -> float:
        img = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY)[1]
        return cv2.countNonZero(img) * 24 / 310
