"""导航层核心 —— 场景图驱动的界面导航。

`Navigator` 负责：从当前 scene 走到目标 scene（`navigate`）、等界面稳定
（`wait_scene_stable`）、房间定位（`enter_room`）以及点击/返回原语。

| 文件 | 职责 |
|---|---|
| `navigator.py` | 构造、`navigate`、`enter_room`、识别辅助、等待、点击原语 |
| `navigator_actions.py` | 55 个 `_action_*` 处理器（**Mixin**） |

⚠️ `navigate` 用 `getattr(self, f"_action_{transition.action}")` 做字符串分派，
因此 `_action_*` **必须绑定在 `Navigator` 实例上**（Mixin/继承）。若改成组合
（`self._actions = NavigatorActions(...)`），55 个动作会同时取到 `None` →
全部报 "no handler" → 导航全面失效。守卫用例见
`tests/unit/scheduler/navigator_split_guard_tests.py`。
"""

from __future__ import annotations

from typing import Callable, Optional

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W, TapPosition
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.graph import SceneGraph
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.navigator_actions import NavigatorActionsMixin
from arknights_mower.scheduler.scene import Scene
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger

_WAITING_SCENES = {Scene.LOADING, Scene.CONNECTING, Scene.LOGIN_LOADING, Scene.SKIP}


class Navigator(NavigatorActionsMixin):
    MAX_UNKNOWN = 6
    MAX_ERROR = 5

    def __init__(
        self,
        device: DevicePort,
        graph: SceneGraph,
        get_scene: Callable[[], Scene],
        pause_controller: PauseController,
        recognizer: Optional[object] = None,
    ) -> None:
        self._device = device
        self._graph = graph
        self._get_scene = get_scene
        self._recognizer = recognizer
        self._pause = pause_controller

    def navigate(self, target: Scene) -> bool:
        error_count = 0
        unknown_count = 0

        while (current := self._get_scene()) != target:
            self._pause.wait_if_paused()

            if current in _WAITING_SCENES:
                continue

            if current == Scene.UNKNOWN:
                unknown_count += 1
                if unknown_count <= 3:
                    continue
                elif unknown_count <= self.MAX_UNKNOWN:
                    self._back()
                else:
                    logger.warning(f"abort: unknown scene persists target={target}")
                    return False
                continue

            path = self._graph.find_path(current, target)
            if path is None:
                logger.error(f"no path from {current} to {target}")
                return False
            transition = path[0]
            handler = getattr(self, f"_action_{transition.action}", None)

            if handler is None:
                logger.error(f"no handler for {transition.action}")
                return False


            try:
                handler()
                error_count = 0
                unknown_count = 0
            except MowerExit:
                return False
            except Exception:
                logger.exception(f"navigate action failed: {transition.action}")
                error_count += 1
                if error_count > self.MAX_ERROR:
                    return False

        return True

    def enter_room(self, room: str) -> bool:
        if self._get_scene() != Scene.INFRA_MAIN:
            self.navigate(Scene.INFRA_MAIN)
            self.wait_scene_stable()

        central = self._recognizer.find("control_central") if self._recognizer else None
        if central is None:
            return False

        from arknights_mower.utils.segment import base as segment_base

        rooms_map = segment_base(self._recognizer.img, central)
        target = rooms_map.get(room)
        if target is None:
            return False

        import numpy as np

        target = np.clip(target, [0, 0], [SCREEN_W, SCREEN_H])
        min_x = min(p[0] for p in target)
        max_x = max(p[0] for p in target)
        if min_x < 0:
            dx = -min_x
            self._device.swipe(960 / SCREEN_W, 540 / SCREEN_H, (960 + dx) / SCREEN_W, 540 / SCREEN_H, duration=500)
            for i in range(len(target)):
                target[i][0] += dx
            target = np.clip(target, [0, 0], [SCREEN_W, SCREEN_H])
        elif max_x > SCREEN_W:
            dx = SCREEN_W - max_x
            self._device.swipe(960 / SCREEN_W, 540 / SCREEN_H, (960 + dx) / SCREEN_W, 540 / SCREEN_H, duration=500)
            for i in range(len(target)):
                target[i][0] += dx
            target = np.clip(target, [0, 0], [SCREEN_W, SCREEN_H])
        cx = int((target[0][0] + target[2][0]) // 2)
        cy = int((target[0][1] + target[2][1]) // 2)
        self._device.tap(cx / SCREEN_W, cy / SCREEN_H)
        self.wait_scene_stable(max_duration=3.0, min_stable=2, crop=((0,0),(SCREEN_W,162)))
        return True

    def _detect_room(self) -> str | None:
        if self._recognizer is None:
            return None
        import cv2

        from arknights_mower.utils.image import cropimg, loadres

        img = cropimg(self._recognizer.img, ((568, 18), (957, 95)))
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        color_map = {"room_1_": 25, "room_2_": 99, "room_3_": 36, "train": 178, "factory": 32}
        for room, color in color_map.items():
            mask = cv2.inRange(hsv, (color - 1, 0, 0), (color + 2, 255, 255))
            if cv2.countNonZero(mask) > 1000:
                if room in ("train", "factory"):
                    return room
                d1 = self._detect_digit(cropimg(img, ((211, 24), (232, 54))))
                d2 = self._detect_digit(cropimg(img, ((253, 24), (274, 54))))
                return f"room_{d1}_{d2}"
        white_rooms = ["central", "dormitory", "meeting", "contact"]
        scores = []
        for room in white_rooms:
            tpl = loadres(f"room/{room}")
            result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            scores.append(max_val)
        room = white_rooms[scores.index(max(scores))]
        if room == "dormitory":
            digit = self._detect_digit(cropimg(img, ((174, 24), (195, 54))))
            return f"dormitory_{digit}"
        return room

    def _detect_digit(self, img) -> int:
        import cv2

        from arknights_mower.utils.image import loadres

        scores = []
        for i in range(1, 5):
            digit = loadres(f"room/{i}")
            result = cv2.matchTemplate(img, digit, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            scores.append(max_val)
        return scores.index(max(scores)) + 1

    def wait_scene(self, targets: set) -> bool:
        self._pause.wait_if_paused()
        return self._get_scene() in targets

    def wait_scene_stable(
        self,
        max_duration: float = 5.0,
        min_stable: int = 3,
        threshold: float = 0.012,
        crop: tuple = None,
    ) -> bool:
        import time as _time

        import cv2
        import numpy as np

        t0 = _time.time()
        stable = 0
        last = None
        while _time.time() - t0 < max_duration:
            self._pause.wait_if_paused()
            self._recognizer.update()
            gray = self._recognizer.gray if self._recognizer else None
            if gray is None:
                continue
            if crop is not None:
                x1, y1, x2, y2 = crop[0][0], crop[0][1], crop[1][0], crop[1][1]
                gray = gray[y1:y2, x1:x2]
            current = cv2.resize(gray, (240, 135))
            if last is not None:
                diff = np.mean(cv2.absdiff(current, last)) / 255.0
                if diff <= threshold:
                    stable += 1
                else:
                    stable = 0
            last = current
            if stable >= min_stable:
                return True
        return False

    def _wait_room_detail(self) -> bool:  
        from arknights_mower.scheduler.scene import Scene as V2Scene
        success = False                      
        while True:
            scene = self._get_scene()
            if scene == V2Scene.INFRA_DETAILS_OPEN:
                success = True
                break
            elif scene == V2Scene.INFRA_DETAILS or scene == V2Scene.CTRLCENTER_ASSISTANT:      
                if self._recognizer and self._recognizer.find("arrange_check_in"):
                    self._tap_element("arrange_check_in")
                    success = True                                        
                elif self._recognizer and self._recognizer.find("arrange_check_in_small"):
                    self._tap_element("arrange_check_in_small")
                    success = True
                continue
            elif scene == V2Scene.INFRA_ROOM_GAP:
                return False
            else:
                break  
        self._recognizer.update()
        return success

    def _back(self) -> None:
        self._device.back()

    def _tap_pos(self, pos: TapPosition) -> None:
        self._device.tap(*pos.value)

    def _tap(self, x: int, y: int) -> None:
        self._device.tap(x / SCREEN_W, y / SCREEN_H)

    def _center(self, box) -> tuple[int, int]:
        if isinstance(box, list) and len(box) == 2 and isinstance(box[0], list):
            x1, y1 = box[0]
            x2, y2 = box[1]
            return ((x1 + x2) // 2, (y1 + y2) // 2)
        if isinstance(box, tuple) and len(box) == 2:
            if isinstance(box[0], (list, tuple)):
                x1, y1 = box[0]
                x2, y2 = box[1]
                return ((x1 + x2) // 2, (y1 + y2) // 2)
            return box
        return (0, 0)

    def _tap_element(self, name: str, wait_duration: float = 0.25) -> None:
        if self._recognizer is None:
            return
        result = self._recognizer.find(name)
        if result is None:
            return
        box = result[0] if isinstance(result, tuple) else result
        self._tap(*self._center(box))
        self.wait_scene_stable(max_duration=wait_duration, min_stable=1)

    def _tap_confirm(self, confirm: bool = True) -> None:
        self._tap_pos(TapPosition.CONFIRM_YES if confirm else TapPosition.CONFIRM_NO)

    def _cback(self, limit: int = 1) -> None:
        for _ in range(limit):
            scene = self._get_scene()
            self._back()
            for _ in range(20):
                self._pause.wait_if_paused()
                if self._get_scene() != scene:
                    return

