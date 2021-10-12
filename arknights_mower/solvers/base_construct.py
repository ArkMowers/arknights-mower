import traceback

from ..utils import detector
from ..utils.log import logger
from ..utils.config import MAX_RETRYTIME
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError


class BaseConstructSolver(BaseSolver):
    """
    收集基建的产物：物资、赤金、信赖
    """

    def __init__(self, adb=None, recog=None):
        super(BaseConstructSolver, self).__init__(adb, recog)

    def run(self):
        logger.info('Start: 基建')
        
        retry_times = MAX_RETRYTIME
        while retry_times > 0:
            try:
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_infrastructure')
                elif self.scene() == Scene.INFRA_MAIN:
                    notification = detector.infra_notification(self.recog.img)
                    if notification is None:
                        self.sleep(1)
                        notification = detector.infra_notification(self.recog.img)
                    if notification is not None:
                        self.tap(notification)
                    else:
                        break
                elif self.scene() == Scene.INFRA_TODOLIST:
                    tapped = False
                    trust = self.recog.find('infra_collect_trust')
                    if trust is not None:
                        logger.info('基建：干员信赖')
                        self.tap(trust)
                        tapped = True
                    bill = self.recog.find('infra_collect_bill')
                    if bill is not None:
                        logger.info('基建：订单交付')
                        self.tap(bill)
                        tapped = True
                    factory = self.recog.find('infra_collect_factory')
                    if factory is not None:
                        logger.info('基建：可收获')
                        self.tap(factory)
                        tapped = True
                    if not tapped:
                        break
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap_element('nav_infrastructure')
                elif self.scene() != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError:
                logger.warn('识别出了点小差错 qwq')
                retry_times -= 1
                self.sleep(3)
                continue
            except StrategyError as e:
                logger.error(e)
                logger.debug(traceback.format_exc())
                return
            except Exception as e:
                raise e
            retry_times = MAX_RETRYTIME
