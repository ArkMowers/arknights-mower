from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from arknights_mower.scheduler.constants import TapPosition
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.graph import SceneGraph
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.utils.log import logger


_WAITING_SCENES = {Scene.LOADING, Scene.CONNECTING, Scene.LOGIN_LOADING, Scene.SKIP}


class Navigator:
    MAX_UNKNOWN = 6
    MAX_ERROR = 5

    def __init__(
        self,
        device: DevicePort,
        graph: SceneGraph,
        get_scene: Callable[[], Scene],
        recognizer: Optional[object] = None,
        pause_controller: Optional[PauseController] = None,
    ) -> None:
        self._device = device
        self._graph = graph
        self._get_scene = get_scene
        self._recognizer = recognizer
        self._pause = pause_controller or ThreadPauseController()

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
            except Exception:
                logger.exception(f"navigate action failed: {transition.action}")
                error_count += 1
                if error_count > self.MAX_ERROR:
                    return False

        return True

    def enter_room(self, room: str) -> bool:
        import time
        t0 = time.time()

        if self._get_scene() != Scene.INFRA_MAIN:
            self.navigate(Scene.INFRA_MAIN)
            self.wait_scene_stable()

        logger.info(f"enter_room({room}): _get_scene + navigate took {time.time()-t0:.2f}s")
        t1 = time.time()

        central = self._recognizer.find("control_central") if self._recognizer else None
        if central is None:
            logger.warning(f"enter_room({room}): control_central not found ({time.time()-t1:.2f}s)")
            return False

        logger.info(f"enter_room({room}): find control_central took {time.time()-t1:.2f}s")
        t2 = time.time()

        from arknights_mower.utils.segment import base as segment_base

        rooms_map = segment_base(self._recognizer.img, central)
        target = rooms_map.get(room)
        if target is None:
            logger.warning(f"enter_room({room}): room not in segmented map, keys={list(rooms_map.keys())} ({time.time()-t2:.2f}s)")
            return False

        logger.info(f"enter_room({room}): segment took {time.time()-t2:.2f}s")
        t3 = time.time()

        import numpy as np

        target = np.clip(target, [0, 0], [1920, 1080])
        min_x = min(p[0] for p in target)
        max_x = max(p[0] for p in target)
        if min_x < 0:
            dx = -min_x
            self._device.swipe(960 / 1920, 540 / 1080, (960 + dx) / 1920, 540 / 1080, duration=500)
            for i in range(len(target)):
                target[i][0] += dx
            target = np.clip(target, [0, 0], [1920, 1080])
        elif max_x > 1920:
            dx = 1920 - max_x
            self._device.swipe(960 / 1920, 540 / 1080, (960 + dx) / 1920, 540 / 1080, duration=500)
            for i in range(len(target)):
                target[i][0] += dx
            target = np.clip(target, [0, 0], [1920, 1080])
        cx = int((target[0][0] + target[2][0]) // 2)
        cy = int((target[0][1] + target[2][1]) // 2)
        logger.debug(f"enter_room({room}): tap at ({cx}, {cy})")
        self._device.tap(cx / 1920, cy / 1080)
        self.wait_scene_stable(max_duration=3.0, min_stable=2, crop=((0,0),(1920,162)))
        logger.info(f"enter_room({room}): TOTAL {time.time()-t0:.2f}s")   
        return True

    def _detect_room(self) -> str | None:
        if self._recognizer is None:
            return None
        import cv2
        import numpy as np
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
        import cv2
        import numpy as np
        import time as _time

        t0 = _time.time()
        debug_dir = Path("debug_ws_stable")
        debug_dir.mkdir(exist_ok=True)
        ts = str(int(t0))

        crop_name = ""
        if crop is not None:
            crop_name = f" crop{crop[0]}-{crop[1]}"
        logger.info(f"wait_scene_stable: start max_duration={max_duration} min_stable={min_stable}{crop_name}")

        stable = 0
        last = None
        i = 0
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
                    cv2.imwrite(str(debug_dir / f"gap_{ts}_i{i}_diff{diff:.4f}.png"), gray)
                logger.info(f"wait_scene_stable: i={i} diff={diff:.4f} stable={stable}/{min_stable}")
            last = current
            i += 1
            if stable >= min_stable:
                logger.info(f"wait_scene_stable: done i={i} stable={stable}")
                return True
        logger.info(f"wait_scene_stable: TIMEOUT after {_time.time()-t0:.1f}s, {i} checks")
        cv2.imwrite(str(debug_dir / f"timeout_{ts}.png"), gray if gray is not None else np.zeros((1,1)))
        return False

    def _wait_room_detail(self) -> bool:  
        from arknights_mower.scheduler.scene import Scene as V2Scene    
        success = False                      
        while True:
            scene = self._get_scene()
            if scene == V2Scene.INFRA_DETAILS_OPEN:
                success = True
                break
            elif scene == V2Scene.INFRA_DETAILS:      
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
        self._device.tap(x / 1920, y / 1080)

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

    def _action_back_to_index(self) -> None:
        self._cback(1)

    def _action_leave_infrastructure(self) -> None:
        self._tap_confirm(True)

    def _action_dont_download_voice(self) -> None:
        self._tap_confirm(False)

    def _action_login_quickly(self) -> None:
        self._tap_element("login_awake")

    def _action_login_captcha(self) -> None:
        self._tap_element("login_captcha")
        self.wait_scene_stable()

    def _action_login_bilibili(self) -> None:
        self._tap_pos(TapPosition.LOGIN_BILIBILI)

    def _action_exit_cancel(self) -> None:
        self._tap_confirm(False)

    def _action_materiel(self) -> None:
        self._tap_pos(TapPosition.MATERIEL)

    def _action_announcement(self) -> None:
        if self._recognizer is not None:
            pos = self._recognizer.check_announcement()
            if pos is not None:
                x, y = pos
                self._device.tap(x / 1920, y / 1080)
            else:
                self._tap_pos(TapPosition.CENTER)

    def _action_agreement(self) -> None:
        if self._recognizer is not None:
            pos = self._recognizer.find("read_and_agree")
            if pos is not None:
                box = pos[0] if isinstance(pos, tuple) else pos
                self._tap(*self._center(box))
            else:
                self._tap_pos(TapPosition.AGREEMENT_LINE1)
                self.wait_scene_stable()
                self._tap_pos(TapPosition.AGREEMENT_LINE2)

    def _action_index_to_infra(self) -> None:
        self._tap_pos(TapPosition.INDEX_INFRASTRUCTURE)

    def _action_index_to_friend(self) -> None:
        self._tap_element("friend")

    def _action_index_to_mission(self) -> None:
        self._tap_element("mission")

    def _action_index_to_recruit(self) -> None:
        self._tap_element("recruit")

    def _action_index_to_shop(self) -> None:
        self._tap_element("shop")

    def _action_index_to_terminal(self) -> None:
        self._tap_element("terminal")

    def _action_index_to_depot(self) -> None:
        self._tap_element("warehouse")

    def _action_index_to_mail(self) -> None:
        self._tap_element("mail")

    def _action_index_to_headhunting(self) -> None:
        self._tap_element("headhunting")

    def _action_index_nav(self) -> None:
        self._tap_element("nav_button")

    def _action_nav_mission(self) -> None:
        self._tap_element("mission")

    def _action_nav_index(self) -> None:
        self._tap_element("index")

    def _action_nav_terminal(self) -> None:
        self._tap_element("terminal")

    def _action_nav_recruit(self) -> None:
        self._tap_element("recruit")

    def _action_nav_shop(self) -> None:
        self._tap_element("shop")

    def _action_nav_headhunting(self) -> None:
        self._tap_element("headhunting")

    def _action_nav_friend(self) -> None:
        self._tap_element("friend")

    def _action_mission_to_weekly(self) -> None:
        self._tap_element("mission_weekly")

    def _action_mission_trainee_to_daily(self) -> None:
        self._tap_element("mission_daily")

    def _action_shop_to_credit(self) -> None:
        self._tap_element("shop_credit_2")

    def _action_shop_confirm(self) -> None:
        self._back()

    def _action_friend_list(self) -> None:
        self._tap_pos(TapPosition.FRIEND_LIST)

    def _action_business_card(self) -> None:
        self._tap_pos(TapPosition.BUSINESS_CARD)

    def _action_friend_visiting_back(self) -> None:
        self._back()

    def _action_back_to_friend_confirm(self) -> None:
        self._tap_confirm(True)

    def _action_terminal_to_main_theme(self) -> None:
        self._tap_element("main_theme")

    def _action_operation_back(self) -> None:
        self._back()

    def _action_operation_give_up(self) -> None:
        self._tap_confirm(True)

    def _action_operation_finish(self) -> None:
        self._tap_pos(TapPosition.OPERATION_FINISH)

    def _action_upgrade(self) -> None:
        self._tap_pos(TapPosition.CENTER)

    def _action_todo_complete(self) -> None:
        self._tap_pos(TapPosition.TODO_COMPLETE)

    def _action_infra_back(self) -> None:
        self._back()
        self.wait_scene_stable()

    def _action_infra_arrange_confirm(self) -> None:
        self._tap_pos(TapPosition.INFRA_ARRANGE_CONFIRM)

    def _action_riic_back(self) -> None:
        self._tap_pos(TapPosition.RIIC_BACK)

    def _action_riic(self) -> None:
        self._tap_element("control_central_assistants")

    def _action_control_central(self) -> None:
        self._tap_element("control_central")

    def _action_recruit_result(self) -> None:
        self._tap_pos(TapPosition.CENTER)

    def _action_refresh_cancel(self) -> None:
        self._tap_confirm(False)

    def _action_recruit_back(self) -> None:
        self._back()

    def _action_skip(self) -> None:
        self._tap_element("skip")

    def _action_get_scene(self) -> None:
        pass

    def _action_login_main_noentry(self) -> None:
        self._device.tap(0.5, 0.5)

    def _action_login_start(self) -> None:
        self._tap_pos(TapPosition.LOGIN_START)

    def _action_confirm(self) -> None:
        self._tap_element("confirm")

    def _action_network_check_cancel(self) -> None:
        self._tap_element("confirm")
