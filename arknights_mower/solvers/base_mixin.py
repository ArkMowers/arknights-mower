from __future__ import annotations

from datetime import timedelta, datetime
from enum import Enum

import cv2

from arknights_mower.utils import character_recognize, segment
from arknights_mower.utils.log import logger
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils import rapidocr
from arknights_mower.data import agent_list, ocr_error


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
            ret = character_recognize.agent(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            select_name = []
            for y in ret:
                name = y[0]
                if name in agent:
                    select_name.append(name)
                    # self.get_agent_detail((y[1][0]))
                    self.tap((y[1][0]), interval=0)
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

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    def detail_filter(self, turn_on, type="not_in_dorm"):
        logger.info(f'开始 {("打开" if turn_on else "关闭")} {type} 筛选')
        self.tap((self.recog.w * 0.95, self.recog.h * 0.05), interval=1)
        if type == "not_in_dorm":
            not_in_dorm = self.find("arrange_non_check_in", score=0.9)
            if turn_on ^ (not_in_dorm is None):
                self.tap((self.recog.w * 0.3, self.recog.h * 0.5), interval=0.5)
        # 确认
        self.tap((self.recog.w * 0.8, self.recog.h * 0.8), interval=0.5)

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
                self.tap(_room[0], interval=3)
                while self.find("control_central") is not None:
                    self.tap(_room[0], interval=3)
                success = True
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

    def read_accurate_mood(self, img, cord):
        try:
            img = img[cord[1] : cord[3], cord[0] : cord[2]]
            # Convert the image to grayscale
            gray_image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            blurred_image = cv2.GaussianBlur(gray_image, (5, 5), 0)

            # Threshold the image to isolate the progress bar region
            contours, hierarchy = cv2.findContours(
                blurred_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Calculate the bounding box of the progress bar
            x, y, w, h = cv2.boundingRect(contours[0])

            # Crop the progress bar region
            progress_bar = img[y : y + h, x : x + w]

            # Convert the progress bar to grayscale
            gray_pb = cv2.cvtColor(progress_bar, cv2.COLOR_BGR2GRAY)

            # Threshold the progress bar to isolate the gray fill
            ret, thresh_pb = cv2.threshold(gray_pb, 137, 255, cv2.THRESH_BINARY)

            # Calculate the ratio of colored pixels to the total number of pixels in the progress bar region
            total_pixels = w * h
            colored_pixels = cv2.countNonZero(thresh_pb)
            return colored_pixels / total_pixels * 24

        except Exception:
            return 24

    def read_screen(self, img, type="mood", limit=24, cord=None):
        if cord is not None:
            img = img[cord[1] : cord[3], cord[0] : cord[2]]
        try:
            ret = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)[0]
            logger.debug(ret)
            if not ret or not ret[0][0]:
                if "name" in type:
                    return character_recognize.agent_name(img, self.recog.h)
                raise Exception("识别失败")
            ret = ret[0][0]
            if "赤金完成" in ret:
                raise Exception("读取到赤金收取提示")
            elif "心情" in ret:
                raise Exception("识别区域错误")
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
                raise Exception(f"读取错误")
            res = int(h) * 3600 + int(m) * 60 + int(s)
            if upperlimit is not None and res > upperlimit:
                raise Exception(f"超过读取上限")
            else:
                return res
        except:
            logger.error("读取失败")
            if error_count > 3:
                logger.exception(f"读取失败{error_count}次超过上限")
                return None
            else:
                return self.read_time(
                    cord, upperlimit, error_count + 1, use_digit_reader
                )
