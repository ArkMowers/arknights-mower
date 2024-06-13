from arknights_mower.utils import hot_update
import cv2
import lzma
import pickle
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver
from arknights_mower import __rootdir__

main = {
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
    }
}


with lzma.open(f"{__rootdir__}/models/navigation.pkl", "rb") as f:
    templates = pickle.load(f)


class NavigationSolver(BaseSolver):
    def run(self, name):
        logger.info("Start: 关卡导航")

        self.success = False
        self.back_to_index()
        hot_update.update()
        if name in hot_update.navigation.NavigationSolver.location:
            hot_update.navigation.NavigationSolver(self.device, self.recog).run(name)
            return True
        if name == "1-7":
            self.name = name
            logger.info(f'常驻关卡导航："{name}"')
            super().run()
            return True
        logger.error(f"暂不支持{name}")
        return False

    def transition(self):
        if (scene := self.scene()) == Scene.INDEX:
            self.tap_index_element("terminal")
        elif scene == Scene.TERMINAL_MAIN:
            self.tap_element("main_theme_small")
        elif scene == Scene.TERMINAL_MAIN_THEME:
            act_scope = ((300, 315), (400, 370))
            if self.find("navigation/act/0", scope=act_scope):
                if pos := self.find("navigation/main/1"):
                    self.tap(pos)
                else:
                    self.device.swipe_ext(
                        ((932, 554), (1425, 554), (1425, 554)), durations=[300, 100]
                    )
                    self.recog.update()
            else:
                self.device.swipe_ext(
                    ((235, 177), (235, 343), (235, 343)), durations=[300, 100]
                )
                self.recog.update()
        elif self.find("navigation/episode"):
            name, val, loc = "", 1, None
            for i in range(1, len(main[1]) + 1):
                result = cv2.matchTemplate(
                    self.recog.gray, templates[f"1-{i}"], cv2.TM_SQDIFF_NORMED
                )
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                if min_val < val:
                    val = min_val
                    loc = min_loc
                    name = f"1-{i}"

            def va(a, b):
                return a[0] + b[0], a[1] + b[1]

            def vm(a, b):
                return a[0] - b[0], a[1] - b[1]

            target = va(vm(loc, main[1][name]), main[1][self.name])
            if target[0] + 200 > 1920:
                self.swipe_noinertia((1400, 540), (-800, 0))
            elif target[0] < 0:
                self.swipe_noinertia((400, 540), (800, 0))
            else:
                self.success = True
                self.tap((target[0] + 60, target[1] + 20))
        elif scene == Scene.OPERATOR_BEFORE:
            if self.success:
                return True
            else:
                self.back()
        elif self.get_navigation():
            self.tap_element("nav_terminal")
        else:
            self.sleep()
