import traceback

from ..utils import config
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import Recognizer, Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError


class MailSolver(BaseSolver):
    """
    收取邮件
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super(MailSolver, self).__init__(device, recog)

    def run(self) -> None:
        logger.info('Start: 邮件')

        self.touched = False  # if it touched
        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                if self.__run():
                    break
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
                retry_times -= 1
                self.sleep(3)
                continue
            except StrategyError as e:
                logger.error(e)
                logger.debug(traceback.format_exc())
                return
            except Exception as e:
                raise e
            retry_times = config.MAX_RETRYTIME

    def __run(self) -> bool:
        if self.scene() == Scene.INDEX:
            scope = ((0, 0), (100+self.recog.w//4, self.recog.h//10))
            nav = self.recog.find('index_nav', thres=250, scope=scope)
            self.tap(nav, 0.625)
        elif self.scene() == Scene.MAIL:
            if self.touched:
                return True
            self.touched = True
            self.tap_element('read_mail')
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.MATERIEL:
            self.tap_element('materiel_ico')
        elif self.get_navigation():
            self.tap_element('nav_index')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError
