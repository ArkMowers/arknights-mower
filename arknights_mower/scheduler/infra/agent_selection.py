from __future__ import annotations

import time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Callable, Optional

import cv2
import numpy as np

from arknights_mower.scheduler.constants import (
    AGENT_SELECT_POSITIONS,
    DORM_ROOM_PREFIX,
    SCREEN_H,
    SCREEN_W,
    FacilityType,
)
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.errors import AgentSelectionError
from arknights_mower.utils.log import logger


class ASState(Enum):
    PREPROCESS = auto()
    FAST_CLEAR = auto()
    MAIN_PREPARE = auto()
    SCAN_SELECT = auto()
    SWIPE_NEXT = auto()
    FREE_ASSIGN = auto()
    FINAL_SORT = auto()
    VERIFY = auto()
    DONE = auto()
    ERROR = auto()


@dataclass
class OpSnapshot:
    mood: float
    upper_limit: float
    current_room: str
    operator_type: str = "low"
    arrange_order: list = field(default_factory=lambda: list(_DEFAULT_ARRANGE_FALLBACK))


_PROFESSION_LABELS = [
    "ALL", "PIONEER", "WARRIOR", "TANK",
    "SNIPER", "CASTER", "MEDIC", "SUPPORT", "SPECIAL",
]

_PROFESSION_LABEL_POS = [
    (1918, 135 + i * 110) for i in range(9)
]

_DORM_ARRANGE_NAMES = ["工作状态", "技能", "心情", "信赖值"]
_DORM_ARRANGE_X = [1070, 1220, 1358, 1495]

_PROD_ARRANGE_NAMES = ["工作状态", "效率", "技能", "心情", "信赖值"]
_PROD_ARRANGE_X = [935, 1072, 1215, 1360, 1495]

_ARRANGE_Y = 60

_SKIP_SWIPE_MAP = [20, 3, 5, 3, 3, 3, 3, 3, 3]

_CLOSE_FILTER_THRESHOLD = 1650

_DEFAULT_ARRANGE = ("技能", False)
_DEFAULT_ARRANGE_FALLBACK = ("技能", "false")
_MSG_CONNECTING = _MSG_CONNECTING


class AgentSelection:
    MAX_SWIPE = 50
    MAX_RETRY = 1
    POSITIONS = AGENT_SELECT_POSITIONS

    def __init__(
        self,
        device: DevicePort,
        operator_list_fn: Callable[[np.ndarray, bool], tuple],
        find_btn_fn: Callable[[np.ndarray, str], Optional[list]],
        get_color_fn: Callable[[np.ndarray, int, int], tuple[int, int, int]],
    ) -> None:
        self._device = device
        self._operator_list = operator_list_fn
        self._find_btn = find_btn_fn
        self._get_color = get_color_fn

    @classmethod
    def create(
        cls,
        device: DevicePort,
        recognizer: object = None,
    ) -> "AgentSelection":
        from arknights_mower.utils.character_recognize import operator_list

        def _find_btn(img: np.ndarray, name: str):
            if recognizer is None:
                return None
            recognizer._img = img
            recognizer._gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            recognizer._matcher = None
            return recognizer.find(name)

        def _get_color(img: np.ndarray, x: int, y: int):
            return tuple(img[y, x])

        return cls(device, operator_list, _find_btn, _get_color)

    def run(
        self,
        agents: list[str],
        room: str,
        *,
        fast_mode: bool = True,
        train_index: int = 0,
        op_snapshots: Optional[dict[str, OpSnapshot]] = None,
        free_room: bool = False,
        re_order: bool = False,
        current_room_map: Optional[list[str]] = None,
    ) -> list[str]:
        self._agents = list(agents)
        self._room = room
        self._fast_mode = fast_mode
        self._train_index = train_index
        self._op_data = op_snapshots or {}
        self._free_room = free_room
        self._re_order = re_order
        self._current_room_map = current_room_map or []

        self._state = ASState.PREPROCESS
        self._selected: list[str] = []
        self._free_num = 0
        self._right_swipe = 0
        self._first_name = ""
        self._pre_order: tuple = _DEFAULT_ARRANGE
        self._index_change = False
        self._siege = False
        self._last_special_filter = "ALL"
        self._retry_count = 0
        self._first_time = True
        self._exists: list[str] = []
        self._is_dorm = room.startswith(DORM_ROOM_PREFIX)
        self._not_production = not room.startswith("room")
        self._start_time = datetime.now()
        self._finish_time = datetime.now()

        self._max_swipe = self.MAX_SWIPE

        self._agent_profession = _load_agent_profession()
        self._all_agent_names = _load_agent_list()
        self._profession_filter_names = _load_profession_filter()

        _handlers = {
            ASState.PREPROCESS: self._step_preprocess,
            ASState.FAST_CLEAR: self._step_fast_clear,
            ASState.MAIN_PREPARE: self._step_main_prepare,
            ASState.SCAN_SELECT: self._step_scan_select,
            ASState.SWIPE_NEXT: self._step_swipe_next,
            ASState.FREE_ASSIGN: self._step_free_assign,
            ASState.FINAL_SORT: self._step_final_sort,
            ASState.VERIFY: self._step_verify,
        }

        while self._state not in (ASState.DONE, ASState.ERROR):
            handler = _handlers[self._state]
            handler()

        if self._state == ASState.ERROR:
            raise AgentSelectionError(
                f"agent selection failed for room={room}, agents={agents}"
            )

        return self._agents

    def _step_preprocess(self) -> None:
        agents = self._agents

        if "" in agents:
            self._fast_mode = False
            agents = [item for item in agents if item != ""]

        seen: set[str] = set()
        for idx, name in enumerate(agents):
            if name not in seen:
                seen.add(name)
            elif name != "Free":
                agents[idx] = "Free"

            if self._is_dorm and agents[idx] in self._op_data:
                snap = self._op_data[agents[idx]]
                if snap.mood == snap.upper_limit and not snap.current_room.startswith(DORM_ROOM_PREFIX):
                    agents[idx] = "Free"
                    logger.info("检测满心情释放休息位")
                elif agents[idx] == "Free" and not self._re_order and self._free_room:
                    if idx < len(self._current_room_map):
                        current_name = self._current_room_map[idx]
                        if current_name and current_name in self._op_data:
                            current_snap = self._op_data[current_name]
                            if current_snap.mood < current_snap.upper_limit:
                                agents[idx] = current_name

        self._agents = agents
        self._state = ASState.FAST_CLEAR

    def _step_fast_clear(self) -> None:
        if not self._fast_mode:
            self._state = ASState.MAIN_PREPARE
            return

        current = list(self._current_room_map)
        if not current:
            self._state = ASState.MAIN_PREPARE
            return

        current = sorted(current, key=lambda x: x == "")
        differences = []
        for i in range(len(current)):
            if current[i] not in self._agents:
                differences.append(i)
            else:
                self._exists.append(current[i])

        if self._room == FacilityType.TRAIN.value:
            differences = [x for x in differences if x == self._train_index]

        for pos in differences:
            if pos < len(self.POSITIONS) and current[pos] != "":
                self._device.tap(self.POSITIONS[pos][0], self.POSITIONS[pos][1])
                time.sleep(0.1)

        agent_list = [x for x in self._agents if x not in self._exists]
        logger.info(f"安排干员 ：{agent_list}")

        self._free_num = agent_list.count("Free")
        for _ in range(self._free_num):
            agent_list.remove("Free")

        self._agents = agent_list
        self._state = ASState.MAIN_PREPARE

    def _step_main_prepare(self) -> None:
        self._profession_filter_close()

        current_order, _ = self._detect_arrange_order()
        if current_order == "信赖值":
            self._switch_arrange_order("工作状态")

        self._last_special_filter = "ALL"
        self._right_swipe = 0
        self._state = ASState.SCAN_SELECT

    def _step_scan_select(self) -> None:
        agents = self._agents
        if len(agents) == 0:
            if self._free_num > 0:
                self._state = ASState.FREE_ASSIGN
            else:
                self._state = ASState.FINAL_SORT
            return

        if self._retry_count > self.MAX_RETRY:
            self._state = ASState.ERROR
            return

        if self._right_swipe > self._max_swipe:
            self._state = ASState.ERROR
            return

        found, is_siege = self._select_agents()

        if is_siege:
            self._siege = True
            if self._last_special_filter != "ALL":
                self._right_swipe = 0
            return

        if found:
            self._index_change = True
            return

        self._state = ASState.SWIPE_NEXT

    def _select_agents(self) -> tuple[bool, bool]:
        agents = self._agents

        if self._first_time:
            if self._is_dorm:
                self._switch_arrange_order("心情", ascending=True)
                self._pre_order = ("心情", True)
            if not self._fast_mode:
                self._device.tap(0.38, 0.95)
                time.sleep(0.5)
            changed, _ = self._scan_agent(
                agents, full_scan=self._last_special_filter == "ALL"
            )
            if changed:
                self._selected.extend(changed)
                if len(self._agents) == 0:
                    return True, False
                self._index_change = True

        if self._index_change or self._first_time:
            is_custom, arrange_type = self._get_order(agents[0])
            if self._is_dorm and not (
                agents[0] in self._op_data
                and self._op_data[agents[0]].current_room.startswith(FacilityType.DORMITORY.value)
            ):
                arrange_type = ("心情", True)

            if self._pre_order[0] != arrange_type[0] or self._pre_order[1] != arrange_type[1]:
                self._switch_arrange_order(arrange_type[0], ascending=arrange_type[1])
                time.sleep(0.5)
                if not self._siege:
                    self._right_swipe = self._swipe_left()
                self._pre_order = arrange_type

        self._first_time = False

        if (
            not self._siege
            and not self._is_dorm
            and agents
            and all(a in self._profession_filter_names for a in agents)
        ):
            self._siege = True
            name = agents[0]
            prof = self._agent_profession.get(name)
            if prof and self._last_special_filter != prof:
                self._profession_filter_open(prof)
                self._right_swipe = 0
            self._last_special_filter = prof or self._last_special_filter
            return False, True

        elif agents and agents[0] in self._all_agent_names:
            self._apply_profession_filter_for_agent(agents)

        changed, ret = self._scan_agent(
            agents, full_scan=self._last_special_filter == "ALL"
        )
        if changed:
            self._selected.extend(changed)
            self._index_change = True
            self._siege = False
            return True, False

        if ret and ret[0][0] == self._first_name and self._right_swipe >= 3:
            self._max_swipe = self._right_swipe
        elif ret:
            self._first_name = ret[0][0]

        self._index_change = False
        return False, False

    def _apply_profession_filter_for_agent(self, agents: list[str]) -> None:
        if not agents:
            return
        name = agents[0]
        if (self._is_dorm or self._not_production) and name != "阿米娅":
            prof = self._agent_profession.get(name)
            if prof and self._last_special_filter != prof:
                self._profession_filter_open(prof)
                self._right_swipe = 0
                if self._index_change:
                    self._switch_arrange_order("心情", ascending=True)
            self._last_special_filter = prof or self._last_special_filter
        elif (
            (self._is_dorm or self._not_production)
            and name == "阿米娅"
            and self._last_special_filter != "ALL"
        ):
            self._profession_filter_open("ALL")
            self._right_swipe = 0
            self._last_special_filter = "ALL"

        if (
            name in self._op_data
            and self._op_data[name].current_room.startswith(FacilityType.DORMITORY.value)
            and self._fast_mode
            and self._is_dorm
            and name != "阿米娅"
        ):
            try:
                idx = _PROFESSION_LABELS.index(self._last_special_filter)
            except ValueError:
                idx = 0
            skip_count = _SKIP_SWIPE_MAP[idx]
            for _ in range(skip_count):
                self._device.swipe_noinertia((0.8, 0.5), (-1900, 0), interval=0)
            self._right_swipe = skip_count
            time.sleep(1)

    def _step_swipe_next(self) -> None:
        img = self._screencap()
        ret = self._operator_list(img, self._last_special_filter == "ALL")
        if not ret or len(ret) < 2:
            self._state = ASState.ERROR
            return

        st = ret[-2][1]
        ed = ret[0][1]
        st_x, st_y = st[0], st[1]
        delta_x = ed[0] - st_x
        if delta_x >= 0:
            self._state = ASState.SCAN_SELECT
            return

        self._device.swipe_noinertia(
            (st_x / SCREEN_W, st_y / SCREEN_H), (delta_x, 0)
        )
        self._right_swipe += 1
        if self._right_swipe >= 3:
            time.sleep(0.3)
        self._state = ASState.SCAN_SELECT

    def _step_free_assign(self) -> None:
        free_num = self._free_num
        if free_num == 0:
            self._state = ASState.FINAL_SORT
            return

        total_agents = len(self._agents) + free_num
        if free_num == total_agents:
            self._device.tap(0.38, 0.95)
            time.sleep(0.5)

        if not self._first_time:
            self._right_swipe = self._swipe_left()

        if self._last_special_filter != "ALL":
            self._profession_filter_open("ALL")
            self._last_special_filter = "ALL"
            self._right_swipe = 0

        self._switch_arrange_order("心情", ascending=True)

        free_list = self._get_free_list()
        while free_num > 0:
            selected_name, ret = self._scan_agent(
                free_list,
                max_agent_count=free_num,
                full_scan=self._last_special_filter == "ALL",
            )
            self._selected.extend(selected_name)
            free_num -= len(selected_name)

            while selected_name:
                try:
                    idx = self._agents.index("Free")
                except ValueError:
                    break
                self._agents[idx] = selected_name.pop(0)

            if free_num == 0:
                break

            if ret and len(ret) > 1:
                st = ret[-2][1]
                ed = ret[0][1]
                delta_x = ed[0] - st[0]
                self._device.swipe_noinertia(
                    (st[0] / SCREEN_W, st[1] / SCREEN_H), (delta_x, 0)
                )
                self._right_swipe += 1

        self._state = ASState.FINAL_SORT

    def _step_final_sort(self) -> None:
        if len(self._agents) != 1:
            self._right_swipe = self._swipe_left()
            self._switch_arrange_order("技能")

            self._exists.extend(self._selected)
            logger.info(self._exists)

            click_order = []
            for a in self._agents:
                if a in self._exists:
                    click_order.append(self._exists.index(a))
                else:
                    self._state = ASState.ERROR
                    return

            if click_order:
                self._device.tap(0.38, 0.95)
                time.sleep(0.5)
                for p_idx in click_order:
                    if p_idx < len(self.POSITIONS):
                        self._device.tap(
                            self.POSITIONS[p_idx][0], self.POSITIONS[p_idx][1]
                        )
                        time.sleep(0.1)

        logger.debug("验证干员选择..")
        self._state = ASState.VERIFY

    def _step_verify(self) -> None:
        self._swipe_left()
        self._switch_arrange_order("技能")

        self._finish_time = datetime.now()
        if self._finish_time - self._start_time > timedelta(seconds=15) * len(
            self._agents
        ):
            logger.debug("agent selection took too long")

        if not self._verify_agent(self._agents):
            self._state = ASState.ERROR
            return

        self._state = ASState.DONE

    def _screencap(self) -> np.ndarray:
        return self._device.screencap()

    def _scan_agent(
        self,
        agent: list[str],
        error_count: int = 0,
        max_agent_count: int = -1,
        full_scan: bool = True,
    ) -> tuple[list[str], tuple]:
        try:
            img = self._screencap()

            while self._find_btn(img, "connecting"):
                logger.info(_MSG_CONNECTING)
                time.sleep(1)
                img = self._screencap()

            ret = self._operator_list(img, full_scan)

            select_name = []
            for name, scope in ret:
                if name in agent:
                    select_name.append(name)
                    center_x = (scope[0][0] + scope[1][0]) / 2 / SCREEN_W
                    center_y = (scope[0][1] + scope[1][1]) / 2 / SCREEN_H
                    self._device.tap(center_x, center_y)
                    agent.remove(name)
                    if max_agent_count != -1 and len(select_name) >= max_agent_count:
                        return select_name, ret
            return select_name, ret
        except (AgentSelectionError, SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            error_count += 1
            if error_count < 3:
                return self._scan_agent(agent, error_count, max_agent_count, False)
            logger.exception(e)
            raise

    def _verify_agent(
        self,
        agent: list[str],
        error_count: int = 0,
        full_scan: bool = True,
    ) -> bool:
        try:
            img = self._screencap()
            while self._find_btn(img, "connecting"):
                logger.info(_MSG_CONNECTING)
                time.sleep(1)
                img = self._screencap()

            ret = self._operator_list(img, full_scan)
            index = 0
            for name, _ in ret:
                if index >= len(agent):
                    return True
                if name != agent[index]:
                    return False
                index += 1
            return True
        except (AgentSelectionError, SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            error_count += 1
            if self._room != FacilityType.TRAIN.value:
                self._switch_arrange_order("技能")
            if error_count < 3:
                return self._verify_agent(agent, error_count, full_scan=False)
            logger.exception(e)
            raise

    def _detect_arrange_order(self) -> tuple[Optional[str], bool]:
        img = self._screencap()
        if self._is_dorm or self._room == FacilityType.CENTRAL.value:
            names = _DORM_ARRANGE_NAMES
            x_list = _DORM_ARRANGE_X
        else:
            names = _PROD_ARRANGE_NAMES
            x_list = _PROD_ARRANGE_X

        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (95, 100, 100), (105, 255, 255))
        y = _ARRANGE_Y
        for idx, x in enumerate(x_list):
            if np.count_nonzero(mask[y : y + 3, x : x + 5]):
                return names[idx], False
            if np.count_nonzero(mask[y + 10 : y + 13, x : x + 5]):
                return names[idx], True
        return None, False

    def _get_arrange_x(self, name: str) -> int:
        if self._is_dorm or self._room == FacilityType.CENTRAL.value:
            mapping = dict(zip(_DORM_ARRANGE_NAMES, _DORM_ARRANGE_X))
        else:
            mapping = dict(zip(_PROD_ARRANGE_NAMES, _PROD_ARRANGE_X))
        return mapping.get(name, _PROD_ARRANGE_X[0])

    def _switch_arrange_order(
        self, name: str, ascending: bool = False
    ) -> None:
        x = self._get_arrange_x(name)
        self._device.tap(x / SCREEN_W, _ARRANGE_Y / SCREEN_H)
        time.sleep(0.5)
        while True:
            n, s = self._detect_arrange_order()
            if n == name and s == ascending:
                break
            self._device.tap(x / SCREEN_W, _ARRANGE_Y / SCREEN_H)
            time.sleep(0.5)

    def _profession_filter_close(self) -> None:
        logger.info("关闭职业筛选")
        self._profession_filter_open("ALL")
        retry = 0
        while True:
            img = self._screencap()
            confirm_blue = self._find_btn(img, "confirm_blue")
            confirm_train = self._find_btn(img, "confirm_train")
            is_open_blue = (
                confirm_blue
                and confirm_blue[0][0][0] < _CLOSE_FILTER_THRESHOLD
            )
            is_open_train = (
                confirm_train
                and confirm_train[0][0][0] < _CLOSE_FILTER_THRESHOLD
            )
            if not is_open_blue and not is_open_train:
                return
            self._device.tap(1860 / SCREEN_W, 60 / SCREEN_H)
            time.sleep(0.1)
            retry += 1
            if retry > 5:
                raise AgentSelectionError("关闭职业筛选失败")

    def _profession_filter_open(self, profession: str) -> None:
        logger.info(f"打开 {profession} 筛选")
        retry = 0
        while True:
            img = self._screencap()
            confirm_blue = self._find_btn(img, "confirm_blue")
            confirm_train = self._find_btn(img, "confirm_train")
            is_open_blue = (
                confirm_blue
                and confirm_blue[0][0][0] > _CLOSE_FILTER_THRESHOLD
            )
            is_open_train = (
                confirm_train
                and confirm_train[0][0][0] > _CLOSE_FILTER_THRESHOLD
            )
            if is_open_blue or is_open_train:
                break
            self._device.tap(1860 / SCREEN_W, 60 / SCREEN_H)
            time.sleep(0.1)
            retry += 1
            if retry > 5:
                raise AgentSelectionError("打开职业筛选失败")

        all_idx = _PROFESSION_LABELS.index("ALL")
        label_x, label_y = _PROFESSION_LABEL_POS[all_idx]
        self._device.tap(label_x / SCREEN_W, label_y / SCREEN_H)
        time.sleep(0.1)

        prof_idx = _PROFESSION_LABELS.index(profession)
        prof_x, prof_y = _PROFESSION_LABEL_POS[prof_idx]
        retry = 0
        while True:
            img = self._screencap()
            r, g, b = self._get_color(img, prof_x, prof_y)
            if b >= 240:
                break
            logger.debug(f"配色为： {b}")
            self._device.tap(prof_x / SCREEN_W, prof_y / SCREEN_H)
            time.sleep(0.1)
            retry += 1
            if retry > 5:
                raise AgentSelectionError("打开职业筛选失败")

    def _swipe_left(self) -> int:
        if self._right_swipe > 3:
            if self._last_special_filter == "ALL":
                other = [l for l in _PROFESSION_LABELS if l != self._last_special_filter]
                if other:
                    self._profession_filter_open(other[0])
            else:
                self._profession_filter_open("ALL")
            self._profession_filter_open(self._last_special_filter)
        else:
            swipe_time = 2 if self._right_swipe == 3 else self._right_swipe
            for _ in range(swipe_time):
                self._device.swipe_noinertia((650 / SCREEN_W, 540 / SCREEN_H), (2500, 0))
        return 0

    def _get_order(self, name: str) -> tuple[bool, tuple]:
        if name in self._op_data:
            return True, tuple(self._op_data[name].arrange_order)
        return False, _DEFAULT_ARRANGE_FALLBACK

    def _get_free_list(self) -> list[str]:
        agents_set = set(self._agents)
        free_list = []
        if self._op_data:
            for name, snap in self._op_data.items():
                if (
                    name not in agents_set
                    and snap.operator_type != "high"
                    and snap.current_room == ""
                ):
                    free_list.append(name)

        free_list.extend(
            name
            for name in self._all_agent_names
            if name not in agents_set and name not in self._op_data
        )

        remove_set = {a for a in self._agents if a != "Current" and a != "Free"}
        logger.debug(f"去除被安排的人员{remove_set}")
        free_list = list(set(free_list) - remove_set)
        return free_list


def _load_agent_profession() -> dict[str, str]:
    from arknights_mower.data import agent_profession

    return agent_profession


def _load_agent_list() -> set[str]:
    from arknights_mower.data import agent_list

    return set(agent_list)


def _load_profession_filter() -> set[str]:
    from arknights_mower.data import agent_arrange_order

    return set(agent_arrange_order.get("职介选择开关", []))
