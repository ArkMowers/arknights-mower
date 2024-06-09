from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .. import __rootdir__
from . import config
from . import typealias as tp
from .device import Device
from .image import bytes2img, cropimg, loadres, thres2
from .log import logger, save_screenshot
from .matcher import Matcher
from .scene import Scene, SceneComment


class RecognizeError(Exception):
    pass


class Recognizer(object):
    def __init__(self, device: Device, screencap: bytes = None) -> None:
        self.device = device
        self.w = 1920
        self.h = 1080
        if screencap is None:
            self.clear()
        else:
            self.start(screencap)
            self.matcher = None
            self.scene = Scene.UNDEFINED
        self.loading_time = 0
        self.LOADING_TIME_LIMIT = 5

    def clear(self):
        self._screencap = None
        self._img = None
        self._gray = None
        self.matcher = None
        self.scene = Scene.UNDEFINED

    @property
    def screencap(self):
        if self._screencap is None:
            self.start()
        return self._screencap

    @property
    def img(self):
        if self._img is None:
            self.start()
        return self._img

    @property
    def gray(self):
        if self._gray is None:
            self.start()
        return self._gray

    def start(self, screencap: bytes = None) -> None:
        """init with screencap"""
        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                if screencap is not None:
                    self._screencap = screencap
                    self._img = bytes2img(screencap)
                    self._gray = bytes2img(screencap, True)
                else:
                    self._screencap, self._img, self._gray = self.device.screencap()
                return
            except cv2.error as e:
                logger.warning(e)
                retry_times -= 1
                time.sleep(1)
                continue
        raise RuntimeError("init Recognizer failed")

    def update(self) -> None:
        from arknights_mower.utils.solver import MowerExit

        if config.stop_mower is not None and config.stop_mower.is_set():
            raise MowerExit
        self.clear()

    def color(self, x: int, y: int) -> tp.Pixel:
        """get the color of the pixel"""
        return self.img[y][x]

    def save_screencap(self, folder):
        save_screenshot(self.screencap, subdir=f"{folder}/{self.h}x{self.w}")

    def detect_index_scene(self) -> bool:
        return (
            self.find(
                "index_nav",
                thres=250,
                scope=((0, 0), (100 + self.w // 4, self.h // 10)),
            )
            is not None
        )

    def check_loading_time(self):
        if self.scene == Scene.CONNECTING:
            self.loading_time += 1
            if self.loading_time > 1:
                logger.debug(f"检测到连续等待{self.loading_time}次")
        else:
            self.loading_time = 0
        if self.loading_time > self.LOADING_TIME_LIMIT:
            logger.info(f"检测到连续等待{self.loading_time}次")
            self.device.exit()
            time.sleep(3)
            if self.device.check_current_focus():
                self.update()

    def check_announcement(self):
        img = cropimg(self.gray, ((960, 0), (1920, 540)))
        tpl = loadres("announcement_close", True)
        msk = thres2(tpl, 1)
        result = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED, None, msk)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if min_val < 0.02:
            return (min_loc[0] + 960 + 42, min_loc[1] + 42)

    def get_scene(self) -> int:
        """get the current scene in the game"""
        if self.scene != Scene.UNDEFINED:
            return self.scene
        if self.find("connecting"):
            self.scene = Scene.CONNECTING
        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.find("nav_index") is not None:
            self.scene = Scene.NAVIGATION_BAR
        elif self.find("login_new") is not None:
            self.scene = Scene.LOGIN_NEW
        elif self.find("login_bilibili"):  # 会被识别成公告，优先级应当比公告高
            self.scene = Scene.LOGIN_BILIBILI
        elif self.find("login_bilibili_privacy"):
            self.scene = Scene.LOGIN_BILIBILI_PRIVACY
        elif self.find("close_mine") is not None:
            self.scene = Scene.CLOSE_MINE
        elif self.find("check_in") is not None:
            self.scene = Scene.CHECK_IN
        elif self.find("materiel_ico") is not None:
            self.scene = Scene.MATERIEL
        elif self.find("mail") is not None:
            self.scene = Scene.MAIL
        elif self.find("loading") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading2") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading3") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading4") is not None:
            self.scene = Scene.LOADING
        elif self.is_black():
            self.scene = Scene.LOADING
        elif self.find("ope_plan") is not None:
            self.scene = Scene.OPERATOR_BEFORE
        elif self.find("ope_select_start") is not None:
            self.scene = Scene.OPERATOR_SELECT
        elif self.find("ope_agency_going", scope=((470, 915), (755, 1045))) is not None:
            self.scene = Scene.OPERATOR_ONGOING
        elif self.find("ope_elimi_finished") is not None:
            self.scene = Scene.OPERATOR_ELIMINATE_FINISH
        elif self.find("ope_finish") is not None:
            self.scene = Scene.OPERATOR_FINISH
        elif self.find("ope_recover_potion_on") is not None:
            self.scene = Scene.OPERATOR_RECOVER_POTION
        elif (
            self.find("ope_recover_originite_on", scope=((1530, 120), (1850, 190)))
            is not None
        ):
            self.scene = Scene.OPERATOR_RECOVER_ORIGINITE
        elif self.find("double_confirm") is not None:
            if self.find("network_check") is not None:
                self.scene = Scene.NETWORK_CHECK
            else:
                self.scene = Scene.DOUBLE_CONFIRM
        elif self.find("ope_firstdrop") is not None:
            self.scene = Scene.OPERATOR_DROP
        elif self.find("ope_eliminate") is not None:
            self.scene = Scene.OPERATOR_ELIMINATE
        elif self.find("ope_elimi_agency_panel") is not None:
            self.scene = Scene.OPERATOR_ELIMINATE_AGENCY
        elif self.find("ope_giveup") is not None:
            self.scene = Scene.OPERATOR_GIVEUP
        elif self.find("ope_failed") is not None:
            self.scene = Scene.OPERATOR_FAILED
        elif self.find("friend_list_on") is not None:
            self.scene = Scene.FRIEND_LIST_ON
        elif self.find("credit_visiting") is not None:
            self.scene = Scene.FRIEND_VISITING
        elif self.find("riic_report_title", scope=((1700, 0), (1920, 100))):
            self.scene = Scene.RIIC_REPORT
        elif self.find("control_central_assistants") is not None:
            self.scene = Scene.CTRLCENTER_ASSISTANT
        elif self.find("infra_overview", scope=((20, 120), (360, 245))) is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find("infra_todo") is not None:
            self.scene = Scene.INFRA_TODOLIST
        elif self.find("clue") is not None:
            self.scene = Scene.INFRA_CONFIDENTIAL
        elif (
            self.find("arrange_check_in")
            or self.find("arrange_check_in_on") is not None
        ):
            self.scene = Scene.INFRA_DETAILS
        elif self.find("infra_overview_in", scope=((50, 690), (430, 770))) is not None:
            self.scene = Scene.INFRA_ARRANGE
        elif self.find("arrange_confirm") is not None:
            self.scene = Scene.INFRA_ARRANGE_CONFIRM
        elif self.find("friend_list") is not None:
            self.scene = Scene.FRIEND_LIST_OFF
        elif self.find("mission_trainee_on", scope=((670, 0), (1920, 120))) is not None:
            self.scene = Scene.MISSION_TRAINEE
        elif self.find("mission_daily_on", scope=((670, 0), (1920, 120))) is not None:
            self.scene = Scene.MISSION_DAILY
        elif self.find("mission_weekly_on", scope=((670, 0), (1920, 120))) is not None:
            self.scene = Scene.MISSION_WEEKLY
        elif self.find("terminal_pre") is not None:
            self.scene = Scene.TERMINAL_MAIN
        elif self.find("open_recruitment") is not None:
            self.scene = Scene.RECRUIT_MAIN
        elif self.find("recruiting_instructions") is not None:
            self.scene = Scene.RECRUIT_TAGS
        elif self.find("agent_token", scope=((1735, 745), (1855, 820)), score=0.1):
            self.scene = Scene.RECRUIT_AGENT
        elif self.find("agent_unlock") is not None:
            self.scene = Scene.SHOP_CREDIT
        elif self.find("shop_credit_2") is not None:
            self.scene = Scene.SHOP_OTHERS
        elif self.find("shop_cart") is not None:
            self.scene = Scene.SHOP_CREDIT_CONFIRM
        elif self.find("shop_assist") is not None:
            self.scene = Scene.SHOP_ASSIST
        elif self.find("spent_credit") is not None:
            self.scene = Scene.SHOP_UNLOCK_SCHEDULE
        elif (
            self.find("login_logo") is not None and self.find("hypergryph") is not None
        ):
            if self.find("login_awake") is not None:
                self.scene = Scene.LOGIN_QUICKLY
            elif self.find("login_account") is not None:
                self.scene = Scene.LOGIN_MAIN
            elif self.find("login_iknow") is not None:
                self.scene = Scene.LOGIN_ANNOUNCE
            else:
                self.scene = Scene.LOGIN_MAIN_NOENTRY
        elif self.find("register") is not None:
            self.scene = Scene.LOGIN_REGISTER
        elif self.find("login_loading") is not None:
            self.scene = Scene.LOGIN_LOADING
        elif self.find("login_iknow") is not None:
            self.scene = Scene.LOGIN_ANNOUNCE
        elif self.find("12cadpa") is not None:
            if self.find("cadpa_detail") is not None:
                self.scene = Scene.LOGIN_CADPA_DETAIL
            else:
                self.scene = Scene.LOGIN_START
        elif self.check_announcement():
            self.scene = Scene.ANNOUNCEMENT
        elif self.find("skip") is not None:
            self.scene = Scene.SKIP
        elif self.find("upgrade") is not None:
            self.scene = Scene.UPGRADE
        elif self.find("confirm"):
            self.scene = Scene.CONFIRM
        elif self.find("login_verify") is not None:
            self.scene = Scene.LOGIN_INPUT
        elif self.find("login_captcha") is not None:
            self.scene = Scene.LOGIN_CAPTCHA
        elif self.find("login_connecting") is not None:
            self.scene = Scene.LOGIN_LOADING
        elif self.find("main_theme") is not None:
            self.scene = Scene.TERMINAL_MAIN_THEME
        elif self.find("episode") is not None:
            self.scene = Scene.TERMINAL_EPISODE
        elif self.find("biography") is not None:
            self.scene = Scene.TERMINAL_BIOGRAPHY
        elif self.find("collection") is not None:
            self.scene = Scene.TERMINAL_COLLECTION
        elif self.find("loading6") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading7") is not None:
            self.scene = Scene.LOADING
        elif self.find("arrange_order_options_scene") is not None:
            self.scene = Scene.INFRA_ARRANGE_ORDER
        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()
        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def get_scene_concurrent(self) -> int:
        if self.scene != Scene.UNDEFINED:
            return self.scene

        if self.matcher is None:
            self.matcher = Matcher(self.gray)

        with ThreadPoolExecutor(max_workers=config.get_scene["max_workers"]) as e:

            def submit(res, scope=None):
                return e.submit(lambda: self.find(res, scope=scope))

            connecting = submit("connecting")
            index = e.submit(self.detect_index_scene)
            nav_index = submit("nav_index")
            login_new = submit("login_new")
            login_bilibili = submit("login_bilibili")
            login_bilibili_privacy = submit("login_bilibili_privacy")
            close_mine = submit("close_mine")
            check_in = submit("check_in")
            materiel_ico = submit("materiel_ico")
            mail = submit("mail")
            loading = submit("loading")
            loading2 = submit("loading2")
            loading3 = submit("loading3")
            loading4 = submit("loading4")
            black = e.submit(self.is_black)
            ope_plan = submit("ope_plan")
            ope_select_start = submit("ope_select_start")
            ope_agency_going = submit("ope_agency_going", ((470, 915), (755, 1045)))
            ope_elimi_finished = submit("ope_elimi_finished")
            ope_finish = submit("ope_finish")
            ope_recover_potion_on = submit("ope_recover_potion_on")
            ope_recover_originite_on = submit(
                "ope_recover_originite_on", ((1530, 120), (1850, 190))
            )
            double_confirm = submit("double_confirm")
            network_check = submit("network_check")
            ope_firstdrop = submit("ope_firstdrop")
            ope_eliminate = submit("ope_eliminate")
            ope_elimi_agency_panel = submit("ope_elimi_agency_panel")
            ope_giveup = submit("ope_giveup")
            ope_failed = submit("ope_failed")
            friend_list_on = submit("friend_list_on")
            credit_visiting = submit("credit_visiting")
            riic_report_title = submit("riic_report_title", ((1700, 0), (1920, 100)))
            control_central_assistants = submit("control_central_assistants")
            infra_overview = submit("infra_overview", ((20, 120), (360, 245)))
            infra_todo = submit("infra_todo")
            clue = submit("clue")
            arrange_check_in = submit("arrange_check_in")
            arrange_check_in_on = submit("arrange_check_in_on")
            infra_overview_in = submit("infra_overview_in", ((50, 690), (430, 770)))
            arrange_confirm = submit("arrange_confirm")
            friend_list = submit("friend_list")
            mission_trainee_on = submit("mission_trainee_on", ((670, 0), (1920, 120)))
            mission_daily_on = submit("mission_daily_on", ((670, 0), (1920, 120)))
            mission_weekly_on = submit("mission_weekly_on", ((670, 0), (1920, 120)))
            terminal_pre = submit("terminal_pre")
            open_recruitment = submit("open_recruitment")
            recruiting_instructions = submit("recruiting_instructions")
            agent_token = e.submit(
                lambda: self.find(
                    "agent_token",
                    scope=((1735, 745), (1855, 820)),
                    score=0.1,
                ),
            )
            agent_unlock = submit("agent_unlock")
            shop_credit_2 = submit("shop_credit_2")
            shop_cart = submit("shop_cart")
            shop_assist = submit("shop_assist")
            spent_credit = submit("spent_credit")
            login_logo = submit("login_logo")
            hypergryph = submit("hypergryph")
            login_awake = submit("login_awake")
            login_account = submit("login_account")
            login_iknow = submit("login_iknow")
            register = submit("register")
            login_loading = submit("login_loading")
            cadpa12 = submit("12cadpa")
            cadpa_detail = submit("cadpa_detail")
            announcement = e.submit(self.check_announcement)
            skip = submit("skip")
            upgrade = submit("upgrade")
            detector_confirm = submit("confirm")
            login_verify = submit("login_verify")
            login_captcha = submit("login_captcha")
            login_connecting = submit("login_connecting")
            main_theme = submit("main_theme")
            episode = submit("episode")
            biography = submit("biography")
            collection = submit("collection")
            loading6 = submit("loading6")
            loading7 = submit("loading7")
            arrange_order_options_scene = submit("arrange_order_options_scene")

            if connecting.result():
                self.scene = Scene.CONNECTING
            elif index.result():
                self.scene = Scene.INDEX
            elif nav_index.result():
                self.scene = Scene.NAVIGATION_BAR
            elif login_new.result():
                self.scene = Scene.LOGIN_NEW
            elif login_bilibili.result():  # 会被识别成公告，优先级应当比公告高
                self.scene = Scene.LOGIN_BILIBILI
            elif login_bilibili_privacy.result():
                self.scene = Scene.LOGIN_BILIBILI_PRIVACY
            elif close_mine.result():
                self.scene = Scene.CLOSE_MINE
            elif check_in.result():
                self.scene = Scene.CHECK_IN
            elif materiel_ico.result():
                self.scene = Scene.MATERIEL
            elif mail.result():
                self.scene = Scene.MAIL
            elif loading.result():
                self.scene = Scene.LOADING
            elif loading2.result():
                self.scene = Scene.LOADING
            elif loading3.result():
                self.scene = Scene.LOADING
            elif loading4.result():
                self.scene = Scene.LOADING
            elif black.result():
                self.scene = Scene.LOADING
            elif ope_plan.result():
                self.scene = Scene.OPERATOR_BEFORE
            elif ope_select_start.result():
                self.scene = Scene.OPERATOR_SELECT
            elif ope_agency_going.result():
                self.scene = Scene.OPERATOR_ONGOING
            elif ope_elimi_finished.result():
                self.scene = Scene.OPERATOR_ELIMINATE_FINISH
            elif ope_finish.result():
                self.scene = Scene.OPERATOR_FINISH
            elif ope_recover_potion_on.result():
                self.scene = Scene.OPERATOR_RECOVER_POTION
            elif ope_recover_originite_on.result():
                self.scene = Scene.OPERATOR_RECOVER_ORIGINITE
            elif double_confirm.result():
                if network_check.result():
                    self.scene = Scene.NETWORK_CHECK
                else:
                    self.scene = Scene.DOUBLE_CONFIRM
            elif ope_firstdrop.result():
                self.scene = Scene.OPERATOR_DROP
            elif ope_eliminate.result():
                self.scene = Scene.OPERATOR_ELIMINATE
            elif ope_elimi_agency_panel.result():
                self.scene = Scene.OPERATOR_ELIMINATE_AGENCY
            elif ope_giveup.result():
                self.scene = Scene.OPERATOR_GIVEUP
            elif ope_failed.result():
                self.scene = Scene.OPERATOR_FAILED
            elif friend_list_on.result():
                self.scene = Scene.FRIEND_LIST_ON
            elif credit_visiting.result():
                self.scene = Scene.FRIEND_VISITING
            elif riic_report_title.result():
                self.scene = Scene.RIIC_REPORT
            elif control_central_assistants.result():
                self.scene = Scene.CTRLCENTER_ASSISTANT
            elif infra_overview.result():
                self.scene = Scene.INFRA_MAIN
            elif infra_todo.result():
                self.scene = Scene.INFRA_TODOLIST
            elif clue.result():
                self.scene = Scene.INFRA_CONFIDENTIAL
            elif arrange_check_in.result() or arrange_check_in_on.result():
                self.scene = Scene.INFRA_DETAILS
            elif infra_overview_in.result():
                self.scene = Scene.INFRA_ARRANGE
            elif arrange_confirm.result():
                self.scene = Scene.INFRA_ARRANGE_CONFIRM
            elif friend_list.result():
                self.scene = Scene.FRIEND_LIST_OFF
            elif mission_trainee_on.result():
                self.scene = Scene.MISSION_TRAINEE
            elif mission_daily_on.result():
                self.scene = Scene.MISSION_DAILY
            elif mission_weekly_on.result():
                self.scene = Scene.MISSION_WEEKLY
            elif terminal_pre.result():
                self.scene = Scene.TERMINAL_MAIN
            elif open_recruitment.result():
                self.scene = Scene.RECRUIT_MAIN
            elif recruiting_instructions.result():
                self.scene = Scene.RECRUIT_TAGS
            elif agent_token.result():
                self.scene = Scene.RECRUIT_AGENT
            elif agent_unlock.result():
                self.scene = Scene.SHOP_CREDIT
            elif shop_credit_2.result():
                self.scene = Scene.SHOP_OTHERS
            elif shop_cart.result():
                self.scene = Scene.SHOP_CREDIT_CONFIRM
            elif shop_assist.result():
                self.scene = Scene.SHOP_ASSIST
            elif spent_credit.result():
                self.scene = Scene.SHOP_UNLOCK_SCHEDULE
            elif login_logo.result() and hypergryph.result():
                if login_awake.result():
                    self.scene = Scene.LOGIN_QUICKLY
                elif login_account.result():
                    self.scene = Scene.LOGIN_MAIN
                elif login_iknow.result():
                    self.scene = Scene.LOGIN_ANNOUNCE
                else:
                    self.scene = Scene.LOGIN_MAIN_NOENTRY
            elif register.result():
                self.scene = Scene.LOGIN_REGISTER
            elif login_loading.result():
                self.scene = Scene.LOGIN_LOADING
            elif login_iknow.result():
                self.scene = Scene.LOGIN_ANNOUNCE
            elif cadpa12.result():
                if cadpa_detail.result():
                    self.scene = Scene.LOGIN_CADPA_DETAIL
                else:
                    self.scene = Scene.LOGIN_START
            elif announcement.result():
                self.scene = Scene.ANNOUNCEMENT
            elif skip.result():
                self.scene = Scene.SKIP
            elif upgrade.result():
                self.scene = Scene.UPGRADE
            elif detector_confirm.result() is not None:
                self.scene = Scene.CONFIRM
            elif login_verify.result():
                self.scene = Scene.LOGIN_INPUT
            elif login_captcha.result():
                self.scene = Scene.LOGIN_CAPTCHA
            elif login_connecting.result():
                self.scene = Scene.LOGIN_LOADING
            elif main_theme.result():
                self.scene = Scene.TERMINAL_MAIN_THEME
            elif episode.result():
                self.scene = Scene.TERMINAL_EPISODE
            elif biography.result():
                self.scene = Scene.TERMINAL_BIOGRAPHY
            elif collection.result():
                self.scene = Scene.TERMINAL_COLLECTION
            elif loading6.result():
                self.scene = Scene.LOADING
            elif loading7.result():
                self.scene = Scene.LOADING
            elif arrange_order_options_scene.result():
                self.scene = Scene.INFRA_ARRANGE_ORDER
            else:
                self.scene = Scene.UNKNOWN
                if self.device.check_current_focus():
                    self.update()
            e.shutdown(wait=False, cancel_futures=True)

        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def get_infra_scene(self) -> int:
        if self.scene != Scene.UNDEFINED:
            return self.scene
        if self.find("connecting"):
            self.scene = Scene.CONNECTING
        elif self.find("double_confirm") is not None:
            if self.find("network_check") is not None:
                self.scene = Scene.NETWORK_CHECK
            else:
                self.scene = Scene.DOUBLE_CONFIRM
        elif self.find("infra_overview", scope=((20, 120), (360, 245))) is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find("infra_todo") is not None:
            self.scene = Scene.INFRA_TODOLIST
        elif self.find("clue") is not None:
            self.scene = Scene.INFRA_CONFIDENTIAL
        elif (
            self.find("arrange_check_in")
            or self.find("arrange_check_in_on") is not None
        ):
            self.scene = Scene.INFRA_DETAILS
        elif self.find("infra_overview_in", scope=((50, 690), (430, 770))) is not None:
            self.scene = Scene.INFRA_ARRANGE
        elif self.find("arrange_order_options"):
            self.scene = Scene.INFRA_ARRANGE_ORDER
        elif self.find("arrange_confirm") is not None:
            self.scene = Scene.INFRA_ARRANGE_CONFIRM
        elif self.find("arrange_order_options_scene") is not None:
            self.scene = Scene.INFRA_ARRANGE_ORDER
        elif self.find("loading") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading2") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading3") is not None:
            self.scene = Scene.LOADING
        elif self.find("loading4") is not None:
            self.scene = Scene.LOADING
        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.is_black():
            self.scene = Scene.LOADING
        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()
        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def find_ra_battle_exit(self) -> bool:
        im = cv2.cvtColor(self.img, cv2.COLOR_RGB2HSV)
        im = cv2.inRange(im, (29, 0, 0), (31, 255, 255))
        score, scope = self.template_match(
            "ra/battle_exit", ((75, 47), (165, 126)), cv2.TM_CCOEFF_NORMED
        )
        return scope if score > 0.8 else None

    def get_ra_scene(self) -> int:
        """
        生息演算场景识别
        """
        # 场景缓存
        if self.scene != Scene.UNDEFINED:
            return self.scene

        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING

        # 奇遇
        elif self.find("ra/adventure", scope=((380, 360), (470, 460)), thres=250):
            self.scene = Scene.RA_ADVENTURE

        # 快速跳过剧情对话
        elif self.find("ra/guide_dialog", scope=((0, 0), (160, 110))):
            self.scene = Scene.RA_GUIDE_DIALOG

        # 快速退出作战
        elif self.find_ra_battle_exit():
            self.scene = Scene.RA_BATTLE
        elif self.find("ra/battle_exit_dialog", scope=((600, 360), (970, 430))):
            self.scene = Scene.RA_BATTLE_EXIT_CONFIRM

        # 作战与分队
        elif self.find("ra/start_action", scope=((1410, 790), (1900, 935))):
            if self.find("ra/action_points", scope=((1660, 55), (1820, 110))):
                self.scene = Scene.RA_BATTLE_ENTRANCE
            else:
                self.scene = Scene.RA_GUIDE_BATTLE_ENTRANCE
        elif self.find("ra/squad_edit", scope=((1090, 0), (1910, 105))):
            self.scene = Scene.RA_SQUAD_EDIT
        elif self.find("ra/get_item", scope=((875, 360), (1055, 420))):
            self.scene = Scene.RA_GET_ITEM
        elif self.find("ra/return_from_kitchen", scope=((0, 0), (300, 105))):
            self.scene = Scene.RA_KITCHEN
        elif self.find("ra/squad_edit_confirm_dialog", scope=((585, 345), (1485, 440))):
            self.scene = Scene.RA_SQUAD_EDIT_DIALOG
        elif self.find("ra/battle_complete", scope=((70, 310), (580, 500))):
            self.scene = Scene.RA_BATTLE_COMPLETE

        # 结算界面
        elif self.find("ra/day_complete", scope=((800, 330), (1130, 410))):
            self.scene = Scene.RA_DAY_COMPLETE
        elif self.find(
            "ra/period_complete", scope=((800, 190), (1120, 265))
        ) and self.find("ra/click_anywhere", scope=((830, 990), (1090, 1040))):
            self.scene = Scene.RA_PERIOD_COMPLETE

        # 森蚺图耶对话
        elif self.find("ra/guide_entrance", scope=((810, 270), (1320, 610))):
            self.scene = Scene.RA_GUIDE_ENTRANCE

        # 存档操作
        elif self.find(
            "ra/delete_save_confirm_dialog", scope=((585, 345), (1020, 440))
        ):
            self.scene = Scene.RA_DELETE_SAVE_DIALOG

        # 地图识别
        elif self.find("ra/waste_time_button", scope=((1665, 220), (1855, 290))):
            self.scene = Scene.RA_DAY_DETAIL
        elif self.find("ra/waste_time_dialog", scope=((585, 345), (1070, 440))):
            self.scene = Scene.RA_WASTE_TIME_DIALOG
        elif self.find("ra/map_back", thres=200) and self.color(1817, 333)[0] > 250:
            self.scene = Scene.RA_MAP

        # 从首页选择终端进入生息演算主页
        elif self.find("terminal_longterm"):
            self.scene = Scene.TERMINAL_LONGTERM
        elif self.find("ra/main_title"):
            self.scene = Scene.RA_MAIN
        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.find("terminal_pre") is not None:
            self.scene = Scene.TERMINAL_MAIN
        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()

        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        log_msg = f"Scene: {self.scene}: {SceneComment[self.scene]}"
        if self.scene == Scene.UNKNOWN:
            logger.debug(log_msg)
        else:
            logger.info(log_msg)

        self.check_loading_time()

        return self.scene

    def get_sf_scene(self) -> int:
        """
        隐秘战线场景识别
        """
        # 场景缓存
        if self.scene != Scene.UNDEFINED:
            return self.scene

        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING

        elif self.find("sf/success") or self.find("sf/failure"):
            self.scene = Scene.SF_RESULT
        elif self.find("sf/continue"):
            self.scene = Scene.SF_CONTINUE
        elif self.find("sf/select"):
            self.scene = Scene.SF_SELECT
        elif self.find("sf/properties"):
            self.scene = Scene.SF_ACTIONS
        elif self.find("sf/continue_event"):
            self.scene = Scene.SF_EVENT
        elif self.find("sf/team_pass"):
            self.scene = Scene.SF_TEAM_PASS

        elif self.find("sf/inheritance", scope=((1490, 0), (1920, 100))):
            self.scene = Scene.SF_SELECT_TEAM

        # 从首页进入隐秘战线
        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.find("terminal_pre"):
            self.scene = Scene.TERMINAL_MAIN
        elif self.find("main_theme"):
            self.scene = Scene.TERMINAL_MAIN_THEME
        elif self.find("sf/entrance"):
            self.scene = Scene.SF_ENTRANCE
        elif self.find("sf/info"):
            self.scene = Scene.SF_INFO

        elif self.find("sf/click_anywhere"):
            self.scene = Scene.SF_CLICK_ANYWHERE
        elif self.find("sf/end"):
            self.scene = Scene.SF_END
        elif self.find("sf/exit"):
            self.scene = Scene.SF_EXIT

        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()

        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        log_msg = f"Scene: {self.scene}: {SceneComment[self.scene]}"
        if self.scene == Scene.UNKNOWN:
            logger.debug(log_msg)
        else:
            logger.info(log_msg)

        self.check_loading_time()

        return self.scene

    def get_sss_scene(self) -> int:
        """
        保全导航场景识别
        """
        # 场景缓存
        if self.scene != Scene.UNDEFINED:
            return self.scene

        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING

        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.find("terminal_pre", score=0.3) is not None:
            self.scene = Scene.TERMINAL_MAIN
        elif self.find("terminal_regular"):
            self.scene = Scene.TERMINAL_REGULAR
        elif self.find("sss/main"):
            self.scene = Scene.SSS_MAIN
        elif self.find("sss/start_button"):
            self.scene = Scene.SSS_START
        elif self.find("sss/ec_button"):
            self.scene = Scene.SSS_EC
        elif self.find("sss/device_button"):
            self.scene = Scene.SSS_DEVICE
        elif self.find("sss/squad_button"):
            self.scene = Scene.SSS_SQUAD
        elif self.find("sss/deploy_button"):
            self.scene = Scene.SSS_DEPLOY
        elif self.find("sss/redeploy_button"):
            self.scene = Scene.SSS_REDEPLOY
        elif self.find("sss/loading"):
            self.scene = Scene.SSS_LOADING
        elif self.find("sss/close_button"):
            self.scene = Scene.SSS_GUIDE
        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()

        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def get_clue_scene(self) -> int:
        """
        线索场景识别
        """
        # 场景缓存
        if self.scene != Scene.UNDEFINED:
            return self.scene

        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING

        elif self.find("arrange_check_in") or self.find("arrange_check_in_on"):
            self.scene = Scene.INFRA_DETAILS
        elif self.find("clue/main", scope=((1740, 850), (1860, 1050))):
            self.scene = Scene.INFRA_CONFIDENTIAL
        elif self.find("clue/daily"):
            self.scene = Scene.CLUE_DAILY
        elif (
            self.find("clue/receive", scope=((1280, 0), (1600, 90)))
            and self.color(1275, 0)[0] > 144
        ):
            self.scene = Scene.CLUE_RECEIVE
        elif (
            self.find("clue/filter", scope=((0, 80), (650, 180)), score=0.5)
            and self.color(53, 113)[0] > 250
        ):
            self.scene = Scene.CLUE_GIVE_AWAY
        elif self.find("clue/summary", scope=((30, 120), (350, 370))):
            self.scene = Scene.CLUE_SUMMARY
        elif self.find("clue/filter", scope=((1280, 80), (1920, 180)), score=0.5):
            self.scene = Scene.CLUE_PLACE
        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()

        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def get_train_scene(self) -> int:
        """
        训练室场景识别
        """
        # 场景缓存
        if self.scene != Scene.UNDEFINED:
            return self.scene
        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING
        elif self.find("infra_overview", scope=((20, 120), (360, 245))) is not None:
            self.scene = Scene.INFRA_MAIN
        elif self.find("train_main"):
            self.scene = Scene.TRAIN_MAIN
        elif self.find("skill_collect_confirm", scope=((1142, 831), (1282, 932))):
            self.scene = Scene.TRAIN_FINISH
        elif self.find("training_support"):
            self.scene = Scene.TRAIN_SKILL_SELECT
        elif self.find("upgrade_failure"):
            self.scene = Scene.TRAIN_SKILL_UPGRADE_ERROR
        elif self.find("skill_confirm"):
            self.scene = Scene.TRAIN_SKILL_UPGRADE
        else:
            self.scene = Scene.UNKNOWN
            if self.device.check_current_focus():
                self.update()

        # save screencap to analyse
        if config.SCREENSHOT_PATH is not None:
            self.save_screencap(self.scene)
        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def is_black(self) -> None:
        """check if the current scene is all black"""
        return np.max(self.gray[:, 105:-105]) < 16

    def nav_button(self):
        """find navigation button"""
        return self.find(
            "nav_button", thres=128, scope=((0, 0), (100 + self.w // 4, self.h // 10))
        )

    def find(
        self,
        res: str,
        draw: bool = False,
        scope: tp.Scope = None,
        thres: int = None,
        judge: bool = True,
        strict: bool = False,
        score=0.0,
    ) -> tp.Scope:
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
        logger.debug(f"find: {res}")

        dpi_aware = res in [
            "login_bilibili",
            "login_bilibili_privacy",
            "login_bilibili_entry",
            "login_bilibili_privacy_accept",
            "login_captcha",
            "control_central",
        ]

        if scope is None and score == 0.0:
            if res == "arrange_check_in":
                scope = ((0, 350), (200, 530))
                score = 0.55
            elif res == "arrange_check_in_on":
                scope = ((0, 350), (200, 530))
            elif res == "connecting":
                scope = ((1087, 978), (1430, 1017))
                score = 0.15
            elif res == "materiel_ico":
                scope = ((860, 60), (1072, 217))
            elif res == "training_completed":
                scope = ((550, 900), (800, 1080))
                score = 0.45

        if thres is not None:
            # 对图像二值化处理
            res_img = thres2(loadres(res, True), thres)
            matcher = Matcher(thres2(self.gray, thres))
            ret = matcher.match(
                res_img,
                draw=draw,
                scope=scope,
                judge=judge,
                prescore=score,
                dpi_aware=dpi_aware,
            )
        else:
            res_img = loadres(res, True)
            if self.matcher is None:
                self.matcher = Matcher(self.gray)
            matcher = self.matcher
            ret = matcher.match(
                res_img,
                draw=draw,
                scope=scope,
                judge=judge,
                prescore=score,
                dpi_aware=dpi_aware,
            )
        if strict and ret is None:
            raise RecognizeError(f"Can't find '{res}'")
        return ret

    def score(
        self, res: str, draw: bool = False, scope: tp.Scope = None, thres: int = None
    ) -> Optional[List[float]]:
        """
        查找元素是否出现在画面中，并返回分数

        :param res: 待识别元素资源文件名
        :param draw: 是否将识别结果输出到屏幕
        :param scope: ((x0, y0), (x1, y1))，提前限定元素可能出现的范围
        :param thres: 是否在匹配前对图像进行二值化处理

        :return ret: 若匹配成功，则返回元素在游戏界面中出现的位置，否则返回 None
        """
        logger.debug(f"find: {res}")
        res = f"{__rootdir__}/resources/{res}.png"

        if thres is not None:
            # 对图像二值化处理
            res_img = thres2(loadres(res, True), thres)
            gray_img = cropimg(self.gray, scope)
            matcher = Matcher(thres2(gray_img, thres))
            score = matcher.score(res_img, draw=draw, only_score=True)
        else:
            res_img = loadres(res, True)
            matcher = self.matcher
            score = matcher.score(res_img, draw=draw, scope=scope, only_score=True)
        return score

    def template_match(
        self, res: str, scope: Optional[tp.Scope] = None, method: int = cv2.TM_CCOEFF
    ) -> Tuple[float, tp.Scope]:
        logger.debug(f"template_match: {res}")

        template = loadres(res, True)
        w, h = template.shape[::-1]

        if scope:
            x, y = scope[0]
            img = cropimg(self.gray, scope)
        else:
            x, y = (0, 0)
            img = self.gray

        result = cv2.matchTemplate(img, template, method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            top_left = min_loc
            score = min_val
        else:
            top_left = max_loc
            score = max_val

        p1 = (top_left[0] + x, top_left[1] + y)
        p2 = (p1[0] + w, p1[1] + h)

        ret_val = (score, (p1, p2))
        logger.debug(f"template_match: {ret_val}")

        return ret_val
