import cv2
import time
from matplotlib.pyplot import draw
import numpy as np

from utils.log import logger
from utils.matcher import FlannBasedMatcher


def bytes2img(data, grey=False):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE if grey else cv2.IMREAD_COLOR)


def loadimg(filename):
    return cv2.imread(filename, cv2.IMREAD_GRAYSCALE)


def threshole(img, thresh=250):
    _, ret = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return ret


class Status:
    UNKNOWN = -1  # 未知
    UNDEFINED = 0  # 未定义
    INDEX = 1  # 首页
    MATERIEL = 2  # 物资领取确认
    ANNOUNCEMENT = 3  # 公告
    LOADING = 4  # 场景跳转时的等待界面
    MISSION = 5  # 任务列表
    NAVIGATION_BAR = 6 # 导航栏返回
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
    OPERATOR_RECOVER = 606  # 恢复理智
    OPERATOR_INTERRUPT = 607  # 对战中断
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
        data = bytes2img(self.screencap, True)
        self.matcher = FlannBasedMatcher(data)
        self.matcher_thres = FlannBasedMatcher(threshole(data))
        self.status = Status.UNDEFINED

    def color(self, x, y):
        return bytes2img(self.screencap)[y][x]

    def skip_sec(self, interval):
        time.sleep(interval)
        self.update()

    def get_status(self):
        if self.status != Status.UNDEFINED:
            return self.status
        if self.find_thres('index_nav') is not None:
            self.status = Status.INDEX
        elif self.find('nav_index') is not None:
            self.status = Status.NAVIGATION_BAR
        elif self.find('announce_close') is not None:
            self.status = Status.ANNOUNCEMENT
        elif self.find('materiel') is not None:
            self.status = Status.MATERIEL
        elif self.find('loading') is not None:
            self.status = Status.LOADING
        elif self.find('loading2') is not None:
            self.status = Status.LOADING
        elif self.find('loading3') is not None:
            self.status = Status.LOADING
        elif self.find('yes') is not None:
            self.status = Status.YES
        elif self.find('login_awake') is not None:
            self.status = Status.LOGIN_QUICKLY
        elif self.find('login_account') is not None:
            self.status = Status.LOGIN_MAIN
        elif self.find('login_button') is not None:
            self.status = Status.LOGIN_INPUT
        elif self.find('login_loading') is not None:
            self.status = Status.LOGIN_LOADING
        elif self.find('start') is not None:
            self.status = Status.LOGIN_START
        elif self.find('infra_overview') is not None:
            self.status = Status.INFRA_MAIN
        elif self.find('infra_todo') is not None:
            self.status = Status.INFRA_TODOLIST
        elif self.find('friend_list') is not None:
            self.status = Status.FRIEND_LIST_OFF
        elif self.find('friend_list_on') is not None:
            self.status = Status.FRIEND_LIST_ON
        elif self.find('friend_next') is not None:
            self.status = Status.FRIEND_VISITING
        elif self.find('mission_daily_on') is not None:
            self.status = Status.MISSION_DAILY
        elif self.find('mission_weekly_on') is not None:
            self.status = Status.MISSION_WEEKLY
        elif self.find('terminal_pre') is not None:
            self.status = Status.TERMINAL_MAIN
        elif self.find('ope_sanity') is not None:
            self.status = Status.OPERATOR_BEFORE
        elif self.find('ope_select_start') is not None:
            self.status = Status.OPERATOR_SELECT
        elif self.find('ope_ongoing') is not None:
            self.status = Status.OPERATOR_ONGOING
        elif self.find('ope_finish') is not None:
            self.status = Status.OPERATOR_FINISH
        elif self.find('ope_recover') is not None:
            self.status = Status.OPERATOR_RECOVER
        elif self.find('ope_interrupt') is not None:
            self.status = Status.OPERATOR_INTERRUPT
        else:
            self.status = Status.UNKNOWN
            # save screencap to analyse
            with open(time.strftime('./screenshot/%Y%m%d%H%M%S.png', time.localtime()), 'wb') as f:
                f.write(self.screencap)
        logger.debug(f'status: {self.status}')
        return self.status

    def is_index(self):
        if self.status == Status.UNDEFINED:
            self.get_status()
        return self.status == Status.INDEX or self.status == Status.ANNOUNCEMENT

    def find(self, item, draw=False, scope=None):
        logger.debug(f'find {item}')
        ret = self.matcher.match(loadimg(f'./resources/{item}.png'), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret

    def find_thres(self, item, draw=False, scope=None):
        logger.debug(f'find {item}')
        ret = self.matcher_thres.match(
            threshole(loadimg(f'./resources/{item}.png')), draw=draw, scope=scope)
        if ret is None:
            return None
        return ret
