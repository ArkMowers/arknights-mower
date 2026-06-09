from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Callable, Optional

import cv2
import numpy as np

from arknights_mower.scheduler.constants import (
    AGENT_SELECT_POSITIONS,
    ARRANGE_Y,
    DEFAULT_FILTER,
    DEFAULT_SORT,
    DORM_ARRANGE_NAMES,
    DORM_ARRANGE_X,
    DORM_SORT,
    FILTER_CLOSE_THRESHOLD,
    MAX_PAGE,
    MAX_RETRY,
    PROD_ARRANGE_NAMES,
    PROD_ARRANGE_X,
    PROFESSION_LABELS,
    PROFESSION_LABEL_POS,
    SCREEN_H,
    SCREEN_W,
    SPECIAL_AGENT_ALL_FILTER,
)
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.executors.base import Step, StepRestart, StepRetry
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.utils.log import logger

_POSITIONS = AGENT_SELECT_POSITIONS


class AgentSwapService:
    def __init__(
        self,
        device: DevicePort,
        recognizer: object,
        get_scene: Callable[[], int],
        pause: Optional[PauseController] = None,
    ) -> None:
        self._device = device
        self._recog = recognizer
        self._get_scene = get_scene
        self._pause = pause or ThreadPauseController()

        from arknights_mower.data import agent_profession, agent_list
        from arknights_mower.utils.character_recognize import operator_list as _op_list

        self._agent_profession = agent_profession
        self._agent_list = set(agent_list)
        self._operator_list_fn = _op_list

        from arknights_mower.data import agent_arrange_order
        self._profession_filter_names = set(agent_arrange_order.get("职介选择开关", []))

    def run(
        self,
        room: str,
        agents: list[str],
        *,
        train_index: int = 0,
        current_operators: Optional[list[str]] = None,
    ) -> bool:
        logger.info(f"AgentSwap: {room} target={agents}")
        if room == "train":
            return self._run_train(agents, train_index)

        self._room = room
        self._is_dorm = room.startswith("dorm")
        self._is_production = room.startswith("room")

        agents = deepcopy(agents)
        seen = set()
        for i, n in enumerate(agents):
            if n in seen and n != "Free":
                agents[i] = "Free"
            seen.add(n)
        logger.info(f"AgentSwap: after dedup {agents}")
        self._agents = agents

        self._to_uncheck = []
        if current_operators:
            for i, cur in enumerate(current_operators):
                if cur and cur not in agents:
                    self._to_uncheck.append(i)
            logger.info(f"AgentSwap: current room={current_operators}, uncheck slots={self._to_uncheck}")

        self._pending = [a for a in agents if a != "Free"]
        self._free_count = agents.count("Free")
        self._last_filter = "ALL"
        self._page_count = 0
        self._last_names: Optional[list[str]] = None
        self._cache: list = []

        steps = []
        if self._to_uncheck:
            steps.append(Step("uncheck", self._scene_check, self._do_uncheck))
        steps += [
            Step("prepare", self._scene_check, self._do_prepare),
            Step("scan",    self._scene_check, self._do_scan),
            Step("select",  self._scene_check, self._do_select),
        ]

        return self._run_steps(steps)

    def _scene_check(self, scene: int) -> bool:
        return scene in (Scene.RIIC_OPERATOR_SELECT, Scene.INFRA_ARRANGE_ORDER)

    def _run_steps(self, steps: list[Step]) -> bool:
        initial = list(steps)
        queue = deque(initial)
        while queue:
            self._pause.wait_if_paused()
            scene = self._get_scene()
            if scene not in (Scene.RIIC_OPERATOR_SELECT, Scene.INFRA_ARRANGE_ORDER, Scene.LOADING, Scene.CONNECTING):
                logger.warning(f"AgentSwap: unexpected scene {scene}, abort")
                return False
            if scene in (Scene.LOADING, Scene.CONNECTING):
                continue
            step = queue[0]
            if step.enter(scene):
                try:
                    extra = step.act() if step.act else None
                    queue.popleft()
                    if extra is not None:
                        queue = deque(extra) + queue
                except StepRetry:
                    continue
                except StepRestart:
                    queue = deque(initial)
                except Exception:
                    logger.exception(f"AgentSwap step {step.name}: unhandled error")
                    return False
        return True

    def _do_uncheck(self) -> list[Step] | None:
        while self._to_uncheck:
            idx = self._to_uncheck.pop(0)
            logger.info(f"AgentSwap: uncheck slot {idx}")
            self._tap_slot(idx)
        logger.info("AgentSwap: uncheck done")
        return None

    def _do_prepare(self) -> list[Step] | None:
        target = self._pending[0] if self._pending else None
        if not target and self._free_count == 0:
            logger.info("AgentSwap: nothing to do, done")
            return []
        if not target and self._free_count > 0:
            logger.info("AgentSwap: switching to free mode")
            return [
                Step("free_prepare", self._scene_check, self._do_free_prepare),
                Step("free_scan",    self._scene_check, self._do_free_scan),
                Step("free_select",  self._scene_check, self._do_free_select),
            ]

        need_sort, need_asc = self._get_target_sort(target, self._is_dorm)
        cur_sort, cur_asc = self._detect_arrange(self._room)
        if cur_sort != need_sort or cur_asc != need_asc:
            logger.info(f"AgentSwap: switch sort {cur_sort} -> {need_sort} asc={need_asc}")
            self._tap_sort(need_sort, need_asc, self._room)
            raise StepRetry
        need_filter = self._get_target_filter(target, self._is_dorm, self._is_production)
        if need_filter is not None and need_filter != self._last_filter:
            logger.info(f"AgentSwap: switch filter {self._last_filter} -> {need_filter}")
            self._open_filter(need_filter)
            self._last_filter = need_filter
            self._page_count = 0
            raise StepRetry
        logger.info(f"AgentSwap: ready for target={target}")
        return None

    def _do_scan(self) -> list[Step] | None:
        self._recog.update()
        self._cache = self._operator_list_fn(self._recog.img, full_scan=(self._last_filter == "ALL"))
        names = [r[0] if isinstance(r, tuple) else r for r in self._cache]
        logger.info(f"AgentSwap: scan page={self._page_count} filter={self._last_filter} names={names}")
        if not self._cache:
            logger.info("AgentSwap: scan returned empty, retry")
            raise StepRetry
        return None

    def _do_select(self) -> list[Step] | None:
        target = self._pending[0] if self._pending else None
        found = self._find_in_cache(self._cache, self._pending)
        if found:
            logger.info(f"AgentSwap: tap {found[0]} at {found[1]}")
            self._tap_center(found[1])
            self._pending.remove(found[0])
            self._cache = [c for c in self._cache if c[0] != found[0]]
            if found[0] == target:
                logger.info(f"AgentSwap: target {target} found, resetting")
                self._switch_filter_other(self._last_filter)
                self._last_filter = self._detect_filter()
                self._page_count = 0
                self._last_names = None

            if self._pending or self._free_count > 0:
                return [
                    Step("prepare", self._scene_check, self._do_prepare),
                    Step("scan",    self._scene_check, self._do_scan),
                    Step("select",  self._scene_check, self._do_select),
                ]
            logger.info(f"AgentSwap: {self._room} done")
            return []

        cur_names = [c[0] for c in self._cache]
        if cur_names == self._last_names:
            logger.error(f"AgentSwap: reached end of list, target={target} not found")
            return []
        self._last_names = cur_names

        if self._page_count < MAX_PAGE:
            logger.info(f"AgentSwap: swipe page={self._page_count}")
            self._swipe_next()
            self._page_count += 1
            return [
                Step("scan",   self._scene_check, self._do_scan),
                Step("select", self._scene_check, self._do_select),
            ]

        logger.error("AgentSwap: max page reached")
        return []

    def _do_free_prepare(self) -> list[Step] | None:
        cur_sort, _ = self._detect_arrange(self._room)
        if cur_sort != "心情":
            logger.info(f"AgentSwap: free switch sort {cur_sort} -> 心情 asc")
            self._tap_sort("心情", True, self._room)
            raise StepRetry
        cur_filter = self._detect_filter()
        if cur_filter != "ALL":
            logger.info(f"AgentSwap: free switch filter {cur_filter} -> ALL")
            self._open_filter("ALL")
            self._last_filter = "ALL"
            raise StepRetry
        logger.info("AgentSwap: free ready")
        return None

    def _do_free_scan(self) -> list[Step] | None:
        self._recog.update()
        self._cache = self._operator_list_fn(self._recog.img, full_scan=True)
        if not self._cache:
            raise StepRetry
        return None

    def _do_free_select(self) -> list[Step] | None:
        found = self._find_free_in_cache(self._cache, self._free_count)
        if found:
            logger.info(f"AgentSwap: free tap {found[0]}")
            self._tap_center(found[1])
            self._free_count -= 1
            self._cache = [c for c in self._cache if c[0] != found[0]]
            if self._free_count > 0:
                return [
                    Step("free_scan",   self._scene_check, self._do_free_scan),
                    Step("free_select", self._scene_check, self._do_free_select),
                ]
            logger.info(f"AgentSwap: free done, {self._room} done")
            return []

        cur_names = [c[0] for c in self._cache]
        if cur_names == self._last_names:
            logger.error("AgentSwap: free end of list")
            return []
        self._last_names = cur_names

        logger.info(f"AgentSwap: free swipe page={self._page_count}")
        self._swipe_next()
        return [
            Step("free_scan",   self._scene_check, self._do_free_scan),
            Step("free_select", self._scene_check, self._do_free_select),
        ]

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
                    logger.info(f"AgentSwap train: select idx={idx} target={target_name}")
                    if idx == 0:
                        self._select_one_agent([target_name], "train")
                    else:
                        self._select_train_ope(target_name)
                    self._tap_confirm_train()
                    select_targets.pop(0)
                    if select_targets:
                        logger.info(f"AgentSwap train: {len(select_targets)} more to go")
                        continue
                    tasks[0] = "scan"

            elif scene == Scene.UNKNOWN:
                continue
            else:
                return False

        return True

    # ─── helpers ───

    def _tap_slot(self, idx: int) -> None:
        self._device.tap(_POSITIONS[idx][0], _POSITIONS[idx][1])

    def _tap_center(self, box) -> None:
        if isinstance(box, (list, tuple)) and len(box) == 2:
            if isinstance(box[0], (list, tuple)):
                x1, y1 = box[0]
                x2, y2 = box[1]
                cx = (x1 + x2) / 2 / SCREEN_W
                cy = (y1 + y2) / 2 / SCREEN_H
                self._device.tap(cx, cy)
            else:
                self._device.tap(box[0] / SCREEN_W, box[1] / SCREEN_H)

    def _back(self) -> None:
        self._device.back()

    def _screencap(self) -> np.ndarray:
        return self._device.screencap()

    def _detect_arrange(self, room: str) -> tuple[Optional[str], bool]:
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
            if np.count_nonzero(mask[y: y + 3, x: x + 5]):
                return names[idx], False
            if np.count_nonzero(mask[y + 10: y + 13, x: x + 5]):
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
        found_blue = self._find("confirm_blue")
        found_train = self._find("confirm_train")
        panel_open = (
            found_blue and found_blue[0][0] > FILTER_CLOSE_THRESHOLD
        ) or (
            found_train and found_train[0][0] > FILTER_CLOSE_THRESHOLD
        )
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
                confirm_blue = self._find("confirm_blue")
                confirm_train = self._find("confirm_train")
                is_open = (
                    confirm_blue and confirm_blue[0][0] < FILTER_CLOSE_THRESHOLD
                ) or (
                    confirm_train and confirm_train[0][0] < FILTER_CLOSE_THRESHOLD
                )
                if not is_open:
                    return
                self._device.tap(1860 / SCREEN_W, 60 / SCREEN_H)
            return

        for _ in range(MAX_RETRY):
            self._recog.update()
            confirm_blue = self._find("confirm_blue")
            confirm_train = self._find("confirm_train")
            is_open = (
                confirm_blue and confirm_blue[0][0] > FILTER_CLOSE_THRESHOLD
            ) or (
                confirm_train and confirm_train[0][0] > FILTER_CLOSE_THRESHOLD
            )
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
        other = next((l for l in PROFESSION_LABELS if l != current and l != "ALL"), "ALL")
        self._open_filter(other)
        return other

    def _swipe_next(self) -> None:
        img = self._screencap()
        ret = self._operator_list_fn(img, full_scan=False)
        if ret and len(ret) >= 2:
            st = ret[-2][1]
            ed = ret[0][1]
            st_x = st[0][0]
            st_y = st[0][1]
            ed_x = ed[0][0]
            delta = ed_x - st_x
            if delta < 0:
                self._device.swipe_noinertia(
                    (st_x / SCREEN_W, st_y / SCREEN_H),
                    (delta / SCREEN_W, 0),
                )
            else:
                self._device.swipe(
                    960 / SCREEN_W, 540 / SCREEN_H,
                    100 / SCREEN_W, 540 / SCREEN_H,
                    duration=300,
                )
        else:
            self._device.swipe(
                960 / SCREEN_W, 540 / SCREEN_H,
                100 / SCREEN_W, 540 / SCREEN_H,
                duration=300,
            )

    def _find(self, name: str):
        if self._recog is None:
            return None
        return self._recog.find(name)

    def _find_in_cache(self, cache: list, pending: list[str]) -> Optional[tuple]:
        for name, box in cache:
            if name in pending:
                return (name, box)
        return None

    def _find_free_in_cache(self, cache: list, count: int) -> Optional[tuple]:
        for name, box in cache:
            if name not in self._agent_list:
                continue
            return (name, box)
        return None

    def _get_target_sort(self, name: str, is_dorm: bool) -> tuple[str, bool]:
        if is_dorm:
            return DORM_SORT
        if name in self._agent_list:
            from arknights_mower.data import agent_arrange_order
            order = agent_arrange_order.get(name, [DEFAULT_SORT[0], str(DEFAULT_SORT[1]).lower()])
            if isinstance(order, list) and len(order) >= 2:
                asc = order[1] == "true"
                return (order[0], asc)
        return DEFAULT_SORT

    def _get_target_filter(self, name: str, is_dorm: bool, is_production: bool) -> Optional[str]:
        if is_dorm or not is_production:
            if name == SPECIAL_AGENT_ALL_FILTER:
                return DEFAULT_FILTER
            return self._agent_profession.get(name, DEFAULT_FILTER)
        if name in self._profession_filter_names:
            return self._agent_profession.get(name, DEFAULT_FILTER)
        return None

    def _select_one_agent(self, agents: list[str], room: str) -> None:
        self._recog.update()
        ret = self._operator_list_fn(self._recog.img, full_scan=True)
        for name, box in ret:
            if name in agents:
                self._tap_center(box)
                return

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
        for btn in ("confirm_blue", "confirm_train", "arrange_confirm"):
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
                gray_crop = cv2.cvtColor(
                    self._recog.img[y[0]:y[1], name_x[0]:name_x[1]],
                    cv2.COLOR_RGB2GRAY,
                ) if len(self._recog.img.shape) == 3 else self._recog.img[y[0]:y[1], name_x[0]:name_x[1]]
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
