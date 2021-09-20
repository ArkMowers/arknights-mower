import cv2
import time
import numpy as np
from matplotlib import pyplot as plt

from ..__init__ import __rootdir__
from .log import logger, save_screenshot
from .matcher import FlannBasedMatcher
from . import config
from . import segment, detector


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


def threshole(img, thresh=250):
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


class Scene:
    UNKNOWN = -1  # 未知
    UNDEFINED = 0  # 未定义
    INDEX = 1  # 首页
    MATERIEL = 2  # 物资领取确认
    ANNOUNCEMENT = 3  # 公告
    MISSION = 4  # 任务列表
    NAVIGATION_BAR = 5  # 导航栏返回
    UPGRADE = 6  #  升级
    LOGIN_MAIN = 101  # 登陆页面
    LOGIN_INPUT = 102  # 登陆页面（输入）
    LOGIN_QUICKLY = 103  # 登陆页面（快速）
    LOGIN_LOADING = 104  # 登陆中
    LOGIN_START = 105  # 启动
    LOGIN_ANNOUNCE = 106  # 启动界面公告
    INFRA_MAIN = 201  # 基建全局视角
    INFRA_TODOLIST = 202  # 基建待办事项
    FRIEND_LIST_OFF = 301  # 好友列表（未选中）
    FRIEND_LIST_ON = 302  # 好友列表（选中）
    FRIEND_VISITING = 303  # 基建内访问好友
    MISSION_DAILY = 401  # 日常任务
    MISSION_WEEKLY = 402  # 周常任务
    TERMINAL_MAIN = 501  # 终端主界面
    OPERATOR_BEFORE = 602  # 作战前，关卡已选定
    OPERATOR_SELECT = 603  # 作战前，正在编队
    OPERATOR_ONGOING = 604  # 作战中
    OPERATOR_FINISH = 605  # 作战结束
    OPERATOR_INTERRUPT = 606  # 对战中断
    OPERATOR_RECOVER_POTION = 607  # 恢复理智（药剂）
    OPERATOR_RECOVER_ORIGINITE = 608  # 恢复理智（源石）
    SHOP_OTHERS = 701  # 商店除了信用兑换处以外的界面
    SHOP_CREDIT = 702  # 信用兑换处
    SHOP_CREDIT_CONFIRM = 703  # 兑换确认
    RECRUIT_MAIN = 801  # 公招主界面
    RECRUIT_TAGS = 802  # 挑选标签时
    LOADING = 9998  # 场景跳转时的等待界面
    CONFIRM = 9999  # 确认对话框


class Recognizer():

    def __init__(self, adb, debug_screencap=None):
        self.adb = adb
        self.update(debug_screencap)

    def update(self, debug_screencap=None):
        if debug_screencap is not None:
            self.screencap = debug_screencap
        else:
            self.screencap = self.adb.screencap()
        if config.SCREENSHOT_ONLYFAIL == False:
            save_screenshot(self.screencap)
        self.img = bytes2img(self.screencap)
        self.gray = bytes2img(self.screencap, True)
        self.x, self.y, _ = self.img.shape
        self.matcher = FlannBasedMatcher(self.gray)
        self.matcher_thres = FlannBasedMatcher(threshole(self.gray))
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
        elif self.find('announce_close') is not None:
            self.scene = Scene.ANNOUNCEMENT
        elif self.find('materiel') is not None:
            self.scene = Scene.MATERIEL
        elif self.find('loading') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading2') is not None:
            self.scene = Scene.LOADING
        elif self.find_thres('loading3') is not None:
            self.scene = Scene.LOADING
        elif self.find_thres('loading4') is not None:
            self.scene = Scene.LOADING
        elif self.find_thres('loading5') is not None:
            self.scene = Scene.LOADING
        elif self.find('ope_plan') is not None:
            self.scene = Scene.OPERATOR_BEFORE
        elif self.find('ope_select_start') is not None:
            self.scene = Scene.OPERATOR_SELECT
        elif self.find('ope_enemy') is not None:
            self.scene = Scene.OPERATOR_ONGOING
        elif self.find('ope_finish') is not None:
            self.scene = Scene.OPERATOR_FINISH
        elif self.find('ope_recover_potion_on') is not None:
            self.scene = Scene.OPERATOR_RECOVER_POTION
        elif self.find('ope_recover_originite_on') is not None:
            self.scene = Scene.OPERATOR_RECOVER_ORIGINITE
        elif self.find('ope_interrupt') is not None:
            self.scene = Scene.OPERATOR_INTERRUPT
        elif self.find('infra_overview') is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find('infra_todo') is not None:
            self.scene = Scene.INFRA_TODOLIST
        elif self.find('friend_list') is not None:
            self.scene = Scene.FRIEND_LIST_OFF
        elif self.find('friend_list_on') is not None:
            self.scene = Scene.FRIEND_LIST_ON
        elif self.find('friend_next') is not None:
            self.scene = Scene.FRIEND_VISITING
        elif self.find('mission_daily_on') is not None:
            self.scene = Scene.MISSION_DAILY
        elif self.find('mission_weekly_on') is not None:
            self.scene = Scene.MISSION_WEEKLY
        elif self.find('terminal_pre') is not None:
            self.scene = Scene.TERMINAL_MAIN
        elif self.find('recruit') is not None:
            if self.find('recruit_refresh') is not None:
                self.scene = Scene.RECRUIT_TAGS
            else:
                self.scene = Scene.RECRUIT_MAIN
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
        elif self.find('login_button') is not None:
            self.scene = Scene.LOGIN_INPUT
        elif self.find('login_loading') is not None:
            self.scene = Scene.LOGIN_LOADING
        elif self.find('login_iknow') is not None:
            self.scene = Scene.LOGIN_ANNOUNCE
        elif self.find('12cadpa') is not None:
            self.scene = Scene.LOGIN_START
        elif self.find('upgrade') is not None:
            self.scene = Scene.UPGRADE
        elif self.is_black():
            self.scene = Scene.LOADING
        elif detector.confirm(self.img) is not None:
            self.scene = Scene.CONFIRM
        else:
            self.scene = Scene.UNKNOWN
            # save screencap to analyse
        save_screenshot(self.screencap, subdir=str(self.scene))
        logger.debug(f'scene: {self.scene}')
        return self.scene

    def is_black(self):
        return np.max(self.gray[:, 105:-105]) <= 20

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
        logger.debug(f'find {item}')
        ret = self.matcher_thres.match(
            threshole(loadimg(f'{__rootdir__}/resources/{item}.png')), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret
