import lzma
import pickle
from datetime import datetime, timedelta

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils import rapidocr, segment
from arknights_mower.utils.character_recognize import operator_list
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger

with lzma.open(f"{__rootdir__}/models/operator_room.model", "rb") as f:
    OP_ROOM = pickle.loads(f.read())

kernel = np.ones((12, 12), np.uint8)


class BaseMixin:
    profession_labels = [
        "ALL",
        "PIONEER",
        "WARRIOR",
        "TANK",
        "SNIPER",
        "CASTER",
        "MEDIC",
        "SUPPORT",
        "SPECIAL",
    ]

    def detect_arrange_order(self):
        name_list = ["工作状态", "技能", "心情", "信赖值"]
        x_list = (1135, 1262, 1363, 1490)
        y = 70
        hsv = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (95, 100, 100), (105, 255, 255))
        for idx, x in enumerate(x_list):
            if np.count_nonzero(mask[y : y + 3, x : x + 5]):
                return (name_list[idx], False)
            if np.count_nonzero(mask[y + 10 : y + 13, x : x + 5]):
                return (name_list[idx], True)

    def switch_arrange_order(self, name, ascending=False):
        name_x = {"工作状态": 1135, "技能": 1264, "心情": 1368, "信赖值": 1495}
        if isinstance(name, int):
            name = list(name_x.keys())[name - 1]
        if isinstance(ascending, str):
            ascending = ascending == "true"
        name_y = 60
        self.tap((name_x[name], name_y), interval=0.5)
        while True:
            n, s = self.detect_arrange_order()
            if n == name and s == ascending:
                break
            self.tap((name_x[name], name_y), interval=0.5)

    def scan_agent(
        self, agent: list[str], error_count=0, max_agent_count=-1, full_scan=True
    ):
        try:
            # 识别干员
            self.recog.update()
            while self.find("connecting"):
                logger.info("等待网络连接")
                self.sleep()
            # 返回的顺序是从左往右从上往下
            ret = operator_list(self.recog.img, full_scan=full_scan)
            # 提取识别出来的干员的名字
            select_name = []
            for name, scope in ret:
                if name in agent:
                    select_name.append(name)
                    self.tap(scope, interval=0)
                    agent.remove(name)
                    # 如果是按照个数选择 Free
                    if max_agent_count != -1:
                        if len(select_name) >= max_agent_count:
                            return select_name, ret
            return select_name, ret
        except MowerExit:
            raise
        except Exception as e:
            error_count += 1
            if error_count < 3:
                return self.scan_agent(agent, error_count, max_agent_count, False)
            else:
                logger.exception(e)
                raise e

    def verify_agent(
        self, agent: list[str], error_count=0, max_agent_count=-1, full_scan=True
    ):
        try:
            # 识别干员
            while self.find("connecting"):
                logger.info("等待网络连接")
                self.sleep()
            ret = operator_list(
                self.recog.img, full_scan=full_scan
            )  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            index = 0
            for name, scope in ret:
                if index >= len(agent):
                    return True
                if name != agent[index]:
                    return False
                index += 1
            return True
        except Exception as e:
            error_count += 1
            self.switch_arrange_order("技能")
            if error_count < 3:
                return self.verify_agent(
                    agent, error_count, max_agent_count, full_scan=False
                )
            else:
                logger.exception(e)
                raise e

    def swipe_left(self, right_swipe, special_filter):
        if right_swipe > 3:
            selected_label = next(
                (label for label in self.profession_labels if label != special_filter),
                None,
            )
            # 硬切换职业筛选 的时候有时候游戏会出bug，回不去，改成切换到ALL
            if special_filter == "ALL":
                self.profession_filter(selected_label)
            else:
                self.profession_filter("ALL")
            self.profession_filter(special_filter)
        else:
            swipe_time = 2 if right_swipe == 3 else right_swipe
            for i in range(swipe_time):
                self.swipe_noinertia((650, 540), (2500, 0))
        return 0

    def profession_filter(self, profession=None):
        retry = 0
        open_threshold = 1700
        if profession:
            logger.info(f"打开 {profession} 筛选")
        else:
            logger.info("关闭职业筛选")
            self.profession_filter("ALL")
            while (
                confirm_btn := self.find("confirm_blue")
            ) is not None and confirm_btn[0][0] < open_threshold:
                self.tap((1860, 60), 0.1)
                retry += 1
                if retry > 5:
                    raise Exception("关闭职业筛选失败")
            return
        x = 1918
        label_pos = [(x, 135 + i * 110) for i in range(9)]
        label_pos_map = dict(zip(self.profession_labels, label_pos))
        while (confirm_btn := self.find("confirm_blue")) is not None and confirm_btn[0][
            0
        ] > open_threshold:
            self.tap((1860, 60), 0.1)
            retry += 1
            if retry > 5:
                raise Exception("打开职业筛选失败")
        retry = 0
        # 点击一次ALL先
        self.tap(label_pos_map["ALL"], 0.1)
        while self.get_color(label_pos_map[profession])[2] < 240:
            logger.debug(f"配色为： {self.get_color(label_pos_map[profession])[2]}")
            self.tap(label_pos_map[profession], 0.1)
            retry += 1
            if retry > 5:
                raise Exception("打开职业筛选失败")

    def detect_room_number(self, img) -> int:
        score = []
        for i in range(1, 5):
            digit = loadres(f"room/{i}")
            result = cv2.matchTemplate(img, digit, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            score.append(max_val)
        return score.index(max(score)) + 1

    def detect_room(self) -> str:
        color_map = {
            "制造站": 25,
            "贸易站": 99,
            "发电站": 36,
            "训练室": 178,
            "加工站": 32,
        }
        img = cropimg(self.recog.img, ((568, 18), (957, 95)))
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        colored_room = None
        for room, color in color_map.items():
            mask = cv2.inRange(hsv, (color - 1, 0, 0), (color + 2, 255, 255))
            if cv2.countNonZero(mask) > 1000:
                colored_room = room
                break
        if colored_room in ["制造站", "贸易站", "发电站"]:
            digit_1 = cropimg(img, ((211, 24), (232, 54)))
            digit_2 = cropimg(img, ((253, 24), (274, 54)))
            digit_1 = self.detect_room_number(digit_1)
            digit_2 = self.detect_room_number(digit_2)
            logger.debug(f"{colored_room}B{digit_1}0{digit_2}")
            return f"room_{digit_1}_{digit_2}"
        elif colored_room == "训练室":
            logger.debug("训练室B305")
            return "train"
        elif colored_room == "加工站":
            logger.debug("加工站B105")
            return "factory"
        white_room = ["central", "dormitory", "meeting", "contact"]
        score = []
        for room in white_room:
            tpl = loadres(f"room/{room}")
            result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            score.append(max_val)
        room = white_room[score.index(max(score))]
        if room == "central":
            logger.debug("控制中枢")
        elif room == "dormitory":
            digit = cropimg(img, ((174, 24), (195, 54)))
            digit = self.detect_room_number(digit)
            if digit == 4:
                logger.debug("宿舍B401")
            else:
                logger.debug(f"宿舍B{digit}04")
            return f"dormitory_{digit}"
        elif room == "meeting":
            logger.debug("会客室1F02")
        else:
            logger.debug("办公室B205")
        return room

    def adjust_room(self, _room):
        # 定义屏幕范围
        screen_min_x = 0
        screen_max_x = 1920

        # 检查是否有点在屏幕范围内
        any_point_in_view = any(screen_min_x <= p[0] <= screen_max_x for p in _room)

        if any_point_in_view:
            logger.debug(
                f"At least one point of {_room} is within screen range [0, 1920]. No movement needed."
            )
            for i in range(4):
                _room[i, 0] = max(_room[i, 0], 0)
                _room[i, 0] = min(_room[i, 0], self.recog.w)
                _room[i, 1] = max(_room[i, 1], 0)
                _room[i, 1] = min(_room[i, 1], self.recog.h)
            return _room

        # 如果所有点都超出屏幕范围，则计算需要的移动距离
        min_x = min(p[0] for p in _room)
        max_x = max(p[0] for p in _room)

        dx = 0
        start = (960, 540)
        if min_x < screen_min_x:
            # 左边超出，向右移动
            dx = screen_min_x - min_x
            logger.debug(f"Moving right by {dx} to bring room into view.")
        elif max_x > screen_max_x:
            # 右边超出，向左移动
            dx = screen_max_x - max_x
            logger.debug(f"Moving left by {-dx} to bring room into view.")

        # 如果需要移动，则移动视图
        if dx != 0:
            movement = (dx, 0)  # 仅水平移动
            self.swipe_noinertia(start, movement, interval=0.5)
            # 更新 _room 的所有点位置
            for i in range(len(_room)):
                _room[i][0] += dx

        # 返回修正后的 _room
        return _room

    def enter_room(self, room):
        """从基建首页进入房间"""

        for enter_times in range(3):
            for retry_times in range(5):
                if pos := self.find("control_central"):
                    _room = segment.base(self.recog.img, pos)[room]
                    self.tap(self.adjust_room(_room))
                elif self.detect_room() == room:
                    return
                else:
                    self.sleep()
            if not pos:
                self.back_to_infrastructure()
        raise Exception("未成功进入房间")

    def double_read_time(self, cord, upperLimit=None, use_digit_reader=False):
        self.recog.update()
        time_in_seconds = self.read_time(cord, upperLimit, use_digit_reader)
        if time_in_seconds is None:
            return datetime.now()
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds))
        return execute_time

    def read_accurate_mood(self, img):
        try:
            img = thres2(img, 200)
            return cv2.countNonZero(img) * 24 / 310
        except Exception as e:
            logger.exception(e)
            return 24

    def detect_product_complete(self):
        for product in ["gold", "exp", "lmd", "ori", "oru", "trust"]:
            if pos := self.find(
                f"infra_{product}_complete",
                scope=((1230, 0), (1920, 1080)),
                score=0.1,
            ):
                return pos

    def read_operator_in_room(self, img):
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

    def read_screen(self, img, type="mood", limit=24, cord=None):
        if cord is not None:
            img = cropimg(img, cord)
        if type == "name":
            img = cropimg(img, ((169, 22), (513, 80)))
            return self.read_operator_in_room(img)
        try:
            ret = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)[0]
            logger.debug(ret)
            if not ret or not ret[0][0]:
                raise Exception("识别失败")
            ret = ret[0][0]
            if "mood" in type:
                if (f"/{limit}") in ret:
                    ret = ret.replace(f"/{limit}", "")
                if len(ret) > 0:
                    if "." in ret:
                        ret = ret.replace(".", "")
                    return int(ret)
                else:
                    return -1
            elif "time" in type:
                if "." in ret:
                    ret = ret.replace(".", ":")
                return ret.strip()
            else:
                return ret
        except Exception:
            return limit + 1

    def read_time(self, cord, upperlimit, error_count=0, use_digit_reader=False):
        # 刷新图片
        self.recog.update()
        try:
            if use_digit_reader:
                time_str = self.digit_reader.get_time(self.recog.gray)
            else:
                time_str = self.read_screen(self.recog.img, type="time", cord=cord)
            logger.debug(time_str)
            h, m, s = str(time_str).split(":")
            if int(m) > 60 or int(s) > 60:
                raise Exception("读取错误")
            res = int(h) * 3600 + int(m) * 60 + int(s)
            if upperlimit is not None and res > upperlimit:
                raise Exception("超过读取上限")
            else:
                return res
        except Exception:
            if error_count > 3:
                logger.debug(f"读取失败{error_count}次超过上限")
                return None
            else:
                logger.debug("读取失败")
                return self.read_time(
                    cord, upperlimit, error_count + 1, use_digit_reader
                )
