from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class MailSolver(BaseSolver):
    """
    收取邮件
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self) -> None:
        # if it touched
        self.touched = False

        logger.info('Start: 邮件')
        super().run()

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            scope = ((0, 0), (100+self.recog.w//4, self.recog.h//10))
            nav = self.find('index_nav', thres=250, scope=scope)
            self.tap(nav, 0.625)
        elif self.scene() == Scene.MAIL:
            if self.touched:
                return True
            self.touched = True
            self.tap_element('read_mail')
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.scene() == Scene.MATERIEL:
            self.tap_element('materiel_ico')
        elif self.get_navigation():
            self.tap_element('nav_index')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')
