import math
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Optional

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg, loadimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.matcher import Matcher
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


class Map:
    def __init__(self, img: tp.GrayImage):
        src_pts = np.float32([[0, 97], [1920, 97], [-400, 1080], [2320, 1080]])
        dst_pts = np.float32([[0, 0], [1920, 0], [0, 1000], [1920, 1000]])
        self.trans_mat = cv2.getPerspectiveTransform(src_pts, dst_pts)
        self.rev_mat = np.linalg.inv(self.trans_mat)

        self.map = cv2.warpPerspective(img, self.trans_mat, (1920, 1000))
        self.matcher = Matcher(self.map)

    def map2scrn(self, point: tp.Coordinate) -> tp.Coordinate:
        x = np.array([[point[0]], [point[1]], [1]])
        y = np.dot(self.rev_mat, x)
        return (round(y[0][0] / y[2][0]), round(y[1][0] / y[2][0]))

    def find(
        self, res: str, scope: Optional[tp.Scope] = None, score: float = 0.0
    ) -> Optional[tp.Scope]:
        logger.debug(f"find: {res}")
        res = f"{__rootdir__}/resources/ra/map/{res}.png"
        res_img = loadimg(res, True)
        return self.matcher.match(res_img, scope=scope, prescore=score)


class ReclamationAlgorithm(BaseSolver):
    fast_tap_scenes = [Scene.RA_GUIDE_DIALOG]
    places = {
        "base": ((1463, 21), (1782, 338)),
        "奇遇_砾沙平原": ((402, 781), (657, 866)),
        "奇遇_崎岖窄路": ((322, 1197), (579, 1281)),
        "奇遇_风啸峡谷": ((2015, 651), (2272, 736)),
        "冲突区_丢失的订单": ((1579, 724), (1860, 808)),
        "捕猎区_聚羽之地": ((858, 194), (1114, 321)),
        "资源区_射程以内": ((9, 1044), (267, 1171)),
        "资源区_林中寻宝": ((702, 477), (960, 607)),
        "要塞_征税的选择": ((593, 993), (874, 1077)),
    }
    drag_scope = ((250, 10), (1630, 895))

    def run(
        self,
        duration: Optional[timedelta] = None,
        timeout: timedelta = timedelta(seconds=30),
    ) -> None:
        logger.info("Start: 生息演算")

        self.timeout = timeout
        self.deadline = datetime.now() + duration - timeout if duration else None

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

    def drag(self, res: str, position: tp.Coordinate = (960, 500)) -> bool:
        place = None
        pos = None
        for place in self.places:
            if pos := self.map.find(place, score=0.65):
                break
        if pos is None:
            return False
        if place.startswith("奇遇"):
            adventures = [i for i in self.places if i.startswith("奇遇")]
            scores = []
            img = cropimg(self.map.map, ((pos[0][0] + 110, pos[0][1]), pos[1]))
            img = thres2(img, 180)
            for i in adventures:
                template = loadimg(f"{__rootdir__}/resources/ra/map/{i}.png", True)
                template = cropimg(template, ((151, 36), (254, 62)))
                template = thres2(template, 180)
                result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF)
                result = cv2.minMaxLoc(result)[1]
                scores.append(result)
            place = adventures[scores.index(max(scores))]

        res_img = loadimg(f"{__rootdir__}/resources/ra/map/{res}.png", True)
        top_left = (
            position[0] - round(res_img.shape[1] / 2),
            position[1] - round(res_img.shape[0] / 2),
        )
        vp1 = tuple(a - b for a, b in zip(self.places[place][0], pos[0]))
        vp2 = tuple(a - b for a, b in zip(self.places[res][0], top_left))
        vp_offset = tuple(a - b for a, b in zip(vp1, vp2))
        total_distance = tuple(abs(a) for a in vp_offset)
        max_drag = tuple(b - a for a, b in zip(*self.drag_scope))
        steps = max(math.ceil(d / m) for d, m in zip(total_distance, max_drag))
        step_distance = tuple(round(i / steps) for i in vp_offset)
        center_point = tuple(round((a + b) / 2) for a, b in zip(*self.drag_scope))
        start_point = self.map.map2scrn(
            tuple(a - round(b / 2) for a, b in zip(center_point, step_distance))
        )
        end_point = self.map.map2scrn(
            tuple(a + round(b / 2) for a, b in zip(center_point, step_distance))
        )
        for _ in range(steps):
            self.device.swipe_ext(
                (start_point, end_point, end_point), durations=[500, 500]
            )
        self.recog.update()
        return True

    def detect_prepared(self) -> int:
        templates = [f"ra/prepared_{i}" for i in range(3)]
        scores = [
            self.template_match(i, ((510, 820), (700, 900)))[0] for i in templates
        ]
        result = scores.index(max(scores))
        logger.info(f"已准备 {result}")
        return result

    def detect_day(self) -> int:
        templates = ["ra/day_next"] + [f"ra/day_{i}" for i in range(1, 5)]
        scores = [
            self.template_match(i, ((1730, 110), (1805, 175)))[0] for i in templates
        ]
        result = scores.index(max(scores))
        logger.info(f"第{result}天" if result > 0 else "进入下一天")
        return result

    def detect_ap(self) -> int:
        ap = 0
        if self.get_color((1752, 182))[0] > 175:
            ap += 1
        if self.get_color((1774, 182))[0] > 175:
            ap += 1
        logger.info(f"决断次数：{ap}")
        return ap

    def map_skip_day(self):
        # 跳过行动，进入下一天
        if pos := self.find("ra/days"):
            self.tap(pos)
        elif pos := self.find("ra/save"):
            self.tap(pos)
        else:
            self.recog.update()

    def move_forward(self, scene):
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
                if pos := self.find(
                    "ra/battle_exit", scope=((0, 0), (200, 160)), score=0.4
                ):
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

        # 奇遇
        elif scene == Scene.RA_ADVENTURE:
            if self.find("ra/no_enough_resources"):
                logger.info("所需资源不足")
                self.tap_element("ra/map_back")
                self.recog.update()
            else:
                tpl = loadimg(f"{__rootdir__}/resources/ra/ap-1.png", True)
                tpl = thres2(tpl, 127)
                w, h = tpl.shape[::-1]
                scope = ((1640, 400), (1900, 900))
                x, y = scope[0]
                img = thres2(self.recog.gray, 127)
                img = cropimg(img, scope)
                res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
                threshold = 0.8
                loc = np.where(res >= threshold)
                scope = tuple(
                    ((a + x, b + y), (a + x + w, b + y + h)) for a, b in zip(*loc[::-1])
                )
                if scope:
                    self.tap(scope[-1])
                elif pos := self.find("ra/adventure_ok"):
                    self.tap((1740, round((pos[0][1] + pos[1][1]) / 2)))
                else:
                    self.tap((428, 411))

        # 地图页操作
        elif scene == Scene.RA_MAP:
            self.map = Map(self.recog.gray)
            if (day := self.detect_day()) == 0:
                self.tap((1760, 140))
            elif day == 4:
                score, pos = self.template_match(
                    "ra/delete_save", scope=((1675, 820), (1785, 940))
                )
                if score > 5000000:
                    self.tap(pos)
                else:
                    self.tap((1540, 1010), interval=2)
            elif day == 1:
                ap = self.detect_ap()
                self.enter_battle = ap > 0
                if self.enter_battle:
                    if ap == 2:
                        if self.drag("奇遇_风啸峡谷"):
                            self.tap_element("ra/map/奇遇_风啸峡谷")
                        else:
                            # 返回首页重新进入，使基地位于屏幕中央
                            self.tap_element("ra/map_back")
                    elif ap == 1:
                        if self.drag("捕猎区_聚羽之地"):
                            self.tap_element("ra/map/捕猎区_聚羽之地")
                        else:
                            self.tap_element("ra/map_back")
                else:
                    self.map_skip_day()
            elif day == 2:
                ap = self.detect_ap()
                self.enter_battle = ap > 0
                if self.enter_battle:
                    if ap == 2:
                        if self.drag("资源区_林中寻宝"):
                            self.tap_element("ra/map/资源区_林中寻宝")
                        else:
                            # 返回首页重新进入，使基地位于屏幕中央
                            self.tap_element("ra/map_back")
                    elif ap == 1:
                        if self.drag("奇遇_砾沙平原"):
                            self.tap_element("ra/map/奇遇_砾沙平原")
                        else:
                            self.tap_element("ra/map_back")
                else:
                    self.map_skip_day()
            elif day == 3:
                ap = self.detect_ap()
                self.enter_battle = ap > 0
                if self.enter_battle:
                    if ap == 2:
                        if self.drag("资源区_射程以内"):
                            self.tap_element("ra/map/资源区_射程以内")
                        else:
                            # 返回首页重新进入，使基地位于屏幕中央
                            self.tap_element("ra/map_back")
                    elif ap == 1:
                        if self.drag("奇遇_崎岖窄路"):
                            self.tap_element("ra/map/奇遇_崎岖窄路")
                        else:
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
        elif scene == Scene.RA_GET_ITEM:
            if pos := self.find("ra/click_to_continue"):
                self.tap(pos)
                if pos := self.find("ra/return_from_kitchen"):
                    self.tap(pos, x_rate=0.07)
            else:
                self.recog.update()
        elif scene == Scene.CONNECTING:
            self.sleep(1)
        else:
            self.recog.update()

    def back_to_index(self, scene):
        if scene in [Scene.RA_MAIN, Scene.TERMINAL_LONGTERM, Scene.TERMINAL_MAIN]:
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
            self.move_forward(scene)
        elif scene == Scene.CONNECTING:
            self.sleep(1)
        else:
            self.recog.update()

    def transition(self) -> bool:
        if (scene := self.ra_scene()) not in self.fast_tap_scenes:
            self.stop_fast_tap()

        now = datetime.now()

        if scene == Scene.UNKNOWN:
            if not self.unknown_time:
                self.unknown_time = now
            elif now - self.unknown_time > self.timeout:
                logger.warning("连续识别到未知场景")
                try:
                    super().back_to_index()
                except Exception:
                    self.device.exit()
        else:
            self.unknown_time = None

        if self.deadline and self.deadline < datetime.now():
            if scene == Scene.INDEX:
                return True
            else:
                self.back_to_index(scene)
        else:
            self.move_forward(scene)
