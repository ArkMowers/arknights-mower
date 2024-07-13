import math
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Optional

import cv2
import numpy as np

from arknights_mower.utils import rapidocr
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.matcher import Matcher
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver, MowerExit

src_pts = np.float32([[0, 97], [1920, 97], [-400, 1080], [2320, 1080]])
dst_pts = np.float32([[0, 0], [1920, 0], [0, 1000], [1920, 1000]])
trans_mat = cv2.getPerspectiveTransform(src_pts, dst_pts)
rev_mat = np.linalg.inv(trans_mat)


class Map:
    def __init__(self, img: tp.GrayImage):
        self.map = cv2.warpPerspective(img, trans_mat, (1920, 1000))
        self.matcher = None

    def map2scrn(self, point: tp.Coordinate) -> tp.Coordinate:
        x = np.array([[point[0]], [point[1]], [1]])
        y = np.dot(rev_mat, x)
        return (round(y[0][0] / y[2][0]), round(y[1][0] / y[2][0]))

    def find(self, res: str) -> Optional[tp.Scope]:
        logger.debug(f"find: {res}")
        if self.matcher is None:
            self.matcher = Matcher(self.map)
        res_img = loadres(f"ra/map/{res}", True)
        return self.matcher.match(res_img, scope=((250, 0), (1620, 900)), prescore=0.5)


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

        self.battle_task = None
        self.task_queue = None
        self.in_adventure = None
        self.ap = None
        self.vp = None

        self.left_kitchen = False

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
        self.sleep()

    def stop_fast_tap(self):
        self.event.set()
        if self.thread:
            self.thread.join()
            self.thread = None
        logger.debug("快速点击已停止")

    def detect_adventure(self, map, pos):
        adventures = [i for i in self.places if i.startswith("奇遇")]
        scores = []
        img = cropimg(
            map,
            (
                (pos[0][0] + 140, pos[0][1] + 25),
                (pos[1][0] + 10, pos[1][1] - 15),
            ),
        )
        img = thres2(img, 180)
        for i in adventures:
            template = loadres(f"ra/map/{i}", True)
            template = cropimg(template, ((151, 36), (254, 62)))
            template = thres2(template, 180)
            result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF)
            result = cv2.minMaxLoc(result)[1]
            scores.append(result)
        return adventures[scores.index(max(scores))]

    def find_place(self, place=None):
        map = Map(self.recog.gray)
        if place is None:
            for place in self.places:
                if pos := map.find(place):
                    break
            if pos is None:
                logger.debug("在当前地图中没有找到任何地点")
                return None, None
            if place.startswith("奇遇"):
                place = self.detect_adventure(map.map, pos)
            pos = map.map2scrn(pos[0]), map.map2scrn(pos[1])
            logger.debug(f"在区域{pos}识别到任意地点{place}")
            return pos, place
        elif place.startswith("奇遇"):
            while True:
                pos = map.find(place)
                if pos is None:
                    logger.debug(f"没有找到地点{place}")
                    return None
                if place == self.detect_adventure(map.map, pos):
                    pos = map.map2scrn(pos[0]), map.map2scrn(pos[1])
                    logger.debug(f"在区域{pos}识别到指定地点{place}")
                    return pos
                else:
                    cv2.rectangle(map.map, pos[0], pos[1], (255,), -1)
                    map.matcher = Matcher(map.map)
        else:
            pos = map.find(place)
            if pos is None:
                logger.debug(f"没有找到地点{place}")
                return None
            pos = map.map2scrn(pos[0]), map.map2scrn(pos[1])
            logger.debug(f"在区域{pos}识别到指定地点{place}")
            return pos

    def drag(
        self, res: str, position: tp.Coordinate = (960, 500), update_vp: bool = True
    ) -> bool:
        res_img = loadres(f"ra/map/{res}", True)
        top_left = (
            position[0] - round(res_img.shape[1] / 2),
            position[1] - round(res_img.shape[0] / 2),
        )
        if update_vp:
            pos, place = self.find_place()
            if pos is None:
                logger.warning("没有找到任何地点，拖拽失败")
                return False
            vp1 = tuple(a - b for a, b in zip(self.places[place][0], pos[0]))
        else:
            vp1 = self.vp
        vp2 = tuple(a - b for a, b in zip(self.places[res][0], top_left))
        self.vp = vp2
        vp_offset = tuple(a - b for a, b in zip(vp1, vp2))
        total_distance = tuple(abs(a) for a in vp_offset)
        max_drag = tuple(b - a for a, b in zip(*self.drag_scope))
        steps = max(math.ceil(d / m) for d, m in zip(total_distance, max_drag))
        if steps == 0:
            logger.warning("拖拽距离异常")
            return False
        step_distance = tuple(round(i / steps) for i in vp_offset)
        center_point = tuple(round((a + b) / 2) for a, b in zip(*self.drag_scope))
        map = Map(self.recog.gray)
        start_point = map.map2scrn(
            tuple(a - round(b / 2) for a, b in zip(center_point, step_distance))
        )
        end_point = map.map2scrn(
            tuple(a + round(b / 2) for a, b in zip(center_point, step_distance))
        )
        for _ in range(steps):
            self.device.swipe_ext(
                (start_point, end_point, end_point), durations=[500, 200]
            )
            self.sleep(0.1)
        self.recog.save_screencap("ra_drag_map")
        return True

    def plan_task(self):
        self.task_queue = []
        if not self.drag("奇遇_风啸峡谷"):
            self.map_back()
            return
        if self.find_place("冲突区_丢失的订单"):
            logger.debug("奇遇_风啸峡谷已完成")
        else:
            logger.debug("添加任务：奇遇_风啸峡谷")
            self.task_queue.append("奇遇_风啸峡谷")
        self.drag("资源区_射程以内", update_vp=False)
        if self.find_place("要塞_征税的选择"):
            logger.debug("左侧区域任务已完成")
        elif self.find_place("奇遇_崎岖窄路"):
            logger.debug("添加任务：奇遇_崎岖窄路")
            self.task_queue.append("奇遇_崎岖窄路")
        elif self.find_place("资源区_射程以内"):
            logger.debug("添加任务：资源区_射程以内、奇遇_崎岖窄路")
            self.task_queue += ["资源区_射程以内", "奇遇_崎岖窄路"]
        elif self.find_place("奇遇_砾沙平原"):
            logger.debug("添加任务：奇遇_砾沙平原，资源区_射程以内，奇遇_崎岖窄路")
            self.task_queue += ["奇遇_砾沙平原", "资源区_射程以内", "奇遇_崎岖窄路"]
        else:
            self.drag("资源区_林中寻宝", update_vp=False)
            if self.find_place("资源区_林中寻宝"):
                logger.debug(
                    "添加任务：资源区_林中寻宝，奇遇_砾沙平原，资源区_射程以内，奇遇_崎岖窄路"
                )
                self.task_queue += [
                    "资源区_林中寻宝",
                    "奇遇_砾沙平原",
                    "资源区_射程以内",
                    "奇遇_崎岖窄路",
                ]
            else:
                logger.debug(
                    "添加任务：捕猎区_聚羽之地，资源区_林中寻宝，奇遇_砾沙平原，资源区_射程以内，奇遇_崎岖窄路"
                )
                self.task_queue += [
                    "捕猎区_聚羽之地",
                    "资源区_林中寻宝",
                    "奇遇_砾沙平原",
                    "资源区_射程以内",
                    "奇遇_崎岖窄路",
                ]

    def detect_prepared(self) -> int:
        templates = [f"ra/prepared_{i}" for i in range(3)]
        scores = [
            self.template_match(i, ((510, 820), (700, 900)))[0] for i in templates
        ]
        result = scores.index(max(scores))
        logger.debug(f"已准备 {result}")
        return result

    def detect_day(self) -> int:
        templates = ["ra/day_next"] + [f"ra/day_{i}" for i in range(1, 5)]
        scores = [
            self.template_match(i, ((1730, 110), (1805, 175)))[0] for i in templates
        ]
        result = scores.index(max(scores))
        logger.debug(f"第{result}天" if result > 0 else "进入下一天")
        return result

    def detect_ap(self) -> int:
        ap = 0
        if self.get_color((1752, 182))[0] > 175:
            ap += 1
        if self.get_color((1774, 182))[0] > 175:
            ap += 1
        logger.debug(f"决断次数：{ap}")
        return ap

    def detect_drink(self) -> int:
        templates = [f"ra/drink_{i}" for i in range(0, 6, 2)]
        scores = [
            self.template_match(i, ((1448, 1004), (1465, 1028)))[0] for i in templates
        ]
        result = scores.index(max(scores)) * 2
        logger.debug(f"饮料数量：{result}")
        return result

    def map_skip_day(self, reason: str):
        logger.debug(f"{reason}，跳过行动，进入下一天")
        self.tap((1764, 134), interval=0.5)

    def print_ap(self):
        logger.debug(f"剩余决断次数：{self.ap}")

    def map_back(self):
        self.tap_element("ra/map_back", thres=200)

    def detect_score(self, scope=None, find_max=True):
        if find_max and self.find("ra/max", scope=scope, score=0.7):
            return "已达上限"
        score = rapidocr.engine(
            thres2(cropimg(self.recog.gray, scope), 127),
            use_det=False,
            use_cls=False,
            use_rec=True,
        )[0][0][0]
        return score or "识别失败"

    def map_select_place(self, pos, place):
        if popup := self.find("ra/popup"):
            if (
                popup[0][0] > pos[1][0]
                or popup[1][0] < pos[0][0]
                or popup[0][1] > pos[1][1]
                or popup[1][1] < pos[0][1]
            ):
                x = int((pos[0][0] + pos[1][0]) / 2)
            else:
                logger.info(f"{place}被虫子挡住了！")
                if popup[0][0] < pos[1][0] < popup[1][0]:
                    x = int((pos[0][0] + popup[0][0]) / 2)
                elif popup[0][0] < pos[0][0] < popup[1][0]:
                    x = int((popup[1][0] + pos[1][0]) / 2)
                else:
                    ll = popup[0][0] - pos[0][0]
                    lr = pos[1][0] - popup[1][0]
                    if ll > lr:
                        x = int(pos[0][0] + ll / 2)
                    else:
                        x = int(popup[1][0] + lr / 2)
        else:
            x = int((pos[0][0] + pos[1][0]) / 2)
        self.tap((x, int((pos[0][1] + pos[1][1]) / 2)), interval=0.5)

    def move_forward(self, scene):
        # 从首页进入生息演算主页
        if scene == Scene.CONNECTING:
            self.sleep()
        elif scene == Scene.INDEX:
            self.tap_index_element("terminal")
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
            pos = self.find("ra/guide_entrance")
            self.tap(pos, x_rate=2, y_rate=1.5, interval=0.5)
        elif scene == Scene.RA_GUIDE_BATTLE_ENTRANCE:
            self.battle_wait = 3
            self.tap_element("ra/start_action", interval=5)
        elif scene == Scene.RA_GUIDE_DIALOG:
            self.battle_wait = 0
            self.fast_tap((1631, 675))

        # 进入与退出战斗
        elif scene == Scene.RA_BATTLE_ENTRANCE:
            if self.battle_task in self.task_queue:
                self.task_queue.remove(self.battle_task)
                self.ap -= 1
            self.tap_element("ra/start_action")
        elif scene == Scene.RA_BATTLE:
            if self.battle_wait > 0:
                self.battle_wait -= 1
                self.sleep()
            else:
                if pos := self.recog.find_ra_battle_exit():
                    self.tap(pos, interval=0.5)
                else:
                    self.recog.update()
        elif scene == Scene.RA_BATTLE_EXIT_CONFIRM:
            self.tap_element("ra/confirm_green", interval=0.5)
        elif scene == Scene.RA_BATTLE_COMPLETE:
            self.tap_element("ra/battle_complete", interval=0.5)

        # 结算界面
        elif scene == Scene.RA_DAY_COMPLETE:
            if pos := self.find("ra/period_complete_start_new_day"):
                self.tap(pos)
            else:
                self.tap((960, 900))
        elif scene == Scene.RA_PERIOD_COMPLETE:
            scope_list = (
                (((860, 550), (1060, 640)), "生息总结", False),
                (((870, 785), (956, 825)), "转化技术点数", True),
                (((1250, 785), (1345, 825)), "转化繁荣点数", True),
            )
            for scope, title, find_max in scope_list:
                score = self.detect_score(scope=scope, find_max=find_max)
                logger.info(f"{title}：{score}")
            self.tap_element("ra/period_complete")

        # 存档操作
        elif scene == Scene.RA_DELETE_SAVE_DIALOG:
            if pos := self.find("ra/delete_save_confirm_dialog_ok_button"):
                self.tap(pos, interval=0.5)
                self.tap(pos)
                self.task_queue = None
                self.ap = None
            else:
                self.sleep()

        # 奇遇
        elif scene == Scene.RA_ADVENTURE:
            if not self.in_adventure:
                self.in_adventure = self.task_queue[0]

            leave_adventure = False
            if self.find("ra/no_enough_resources"):
                leave_adventure = True
                logger.debug("所需资源不足")
            elif self.find("ra/spring"):
                leave_adventure = True
                logger.debug("特殊处理涌泉奇遇")

            if leave_adventure:
                if self.in_adventure in self.task_queue:
                    self.task_queue.remove(self.in_adventure)
                    if self.in_adventure == "奇遇_砾沙平原":
                        self.task_queue.remove("资源区_射程以内")
                        self.task_queue.remove("奇遇_崎岖窄路")
                self.map_back()
            else:
                tpl = loadres("ra/ap-1", True)
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
                    self.tap(scope[-1], interval=0.5)
                    self.tap(scope[-1])
                elif pos := self.find("ra/adventure_ok"):
                    if self.in_adventure in self.task_queue:
                        self.task_queue.remove(self.in_adventure)
                        self.ap -= 1
                    pos = (1740, round((pos[0][1] + pos[1][1]) / 2))
                    self.tap(pos, interval=0.5)
                    self.tap(pos)
                else:
                    self.tap((428, 411), interval=0.5)

        # 地图页操作
        elif scene == Scene.RA_MAP:
            if self.in_adventure:
                if self.in_adventure not in self.task_queue:
                    self.in_adventure = None
                self.recog.update()
                return
            day = self.detect_day()
            if day == 0:
                self.tap((1760, 140), interval=2)
                self.ap = 2
                return
            if day == 4:
                score, pos = self.template_match(
                    "ra/delete_save", scope=((1610, 820), (1785, 940))
                )
                if score > 0.9:
                    self.tap(pos, interval=0.5)
                else:
                    self.tap((1540, 1010), interval=1.5)
                return
            if self.ap is None:
                self.ap = self.detect_ap()
            self.print_ap()
            if self.task_queue is None:
                if day == 1 and self.ap == 2:
                    logger.debug("初始化任务列表")
                    self.task_queue = [
                        "奇遇_风啸峡谷",
                        "捕猎区_聚羽之地",
                        "资源区_林中寻宝",
                        "奇遇_砾沙平原",
                        "资源区_射程以内",
                        "奇遇_崎岖窄路",
                    ]
                else:
                    self.plan_task()
            if self.ap == 0:
                self.map_skip_day("当日已无决断次数")
                return
            remain_ap = (3 - day) * 2 + self.ap
            if remain_ap - len(self.task_queue) >= 2:
                self.map_skip_day("当日无任务")
                return
            if self.ap == 1 and len(self.task_queue) + 1 == remain_ap:
                self.map_skip_day("当日无任务")
                return
            logger.debug(self.task_queue)
            place = self.task_queue[0]
            pos = self.find_place(place)
            if pos is None:
                if self.drag(place):
                    pos = self.find_place(place)
                else:
                    # 返回首页重新进入，使基地位于屏幕中央
                    self.map_back()
                    return
            self.map_select_place(pos, place)
            if place.startswith("奇遇"):
                self.tap((428, 411), interval=0.5)
            else:
                self.battle_task = place
                self.recog.update()
        elif scene == Scene.RA_DAY_DETAIL:
            self.tap_element("ra/waste_time_button", interval=0.5)
        elif scene == Scene.RA_WASTE_TIME_DIALOG:
            self.tap_element("ra/confirm_green")

        # 作战编队
        elif scene == Scene.RA_SQUAD_EDIT:
            if self.detect_drink() == 0:
                self.left_kitchen = False
                self.tap((1430, 1015), interval=0.5)
            else:
                self.tap_element("ra/squad_edit_start_button", interval=0.5)
        elif scene == Scene.RA_SQUAD_EDIT_DIALOG:
            self.tap_element("ra/confirm_red", interval=6)
        elif scene == Scene.RA_SQUAD_ABNORMAL:
            self.tap_element("ra/confirm_red", interval=6)

        # 烹饪台
        elif scene == Scene.RA_KITCHEN:
            if self.left_kitchen:
                self.tap_element("ra/return_from_kitchen", x_rate=0.07)
                return
            last_drink = self.detect_prepared()
            while last_drink < 2:
                self.tap_element("ra/auto+1", interval=0.5)
                drink = self.detect_prepared()
                if drink == last_drink:
                    logger.debug("饮料无法合成，返回地图，清空任务列表")
                    self.task_queue = []
                    self.tap_element("ra/return_from_kitchen", x_rate=0.07)
                    self.tap_element("ra/squad_back")
                    self.map_back()
                    return
                last_drink = drink
            self.tap_element("ra/cook_button", interval=0.5)

        # 能量饮料不足
        elif scene == Scene.RA_INSUFFICIENT_DRINK:
            self.tap_element("ra/dialog_cancel")

        # 获得物资
        elif scene == Scene.RA_GET_ITEM:
            if pos := self.find("ra/click_to_continue"):
                self.tap(pos, interval=0.5)
                if self.in_adventure:
                    self.sleep(0.5)
                    self.tap((428, 411), interval=0.5)
                else:
                    self.left_kitchen = True
                    self.tap_element("ra/return_from_kitchen", x_rate=0.07)
            else:
                self.sleep(0.5)

        # 一张便条
        elif scene == Scene.RA_NOTICE:
            self.tap((1366, 620), interval=0.5)
            self.tap((1366, 620))

        else:
            self.sleep()

    def back_to_index(self, scene):
        if scene == Scene.CONNECTING:
            self.sleep()
        elif scene in [Scene.RA_MAIN, Scene.TERMINAL_LONGTERM, Scene.TERMINAL_MAIN]:
            self.tap_element("nav_button", x_rate=0.21)
        elif scene in [Scene.RA_MAP, Scene.RA_DAY_DETAIL, Scene.RA_BATTLE_ENTRANCE]:
            self.map_back()
        elif scene == Scene.RA_SQUAD_EDIT:
            self.tap_element("ra/squad_back")
        elif scene == Scene.RA_KITCHEN:
            self.tap_element("ra/return_from_kitchen", x_rate=0.07)
        elif scene in [Scene.RA_SQUAD_EDIT_DIALOG, Scene.RA_WASTE_TIME_DIALOG]:
            self.tap_element("ra/dialog_cancel")
        elif 900 < scene < 1000:
            self.move_forward(scene)
        else:
            self.sleep()

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
                    self.task_queue = None
                    self.in_adventure = False
                    self.recog.scene = Scene.UNDEFINED
                    if self.scene() != Scene.UNKNOWN:
                        super().back_to_index()
                    else:
                        self.device.exit()
                        self.check_current_focus()
                except MowerExit:
                    raise
        else:
            self.unknown_time = None

        if self.deadline and self.deadline < datetime.now():
            if scene == Scene.INDEX:
                return True
            else:
                self.back_to_index(scene)
        else:
            self.move_forward(scene)
