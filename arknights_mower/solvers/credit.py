import cv2

from ..utils import detector
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class CreditSolver(BaseSolver):
    """
    通过线索交换自动收集信用
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self) -> None:
        logger.info("Start: 信用")
        super().run()

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.INDEX:
            self.tap_index_element("friend")
        elif scene == Scene.FRIEND_LIST_OFF:
            self.tap_element("friend_list")
        elif scene == Scene.FRIEND_LIST_ON:
            score, pos = self.template_match(
                "friend_visit",
                scope=((1460, 220), (1800, 1000)),
                method=cv2.TM_SQDIFF_NORMED,
            )
            self.tap(pos)
        elif scene == Scene.FRIEND_VISITING:
            if self.find("visit_limit"):
                return True
            if visit_next := detector.visit_next(self.recog.img):
                self.tap(visit_next)
            else:
                return True
        elif scene == Scene.LOADING:
            self.sleep(3)
        elif scene == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element("nav_social")
        elif scene != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError("Unknown scene")
