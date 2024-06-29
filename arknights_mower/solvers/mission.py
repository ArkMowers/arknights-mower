from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene


class MissionSolver(SceneGraphSolver):
    """每日任务与每周任务"""

    def run(self) -> None:
        # status of mission completion, 1: daily, 2: weekly
        self.checked = 0

        logger.info("Start: 任务")
        super().run()

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.MISSION_DAILY:
            self.checked |= 1
            collect = self.find("mission_collect")
            if collect is None:
                self.sleep(1)
                collect = self.find("mission_collect")
            if collect is not None:
                logger.info("任务：一键收取任务")
                self.tap(collect)
            elif self.checked & 2 == 0:
                self.tap_element("mission_weekly")
            else:
                return True
        elif scene == Scene.MISSION_WEEKLY:
            self.checked |= 2
            collect = self.find("mission_collect")
            if collect is None:
                self.sleep(1)
                collect = self.find("mission_collect")
            if collect is not None:
                logger.info("任务：一键收取任务")
                self.tap(collect)
            elif self.checked & 1 == 0:
                self.tap_element("mission_daily")
            else:
                return True
        elif scene in [Scene.UNKNOWN, Scene.LOADING, Scene.CONNECTING]:
            self.waiting_solver(scene, sleep_time=1)
        else:
            self.scene_graph_navigation(Scene.MISSION_DAILY)
