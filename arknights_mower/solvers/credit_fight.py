import cv2
from scipy.signal import argrelmin

from arknights_mower.solvers.auto_fight import AutoFight
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.utils.image import cropimg, loadres
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.solver import BaseSolver


class CreditFight(BaseSolver):
    """信用作战

    从首页导航至OF-1，借助战并自动战斗
    """

    def run(self):
        logger.info("Start: 信用作战")
        self.support = False
        super().run()

    def choose_support(self):
        img = cropimg(self.recog.gray, ((0, 908), (1839, 983)))
        res = loadres("fight/choose", True)
        result = cv2.matchTemplate(img, res, cv2.TM_SQDIFF_NORMED)[0]
        threshold = 0.1
        match = []
        for i in argrelmin(result, order=100)[0]:
            if result[i] < threshold:
                match.append(i)
        logger.debug(match)
        x = match[0]
        return (x, 908), (x + 194, 983)

    def transition(self):
        if (scene := self.scene()) == Scene.INDEX:
            navi_solver = NavigationSolver(self.device, self.recog)
            navi_solver.run("OF-1")
        elif scene == Scene.OPERATOR_BEFORE:
            # 取消代理作战
            if self.recog.gray[907][1600] > 127:
                self.tap((1776, 908))
                return
            self.tap_element("ope_start", interval=2)
        elif scene == Scene.OPERATOR_SELECT:
            if self.support:
                # 开始行动
                self.tap((1655, 781))
                fight_solver = AutoFight(self.device, self.recog)
                fight_solver.run("OF-1")
            else:
                # 借助战
                self.ctap((1660, 315))
        elif scene == Scene.OPERATOR_SUPPORT:
            self.tap(self.choose_support())
            if pos := self.find("fight/use"):
                self.tap(pos)
            self.support = True
        elif scene == Scene.OPERATOR_FINISH:
            return True
        else:
            self.sleep()
