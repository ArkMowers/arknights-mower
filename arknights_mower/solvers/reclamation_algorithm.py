from threading import Event, Thread

from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


class ReclamationAlgorithm(BaseSolver):
    def run(self) -> None:
        logger.info("Start: 生息演算")
        self.enter_battle = True  # 没有饮料时不要进入战斗
        self.battle_not_exit = 3  # 第一次战斗不要点左上角按钮，等剧情
        self.thread = None
        self.event = Event()
        self.last_scene = Scene.UNKNOWN
        super().run()

    def tap_loop(self, pos):
        while not self.event.is_set():
            self.device.tap(pos)

    def fast_tap(self, pos):
        self.event.clear()
        if not self.thread:
            self.thread = Thread(target=self.tap_loop, args=(pos,))
            self.thread.start()
        self.recog.update()

    def detect_prepared(self) -> int:
        templates = [f"ra/prepared_{i}" for i in range(3)]
        scores = [self.template_match(i, ((510, 820), (700, 900)))[0] for i in templates]
        result = scores.index(max(scores))
        logger.info(f"已准备 {result}")
        return result

    def transition(self) -> bool:
        scene = self.ra_scene()
        fast_tap_scenes = [Scene.RA_GUIDE_DIALOG, Scene.RA_GUIDE_NOTE_DIALOG]
        if self.last_scene in fast_tap_scenes and self.scene not in fast_tap_scenes:
            self.event.set()
            if self.thread:
                self.thread.join()
                self.thread = None

        # 从首页进入生息演算主页
        if scene == Scene.INDEX:
            self.tap_themed_element("index_terminal")
        elif scene == Scene.TERMINAL_MAIN:
            self.tap_element("terminal_button_longterm")
        elif scene == Scene.TERMINAL_LONGTERM:
            self.tap_element("terminal_longterm_reclamation_algorithm")

        # 从生息演算主页进入生息演算
        elif scene == Scene.RA_MAIN:
            self.enter_battle = True
            self.battle_not_exit = 3
            # 等动画
            if pos := self.find("ra/start_action"):
                self.tap(pos, interval=3)
            else:
                self.tap_element("ra/continue_button", interval=3)

        # 剧情
        elif scene == Scene.RA_GUIDE_ENTRANCE:
            self.tap_element("ra/guide_entrance")
        elif scene == Scene.RA_GUIDE_DIALOG:
            if self.battle_not_exit > 0:
                self.battle_not_exit = 0
            self.fast_tap((1631, 675))
        elif scene == Scene.RA_GUIDE_NOTE_ENTRANCE:
            self.tap_element("ra/guide_note_entrance")
        elif scene == Scene.RA_GUIDE_NOTE_DIALOG:
            self.fast_tap((1743, 620))

        # 进入与退出战斗
        elif scene == Scene.RA_BATTLE_ENTRANCE:
            # 判断决断次数是否足够
            if self.find("ra/action_points"):
                ap_1 = self.get_color((1852, 80))
                ap_2 = self.get_color((1875, 80))
                if ap_1[0] < 175 and ap_2[0] < 175:
                    self.enter_battle = False
            if self.enter_battle:
                self.tap_element("ra/start_action")
            else:
                self.tap_element("ra/map_back")
        elif scene == Scene.RA_BATTLE:
            if self.battle_not_exit > 0:
                self.battle_not_exit -= 1
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
            self.enter_battle = True
        elif scene == Scene.RA_PERIOD_COMPLETE:
            self.tap_element("ra/period_complete")

        # 存档操作
        elif scene in [Scene.RA_DELETE_SAVE_DIALOG, Scene.RA_DELETE_SAVE_DOUBLE_DIALOG]:
            self.tap_element("ra/delete_save_confirm_dialog_ok_button")

        # 地图页操作
        elif scene == Scene.RA_MAP:
            if pos := self.find("ra/day_4"):
                self.tap((1540, 1010))
                while (pos := self.find("ra/delete_save")) is None:
                    self.recog.update()
                self.tap(pos)
            elif pos := self.find("ra/next_day_button"):
                self.tap(pos)
            elif self.enter_battle:
                if pos := self.find("ra/battle_wood_entrance_1"):
                    self.tap(pos)
                elif pos := self.find("ra/battle_wood_entrance_2"):
                    self.tap(pos)
                else:
                    # 返回首页重新进入，使基地位于屏幕中央
                    self.tap_element("ra/map_back")
            else:
                # 跳过行动，进入下一天
                if pos := self.find("ra/days"):
                    self.tap(pos)
                else:
                    self.tap_element("ra/save")
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
            if self.enter_battle:
                self.tap_element("ra/auto+1")
                if self.detect_prepared() == 1:
                    self.tap_element("ra/auto+1")
                    if self.detect_prepared() == 2:
                        self.tap_element("ra/cook_button")
                    else:
                        self.enter_battle = False
                        self.recog.update()
                else:
                    self.enter_battle = False
                    self.recog.update()
            else:
                self.tap_element("ra/return_from_kitchen", x_rate=0.07)
        elif scene == Scene.RA_KITCHEN_DIALOG:
            while not (pos := self.find("ra/click_to_continue")):
                self.recog.update()
            self.tap(pos)
            self.tap_element("ra/return_from_kitchen", x_rate=0.07)
        elif scene == Scene.CONNECTING:
            self.sleep(1)
        else:
            self.recog.update()

        self.last_scene = scene
