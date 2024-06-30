import lzma
import pickle
from time import sleep

import cv2
from scipy.signal import argrelmax
from skimage.metrics import structural_similarity

from arknights_mower import __rootdir__
from arknights_mower.solvers.secret_front import templates
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.solver import BaseSolver
from arknights_mower.utils.tile_pos import Calc, find_level
from arknights_mower.utils.vector import sa, va

with lzma.open(f"{__rootdir__}/models/avatar.pkl", "rb") as f:
    avatar = pickle.load(f)


class AutoFight(BaseSolver):
    def run(self, level_name):
        logger.info("Start: 自动战斗")
        logger.info("地图坐标计算：https://github.com/yuanyan3060/Arknights-Tile-Pos")
        level = find_level(level_name, None)
        self.calc = Calc(1920, 1080, level)
        conf = config.conf["credit_fight"]
        self.actions = [
            {"type": "SpeedUp"},
            {
                "type": "Deploy",
                "name": conf["operator"],
                "location": [
                    conf["x"],
                    conf["y"],
                ],
                "direction": conf["direction"],
            },
        ]
        self.speed = 1
        self.loading = True
        self.playing = True
        self.operators = {}
        super().run()

    def number(self, scope: tp.Scope, height: int, thres: int):
        img = cropimg(self.recog.gray, scope)
        default_height = 25
        if height != default_height:
            scale = 25 / height
            img = cv2.resize(img, None, None, scale, scale)
        img = thres2(img, thres)
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        rect.sort(key=lambda c: c[0])

        value = 0

        for x, y, w, h in rect:
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            digit = cv2.copyMakeBorder(
                digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,)
            )
            score = []
            for i in range(10):
                im = templates[i]
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                score.append(min_val)
            value = value * 10 + score.index(min(score))

        return value

    def cost(self):
        """获取部署费用，耗时1ms左右"""
        cost = self.number(((1800, 745), (1920, 805)), 52, 200)
        logger.debug(cost)
        return cost

    def kills(self):
        """获取击杀数"""
        img = cropimg(self.recog.gray, ((800, 30), (950, 60)))
        img = thres2(img, 127)
        sep = loadres("fight/kills_separator", True)
        result = cv2.matchTemplate(img, sep, cv2.TM_SQDIFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        x = min_loc[0] + 799
        kills = self.number(((800, 30), (x, 60)), 28, 127)
        logger.debug(kills)
        return kills

    def skill_ready(self, x, y):
        skill_ready = loadres("fight/skill_ready")
        h, w, _ = skill_ready.shape
        pos = self.calc.get_character_screen_pos(x, y, False, False)
        pos = int(pos.x), int(pos.y)
        img = cropimg(self.recog.img, sa(((-15, -168), (15, -138)), pos))
        result = cv2.matchTemplate(img, skill_ready, cv2.TM_SQDIFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        logger.debug(f"{min_val=} {min_loc=}")
        return min_val <= 0.2

    def in_fight(self):
        """识别是否在战斗中，耗时1ms左右"""
        img = cropimg(self.recog.img, ((725, 16), (797, 76)))
        img = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        img = cv2.inRange(img, (12, 0, 0), (16, 255, 255))
        tpl = loadres("fight/enemy", True)
        result = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        logger.debug(min_val)
        return min_val < 0.4

    def complete(self):
        img = cropimg(self.recog.gray, ((87, 268), (529, 383)))
        img = thres2(img, 200)
        tpl = loadres("fight/complete", True)
        result = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        return min_val < 0.4

    def update_operators(self):
        """识别下方干员，耗时数秒"""
        self.pause()
        self.recog.update()
        self.recog.save_screencap("auto_fight")
        y = 887
        img = cropimg(self.recog.gray, ((0, y), (1920, 905)))
        threshold = 0.7
        c = loadres("fight/c", True)
        mask = loadres("fight/c_mask", True)
        result = cv2.matchTemplate(img, c, cv2.TM_CCOEFF_NORMED, None, mask)[0]
        op = []
        for i in argrelmax(result, order=50)[0]:
            if result[i] > threshold:
                op.append(i)
        self.operators = {}
        for x in op:
            scope = sa(((-58, 53), (42, 153)), (x, y))
            tpl = cropimg(self.recog.gray, scope)
            tpl = cv2.resize(tpl, None, None, 0.5, 0.5)
            max_score = 0
            name = None
            for i, img_list in avatar.items():
                for img in img_list:
                    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                    if max_val > max_score:
                        max_score = max_val
                        name = i
            cost_scope = sa(((-13, 19), (30, 44)), (x, y))
            cost = self.number(cost_scope, 25, 80)
            self.operators[name] = {"scope": scope, "cost": cost}
            logger.info(f"{name}：{cost}费")
        self.play()

    @property
    def action(self):
        if len(self.actions) > 0:
            return self.actions[0]
        return None

    def complete_action(self):
        self.actions.pop(0)

    def toggle_play(self):
        self.device.tap((1800, 80))
        sleep(1)
        self.recog.update()
        self.recog.save_screencap("auto_fight_pause")
        img = cropimg(self.recog.gray, ((740, 480), (1180, 665)))
        img = thres2(img, 250)
        res = loadres("fight/pause", True)
        ssim = structural_similarity(img, res)
        logger.debug(ssim)
        self.playing = ssim <= 0.9

    def play(self):
        logger.info("继续")
        while not self.playing:
            self.toggle_play()

    def pause(self):
        logger.info("暂停")
        while self.playing:
            self.toggle_play()

    def toggle_speed(self):
        target = 1 if self.speed == 2 else 2
        logger.info(f"切换至{target}倍速")
        self.device.tap((1650, 80))
        self.speed = target
        self.complete_action()

    def deploy(self):
        name = self.action["name"]
        if self.cost() < self.operators[name]["cost"]:
            return
        start = self.get_pos(self.operators[name]["scope"])
        top = va(start, (0, -100))
        x, y = self.action["location"]
        pos = self.calc.get_character_screen_pos(x, y, True, False)
        pos = int(pos.x), int(pos.y)
        direction = self.action["direction"]
        logger.info(f"在({x}, {y})部署{name}，方向为{direction}")
        if direction in ["Left"]:
            dir = (-200, 0)
        elif direction in ["Right"]:
            dir = (200, 0)
        elif direction in ["Up"]:
            dir = (0, 200)
        else:
            dir = (0, -200)
        dir = va(pos, dir)
        self.device.tap(start)
        sleep(0.1)
        self.device.swipe_ext([start, top, pos], [100, 400])
        sleep(0.1)
        self.device.swipe_ext([pos, dir], [200])
        self.operators = {}
        self.complete_action()

    def transition(self):
        self.recog.update()
        if not self.in_fight():
            if self.complete():
                logger.info("行动结束")
                return True
            else:
                sleep(1)
                return
        if self.action is None:
            self.sleep(10)
            return
        if self.loading:
            self.pause()
            self.loading = False
        elif not self.operators:
            self.update_operators()
        elif self.action["type"] == "SpeedUp":
            self.toggle_speed()
        elif self.action["type"] == "Deploy":
            self.deploy()
