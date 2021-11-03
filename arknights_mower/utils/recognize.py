import numpy as np
import cv2

from ..__init__ import __rootdir__
from . import config, detector
from .log import logger, save_screenshot
from .scene import Scene, SceneComment
from .image import bytes2img, loadimg, threshole
from .matcher import Matcher


class RecognizeError(Exception):
    pass


class Recognizer():

    def __init__(self, adb, debug_screencap=None):
        self.adb = adb
        self.update(debug_screencap)

    def update(self, debug_screencap=None, matcher=True):
        while True:
            try:
                if debug_screencap is not None:
                    self.screencap = debug_screencap
                else:
                    self.screencap = self.adb.screencap()
                self.img = bytes2img(self.screencap)
                self.gray = bytes2img(self.screencap, True)
                self.h, self.w, _ = self.img.shape
                self.matcher = Matcher(self.gray) if matcher else None
                self.scene = Scene.UNDEFINED
                break
            except cv2.error as e:
                logger.warning(e)
                continue

    def color(self, x, y):
        return self.img[y][x]

    def get_scene(self):
        if self.scene != Scene.UNDEFINED:
            return self.scene
        if self.find('index_nav', thres=250, scope=((0, 0), (100+self.w//4, self.h//10))) is not None:
            self.scene = Scene.INDEX
        elif self.find('nav_index') is not None:
            self.scene = Scene.NAVIGATION_BAR
        elif self.find('materiel_ico') is not None:
            self.scene = Scene.MATERIEL
        elif self.find('read_mail') is not None:
            self.scene = Scene.MAIL
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
        elif self.find('ope_agency_going') is not None:
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
        elif self.find('ope_giveup') is not None:
            self.scene = Scene.OPERATOR_GIVEUP
        elif self.find('friend_list_on') is not None:
            self.scene = Scene.FRIEND_LIST_ON
        elif self.find('credit_visiting') is not None:
            self.scene = Scene.FRIEND_VISITING
        elif self.find('infra_overview') is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find('infra_todo') is not None:
            self.scene = Scene.INFRA_TODOLIST
        elif self.find('clue') is not None:
            self.scene = Scene.INFRA_CONFIDENTIAL
        elif self.find('infra_overview_in') is not None:
            self.scene = Scene.INFRA_ARRANGE
        elif self.find('hidden_eye', thres=250, scope=((self.w//4*3, self.h//4*3), (self.w, self.h))) is not None:
            self.scene = Scene.INFRA_DETAILS
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
        elif self.find('agent_unlock') is not None:
            self.scene = Scene.SHOP_CREDIT
        elif self.find('shop_credit_2') is not None:
            self.scene = Scene.SHOP_OTHERS
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
        elif self.find('login_captcha') is not None:
            self.scene = Scene.LOGIN_INPUT
        elif self.find('main_theme') is not None:
            self.scene = Scene.TERMINAL_MAIN_THEME
        elif self.find('episode') is not None:
            self.scene = Scene.TERMINAL_EPISODE
        elif self.find('biography') is not None:
            self.scene = Scene.TERMINAL_BIOGRAPHY
        elif self.find('collection') is not None:
            self.scene = Scene.TERMINAL_COLLECTION
        elif self.find('loading6') is not None:
            self.scene = Scene.LOADING
        else:
            self.scene = Scene.UNKNOWN
        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            save_screenshot(
                self.screencap, subdir=f'{self.scene}/{self.h}x{self.w}')
        logger.info(f'Scene: {self.scene}: {SceneComment[self.scene]}')
        return self.scene

    def is_black(self):
        return np.max(self.gray[:, 105:-105]) < 16

    def find(self, item, draw=False, scope=None, thres=None, judge=True):
        logger.debug(f'find {item}')
        if thres is not None:
            image = threshole(
                loadimg(f'{__rootdir__}/resources/{item}.png'), thres)
            matcher = Matcher(
                threshole(self.gray[scope[0][1]:scope[1][1], scope[0][0]:scope[1][0]], thres))
            ret = matcher.match(image, draw=draw, judge=judge)
        else:
            image = loadimg(f'{__rootdir__}/resources/{item}.png')
            matcher = self.matcher
            ret = matcher.match(image, draw=draw, scope=scope, judge=judge)
        if ret is None:
            return None
        return ret

    def score(self, item, draw=False, scope=None, thres=None):
        logger.debug(f'score {item}')
        if thres is not None:
            image = threshole(
                loadimg(f'{__rootdir__}/resources/{item}.png'), thres)
            matcher = Matcher(
                threshole(self.gray[scope[0][1]:scope[1][1], scope[0][0]:scope[1][0]], thres))
            ret = matcher.score(image, draw=draw)
        else:
            image = loadimg(f'{__rootdir__}/resources/{item}.png')
            matcher = self.matcher
            ret = matcher.score(image, draw=draw, scope=scope)
        if ret is None:
            return None
        return ret[1:]

    def nav_button(self):
        return self.find('nav_button', thres=128, scope=((0, 0), (100+self.w//4, self.h//10)))
