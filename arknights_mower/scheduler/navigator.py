from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from arknights_mower.scheduler.constants import TapPosition
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.graph import SceneGraph
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene

logger = logging.getLogger(__name__)


class Navigator:
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
        for _ in range(5):
            self._pause.wait_if_paused()
            current = self._get_scene()
            if current == target:
                return True
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
            except Exception:
                logger.exception(f"navigate action failed: {transition.action}")
                time.sleep(1)
        return False

    def _back(self) -> None:
        self._device.back()

    def _tap_pos(self, pos: TapPosition) -> None:
        self._device.tap(*pos.value)

    def _tap(self, x: int, y: int) -> None:
        self._device.tap(x / 1920, y / 1080)

    def _tap_element(self, name: str) -> None:
        if self._recognizer is None:
            return
        result = self._recognizer.find(name)
        if result is not None:
            self._tap(*result)

    def _tap_confirm(self, confirm: bool = True) -> None:
        self._tap_pos(TapPosition.CONFIRM_YES if confirm else TapPosition.CONFIRM_NO)

    def _cback(self, limit: int = 1) -> None:
        for _ in range(limit):
            scene = self._get_scene()
            self._back()
            for _ in range(20):
                self._pause.wait_if_paused()
                time.sleep(0.25)
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
        time.sleep(5)

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
                self._tap(*pos)

    def _action_agreement(self) -> None:
        if self._recognizer is not None:
            pos = self._recognizer.find("read_and_agree")
            if pos is not None:
                self._tap(*pos)
            else:
                self._tap_pos(TapPosition.AGREEMENT_LINE1)
                time.sleep(0.5)
                self._tap_pos(TapPosition.AGREEMENT_LINE2)

    def _action_index_to_infra(self) -> None:
        self._tap_element("infrastructure")

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

    def _action_login_start(self) -> None:
        self._tap_pos(TapPosition.LOGIN_START)

    def _action_confirm(self) -> None:
        self._tap_element("confirm")

    def _action_network_check_cancel(self) -> None:
        self._tap_element("confirm")
