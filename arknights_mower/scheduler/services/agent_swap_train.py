"""训练位专用换班流程。

对应拆分前的 `_run_train` 及其私有辅助 `_select_train_ope`、
`_tap_confirm_train`、`_tap_element`、`_read_operators_on_screen`、`_read_name`。

训练位与其他房间**不是同一套流程**：它没有"排序/筛选"步骤，
而是靠 `INFRA_DETAILS` ↔ `INFRA_ARRANGE_ORDER` 的场景往返驱动，
因此单独成一个文件，不混入 `_do_select` 的编排。
"""

from __future__ import annotations

import cv2
import numpy as np

from arknights_mower.scheduler.constants import (
    ARRANGE_CONFIRM,
    CONFIRM_BLUE,
    CONFIRM_TRAIN,
    MAX_PAGE,
    SCREEN_H,
    SCREEN_W,
)
from arknights_mower.scheduler.scene import Scene
from arknights_mower.utils.log import logger


class AgentSwapTrainMixin:
    """`room == "train"` 的专用流程。"""

    def _run_train(self, agents: list[str], train_index: int) -> bool:
        logger.info(f"AgentSwap train: target={agents}")
        tasks = ["scan"]
        select_targets: list = []

        while tasks:
            self._pause.wait_if_paused()
            scene = self._get_scene()
            if scene in (Scene.LOADING, Scene.CONNECTING):
                continue

            if scene == Scene.INFRA_DETAILS:
                if tasks[0] == "scan":
                    scanned = self._read_operators_on_screen()
                    logger.info(f"AgentSwap train: current room = {scanned}")
                    desired = list(agents)
                    for idx, name in enumerate(desired):
                        if name == "Current":
                            desired[idx] = scanned[idx] if idx < len(scanned) else "Free"
                    select_targets = [
                        (idx, desired_name)
                        for idx, desired_name in enumerate(desired)
                        if idx >= len(scanned) or scanned[idx] != desired_name
                    ]
                    logger.info(f"AgentSwap train: need change = {select_targets}")
                    if not select_targets:
                        logger.info("AgentSwap train: already correct")
                        return True
                    tasks[0] = "select"
                else:
                    if not select_targets:
                        return True
                    idx = select_targets[0][0]
                    logger.info(f"AgentSwap train: tap slot {idx}")
                    self._device.tap(0.82, 0.18 * (idx + 1))
                continue

            elif scene == Scene.INFRA_ARRANGE_ORDER:
                if tasks[0] == "scan":
                    logger.info("AgentSwap train: back from arrange")
                    self._back()
                else:
                    if not select_targets:
                        return True
                    idx, target_name = select_targets[0]
                    logger.info(
                        f"AgentSwap train: select idx={idx} target={target_name}"
                    )
                    if idx == 0:
                        self._select_one_agent([target_name], "train")
                    else:
                        self._select_train_ope(target_name)
                    self._tap_confirm_train()
                    select_targets.pop(0)
                    if select_targets:
                        logger.info(
                            f"AgentSwap train: {len(select_targets)} more to go"
                        )
                        continue
                    tasks[0] = "scan"

            elif scene == Scene.UNKNOWN:
                continue
            else:
                return False

        return True

    # ─── 训练位私有辅助 ───

    def _select_train_ope(self, target: str) -> None:
        if target == "Free":
            self._open_filter("ALL")
        else:
            profession = self._agent_profession.get(target)
            if profession:
                self._open_filter(profession)

        first_name = ""
        page = 0
        while True:
            self._recog.update()
            ret = self._operator_list_fn(self._recog.img, full_scan=(page == 0))
            if not ret:
                continue
            for name, box in ret:
                if target == "Free" or name == target:
                    self._tap_center(box)
                    return
                if name == first_name and page >= 3:
                    return
                first_name = ret[0][0] if page == 0 else first_name
            page += 1
            if page > MAX_PAGE:
                return
            st = ret[-2][1][0] if len(ret) >= 2 else 500
            ed = ret[0][1][0]
            delta = ed - st
            if delta >= 0:
                continue
            self._device.swipe_noinertia(
                (st / SCREEN_W, 540 / SCREEN_H),
                (delta / SCREEN_W, 0),
            )

    def _tap_confirm_train(self) -> None:
        for btn in (CONFIRM_BLUE, CONFIRM_TRAIN, ARRANGE_CONFIRM):
            for _ in range(4):
                if self._find(btn):
                    self._tap_element(btn)

    def _tap_element(self, name: str) -> None:
        pos = self._find(name)
        if pos:
            self._tap_center(pos[0] if isinstance(pos, tuple) else pos)

    def _read_operators_on_screen(self) -> list[str]:
        self._recog.update()
        names = []
        name_x = (1288, 1869)
        name_y = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        for y in name_y:
            crop_box = tuple(zip(name_x, y))
            if self._recog.find("infra_no_operator", scope=crop_box) is None:
                if len(self._recog.img.shape) == 3:
                    gray_crop = cv2.cvtColor(
                        self._recog.img[y[0] : y[1], name_x[0] : name_x[1]],
                        cv2.COLOR_RGB2GRAY,
                    )
                else:
                    gray_crop = self._recog.img[y[0] : y[1], name_x[0] : name_x[1]]
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
