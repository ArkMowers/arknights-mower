import lzma
import pickle

import cv2

from arknights_mower import __rootdir__
from arknights_mower.utils import hot_update
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver
from arknights_mower.utils.vector import va, vs

location = {
    1: {
        "1-1": (0, 0),
        "1-2": (428, -1),
        "1-3": (700, 157),
        "1-4": (1138, 158),
        "1-5": (1600, 158),
        "1-6": (2360, -1),
        "1-7": (3073, -180),
        "1-8": (3535, -181),
        "1-9": (4288, -1),
        "1-10": (4635, 167),
        "1-11": (4965, -9),
        "1-12": (5436, -10),
    },
    "OF": {
        "OF-1": (0, 0),
        "OF-2": (738, 144),
        "OF-3": (1122, 299),
        "OF-4": (1475, 135),
        "OF-5": (2288, -45),
        "OF-6": (2737, -45),
        "OF-7": (3550, 135),
        "OF-8": (3899, 299),
    },
}


with lzma.open(f"{__rootdir__}/models/navigation.pkl", "rb") as f:
    templates = pickle.load(f)


class NavigationSolver(BaseSolver):
    def run(self, name: str):
        logger.info("Start: 关卡导航")
        self.success = False
        self.back_to_index()

        hot_update.update()
        if name in hot_update.navigation.NavigationSolver.location:
            hot_update.navigation.NavigationSolver(self.device, self.recog).run(name)
            return True

        self.name = name
        prefix = name.split("-")[0]
        self.prefix = prefix

        if name == "Annihilation":
            logger.info("剿灭导航")
        elif prefix.isdigit():
            prefix = int(prefix)
            self.prefix = prefix
            if prefix in location and name in location[prefix]:
                logger.info(f"主线关卡导航：{name}")
                if prefix < 4:
                    act = 0
                elif prefix < 9:
                    act = 1
                else:
                    act = 2
                self.act = act
            else:
                logger.error(f"暂不支持{name}")
                return False
        elif prefix in ["OF"]:
            logger.info(f'别传关卡导航："{name}"')
        else:
            logger.error(f"暂不支持{name}")
            return False

        super().run()
        return self.success

    def transition(self):
        if (scene := self.scene()) == Scene.INDEX:
            self.tap_index_element("terminal")
        elif scene == Scene.TERMINAL_MAIN:
            if self.name == "Annihilation":
                if pos := self.find("terminal_eliminate"):
                    self.tap(pos)
                else:
                    logger.info("本周剿灭已完成")
                    return True
            elif isinstance(self.prefix, int):
                self.tap_element("main_theme_small")
            elif self.prefix in ["OF"]:
                self.tap_element("biography_small")
        elif scene == Scene.OPERATOR_ELIMINATE:
            if self.name != "Annihilation":
                self.back()
                return
            self.success = True
            return True
        elif scene == Scene.TERMINAL_MAIN_THEME:
            if not isinstance(self.prefix, int):
                self.back()
                return
            act_scope = ((300, 315), (400, 370))
            if self.find("navigation/act/0", scope=act_scope):
                if pos := self.find(f"navigation/main/{self.prefix}"):
                    self.tap(pos)
                else:
                    self.device.swipe_ext(
                        ((932, 554), (1425, 554), (1425, 554)), durations=[300, 100]
                    )
                    self.recog.update()
            else:
                self.tap((230, 175), interval=2)
        elif scene == Scene.TERMINAL_BIOGRAPHY:
            if self.prefix not in ["OF"]:
                self.back()
                return
            if self.find(f"navigation/biography/{self.prefix}_banner"):
                self.tap_element("navigation/entry")
                return
            self.tap_element(f"navigation/biography/{self.prefix}_entry")
        elif scene == Scene.OPERATOR_CHOOSE_LEVEL:
            name, val, loc = "", 1, None
            prefix = self.prefix
            for i in location[prefix]:
                result = cv2.matchTemplate(
                    self.recog.gray, templates[i], cv2.TM_SQDIFF_NORMED
                )
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                if min_val < val:
                    val = min_val
                    loc = min_loc
                    name = i

            target = va(vs(loc, location[prefix][name]), location[prefix][self.name])
            if target[0] + 200 > 1920:
                self.swipe_noinertia((1400, 540), (-800, 0))
            elif target[0] < 0:
                self.swipe_noinertia((400, 540), (800, 0))
            else:
                self.success = True
                self.tap(va(target, (60, 20)))
        elif scene == Scene.OPERATOR_BEFORE:
            if self.success:
                return True
            else:
                self.back()
        elif self.get_navigation():
            self.tap_element("nav_terminal")
        elif scene == Scene.CONFIRM:
            self.success = False
            self.back_to_index()
        else:
            self.sleep()
