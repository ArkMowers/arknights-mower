import cv2

from arknights_mower.utils.device import Device
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Recognizer, Scene
from arknights_mower.utils.solver import BaseSolver


class CreditSolver(BaseSolver):
    """
    通过线索交换自动收集信用
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self) -> None:
        logger.info("Start: 信用")
        self.wait_times = 5
        return super().run()

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.INDEX:
            self.tap_index_element("friend")
        elif scene == Scene.FRIEND_LIST_OFF:
            self.tap_element("friend_list")
        elif scene == Scene.FRIEND_LIST_ON:
            left, top = 1460, 220
            img = cropimg(self.recog.gray, ((left, top), (1800, 1000)))
            img = thres2(img, 254)
            tpl = loadres("friend_visit", True)
            result = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            h, w = tpl.shape
            pos = (
                (min_loc[0] + left, min_loc[1] + top),
                (min_loc[0] + left + w, min_loc[1] + top + h),
            )
            logger.debug(f"{min_val=}, {pos=}")
            if min_val < 0.5:
                self.tap(pos)
            else:
                self.sleep()
        elif self.find("visit_limit"):
            return True
        elif scene == Scene.FRIEND_VISITING:
            if clue_next := self.find("clue_next"):
                x, y = self.get_pos(clue_next, x_rate=0.5, y_rate=0.85)
                hsv = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
                if abs(hsv[y][x][0] - 12) < 3:
                    self.wait_times = 5
                    self.tap(clue_next)
                else:
                    return True
            else:
                if self.wait_times > 0:
                    self.wait_times -= 1
                    self.sleep()
                else:
                    return True
        elif scene in [Scene.LOADING, Scene.CONNECTING]:
            self.sleep()
        elif self.get_navigation():
            self.tap_element("nav_social")
        elif scene != Scene.UNKNOWN:
            self.back_to_index()
        else:
            self.sleep()
