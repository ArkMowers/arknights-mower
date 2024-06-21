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
    "AP": {
        "AP-1": (0, 0),
        "AP-2": (416, -74),
        "AP-3": (716, -247),
        "AP-4": (964, -417),
        "AP-5": (1116, -589),
    },
    "LS": {
        "LS-1": (0, 0),
        "LS-2": (385, -34),
        "LS-3": (710, -130),
        "LS-4": (970, -257),
        "LS-5": (1138, -421),
        "LS-6": (1213, -600),
    },
    "CA": {
        "CA-1": (0, 0),
        "CA-2": (416, -73),
        "CA-3": (716, -246),
        "CA-4": (964, -417),
        "CA-5": (1116, -589),
    },
    "CE": {
        "CE-1": (0, 0),
        "CE-2": (382, -33),
        "CE-3": (709, -128),
        "CE-4": (970, -259),
        "CE-5": (1136, -420),
        "CE-6": (1210, -597),
    },
    "SK": {
        "SK-1": (0, 0),
        "SK-2": (416, -73),
        "SK-3": (716, -246),
        "SK-4": (965, -417),
        "SK-5": (1116, -589),
    },
    "PR-A": {"PR-A-1": (0, 0), "PR-A-2": (604, -283)},
    "PR-B": {"PR-B-1": (0, 0), "PR-B-2": (684, -296)},
    "PR-C": {"PR-C-1": (0, 0), "PR-C-2": (667, -231)},
}

collection_prefixs = [
    "AP",
    "LS",
    "CA",
    "CE",
    "PR",
    "SK",
]

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
        pr_prefix = ""
        if prefix == "PR":
            pr_prefix = name.split("-")[1]
        self.prefix = prefix
        self.pr_prefix = pr_prefix

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
        elif prefix in ["AP", "LS", "CA", "CE", "SK"]:
            logger.info(f'资源收集关卡导航："{name}"')
        elif prefix.split("-")[0] in ["PR"]:
            logger.info(f'芯片关卡导航："{name}"')

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
            elif self.prefix in collection_prefixs:
                self.tap_element("collection_small")
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
                    self.device.swipe_ext(((932, 554), (1425, 554), (1425, 554)), durations=[300, 100])
                    self.recog.update()
            else:
                self.tap((230, 175))
        elif scene == Scene.TERMINAL_BIOGRAPHY:
            if self.prefix not in ["OF"]:
                self.back()
                return
            if self.find(f"navigation/biography/{self.prefix}_banner"):
                self.tap_element("navigation/entry")
                return
            self.tap_element(f"navigation/biography/{self.prefix}_entry")
        elif scene == Scene.TERMINAL_COLLECTION:
            prefix = self.prefix
            if self.prefix not in collection_prefixs:
                self.back()
                return

            if self.prefix == "PR":
                prefix = self.prefix + "-" + self.pr_prefix
            if pos := self.find(f"navigation/collection/{prefix}_entry"):
                self.tap(pos)
            else:
                if self.prefix in ["AP", "CA", "CE", "SK"]:
                    self.swipe_noinertia((900, 500), (600, 0))
                if self.prefix in ["PR"]:
                    self.swipe_noinertia((900, 500), (-600, 0))
        elif scene == Scene.OPERATOR_CHOOSE_LEVEL:
            name, val, loc = "", 1, None
            prefix = self.prefix
            # 资源收集关直接按坐标点击
            if prefix in collection_prefixs:
                if self.prefix == "PR":
                    prefix = "{}-{}".format(self.prefix, self.pr_prefix)
                if pos := self.find(f"navigation/collection/{prefix}-1"):
                    self.success = True
                    self.tap(va(pos[0], location[prefix][self.name]))
                return True
            # 其余关
            for i in location[prefix]:
                result = cv2.matchTemplate(self.recog.gray, templates[i], cv2.TM_SQDIFF_NORMED)
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
