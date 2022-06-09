from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


class MissionSolver(BaseSolver):
    """
    点击确认完成每日任务和每周任务
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self) -> None:
        # status of mission completion, 1: daily, 2: weekly
        self.checked = 0

        logger.info('Start: 任务')
        super().run()

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_element('index_mission')
        elif self.scene() == Scene.MISSION_TRAINEE:
            if self.checked & 1 == 0:
                self.tap_element('mission_daily')
            elif self.checked & 2 == 0:
                self.tap_element('mission_weekly')
            else:
                return True
        elif self.scene() == Scene.MISSION_DAILY:
            self.checked |= 1
            collect = self.find('mission_collect')
            if collect is None:
                self.sleep(1)
                collect = self.find('mission_collect')
            if collect is not None:
                logger.info('任务：一键收取任务')
                self.tap(collect)
            elif self.checked & 2 == 0:
                self.tap_element('mission_weekly')
            else:
                return True
        elif self.scene() == Scene.MISSION_WEEKLY:
            self.checked |= 2
            collect = self.find('mission_collect')
            if collect is None:
                self.sleep(1)
                collect = self.find('mission_collect')
            if collect is not None:
                logger.info('任务：一键收取任务')
                self.tap(collect)
            elif self.checked & 1 == 0:
                self.tap_element('mission_daily')
            else:
                return True
        elif self.scene() == Scene.MATERIEL:
            self.tap_element('materiel_ico')
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_mission')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')
