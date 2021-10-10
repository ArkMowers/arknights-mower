import cv2
import time
import numpy as np
from matplotlib import pyplot as plt

from ..__init__ import __rootdir__
from .log import logger, save_screenshot
from .matcher import Matcher
from . import config
from . import segment, detector
from .scene import Scene, SceneComment


class RecognizeError(Exception):
    pass


def bytes2img(data, gray=False):
    if gray:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    else:
        return cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def loadimg(filename):
    logger.debug(filename)
    return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)


def threshole(img, thresh):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


# def detect_circle_small(img, draw=False, scope=None, maxRadius=40):

#     (x1, y1), (x2, y2) = scope
#     img = img[x1: x2, y1: y2]

#     coins_circle = cv2.HoughCircles(img,
#                                     cv2.HOUGH_GRADIENT,
#                                     2,
#                                     50,
#                                     param1=10,
#                                     param2=30,
#                                     minRadius=1,
#                                     maxRadius=40)

#     print(coins_circle)

#     circles = coins_circle.reshape(-1, 3)
#     circles = np.uint16(np.around(circles))

#     for i in circles:
#         ret = cv2.circle(img, (i[0], i[1]), i[2], (128, 128, 128), 3)   # 画圆
#         ret = cv2.circle(img, (i[0], i[1]), 2, (128, 128, 128), 3)     # 画圆心

#     # cv2.
#     # cv2.imshow('', img)

#     # cv2.imencode('.png', im)

#     plt.imshow(ret, 'gray')
#     plt.show()

#     # time.sleep(10000)
#     # cv2.waitKey(0)
#     # cv2.destroyAllWindows()


