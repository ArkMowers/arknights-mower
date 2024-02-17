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
        "base": [[1623, 588], [1943, 906]],
        "奇遇_砾沙平原": [[563, 1348], [819, 1433]],
        "奇遇_崎岖窄路": [[485, 1764], [740, 1848]],
        "奇遇_风啸峡谷": [[2177, 1218], [2434, 1303]],
        "冲突区_丢失的订单": [[1741, 1291], [2022, 1375]],
        "捕猎区_聚羽之地": [[1020, 761], [1276, 888]],
        "资源区_射程以内": [[171, 1611], [429, 1738]],
        "资源区_林中寻宝": [[864, 1044], [1122, 1174]],
        "要塞_征税的选择": [[755, 1560], [1036, 1644]],
        "后舍_众人会聚之地": [[1992, 521], [2334, 643]],
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

        self.battle_wait = 0  # 进入战斗后等待剧情出现

        self.thread = None
        self.event = Event()
        self.unknown_time = None

        self.task_queue = None
        self.in_adventure = False

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

    def detect_drink(self) -> int:
        templates = [f"ra/drink_{i}" for i in range(0, 6, 2)]
        scores = [
            self.template_match(i, ((1448, 1004), (1465, 1028)))[0] for i in templates
        ]
        result = scores.index(max(scores)) * 2
        logger.info(f"饮料数量：{result}")
        return result

    def map_skip_day(self):
        # 跳过行动，进入下一天
        if pos := self.find("ra/days"):
            self.tap(pos, interval=0.5)
        elif pos := self.find("ra/save"):
            self.tap(pos, interval=0.5)
        else:
            self.sleep()

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
            if pos := self.find("ra/start_button"):
                self.tap(pos, interval=8)
            else:
                self.tap_element("ra/continue_button", interval=3)

        # 剧情
        elif scene == Scene.RA_GUIDE_ENTRANCE:
            self.tap_element("ra/guide_entrance", interval=0.5)
        elif scene == Scene.RA_GUIDE_BATTLE_ENTRANCE:
            self.battle_wait = 3
            self.tap_element("ra/start_action", interval=5)
        elif scene == Scene.RA_GUIDE_DIALOG:
            self.battle_wait = 0
            self.fast_tap((1631, 675))

        # 进入与退出战斗
        elif scene == Scene.RA_BATTLE_ENTRANCE:
            self.tap_element("ra/start_action", interval=2)
        elif scene == Scene.RA_BATTLE:
            if self.battle_wait > 0:
                self.battle_wait -= 1
                self.sleep()
            else:
                if pos := self.find(
                    "ra/battle_exit", scope=((0, 0), (200, 160)), score=0.4
                ):
                    self.tap(pos)
                else:
                    self.recog.update()
        elif scene == Scene.RA_BATTLE_EXIT_CONFIRM:
            self.tap_element("ra/battle_exit_confirm", interval=0.5)
        elif scene == Scene.RA_BATTLE_COMPLETE:
            self.tap_element("ra/battle_complete", interval=8)

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
            if pos := self.find("ra/delete_save_confirm_dialog_ok_button"):
                self.tap(pos, rebuild=False, interval=0.5)
                self.tap(pos, interval=2)

        # 奇遇
        elif scene == Scene.RA_ADVENTURE:
            if not self.in_adventure:
                self.in_adventure = self.task_queue[0]
            if self.find("ra/no_enough_resources"):
                logger.info("所需资源不足")
                if self.in_adventure == "奇遇_砾沙平原":
                    self.task_queue.remove("资源区_射程以内")
                    self.task_queue.remove("奇遇_崎岖窄路")
                if self.in_adventure in self.task_queue:
                    self.task_queue.remove(self.in_adventure)
                self.tap_element("ra/map_back")
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
                    self.tap(scope[-1], interval=0.5, rebuild=False)
                    self.tap(scope[-1])
                elif pos := self.find("ra/adventure_ok"):
                    if self.in_adventure in self.task_queue:
                        self.task_queue.remove(self.in_adventure)
                    pos = (1740, round((pos[0][1] + pos[1][1]) / 2))
                    self.tap(pos, interval=0.5, rebuild=False)
                    self.tap(pos)
                else:
                    self.tap((428, 411), interval=0.5)

        # 地图页操作
        elif scene == Scene.RA_MAP:
            if self.in_adventure:
                if self.in_adventure not in self.task_queue:
                    self.in_adventure = None
                self.recog.update()
            elif (day := self.detect_day()) == 0:
                self.tap((1760, 140), interval=2)
            elif day == 4:
                score, pos = self.template_match(
                    "ra/delete_save", scope=((1610, 820), (1785, 940))
                )
                if score > 5000000:
                    self.tap(pos, interval=0.5)
                else:
                    self.tap((1540, 1010), interval=1.5)
            else:
                if self.task_queue is None:
                    self.task_queue = [
                        "奇遇_风啸峡谷",
                        "捕猎区_聚羽之地",
                        "资源区_林中寻宝",
                        "奇遇_砾沙平原",
                        "资源区_射程以内",
                        "奇遇_崎岖窄路",
                    ]
                if (ap := self.detect_ap()) == 0:
                    self.map_skip_day()
                else:
                    remain_ap = (3 - day) * 2 + ap
                    if remain_ap - len(self.task_queue) >= 2:
                        self.map_skip_day()
                    elif ap == 1 and len(self.task_queue) + 1 == remain_ap:
                        self.map_skip_day()
                    else:
                        logger.info(self.task_queue)
                        place = self.task_queue[0]
                        self.map = Map(self.recog.gray)
                        pos = self.find(f"ra/map/{place}")
                        if not pos:
                            if self.drag(place):
                                pos = self.find(f"ra/map/{place}")
                            else:
                                # 返回首页重新进入，使基地位于屏幕中央
                                self.tap_element("ra/map_back")
                                return
                        self.tap(pos, rebuild=False, interval=0.5)
                        if place.startswith("奇遇"):
                            self.tap((428, 411), interval=0.5)
                        else:
                            self.task_queue.pop(0)
                            self.recog.update()
        elif scene == Scene.RA_DAY_DETAIL:
            self.tap_element("ra/waste_time_button", interval=0.5)
        elif scene == Scene.RA_WASTE_TIME_DIALOG:
            self.tap_element("ra/waste_time_dialog_confirm_button")

        # 作战编队
        elif scene == Scene.RA_SQUAD_EDIT:
            if self.detect_drink() == 0:
                self.tap((1430, 1015), interval=0.5)
            else:
                self.tap_element("ra/squad_edit_start_button", interval=0.5)
        elif scene == Scene.RA_SQUAD_EDIT_DIALOG:
            self.tap_element("ra/squad_edit_confirm_dialog_ok_button", interval=6)

        # 烹饪台
        elif scene == Scene.RA_KITCHEN:
            self.tap_element("ra/auto+1", interval=0.5)
            if self.detect_prepared() == 1:
                self.tap_element("ra/auto+1", interval=0.5)
                if self.detect_prepared() == 2:
                    self.tap_element("ra/cook_button", interval=0.5)
                else:
                    self.recog.update()
            else:
                self.recog.update()

        elif scene == Scene.RA_GET_ITEM:
            if pos := self.find("ra/click_to_continue"):
                self.tap(pos, interval=0.5)
                if pos := self.find("ra/return_from_kitchen"):
                    # 烹饪台合成
                    self.tap(pos, x_rate=0.07)
                else:
                    self.sleep(1, rebuild=False)
                    self.tap((428, 411), interval=0.5)
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
