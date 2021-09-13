import cv2
import numpy as np

from ..__init__ import __rootdir__
from .log import logger, save_screenshot
from .matcher import FlannBasedMatcher
from . import config


def bytes2img(data, grey=False):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE if grey else cv2.IMREAD_COLOR)


def loadimg(filename):
    logger.debug(filename)
    return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)


def threshole(img, thresh=250):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


def credit_segment(im):
    """
    信用交易所特供的图像分割算法
    """
    x, y, z = im.shape

    def average(i):
        n, s = 0, 0
        for j in range(y):
            if im[i][j][0] == im[i][j][1] and im[i][j][0] == im[i][j][2]:
                n += 1
                s += im[i][j][0]
        return int(s / n)

    def ptp(j):
        mx = -999999
        mn = 999999
        for i in range(up, up2):
            if im[i][j][0] == im[i][j][1] and im[i][j][0] == im[i][j][2]:
                mn = min(mn, im[i][j][0])
                mx = max(mx, im[i][j][0])
        return mx - mn

    up = 0
    fg = False
    while fg == False or average(up) >= 250:
        fg |= average(up) >= 250
        up += 1

    up2 = up
    fg = False
    while fg == False or average(up2) < 220:
        fg |= average(up2) < 220
        up2 += 1

    down = x - 1
    while average(down) < 180:
        down -= 1

    right = y - 1
    while ptp(right) < 50:
        right -= 1

    left = 0
    while ptp(left) < 50:
        left += 1

    split_x = [up, (up + down) // 2, down]
    split_y = [left] + [left + (right - left) //
                        5 * i for i in range(1, 5)] + [right]

    ret = []
    for x1, x2 in zip(split_x[:-1], split_x[1:]):
        for y1, y2 in zip(split_y[:-1], split_y[1:]):
            ret.append(((y1, x1), (y2, x2)))

    logger.debug(f'credit_segment: {ret}')
    return ret


class Scene:
    UNKNOWN = -1  # 未知
    UNDEFINED = 0  # 未定义
    INDEX = 1  # 首页
    MATERIEL = 2  # 物资领取确认
    ANNOUNCEMENT = 3  # 公告
    MISSION = 4  # 任务列表
    NAVIGATION_BAR = 5  # 导航栏返回
    LOGIN_MAIN = 101  # 登陆页面
    LOGIN_INPUT = 102  # 登陆页面（输入）
    LOGIN_QUICKLY = 103  # 登陆页面（快速）
    LOGIN_LOADING = 104  # 登陆中
    LOGIN_START = 105  # 启动
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
    LOADING = 9998  # 场景跳转时的等待界面
    YES = 9999  # 确认对话框


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
        data = bytes2img(self.screencap, True)
        self.matcher = FlannBasedMatcher(data)
        self.matcher_thres = FlannBasedMatcher(threshole(data))
        self.scene = Scene.UNDEFINED

    def color(self, x, y):
        return bytes2img(self.screencap)[y][x]

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
        elif self.find('yes') is not None:
            self.scene = Scene.YES
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
        elif self.find('start') is not None:
            self.scene = Scene.LOGIN_START
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
        elif self.find('ope_plan') is not None:
            self.scene = Scene.OPERATOR_BEFORE
        elif self.find('ope_select_start') is not None:
            self.scene = Scene.OPERATOR_SELECT
        elif self.find('ope_ongoing') is not None:
            self.scene = Scene.OPERATOR_ONGOING
        elif self.find('ope_finish') is not None:
            self.scene = Scene.OPERATOR_FINISH
        elif self.find('ope_recover_potion_on') is not None:
            self.scene = Scene.OPERATOR_RECOVER_POTION
        elif self.find('ope_recover_originite_on') is not None:
            self.scene = Scene.OPERATOR_RECOVER_ORIGINITE
        elif self.find('ope_interrupt') is not None:
            self.scene = Scene.OPERATOR_INTERRUPT
        else:
            self.scene = Scene.UNKNOWN
            # save screencap to analyse
            save_screenshot(self.screencap)
        logger.debug(f'scene: {self.scene}')
        return self.scene

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
