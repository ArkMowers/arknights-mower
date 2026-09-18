"""`Navigator` 的 55 个 `_action_*` 处理器（Mixin）。

每个方法对应 `graph.py` 里一条 `SceneTransition.action`，由
`Navigator.navigate` 用 `getattr(self, f"_action_{action}")` 取出后调用。

⚠️ 这些方法**必须**混入 `Navigator` 实例（`class Navigator(NavigatorActionsMixin)`）。
不要改成组合对象 —— `getattr(self, ...)` 会全部取不到，55 个动作同时失效。
"""

from __future__ import annotations

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W, TapPosition


class NavigatorActionsMixin:
    """55 个场景转换动作。

    宿主类须提供 `_device` / `_recognizer` / `_get_scene` / `_pause`，以及
    `_back` / `_cback` / `_tap` / `_tap_pos` / `_tap_element` / `_tap_confirm` /
    `_center` / `wait_scene_stable`（均由 `Navigator` 提供）。
    """

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
                self._device.tap(x / SCREEN_W, y / SCREEN_H)
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
