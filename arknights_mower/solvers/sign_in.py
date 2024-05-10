from datetime import datetime, timedelta
from typing import Optional

import cv2
import numpy as np

import arknights_mower.utils.typealias as tp
from arknights_mower import __rootdir__
from arknights_mower.utils.image import cropimg, loadimg, saveimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.matcher import ORB
from arknights_mower.utils.solver import BaseSolver


class TaskManager:
    def __init__(self):
        self.task_list = ["back_to_index"]

    @property
    def task(self):
        return self.task_list[0] if self.task_list else None

    def add(self, task: str, year: int, month: int, day: int):
        if datetime.now() > datetime(year, month, day):
            return
        self.task_list.insert(-1, task)

    def complete(self, task: Optional[str]):
        task = task or self.task
        if task in self.task_list:
            self.task_list.remove(task)


class SignInSolver(BaseSolver):
    def run(self) -> None:
        logger.info("Start: 签到活动")
        self.back_to_index()
        self.tm = TaskManager()
        self.tm.add("monthly_card", 2024, 6, 1)  # 五周年专享月卡
        self.tm.add("orundum", 2024, 5, 15)  # 限时开采许可
        self.tm.add("headhunting", 2024, 5, 15)  # 每日赠送单抽
        self.tm.add("ann5", 2024, 5, 15)  # 五周年庆典签到活动
        self.tm.add("ep14", 2024, 5, 22)  # 第十四章慈悲灯塔物资领取

        self.failure = 0
        self.in_progress = False
        self.start_time = datetime.now()
        super().run()

    def notify(self, msg):
        logger.info(msg)
        self.recog.save_screencap("sign_in")
        if hasattr(self, "send_message_config") and self.send_message_config:
            self.send_message(msg, attach_image=self.recog.img)

    def handle_unknown(self):
        self.failure += 1
        if self.failure > 30:
            self.notify("签到任务执行失败！")
            self.back_to_index()
            return True
        self.sleep()

    def transition(self) -> bool:
        if datetime.now() - self.start_time > timedelta(minutes=2):
            self.notify("签到任务超时！")
            self.back_to_index()
            return True
        if not self.tm.task:
            return True

        if self.find("connecting"):
            return self.handle_unknown()
        elif self.recog.detect_index_scene():
            if self.tm.task == "back_to_index":
                self.tm.complete("back_to_index")
                return True
            elif self.tm.task == "monthly_card":
                if pos := self.find("sign_in/monthly_card/entry"):
                    self.tap(pos)
                else:
                    self.notify("未检测到五周年月卡领取入口！")
                    self.tm.complete("monthly_card")
            elif self.tm.task == "orundum":
                if pos := self.find("sign_in/orundum/entry"):
                    self.tap(pos)
                else:
                    self.notify("未检测到限时开采许可入口！")
                    self.tm.complete("orundum")
            elif self.tm.task == "headhunting":
                self.tap_index_element("headhunting")
            elif self.tm.task == "ann5":
                if pos := self.find("sign_in/ann5/entry"):
                    self.tap(pos)
                else:
                    self.notify("未检测到五周年庆典签到活动入口！")
                    self.tm.complete("ann5")
            elif self.tm.task == "ep14":
                self.tap_index_element("terminal")
            else:
                return True
        elif self.find("sign_in/monthly_card/banner"):
            if self.tm.task == "monthly_card":
                if pos := self.find("sign_in/monthly_card/button_ok"):
                    self.ctap("monthly_card", pos)
                else:
                    self.notify("今天的五周年专享月卡已经领取过了")
                    self.tm.complete("monthly_card")
                    self.back()
            else:
                self.back()
        elif self.find("materiel_ico"):
            if self.tm.task == "monthly_card":
                self.notify("成功领取五周年专享月卡")
                self.tm.complete("monthly_card")
            elif self.tm.task == "orundum":
                self.notify("成功开采合成玉")
                self.in_progress = False
                self.tm.complete("orundum")
            elif self.tm.task == "ann5":
                self.notify("成功领取五周年庆典签到活动奖励")
            elif self.tm.task == "ep14":
                self.notify("成功领取理智小样和材料箱子")
                self.tm.complete("ep14")
            self.tap((960, 960))
        elif self.find("sign_in/orundum/banner"):
            if self.tm.task == "orundum":
                if pos := self.find("sign_in/orundum/button_start", score=0.6):
                    self.in_progress = True
                    self.tap(pos)
                elif self.find("sign_in/orundum/button_complete"):
                    if self.in_progress:
                        self.sleep()
                    else:
                        self.notify("今天的限时开采活动已经做完了")
                        self.tm.complete("orundum")
                        self.back()
                else:
                    self.sleep()
            else:
                self.back()
        elif pos := self.find("sign_in/headhunting/button"):
            if self.tm.task == "headhunting":
                if self.find("sign_in/headhunting/banner"):
                    if self.find("sign_in/headhunting/available"):
                        self.tap(pos, x_rate=0.25)
                    else:
                        self.notify("今天的赠送单抽已经抽完了")
                        self.tm.complete("headhunting")
                        self.back()
                elif self.find("sign_in/headhunting/banner_exclusive"):
                    self.tap((1880, 590))
                else:
                    self.notify("何以为我卡池已关闭")
                    self.tm.complete("headhunting")
                    self.back()
            else:
                self.back()
        elif self.find("sign_in/headhunting/dialog"):
            if self.tm.task == "headhunting":
                self.tap((1263, 744))
            else:
                self.tap((663, 741))
        elif pos := self.find("skip"):
            self.ctap("skip", pos)
        elif self.find(
            "sign_in/headhunting/contract",
            scope=((1550, 650), (1920, 850)),
            score=0.1,
        ):
            if self.tm.task == "headhunting":
                self.notify("成功抽完赠送单抽")
                self.tm.complete("headhunting")
            self.tap((960, 540))
        elif self.find("sign_in/ann5/banner"):
            if self.tm.task == "ann5":
                img = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
                img = cv2.inRange(img, (8, 150, 0), (8, 255, 255))
                tpl = np.zeros((100, 100), dtype=np.uint8)
                tpl[:] = (255,)
                result = cv2.matchTemplate(img, tpl, cv2.TM_CCORR_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                if max_val > 0.9:
                    self.in_progress = True
                    self.ctap("ann5", (max_loc[0] + 50, max_loc[1] + 50))
                else:
                    if not self.in_progress:
                        self.notify("五周年庆典签到活动奖励已领完")
                    self.in_progress = False
                    self.tm.complete("ann5")
                    self.back()
            else:
                self.back()
        elif self.find("sign_in/ann5/phono"):
            if self.tm.task == "ann5":
                self.notify("成功领取PhonoR-0小车")
            self.ctap("phono", (960, 540))
        elif self.find("sign_in/ann5/savage"):
            if self.tm.task == "ann5":
                self.notify("成功领取暴行皮肤")
            self.ctap("skin", (960, 540))
        elif self.find("terminal_pre"):
            if self.tm.task == "ep14":
                img = loadimg(
                    f"{__rootdir__}/resources/sign_in/ep14/terminal.jpg", True
                )
                kp1, des1 = ORB.detectAndCompute(img, None)
                kp2, des2 = ORB.detectAndCompute(self.recog.gray, None)
                FLANN_INDEX_LSH = 6
                index_params = dict(
                    algorithm=FLANN_INDEX_LSH,
                    table_number=6,  # 12
                    key_size=12,  # 20
                    multi_probe_level=1,  # 2
                )
                search_params = dict(checks=50)
                flann = cv2.FlannBasedMatcher(index_params, search_params)
                matches = flann.knnMatch(des1, des2, k=2)
                GOOD_DISTANCE_LIMIT = 0.7
                good = []
                for pair in matches:
                    if (len_pair := len(pair)) == 2:
                        x, y = pair
                        if x.distance < GOOD_DISTANCE_LIMIT * y.distance:
                            good.append(x)
                    elif len_pair == 1:
                        good.append(pair[0])
                good = sorted(good, key=lambda x: x.distance)
                debug_img = cv2.drawMatches(
                    img,
                    kp1,
                    self.recog.gray,
                    kp2,
                    good[:10],
                    None,
                    flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
                )
                saveimg(debug_img, "navigation")
                self.tap(kp2[good[0].trainIdx].pt)
            else:
                self.back()
        elif self.find("sign_in/ep14/banner"):
            if self.tm.task == "ep14":
                self.ctap("ep14", (157, 215))
            else:
                self.back()
        elif self.find("sign_in/ep14/details"):
            if self.tm.task == "ep14":
                self.notify("理智小样和材料箱子领完啦")
                self.tm.complete("ep14")
            self.back()
        else:
            return self.handle_unknown()
