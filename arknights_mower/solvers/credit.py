import cv2

from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene


class CreditSolver(SceneGraphSolver):
    def run(self) -> None:
        logger.info("Start: 访问好友")
        self.wait_times = 5
        return super().run()

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.FRIEND_LIST_ON:
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
            logger.info("今日参与交流已达上限")
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
        elif scene in [Scene.UNKNOWN, Scene.LOADING, Scene.CONNECTING]:
            self.waiting_solver(scene, sleep_time=1)
        else:
            self.scene_graph_navigation(Scene.FRIEND_LIST_ON)
