import traceback

from ..utils import config
from ..utils import detector
from ..utils.log import logger
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError


class CreditSolver(BaseSolver):
    """
    通过线索交换自动收集信用
    """

    def __init__(self, adb=None, recog=None):
        super(CreditSolver, self).__init__(adb, recog)

    def run(self):
        logger.info('Start: 信用')

        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_friend')
                elif self.scene() == Scene.FRIEND_LIST_OFF:
                    self.tap_element('friend_list')
                elif self.scene() == Scene.FRIEND_LIST_ON:
                    down = self.recog.find('friend_list_on')[1][1]
                    scope = [(0, 0), (100000, down)]
                    if not self.tap_element('friend_visit', scope=scope, detected=True):
                        self.sleep(1)
                elif self.scene() == Scene.FRIEND_VISITING:
                    visit_limit = self.recog.find('visit_limit')
                    if visit_limit is not None:
                        break
                    visit_next = detector.visit_next(self.recog.img)
                    if visit_next is not None:
                        self.tap(visit_next)
                    else:
                        break
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap_element('nav_social')
                elif self.scene() != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
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
