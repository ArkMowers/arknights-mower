from datetime import datetime, timedelta
from typing import Optional

import cv2

from arknights_mower.solvers.secret_front import templates
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.solver import BaseSolver


class OperationSolver(BaseSolver):
    def run(self, stop_time: datetime):
        logger.info("Start: 代理作战")
        self.stop_time = stop_time - timedelta(minutes=5)
        super().run()

    def number(self, scope: tp.Scope, height: Optional[int] = None):
        img = cropimg(self.recog.gray, scope)
        if height:
            scale = 25 / height
            img = cv2.resize(img, None, None, scale, scale)
        img = thres2(img, 127)
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

    def transition(self):
        if datetime.now() > self.stop_time:
            self.back_to_index()
            return True

        if (scene := self.scene()) == Scene.OPERATOR_BEFORE:
            if self.recog.gray[907][1600] < 127:
                self.tap((1776, 908))
            repeat = self.number(((1520, 890), (1545, 930)), 28)
            if repeat > 1:
                self.tap((1500, 910))
                self.tap((1500, 801))
            self.tap_element("ope_start", interval=2)
        elif scene == Scene.OPERATOR_SELECT:
            self.tap((1655, 781))
        elif scene == Scene.OPERATOR_FINISH:
            self.tap((310, 330))
        elif scene == Scene.OPERATOR_ONGOING:
            self.sleep(10)
        elif scene == Scene.OPERATOR_RECOVER_POTION:
            return True
        elif scene == Scene.OPERATOR_RECOVER_ORIGINITE:
            return True

        # 刷上次关卡
        elif scene == Scene.INDEX:
            self.tap_index_element("terminal")
        elif scene == Scene.TERMINAL_MAIN:
            self.tap_element("terminal_pre")
        else:
            self.sleep()
