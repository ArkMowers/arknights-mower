"""换班服务的排序/筛选原语。

对应拆分前的 `_detect_arrange` / `_arrange_x` / `_tap_sort` /
`_detect_filter` / `_open_filter` / `_switch_filter_other` 六个方法，
以及 `_select_one_agent`（"扫描一次面板并点中给定名字之一"）。

全部为 UI 原语，不含换班编排逻辑。
"""

from __future__ import annotations

import cv2
import numpy as np

from arknights_mower.scheduler.constants import (
    ARRANGE_Y,
    CONFIRM_BLUE,
    CONFIRM_TRAIN,
    DORM_ARRANGE_NAMES,
    DORM_ARRANGE_X,
    FILTER_CLOSE_THRESHOLD,
    MAX_RETRY,
    PROD_ARRANGE_NAMES,
    PROD_ARRANGE_X,
    PROFESSION_LABEL_POS,
    PROFESSION_LABELS,
    SCREEN_H,
    SCREEN_W,
)


class AgentSwapArrangeMixin:
    """重排面板的排序方向与职介筛选原语。"""

    def _detect_arrange(self, room: str) -> tuple[str | None, bool]:
        img = self._screencap()
        if room.startswith("dorm") or room == "central":
            names = DORM_ARRANGE_NAMES
            x_list = DORM_ARRANGE_X
        else:
            names = PROD_ARRANGE_NAMES
            x_list = PROD_ARRANGE_X
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (95, 100, 100), (105, 255, 255))
        y = ARRANGE_Y
        for idx, x in enumerate(x_list):
            if np.count_nonzero(mask[y : y + 3, x : x + 5]):
                return names[idx], False
            if np.count_nonzero(mask[y + 10 : y + 13, x : x + 5]):
                return names[idx], True
        return None, False

    def _arrange_x(self, name: str, room: str) -> int:
        if room.startswith("dorm") or room == "central":
            mapping = dict(zip(DORM_ARRANGE_NAMES, DORM_ARRANGE_X))
        else:
            mapping = dict(zip(PROD_ARRANGE_NAMES, PROD_ARRANGE_X))
        return mapping.get(name, PROD_ARRANGE_X[0])

    def _tap_sort(self, name: str, ascending: bool, room: str) -> None:
        x = self._arrange_x(name, room)
        self._device.tap(x / SCREEN_W, ARRANGE_Y / SCREEN_H)
        for _ in range(MAX_RETRY):
            n, s = self._detect_arrange(room)
            if n == name and s == ascending:
                return
            self._device.tap(x / SCREEN_W, ARRANGE_Y / SCREEN_H)

    def _detect_filter(self) -> str:
        self._recog.update()
        img = self._recog.img
        found_blue = self._find(CONFIRM_BLUE)
        found_train = self._find(CONFIRM_TRAIN)
        panel_open = (
            found_blue and found_blue[0][0] > FILTER_CLOSE_THRESHOLD
        ) or (found_train and found_train[0][0] > FILTER_CLOSE_THRESHOLD)
        if not panel_open:
            return "ALL"
        for label, (lx, ly) in zip(PROFESSION_LABELS, PROFESSION_LABEL_POS):
            if img[ly, lx, 2] >= 240:
                return label
        return "ALL"

    def _open_filter(self, profession: str) -> None:
        label_pos_map = dict(zip(PROFESSION_LABELS, PROFESSION_LABEL_POS))

        if profession == "ALL":
            for _ in range(MAX_RETRY):
                self._recog.update()
                confirm_blue = self._find(CONFIRM_BLUE)
                confirm_train = self._find(CONFIRM_TRAIN)
                is_open = (
                    confirm_blue and confirm_blue[0][0] < FILTER_CLOSE_THRESHOLD
                ) or (confirm_train and confirm_train[0][0] < FILTER_CLOSE_THRESHOLD)
                if not is_open:
                    return
                self._device.tap(1860 / SCREEN_W, 60 / SCREEN_H)
            return

        for _ in range(MAX_RETRY):
            self._recog.update()
            confirm_blue = self._find(CONFIRM_BLUE)
            confirm_train = self._find(CONFIRM_TRAIN)
            is_open = (
                confirm_blue and confirm_blue[0][0] > FILTER_CLOSE_THRESHOLD
            ) or (confirm_train and confirm_train[0][0] > FILTER_CLOSE_THRESHOLD)
            if is_open:
                break
            self._device.tap(1860 / SCREEN_W, 60 / SCREEN_H)

        all_pos = label_pos_map["ALL"]
        self._device.tap(all_pos[0] / SCREEN_W, all_pos[1] / SCREEN_H)

        px, py = label_pos_map[profession]
        for _ in range(MAX_RETRY):
            self._recog.update()
            if self._recog.img[py, px, 2] >= 240:
                return
            self._device.tap(px / SCREEN_W, py / SCREEN_H)

    def _switch_filter_other(self, current: str) -> str:
        other = next(
            (label for label in PROFESSION_LABELS if label != current and label != "ALL"),
            "ALL",
        )
        self._open_filter(other)
        return other

    def _select_one_agent(self, agents: list[str], room: str) -> None:
        self._recog.update()
        ret = self._operator_list_fn(self._recog.img, full_scan=True)
        for name, box in ret:
            if name in agents:
                self._tap_center(box)
                return
