import copy
import lzma
import pickle

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils import character_recognize, segment
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.solver import BaseSolver
from arknights_mower.utils.scene import Scene

with lzma.open(f"{__rootdir__}/models/operator_room.model", "rb") as f:
    OP_ROOM = pickle.loads(f.read())

kernel = np.ones((12, 12), np.uint8)


class AreneSolver(BaseSolver):
    def run(self, plan):
        logger.info("Start: 一键芳汀")
        self.current = {
            "dormitory_1": None,
            "dormitory_2": None,
            "dormitory_3": None,
            "dormitory_4": None,
        }
        self.plan = plan
        self.origin = {}
        self.room = None
        self.recog.update()
        super().run()

    def enter_room(self, room):
        base_room = segment.base(self.recog.img, self.find("control_central"))
        _room = base_room[room]

        for i in range(4):
            _room[i, 0] = max(_room[i, 0], 0)
            _room[i, 0] = min(_room[i, 0], self.recog.w)
            _room[i, 1] = max(_room[i, 1], 0)
            _room[i, 1] = min(_room[i, 1], self.recog.h)

        self.tap(_room[0], interval=1.1)

    def check_room_detail(self):
        return (pos := self.find("room_detail")) and self.get_color(pos[0])[0] == 255

    def turn_on_room_detail(self):
        if pos := self.find("arrange_check_in", score=0.5):
            self.tap(pos, interval=0.7)

    def detect_product_complete(self):
        for product in ["gold", "exp", "lmd", "ori"]:
            if pos := self.find(
                f"infra_{product}_complete", score=0.1, scope=((1230, 0), (1920, 1080))
            ):
                return pos

    def read_operator_in_room(self, img):
        img = cropimg(img, ((169, 22), (513, 80)))
        img = thres2(img, 200)
        img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,))
        dilation = cv2.dilate(img, kernel, iterations=1)
        contours, _ = cv2.findContours(dilation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect = map(lambda c: cv2.boundingRect(c), contours)
        x, y, w, h = sorted(rect, key=lambda c: c[0])[0]
        img = img[y : y + h, x : x + w]
        tpl = np.zeros((46, 265), dtype=np.uint8)
        tpl[: img.shape[0], : img.shape[1]] = img
        tpl = cv2.copyMakeBorder(tpl, 2, 2, 2, 2, cv2.BORDER_CONSTANT, None, (0,))
        max_score = 0
        best_operator = None
        for operator, template in OP_ROOM.items():
            result = cv2.matchTemplate(tpl, template, cv2.TM_CCORR_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val > max_score:
                max_score = max_val
                best_operator = operator
        return best_operator

    def get_agent_from_room(self):
        while self.detect_product_complete():
            logger.info("检测到产物收取提示")
            self.sleep(1)
        while self.get_color((1800, 138))[0] != 49:
            self.swipe(
                (self.recog.w * 0.8, self.recog.h * 0.5),
                (0, self.recog.h * 0.45),
                duration=500,
                interval=1,
                rebuild=True,
            )
        name_x = (1288, 1869)
        name_y = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        name_p = [tuple(zip(name_x, y)) for y in name_y]
        result = []
        swiped = False
        for i in range(5):
            if i >= 3 and not swiped:
                while self.get_color((1800, 930))[0] != 49:
                    self.swipe(
                        (self.recog.w * 0.8, self.recog.h * 0.5),
                        (0, -self.recog.h * 0.45),
                        duration=500,
                        interval=1,
                        rebuild=True,
                    )
                swiped = True
            if self.find("infra_no_operator", scope=name_p[i]):
                _name = ""
            else:
                _name = self.read_operator_in_room(cropimg(self.recog.gray, name_p[i]))
            result.append(_name)
        return result

    def detail_filter(self, **kwargs):
        if kwargs:
            text = "，".join(
                f"{'打开' if value else '关闭'}{label}筛选"
                for label, value in kwargs.items()
            )
            text += "，关闭其余筛选"
            logger.info(text)
        else:
            logger.info("关闭所有筛选")

        labels = [
            "未进驻",
            "产出设施",
            "功能设施",
            "自定义设施",
            "控制中枢",
            "生产类后勤",
            "功能类后勤",
            "恢复类后勤",
        ]
        label_x = (560, 815, 1070, 1330)
        label_y = (540, 645)

        label_pos = []
        for y in label_y:
            for x in label_x:
                label_pos.append((x, y))

        label_pos_map = dict(zip(labels, label_pos))
        target_state = dict(zip(labels, [False] * len(labels)))
        target_state.update(kwargs)

        filter_pos = (self.recog.w * 0.95, self.recog.h * 0.05)
        self.tap(filter_pos)
        while not self.find("arrange_order_options_scene"):
            self.tap(filter_pos)

        for label, pos in label_pos_map.items():
            current_state = self.get_color(pos)[2] > 100
            if target_state[label] != current_state:
                self.tap(pos, interval=0.1, rebuild=False)

        self.recog.update()
        confirm_pos = (self.recog.w * 0.8, self.recog.h * 0.8)
        self.tap(confirm_pos)
        while self.find("arrange_order_options_scene"):
            self.tap(confirm_pos)

    def scan_agent(self, agent):
        ret = character_recognize.operator_list(self.recog.img)
        selected = []
        for name, scope in ret:
            if name in agent:
                selected.append(name)
                self.tap(scope, interval=0)
                agent.remove(name)
        return selected, ret

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    def detect_arrange_order(self):
        name_list = ["工作状态", "技能", "心情", "信赖值"]
        x_list = (1196, 1320, 1445, 1572)
        y = 70
        hsv = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (99, 200, 0), (100, 255, 255))
        for idx, x in enumerate(x_list):
            if np.count_nonzero(mask[y : y + 3, x : x + 5]):
                return (name_list[idx], True)
            if np.count_nonzero(mask[y + 10 : y + 13, x : x + 5]):
                return (name_list[idx], False)

    def set_arrange_order(self, name: str, ascending: bool):
        name_x = {"工作状态": 1197, "技能": 1322, "心情": 1447, "信赖值": 1575}
        name_y = 60
        while True:
            n, s = self.detect_arrange_order()
            if n == name and s == ascending:
                break
            self.tap((name_x[name], name_y), interval=0.5)

    def choose_agent(self, agents):
        h, w = self.recog.h, self.recog.w

        self.detail_filter()
        self.tap_element("arrange_clean")
        self.set_arrange_order("心情", True)

        max_swipe = 50
        target = copy.deepcopy(agents)
        selected = []

        for right_swipe in range(max_swipe):
            new, ret = self.scan_agent(target)
            selected += new
            if len(target) == 0:
                break
            st = ret[-2][1][0]  # 起点
            ed = ret[0][1][0]  # 终点
            self.swipe_noinertia(st, (ed[0] - st[0], 0))

        # 排序
        self.swipe_left(right_swipe, w, h)

        self.set_arrange_order("心情", False)

        position = [
            (0.35, 0.35),
            (0.35, 0.75),
            (0.45, 0.35),
            (0.45, 0.75),
            (0.55, 0.35),
        ]

        for op in agents:
            i = selected.index(op)
            x = w * position[i][0]
            y = h * position[i][1]
            self.tap((x, y), interval=0, rebuild=False)
            self.tap((x, y), interval=0, rebuild=False)

        self.recog.update()
        self.tap_element("confirm_blue")

    def transition(self):
        if (scene := self.get_infra_scene()) == Scene.INFRA_MAIN:
            self.room = None
            for room, operators in self.plan.items():
                if self.current[room] != operators:
                    self.room = room
                    break
            if self.room:
                self.enter_room(room)
            else:
                logger.info(self.origin)
                return True
        elif scene == Scene.INFRA_DETAILS:
            if not self.room:
                self.back()
                return
            if not self.check_room_detail():
                self.turn_on_room_detail()
                return
            self.current[self.room] = self.get_agent_from_room()
            if self.room not in self.origin:
                self.origin[self.room] = self.current[self.room]
            if self.current[self.room] != self.plan[self.room]:
                self.tap((1600, 230))
            else:
                self.back()
        elif scene == Scene.INFRA_ARRANGE_ORDER:
            if not self.room:
                self.back()
                return
            self.choose_agent(self.plan[self.room])
            self.room = None
        else:
            self.sleep(1)
