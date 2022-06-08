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
        logger.info('Start: 信用')
        super().run()

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_element('index_friend')
        elif self.scene() == Scene.FRIEND_LIST_OFF:
            self.tap_element('friend_list')
        elif self.scene() == Scene.FRIEND_LIST_ON:
            down = self.find('friend_list_on', strict=True)[1][1]
            scope = [(0, 0), (100000, down)]
            if not self.tap_element('friend_visit', scope=scope, detected=True):
                self.sleep(1)
        elif self.scene() == Scene.FRIEND_VISITING:
            visit_limit = self.find('visit_limit')
            if visit_limit is not None:
                return True
            visit_next = detector.visit_next(self.recog.img)
            if visit_next is not None:
                self.tap(visit_next)
            else:
                return True
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_social')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')
