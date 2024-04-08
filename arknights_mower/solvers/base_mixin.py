from __future__ import annotations

from datetime import timedelta, datetime
from enum import Enum
import lzma
import pickle

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils import character_recognize, segment
from arknights_mower.utils.log import logger
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils import rapidocr
from arknights_mower.data import agent_list, ocr_error
from arknights_mower.utils.image import thres2, loadimg, cropimg
from arknights_mower.utils.matcher import Matcher


class ArrangeOrder(Enum):
    STATUS = 1
    SKILL = 2
    FEELING = 3
    TRUST = 4


arrange_order_res = {
    ArrangeOrder.STATUS: (1560 / 2496, 96 / 1404),
    ArrangeOrder.SKILL: (1720 / 2496, 96 / 1404),
    ArrangeOrder.FEELING: (1880 / 2496, 96 / 1404),
    ArrangeOrder.TRUST: (2050 / 2496, 96 / 1404),
}

with lzma.open(f"{__rootdir__}/models/operator_room.model", "rb") as f:
    OP_ROOM = pickle.loads(f.read())

kernel = np.ones((12, 12), np.uint8)


class BaseMixin:
    def switch_arrange_order(self, index: int, asc="false") -> None:
        self.tap(
            (
                self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
            ),
            interval=0,
            rebuild=False,
        )
        # 点个不需要的
        if index < 4:
            self.tap(
                (
                    self.recog.w * arrange_order_res[ArrangeOrder(index + 1)][0],
                    self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
                ),
                interval=0,
                rebuild=False,
            )
        else:
            self.tap(
                (
                    self.recog.w * arrange_order_res[ArrangeOrder(index - 1)][0],
                    self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
                ),
                interval=0,
                rebuild=False,
            )
        # 切回来
        self.tap(
            (
                self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
            ),
            interval=0.2,
            rebuild=True,
        )
        # 倒序
        if asc != "false":
            self.tap(
                (
                    self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                    self.recog.h * arrange_order_res[ArrangeOrder(index)][1],
                ),
                interval=0.2,
                rebuild=True,
            )

    def scan_agent(self, agent: list[str], error_count=0, max_agent_count=-1):
        try:
            # 识别干员
            self.recog.update()
            ret = character_recognize.operator_list(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            select_name = []
            for name, scope in ret:
                if name in agent:
                    select_name.append(name)
                    # self.get_agent_detail((y[1][0]))
                    self.tap(scope, interval=0)
                    agent.remove(name)
                    # 如果是按照个数选择 Free
                    if max_agent_count != -1:
                        if len(select_name) >= max_agent_count:
                            return select_name, ret
            return select_name, ret
        except Exception as e:
            error_count += 1
            if error_count < 3:
                logger.exception(e)
                self.sleep(3)
                return self.scan_agent(agent, error_count, max_agent_count)
            else:
                raise e

    def verify_agent(self, agent: list[str], error_count=0, max_agent_count=-1):
        try:
            # 识别干员
            self.recog.update()
            ret = character_recognize.operator_list(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            select_name = []
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
            self.tap((self.recog.w * arrange_order_res[ArrangeOrder.SKILL][0],
                      self.recog.h * arrange_order_res[ArrangeOrder.SKILL][1]), interval=0, rebuild=False)
            self.tap((self.recog.w * arrange_order_res[ArrangeOrder.SKILL][0],
                      self.recog.h * arrange_order_res[ArrangeOrder.SKILL][1]), interval=0, rebuild=False)
            if error_count < 3:
                logger.exception(e)
                self.sleep(3)
                return self.verify_agent(agent, error_count, max_agent_count)
            else:
                raise e

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    def detail_filter(self, **kwargs):
        if kwargs:
            text = "，".join(f"{'打开' if value else '关闭'}{label}筛选" for label, value in kwargs.items())
            text += "，关闭其余筛选"
            logger.info(text)
        else:
            logger.info("关闭所有筛选")

        labels = ["未进驻", "产出设施", "功能设施", "自定义设施", "控制中枢", "生产类后勤", "功能类后勤", "恢复类后勤"]
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

        self.recog.save_screencap("detail_filter")
        for label, pos in label_pos_map.items():
            current_state = self.get_color(pos)[2] > 100
            if target_state[label] != current_state:
                self.tap(pos, interval=0.1, rebuild=False)

        self.recog.update()
        confirm_pos = (self.recog.w * 0.8, self.recog.h * 0.8)
        self.tap(confirm_pos)
        while self.find("arrange_order_options_scene"):
            self.tap(confirm_pos)

    def detect_room_number(self, img) -> int:
        score = []
        for i in range(1, 5):
            digit = loadimg(f"{__rootdir__}/resources/room/{i}.png")
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
            if cv2.countNonZero(mask) > 0:
                colored_room = room
                break
        if colored_room in ["制造站", "贸易站", "发电站"]:
            digit_1 = cropimg(img, ((211, 24), (232, 54)))
            digit_2 = cropimg(img, ((253, 24), (274, 54)))
            digit_1 = self.detect_room_number(digit_1)
            digit_2 = self.detect_room_number(digit_2)
            logger.info(f"{colored_room}B{digit_1}0{digit_2}")
            return f"room_{digit_1}_{digit_2}"
        elif colored_room == "训练室":
            logger.info("训练室B305")
            return "train"
        elif colored_room == "加工站":
            logger.info("加工站B105")
            return "factory"
        white_room = ["central", "dormitory", "meeting", "contact"]
        score = []
        for room in white_room:
            tpl = loadimg(f"{__rootdir__}/resources/room/{room}.png")
            result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            score.append(max_val)
        room = white_room[score.index(max(score))]
        if room == "central":
            logger.info("控制中枢")
        elif room == "dormitory":
            digit = cropimg(img, ((174, 24), (195, 54)))
            digit = self.detect_room_number(digit)
            if digit == 4:
                logger.info("宿舍B401")
            else:
                logger.info(f"宿舍B{digit}04")
            return f"dormitory_{digit}"
        elif room == "meeting":
            logger.info("会客室1F02")
        else:
            logger.info("办公室B205")
        return room

    def enter_room(self, room: str) -> tp.Rectangle:
        """获取房间的位置并进入"""
        success = False
        retry = 3
        while not success:
            try:
                # 获取基建各个房间的位置
                base_room = segment.base(
                    self.recog.img, self.find("control_central", strict=True)
                )
                # 将画面外的部分删去
                _room = base_room[room]

                for i in range(4):
                    _room[i, 0] = max(_room[i, 0], 0)
                    _room[i, 0] = min(_room[i, 0], self.recog.w)
                    _room[i, 1] = max(_room[i, 1], 0)
                    _room[i, 1] = min(_room[i, 1], self.recog.h)

                # 点击进入
                self.tap(_room[0], interval=1.1)
                while self.find("control_central") is not None:
                    self.tap(_room[0], interval=1.1)
                if self.detect_room() == room:
                    success = True
                else:
                    self.back()
            except Exception as e:
                retry -= 1
                self.back_to_infrastructure()
                self.wait_for_scene(Scene.INFRA_MAIN, "get_infra_scene")
                if retry <= 0:
                    raise e

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
        except Exception:
            return 24
        
    def detect_product_complete(self):
        for product in ["gold", "exp", "lmd", "ori", "oru", "trust"]:
            if pos := self.find(f"infra_{product}_complete", scope=((1230, 0), (1920, 1080))):
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
                if "name" in type:
                    return character_recognize.agent_name(img, self.recog.h)
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
            elif "name" in type:
                if ret in agent_list:
                    return ret
                if ret in ocr_error:
                    name = ocr_error[ret]
                    logger.debug(f"{ret} =====> {name}")
                    return name
                return character_recognize.agent_name(img, self.recog.h)
            else:
                return ret
        except Exception as e:
            logger.exception(e)
            return limit + 1

    def read_time(self, cord, upperlimit, error_count=0, use_digit_reader=False):
        # 刷新图片
        self.recog.update()
        try:
            if use_digit_reader:
                time_str = self.digit_reader.get_time(self.recog.gray)
            else:
                time_str = self.read_screen(self.recog.img, type="time", cord=cord)
            h, m, s = str(time_str).split(":")
            if int(m) > 60 or int(s) > 60:
                raise Exception("读取错误")
            res = int(h) * 3600 + int(m) * 60 + int(s)
            if upperlimit is not None and res > upperlimit:
                raise Exception("超过读取上限")
            else:
                return res
        except Exception:
            logger.error("读取失败")
            if error_count > 3:
                logger.exception(f"读取失败{error_count}次超过上限")
                return None
            else:
                return self.read_time(
                    cord, upperlimit, error_count + 1, use_digit_reader
                )
