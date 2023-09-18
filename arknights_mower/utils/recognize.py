from __future__ import annotations

import time
from typing import List, Optional

import cv2
import numpy as np

from .. import __rootdir__
from . import config, detector
from . import typealias as tp
from .device import Device
from .image import bytes2img, cropimg, loadimg, thres2
from .log import logger, save_screenshot
from .matcher import Matcher
from .scene import Scene, SceneComment


class RecognizeError(Exception):
    pass


class Recognizer(object):

    def __init__(self, device: Device, screencap: bytes = None) -> None:
        self.device = device
        self.start(screencap)

    def start(self, screencap: bytes = None, build: bool = True) -> None:
        """ init with screencap, build matcher  """
        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                if screencap is not None:
                    self.screencap = screencap
                else:
                    self.screencap = self.device.screencap()
                self.img = bytes2img(self.screencap, False)
                self.gray = bytes2img(self.screencap, True)
                self.h, self.w, _ = self.img.shape
                self.matcher = Matcher(self.gray) if build else None
                self.scene = Scene.UNDEFINED
                return
            except cv2.error as e:
                logger.warning(e)
                retry_times -= 1
                time.sleep(1)
                continue
        raise RuntimeError('init Recognizer failed')

    def update(self, screencap: bytes = None, rebuild: bool = True) -> None:
        """ rebuild matcher """
        self.start(screencap, rebuild)

    def color(self, x: int, y: int) -> tp.Pixel:
        """ get the color of the pixel """
        return self.img[y][x]

    def save_screencap(self, folder):
        save_screenshot(self.screencap, subdir=f'{folder}/{self.h}x{self.w}')

    def get_scene(self) -> int:
        """ get the current scene in the game """
        if self.scene != Scene.UNDEFINED:
            return self.scene
        if self.find('connecting', scope=((self.w//2, self.h//10*8), (self.w//4*3, self.h))) is not None:
            self.scene = Scene.CONNECTING
        elif self.find('index_nav', thres=250, scope=((0, 0), (100+self.w//4, self.h//10))) is not None:
            self.scene = Scene.INDEX
        elif self.find('nav_index') is not None:
            self.scene = Scene.NAVIGATION_BAR
        elif self.find('login_new',score= 0.8) is not None:
            self.scene = Scene.LOGIN_NEW
        elif self.find('login_bilibili_new',score= 0.8) is not None:
            self.scene = Scene.LOGIN_NEW_B
        elif self.find('close_mine') is not None:
            self.scene = Scene.CLOSE_MINE
        elif self.find('check_in') is not None:
            self.scene = Scene.CHECK_IN
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
            if self.find('network_check') is not None:
                self.scene = Scene.NETWORK_CHECK
            else:
                self.scene = Scene.DOUBLE_CONFIRM
        elif self.find('ope_firstdrop') is not None:
            self.scene = Scene.OPERATOR_DROP
        elif self.find('ope_eliminate') is not None:
            self.scene = Scene.OPERATOR_ELIMINATE
        elif self.find('ope_elimi_agency_panel') is not None:
            self.scene = Scene.OPERATOR_ELIMINATE_AGENCY
        elif self.find('ope_giveup') is not None:
            self.scene = Scene.OPERATOR_GIVEUP
        elif self.find('ope_failed') is not None:
            self.scene = Scene.OPERATOR_FAILED
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
        elif self.find('arrange_check_in') or self.find('arrange_check_in_on') is not None:
            self.scene = Scene.INFRA_DETAILS
        elif self.find('infra_overview_in') is not None:
            self.scene = Scene.INFRA_ARRANGE
        elif self.find('arrange_confirm') is not None:
            self.scene = Scene.INFRA_ARRANGE_CONFIRM
        elif self.find('friend_list') is not None:
            self.scene = Scene.FRIEND_LIST_OFF
        elif self.find("mission_trainee_on") is not None:
            self.scene = Scene.MISSION_TRAINEE
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
        elif self.find('agent_token_1080_1440') is not None:
            self.scene = Scene.RECRUIT_AGENT
        elif self.find('agent_token_900_1440') is not None:
            self.scene = Scene.RECRUIT_AGENT
        elif self.find('agent_unlock') is not None:
            self.scene = Scene.SHOP_CREDIT
        elif self.find('shop_credit_2') is not None:
            self.scene = Scene.SHOP_OTHERS
        elif self.find('shop_cart') is not None:
            self.scene = Scene.SHOP_CREDIT_CONFIRM
        elif self.find('shop_assist') is not None:
            self.scene = Scene.SHOP_ASSIST
        elif self.find('login_logo') is not None and self.find('hypergryph') is not None:
            if self.find('login_awake') is not None:
                self.scene = Scene.LOGIN_QUICKLY
            elif self.find('login_account') is not None:
                self.scene = Scene.LOGIN_MAIN
            elif self.find('login_iknow') is not None:
                self.scene = Scene.LOGIN_ANNOUNCE
            else:
                self.scene = Scene.LOGIN_MAIN_NOENTRY
        elif self.find('register') is not None:
            self.scene = Scene.LOGIN_REGISTER
        elif self.find('login_loading') is not None:
            self.scene = Scene.LOGIN_LOADING
        elif self.find('login_iknow') is not None:
            self.scene = Scene.LOGIN_ANNOUNCE
        elif self.find('12cadpa') is not None:
            if self.find('cadpa_detail') is not None:
                self.scene = Scene.LOGIN_CADPA_DETAIL
            else:
                self.scene = Scene.LOGIN_START
        elif detector.announcement_close(self.img) is not None:
            self.scene = Scene.ANNOUNCEMENT
        elif self.find('skip') is not None:
            self.scene = Scene.SKIP
        elif self.find('upgrade') is not None:
            self.scene = Scene.UPGRADE
        elif detector.confirm(self.img) is not None:
            self.scene = Scene.CONFIRM
        elif self.find('login_verify') is not None:
            self.scene = Scene.LOGIN_INPUT
        elif self.find('login_captcha') is not None:
            self.scene = Scene.LOGIN_CAPTCHA
        elif self.find('login_connecting') is not None:
            self.scene = Scene.LOGIN_LOADING
        elif self.find('main_theme') is not None:
            self.scene = Scene.TERMINAL_MAIN_THEME
        elif self.find('episode') is not None:
            self.scene = Scene.TERMINAL_EPISODE
        elif self.find('biography') is not None:
            self.scene = Scene.TERMINAL_BIOGRAPHY
        elif self.find('collection') is not None:
            self.scene = Scene.TERMINAL_COLLECTION
        elif self.find('login_bilibili') is not None:
            self.scene = Scene.LOGIN_BILIBILI
        elif self.find('loading6') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading7') is not None:
            self.scene = Scene.LOADING
        elif self.find('arrange_order_options_scene') is not None:
            self.scene = Scene.INFRA_ARRANGE_ORDER
        else:
            self.scene = Scene.UNKNOWN
            self.device.check_current_focus()
        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f'Scene: {self.scene}: {SceneComment[self.scene]}')
        return self.scene

    def get_infra_scene(self)-> int:
        if self.scene != Scene.UNDEFINED:
            return self.scene
        if self.find('connecting', scope=((self.w//2, self.h//10*8), (self.w//4*3, self.h))) is not None:
            self.scene = Scene.CONNECTING
        elif self.find('double_confirm') is not None:
            if self.find('network_check') is not None:
                self.scene = Scene.NETWORK_CHECK
            else:
                self.scene = Scene.DOUBLE_CONFIRM
        elif self.find('infra_overview') is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find('infra_todo') is not None:
            self.scene = Scene.INFRA_TODOLIST
        elif self.find('clue') is not None:
            self.scene = Scene.INFRA_CONFIDENTIAL
        elif self.find('arrange_check_in') or self.find('arrange_check_in_on') is not None:
            self.scene = Scene.INFRA_DETAILS
        elif self.find('infra_overview_in') is not None:
            self.scene = Scene.INFRA_ARRANGE
        elif self.find('arrange_confirm') is not None:
            self.scene = Scene.INFRA_ARRANGE_CONFIRM
        elif self.find('arrange_order_options_scene') is not None:
            self.scene = Scene.INFRA_ARRANGE_ORDER
        elif self.find('loading') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading2') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading3') is not None:
            self.scene = Scene.LOADING
        elif self.find('loading4') is not None:
            self.scene = Scene.LOADING
        elif self.find('index_nav', thres=250, scope=((0, 0), (100+self.w//4, self.h//10))) is not None:
            self.scene = Scene.INDEX
        elif self.is_black():
            self.scene = Scene.LOADING
        else:
            self.scene = Scene.UNKNOWN
            self.device.check_current_focus()
        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f'Scene: {self.scene}: {SceneComment[self.scene]}')
        return self.scene

    def is_black(self) -> None:
        """ check if the current scene is all black """
        return np.max(self.gray[:, 105:-105]) < 16

    def nav_button(self):
        """ find navigation button """
        return self.find('nav_button', thres=128, scope=((0, 0), (100+self.w//4, self.h//10)))

    def find(self, res: str, draw: bool = False, scope: tp.Scope = None, thres: int = None, judge: bool = True, strict: bool = False,score = 0.0) -> tp.Scope:
        """
        查找元素是否出现在画面中

        :param res: 待识别元素资源文件名
        :param draw: 是否将识别结果输出到屏幕
        :param scope: ((x0, y0), (x1, y1))，提前限定元素可能出现的范围
        :param thres: 是否在匹配前对图像进行二值化处理
        :param judge: 是否加入更加精确的判断
        :param strict: 是否启用严格模式，未找到时报错
        :param score: 是否启用分数限制，有些图片精确识别需要提高分数阈值

        :return ret: 若匹配成功，则返回元素在游戏界面中出现的位置，否则返回 None
        """
        logger.debug(f'find: {res}')
        res = f'{__rootdir__}/resources/{res}.png'

        if thres is not None:
            # 对图像二值化处理
            res_img = thres2(loadimg(res, True), thres)
            gray_img = cropimg(self.gray, scope)
            matcher = Matcher(thres2(gray_img, thres))
            ret = matcher.match(res_img, draw=draw, judge=judge,prescore=score)
        else:
            res_img = loadimg(res, True)
            matcher = self.matcher
            ret = matcher.match(res_img, draw=draw, scope=scope, judge=judge,prescore=score)
        if strict and ret is None:
            raise RecognizeError(f"Can't find '{res}'") 
        return ret

    def score(self, res: str, draw: bool = False, scope: tp.Scope = None, thres: int = None) -> Optional[List[float]]:
        """
        查找元素是否出现在画面中，并返回分数

        :param res: 待识别元素资源文件名
        :param draw: 是否将识别结果输出到屏幕
        :param scope: ((x0, y0), (x1, y1))，提前限定元素可能出现的范围
        :param thres: 是否在匹配前对图像进行二值化处理

        :return ret: 若匹配成功，则返回元素在游戏界面中出现的位置，否则返回 None
        """
        logger.debug(f'find: {res}')
        res = f'{__rootdir__}/resources/{res}.png'

        if thres is not None:
            # 对图像二值化处理
            res_img = thres2(loadimg(res, True), thres)
            gray_img = cropimg(self.gray, scope)
            matcher = Matcher(thres2(gray_img, thres))
            score = matcher.score(res_img, draw=draw, only_score=True)
        else:
            res_img = loadimg(res, True)
            matcher = self.matcher
            score = matcher.score(res_img, draw=draw, scope=scope, only_score=True)
        return score
