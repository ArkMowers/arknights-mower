from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene


class MissionSolver(SceneGraphSolver):
    """每日与每周任务"""

    def run(self) -> None:
        self.daily = False
        logger.info("Start: 任务")
        super().run()

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.MISSION_DAILY:
            if self.daily:
                self.tap_element("mission_weekly")
                return
            if pos := self.find("mission_collect"):
                logger.info("任务：一键收取任务")
                self.tap(pos)
                return
            self.sleep(1)
            if pos := self.find("mission_collect"):
                logger.info("任务：一键收取任务")
                self.tap(pos)
                return
            self.daily = True
            return

        if scene == Scene.MISSION_TRAINEE:
            if self.daily:
                self.tap_element("mission_weekly")
            else:
                self.tap_element("mission_daily")
            return

        if scene == Scene.MISSION_WEEKLY:
            if not self.daily:
                self.tap_element("mission_daily")
                return
            if pos := self.find("mission_collect"):
                logger.info("任务：一键收取任务")
                self.tap(pos)
                return
            self.sleep(1)
            if pos := self.find("mission_collect"):
                logger.info("任务：一键收取任务")
                self.tap(pos)
                return
            return True

        if scene in self.waiting_scene:
            self.waiting_solver()
            return

        self.scene_graph_navigation(Scene.MISSION_DAILY)