class Recognizer():

    def __init__(self, adb, debug_screencap=None):
        self.adb = adb
        self.update(debug_screencap)

    def update(self, debug_screencap=None):
        if debug_screencap is not None:
            self.screencap = debug_screencap
        else:
            self.screencap = self.adb.screencap()
        self.img = bytes2img(self.screencap)
        self.gray = bytes2img(self.screencap, True)
        self.h, self.w, _ = self.img.shape
        self.matcher = Matcher(self.gray)
        self.matcher_thres = Matcher(threshole(self.gray, 250))
        self.scene = Scene.UNDEFINED

    def color(self, x, y):
        return self.img[y][x]

    def get_scene(self):
        if self.scene != Scene.UNDEFINED:
            return self.scene
        if self.find_thres('index_nav') is not None:
            self.scene = Scene.INDEX
        elif self.find('nav_index') is not None:
            self.scene = Scene.NAVIGATION_BAR
        elif self.find('materiel_ico') is not None:
            self.scene = Scene.MATERIEL
        elif self.find('loading') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading2') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading3') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading4') is not None:
            self.scene = Scene.LOADING
        elif self.is_black():
            self.scene = Scene.LOADING
        elif self.find('ope_plan') is not None:
            self.scene = Scene.OPERATOR_BEFORE
        elif self.find('ope_select_start') is not None:
            self.scene = Scene.OPERATOR_SELECT
        elif self.find('ope_top') is not None:
            self.scene = Scene.OPERATOR_ONGOING
        elif self.find('ope_elimi_finished') is not None:
            self.scene = Scene.OPERATOR_ELIMINATE_FINISH
        elif self.find('ope_finish') is not None:
            self.scene = Scene.OPERATOR_FINISH
        elif self.find('ope_recover_potion_on') is not None:
            self.scene = Scene.OPERATOR_RECOVER_POTION
        elif self.find('ope_recover_originite_on') is not None:
            self.scene = Scene.OPERATOR_RECOVER_ORIGINITE
        elif self.find('double_confirm') is not None:
            self.scene = Scene.DOUBLE_CONFIRM
        elif self.find('ope_firstdrop') is not None:
            self.scene = Scene.OPERATOR_DROP
        elif self.find('ope_eliminate') is not None:
            self.scene = Scene.OPERATOR_ELIMINATE
        elif self.find('friend_list_on') is not None:
            self.scene = Scene.FRIEND_LIST_ON
        elif self.find('credit_visiting') is not None:
            self.scene = Scene.FRIEND_VISITING
        elif self.find('infra_overview') is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find('infra_todo') is not None:
            self.scene = Scene.INFRA_TODOLIST
        elif self.find('friend_list') is not None:
            self.scene = Scene.FRIEND_LIST_OFF
        elif self.find('mission_daily_on') is not None:
            self.scene = Scene.MISSION_DAILY
        elif self.find('mission_weekly_on') is not None:
            self.scene = Scene.MISSION_WEEKLY
        elif self.find('terminal_pre') is not None:
            self.scene = Scene.TERMINAL_MAIN
        elif self.find('open_recruitment') is not None:
            self.scene = Scene.RECRUIT_MAIN
        elif self.find('recruiting_instructions') is not None:
            self.scene = Scene.RECRUIT_TAGS
        elif self.find('agent_token') is not None:
            self.scene = Scene.RECRUIT_AGENT
        elif self.find('shop_credit') is not None:
            self.scene = Scene.SHOP_OTHERS
        elif self.find('shop_credit_on') is not None:
            self.scene = Scene.SHOP_CREDIT
        elif self.find('shop_cart') is not None:
            self.scene = Scene.SHOP_CREDIT_CONFIRM
        elif self.find('login_awake') is not None:
            self.scene = Scene.LOGIN_QUICKLY
        elif self.find('login_account') is not None:
            self.scene = Scene.LOGIN_MAIN
        elif self.find('login_loading') is not None:
            self.scene = Scene.LOGIN_LOADING
        elif self.find('login_iknow') is not None:
            self.scene = Scene.LOGIN_ANNOUNCE
        elif self.find('12cadpa') is not None:
            self.scene = Scene.LOGIN_START
        elif detector.announcement_close(self.img) is not None:
            self.scene = Scene.ANNOUNCEMENT
        elif self.find('skip') is not None:
            self.scene = Scene.SKIP
        elif self.find('upgrade') is not None:
            self.scene = Scene.UPGRADE
        elif detector.confirm(self.img) is not None:
            self.scene = Scene.CONFIRM
        elif self.find('login_button') is not None:
            self.scene = Scene.LOGIN_INPUT
        elif self.find('main_theme') is not None:
            self.scene = Scene.TERMINAL_MAIN_THEME
        elif self.find('episode') is not None:
            self.scene = Scene.TERMINAL_EPISODE
        elif self.find('biography') is not None:
            self.scene = Scene.TERMINAL_BIOGRAPHY
        elif self.find('collection') is not None:
            self.scene = Scene.TERMINAL_COLLECTION
        else:
            self.scene = Scene.UNKNOWN
        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            save_screenshot(self.screencap, subdir=f'{self.scene}/{self.h}x{self.w}')
        logger.info(f'Scene: {self.scene}: {SceneComment[self.scene]}')
        return self.scene

    def is_black(self):
        return np.max(self.gray[:, 105:-105]) < 16

    def is_login(self):
        return not (self.get_scene() // 100 == 1 or self.get_scene() // 100 == 99)

    def find(self, item, draw=False, scope=None):
        logger.debug(f'find {item}')
        ret = self.matcher.match(
            loadimg(f'{__rootdir__}/resources/{item}.png'), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret

    def find_thres(self, item, draw=False, scope=None):
        logger.debug(f'find_thres {item}')
        ret = self.matcher_thres.match(
            threshole(loadimg(f'{__rootdir__}/resources/{item}.png'), 250), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret

    def score(self, item, draw=False, scope=None):
        logger.debug(f'score {item}')
        ret = self.matcher.score(
            loadimg(f'{__rootdir__}/resources/{item}.png'), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret[1:]

    def score_thres(self, item, draw=False, scope=None):
        logger.debug(f'score_thres {item}')
        ret = self.matcher_thres.score(
            threshole(loadimg(f'{__rootdir__}/resources/{item}.png'), 250), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret[1:]
