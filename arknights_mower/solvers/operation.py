from datetime import datetime, timedelta
from typing import Optional

import cv2

from arknights_mower.solvers.secret_front import templates
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.solver import BaseSolver


class OperationSolver(BaseSolver):
    def run(self, stop_time: datetime):
        logger.info("Start: 代理作战")
        self.stop_time = stop_time - timedelta(minutes=5)
        self.sanity_drain = False
        super().run()
        return self.sanity_drain

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
            if self.recog.gray[65][1333] < 200:
                self.sleep()
                return
            if self.recog.gray[907][1600] < 127:
                self.tap((1776, 908))
                return
            repeat = self.number(((1520, 890), (1545, 930)), 28)
            if repeat > 1:
                self.tap((1500, 910))
                self.tap((1500, 801))
                return
            self.tap_element("ope_start", interval=2)
        elif scene == Scene.OPERATOR_SELECT:
            self.tap((1655, 781))
        elif scene == Scene.OPERATOR_FINISH:
            self.tap((310, 330))
        elif scene == Scene.OPERATOR_ONGOING:
            self.sleep(10)
        elif scene == Scene.OPERATOR_RECOVER_POTION:
            if config.conf["maa_expiring_medicine"]:
                img = cropimg(self.recog.img, ((1015, 515), (1170, 560)))
                img = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
                img = cv2.inRange(img, (170, 0, 0), (174, 255, 255))
                count = cv2.countNonZero(img)
                logger.debug(count)
                if count > 3000:
                    logger.info("使用即将过期的理智药")
                    self.tap((1635, 865))
                    return
            self.sanity_drain = True
            return True
        elif scene == Scene.OPERATOR_RECOVER_ORIGINITE:
            self.sanity_drain = True
            return True
        elif scene == Scene.OPERATOR_ELIMINATE:
            if self.find("ope_agency_lock"):
                logger.error("无法代理当期剿灭")
                self.sanity_drain = True
                return True
            if self.find("1800"):
                logger.info("本周剿灭已完成")
                self.sanity_drain = True
                return True
            if pos := self.find("ope_elimi_agency"):
                self.tap(pos)
                return
            self.tap_element("ope_start", interval=2)
        elif scene == Scene.OPERATOR_ELIMINATE_AGENCY:
            self.tap_element("ope_elimi_agency_confirm", interval=2)
        elif scene == Scene.CONFIRM:
            self.sanity_drain = False
            self.back_to_index()
        elif scene == Scene.UPGRADE:
            self.tap((960, 540))
        else:
            self.sleep()
