from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Optional

from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


class ReclamationAlgorithm(BaseSolver):
    fast_tap_scenes = [Scene.RA_GUIDE_DIALOG]

    def run(self, duration: Optional[timedelta] = None) -> None:
        logger.info("Start: 生息演算")

        self.deadline = datetime.now() + duration if duration else None

        self.enter_battle = False  # 只在第一天决断次数为2时进入战斗，多进不加分
        self.battle_wait = 0  # 进入战斗后等待剧情出现
        self.thread = None
        self.event = Event()
        self.unknown_time = None
        super().run()

    def tap_loop(self, pos):
        while not self.event.is_set():
            self.device.tap(pos)

    def fast_tap(self, pos):
        self.event.clear()
        if not self.thread:
            self.thread = Thread(target=self.tap_loop, args=(pos,))
            self.thread.start()
            logger.debug(f"开始快速点击{pos}")
        self.recog.update()

    def stop_fast_tap(self):
        self.event.set()
        if self.thread:
            self.thread.join()
            self.thread = None
        logger.debug("快速点击已停止")

    def detect_prepared(self) -> int:
        templates = [f"ra/prepared_{i}" for i in range(3)]
        scores = [
            self.template_match(i, ((510, 820), (700, 900)))[0] for i in templates
        ]
        result = scores.index(max(scores))
        logger.info(f"已准备 {result}")
        return result

    def map_skip_day(self):
        # 跳过行动，进入下一天
        if pos := self.find("ra/days"):
            self.tap(pos)
        else:
            self.tap_element("ra/save")

    def move_forward(self, scene):
        if scene != Scene.UNKNOWN:
            self.unknown_time = None

        # 从首页进入生息演算主页
        if scene == Scene.INDEX:
            self.tap_themed_element("index_terminal")
        elif scene == Scene.TERMINAL_MAIN:
            self.tap_element("terminal_button_longterm")
        elif scene == Scene.TERMINAL_LONGTERM:
            self.tap_element("terminal_longterm_reclamation_algorithm")

        # 从生息演算主页进入生息演算
        elif scene == Scene.RA_MAIN:
            # 等动画
            if pos := self.find("ra/start_action"):
                self.tap(pos, interval=3)
            else:
                self.tap_element("ra/continue_button", interval=3)

        # 剧情
        elif scene == Scene.RA_GUIDE_ENTRANCE:
            self.tap_element("ra/guide_entrance")
        elif scene == Scene.RA_GUIDE_DIALOG:
            self.battle_wait = 0
            self.fast_tap((1631, 675))
        elif scene == Scene.RA_GUIDE_BATTLE_ENTRANCE:
            self.battle_wait = 3
            self.tap_element("ra/start_action")

        # 进入与退出战斗
        elif scene == Scene.RA_BATTLE_ENTRANCE:
            if self.enter_battle:
                self.tap_element("ra/start_action")
            else:
                self.tap_element("ra/map_back")
        elif scene == Scene.RA_BATTLE:
            if self.battle_wait > 0:
                self.battle_wait -= 1
                self.recog.update()
            else:
                if pos := self.find("ra/battle_exit"):
                    self.tap(pos)
                else:
                    self.recog.update()
        elif scene == Scene.RA_BATTLE_EXIT_CONFIRM:
            self.tap_element("ra/battle_exit_confirm")
        elif scene == Scene.RA_BATTLE_COMPLETE:
            self.tap_element("ra/battle_complete")

        # 结算界面
        elif scene == Scene.RA_DAY_COMPLETE:
            if pos := self.find("ra/period_complete_start_new_day"):
                self.tap(pos)
            else:
                self.tap((960, 900))
        elif scene == Scene.RA_PERIOD_COMPLETE:
            self.tap_element("ra/period_complete")

        # 存档操作
        elif scene == Scene.RA_DELETE_SAVE_DIALOG:
            self.tap_element("ra/delete_save_confirm_dialog_ok_button")

        # 地图页操作
        elif scene == Scene.RA_MAP:
            if pos := self.find("ra/day_4"):
                if pos := self.find("ra/delete_save"):
                    self.tap(pos)
                else:
                    self.tap((1540, 1010))
            elif pos := self.find("ra/next_day_button", scope=((1610, 0), (1900, 260))):
                self.tap(pos)
            elif (
                self.template_match("ra/day_1", scope=((1730, 110), (1805, 175)))[0]
                > 6000000
            ):
                # 判断决断次数
                ap_1 = self.get_color((1752, 182))
                ap_2 = self.get_color((1774, 182))
                self.enter_battle = ap_1[0] > 175 and ap_2[0] > 175
                if self.enter_battle:
                    if pos := self.find("ra/battle_wood_entrance_1"):
                        self.tap(pos)
                    elif pos := self.find("ra/battle_wood_entrance_2"):
                        self.tap(pos)
                    else:
                        # 返回首页重新进入，使基地位于屏幕中央
                        self.tap_element("ra/map_back")
                else:
                    self.map_skip_day()
            else:
                self.map_skip_day()
        elif scene == Scene.RA_DAY_DETAIL:
            self.tap_element("ra/waste_time_button")
        elif scene == Scene.RA_WASTE_TIME_DIALOG:
            self.tap_element("ra/waste_time_dialog_confirm_button")

        # 作战编队
        elif scene == Scene.RA_SQUAD_EDIT:
            if self.enter_battle:
                if pos := self.find("ra/out_of_drink", score=0.7):
                    self.tap(pos)
                else:
                    self.tap_element("ra/squad_edit_start_button")
            else:
                self.tap_element("ra/squad_back")
        elif scene == Scene.RA_SQUAD_EDIT_DIALOG:
            self.tap_element("ra/squad_edit_confirm_dialog_ok_button")

        # 烹饪台
        elif scene == Scene.RA_KITCHEN:
            # 速刷不需要合成饮料
            self.tap_element("ra/return_from_kitchen", x_rate=0.07)
        elif scene == Scene.RA_KITCHEN_DIALOG:
            if pos := self.find("ra/click_to_continue"):
                self.tap(pos)
                self.tap_element("ra/return_from_kitchen", x_rate=0.07)
            else:
                self.recog.update()
        elif scene == Scene.CONNECTING:
            self.sleep(1)
        else:
            now = datetime.now()
            if not self.unknown_time:
                self.unknown_time = now
            elif now - self.unknown_time > timedelta(seconds=10):
                super().back_to_index()
            else:
                self.recog.update()

    def back_to_index(self, scene):
        if scene in [Scene.RA_MAIN, Scene.TERMINAL_LONGTERM]:
            self.tap_element("nav_button", x_rate=0.21)
        elif scene in [Scene.RA_MAP, Scene.RA_DAY_DETAIL, Scene.RA_BATTLE_ENTRANCE]:
            self.tap_element("ra/map_back")
        elif scene == Scene.RA_SQUAD_EDIT:
            self.tap_element("ra/squad_back")
        elif scene == Scene.RA_KITCHEN:
            self.tap_element("ra/return_from_kitchen", x_rate=0.07)
        elif scene in [Scene.RA_SQUAD_EDIT_DIALOG, Scene.RA_WASTE_TIME_DIALOG]:
            self.tap_element("ra/dialog_cancel")
        elif 900 < scene < 1000:
            self.move_forward()
        elif scene == Scene.CONNECTING:
            self.sleep(1)
        else:
            super().back_to_index()

    def transition(self) -> bool:
        if (scene := self.ra_scene()) not in self.fast_tap_scenes:
            self.stop_fast_tap()

        if self.deadline and self.deadline < datetime.now():
            if scene == Scene.INDEX:
                return True
            else:
                self.back_to_index(scene)
        else:
            self.move_forward(scene)
