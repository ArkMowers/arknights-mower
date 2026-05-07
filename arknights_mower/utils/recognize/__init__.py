import time
from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity

from arknights_mower import __rootdir__
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.image import bytes2img, cmatch, cropimg, loadres, thres2
from arknights_mower.utils.log import logger, save_screenshot
from arknights_mower.utils.matcher import Matcher
from arknights_mower.utils.scene import Scene, SceneComment
from arknights_mower.utils.vector import va


class RecognizeError(Exception):
    pass


class Recognizer:
    def __init__(self, device: Device, screencap: bytes = None) -> None:
        self.device = device
        self.w = 1920
        self.h = 1080
        if screencap is None:
            self.clear()
        else:
            self.start(screencap)
            self._matcher = None
            self.scene = Scene.UNDEFINED
        self.loading_time = 0
        self.LOADING_TIME_LIMIT = 5
        self.last_scene = None
        self.last_scene_time = time.time()

    def clear(self):
        self._screencap = None
        self._img = None
        self._gray = None
        self._matcher = None
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

    @property
    def matcher(self):
        if self._matcher is None:
            self._matcher = Matcher(self.gray)
        return self._matcher

    def start(self, screencap: Optional[bytes] = None) -> None:
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
        if config.stop_mower.is_set():
            raise MowerExit
        self.clear()

    def color(self, x: int, y: int) -> tp.Pixel:
        """get the color of the pixel"""
        return self.img[y][x]

    def save_screencap(self, folder):
        # del folder  # 兼容2024.05旧版接口
        save_screenshot(self.screencap, folder)

    def detect_index_scene(self) -> bool:
        res = loadres("index_nav", True)
        h, w = res.shape
        img = cropimg(self.gray, ((25, 17), (25 + w, 17 + h)))
        img = thres2(img, 250)
        result = cv2.matchTemplate(img, res, cv2.TM_SQDIFF_NORMED)
        result = result[0][0]
        logger.debug(result)
        return result < 0.31

    def check_current_focus(self):
        if self.device.check_current_focus():
            self.update()

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
            self.check_current_focus()

    def check_announcement(self):
        img = cropimg(self.gray, ((960, 0), (1920, 540)))
        tpl = loadres("announcement_close", True)
        msk = thres2(tpl, 1)
        result = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED, None, msk)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if min_val < 0.02:
            return (min_loc[0] + 960 + 42, min_loc[1] + 42)

    def check_freeze(self, current_time):
        if self.scene != self.last_scene:
            self.last_scene_time = current_time
            self.last_scene = self.scene
        else:
            elapsed_time = (current_time - self.last_scene_time).total_seconds()
            if elapsed_time > config.conf.run_order_delay * 90:
                logger.warning("相同场景等待超时 ")
                self.last_scene = None
                self.last_scene_time = current_time
                self.device.exit()

    def get_scene(self) -> int:
        """get the current scene in the game"""
        current_time = datetime.now()
        # 检查模拟器是否卡死，超过跑单时间*90秒则视为卡死
        if self.scene != Scene.UNDEFINED:
            self.check_freeze(current_time)
            return self.scene

        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING

        # 平均色匹配
        elif self.find("confirm"):
            self.scene = Scene.CONFIRM
        elif self.find("order_label"):
            self.scene = Scene.ORDER_LIST
        elif self.find("drone"):
            self.scene = Scene.DRONE_ACCELERATE
        elif self.find("factory_collect"):
            self.scene = Scene.FACTORY_ROOMS
        elif self.find("nav_bar"):
            self.scene = Scene.NAVIGATION_BAR
        elif self.find("read_mail"):
            self.scene = Scene.MAIL
        elif self.find("navigation/record_restoration"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("fight/refresh"):
            self.scene = Scene.OPERATOR_SUPPORT
        elif self.find("ope_select_start"):
            self.scene = Scene.OPERATOR_SELECT
        elif self.find("ope_eliminate"):
            self.scene = Scene.OPERATOR_ELIMINATE
        elif self.find("ope_elimi_agency_panel"):
            self.scene = Scene.OPERATOR_ELIMINATE_AGENCY
        elif self.find("riic/report_title"):
            self.scene = Scene.RIIC_REPORT
        elif self.find("control_central_assistants"):
            self.scene = Scene.CTRLCENTER_ASSISTANT
        elif self.find("infra_overview"):
            self.scene = Scene.INFRA_MAIN
        elif self.find("infra_todo", scope=((0, 1013), (241, 1080))):
            self.scene = Scene.INFRA_TODOLIST
        elif self.find("clue"):
            self.scene = Scene.INFRA_CONFIDENTIAL
        elif self.find("infra_overview_in"):
            self.scene = Scene.INFRA_ARRANGE
        elif self.find("arrange_confirm"):
            self.scene = Scene.INFRA_ARRANGE_CONFIRM
        elif self.find("terminal_main"):
            self.scene = Scene.TERMINAL_MAIN
        elif self.find("open_recruitment"):
            self.scene = Scene.RECRUIT_MAIN
        elif self.find("recruiting_instructions"):
            self.scene = Scene.RECRUIT_TAGS
        elif self.find("credit_shop_countdown"):
            hsv = cv2.cvtColor(self.img, cv2.COLOR_RGB2HSV)
            if 9 < hsv[870][1530][0] < 19:
                self.scene = Scene.UNKNOWN
            else:
                self.scene = Scene.SHOP_CREDIT
        elif self.find("shop_credit_2"):
            self.scene = Scene.SHOP_OTHERS
        elif self.find("shop_cart"):
            self.scene = Scene.SHOP_CREDIT_CONFIRM
        elif self.find("login_logo") and self.find("hypergryph"):
            if self.find("login_awake"):
                self.scene = Scene.LOGIN_QUICKLY
            elif self.find("login_account"):
                self.scene = Scene.LOGIN_MAIN
            else:
                self.scene = Scene.LOGIN_MAIN_NOENTRY
        elif self.find("login_loading"):
            self.scene = Scene.LOGIN_LOADING
        elif self.find("12cadpa"):
            self.scene = Scene.LOGIN_START
        elif self.find("skip"):
            self.scene = Scene.SKIP
        elif self.find("login_connecting"):
            self.scene = Scene.LOGIN_LOADING
        elif self.find("arrange_order_options"):
            self.scene = Scene.RIIC_OPERATOR_SELECT
        elif (
            self.find("arrange_order_options_scene", threshold=0.90)
            or self.find("op_select_2")
            or self.find("op_select_1")
        ):
            self.scene = Scene.INFRA_ARRANGE_ORDER
        elif self.find("ope_recover_potion_on"):
            self.scene = Scene.OPERATOR_RECOVER_POTION
        elif self.find("ope_recover_originite_on", scope=((1530, 120), (1850, 190))):
            self.scene = Scene.OPERATOR_RECOVER_ORIGINITE
        elif self.find("double_confirm/main"):
            if self.find("double_confirm/exit"):
                self.scene = Scene.EXIT_GAME
            elif self.find("double_confirm/friend"):
                self.scene = Scene.BACK_TO_FRIEND_LIST
            elif self.find("double_confirm/give_up"):
                self.scene = Scene.OPERATOR_GIVEUP
            elif self.find("double_confirm/infrastructure"):
                self.scene = Scene.LEAVE_INFRASTRUCTURE
            elif self.find("double_confirm/recruit"):
                self.scene = Scene.REFRESH_TAGS
            elif self.find("double_confirm/network"):
                self.scene = Scene.NETWORK_CHECK
            elif self.find("double_confirm/voice"):
                self.scene = Scene.DOWNLOAD_VOICE_RESOURCES
            else:
                self.scene = Scene.DOUBLE_CONFIRM
        elif self.find("mission_trainee_on"):
            self.scene = Scene.MISSION_TRAINEE
        elif self.find("spent_credit"):
            self.scene = Scene.SHOP_UNLOCK_SCHEDULE
        elif self.find("loading7"):
            self.scene = Scene.LOADING
        elif self.find("clue/daily"):
            self.scene = Scene.CLUE_DAILY
        elif self.find("clue/receive"):
            self.scene = Scene.CLUE_RECEIVE
        elif self.find("clue/give_away"):
            self.scene = Scene.CLUE_GIVE_AWAY
        elif self.find("clue/summary"):
            self.scene = Scene.CLUE_SUMMARY
        elif self.find("clue/filter_all"):
            self.scene = Scene.CLUE_PLACE
        elif self.find("upgrade"):
            self.scene = Scene.UPGRADE
        elif self.find("depot"):
            self.scene = Scene.DEPOT
        elif self.find("pull_once"):
            self.scene = Scene.HEADHUNTING
        elif self.find("read_and_agree") or self.find("next_step"):
            self.scene = Scene.AGREEMENT_UPDATE
        elif self.is_black():
            self.scene = Scene.LOADING

        # 模板匹配
        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.find("materiel_ico"):
            self.scene = Scene.MATERIEL
        elif self.find("loading"):
            self.scene = Scene.LOADING
        elif self.find("loading2"):
            self.scene = Scene.LOADING
        elif self.find("loading3"):
            self.scene = Scene.LOADING
        elif self.find("loading4"):
            self.scene = Scene.LOADING
        elif self.find("ope_start"):
            self.scene = Scene.OPERATOR_BEFORE
        elif self.find("navigation/episode"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/AP-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/LS-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/CA-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/CE-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/SK-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/PR-A-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/PR-B-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/PR-C-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("navigation/collection/PR-D-1"):
            self.scene = Scene.OPERATOR_CHOOSE_LEVEL
        elif self.find("ope_agency_going"):
            self.scene = Scene.OPERATOR_ONGOING
        elif self.find("ope_finish"):
            self.scene = Scene.OPERATOR_FINISH
        elif self.find("fight/use"):
            self.scene = Scene.OPERATOR_STRANGER_SUPPORT
        elif self.find("business_card"):
            self.scene = Scene.BUSINESS_CARD
        elif self.find("friend_list"):
            self.scene = Scene.FRIEND_LIST
        elif self.find("credit_visiting"):
            self.scene = Scene.FRIEND_VISITING
        elif (
            self.find("arrange_check_in")
            or self.find("arrange_check_in_on")
            or self.find("room_detail")
            or self.find("arrange_check_in_small")
        ):
            self.scene = Scene.INFRA_DETAILS
        elif self.find("ope_failed"):
            self.scene = Scene.OPERATOR_FAILED
        elif self.find("mission_daily_on"):
            self.scene = Scene.MISSION_DAILY
        elif self.find("mission_weekly_on"):
            self.scene = Scene.MISSION_WEEKLY
        elif self.find("recruit/agent_token") or self.find("recruit/agent_token_first"):
            self.scene = Scene.RECRUIT_AGENT
        elif self.find("main_theme"):
            self.scene = Scene.TERMINAL_MAIN_THEME
        elif self.find("episode"):
            self.scene = Scene.TERMINAL_EPISODE
        elif self.find("biography"):
            self.scene = Scene.TERMINAL_BIOGRAPHY
        elif self.find("collection"):
            self.scene = Scene.TERMINAL_COLLECTION
        elif self.check_announcement():
            self.scene = Scene.ANNOUNCEMENT

        # 特征匹配
        # elif self.find("login_new"):
        #     self.scene = Scene.LOGIN_NEW
        elif self.find("login_bilibili"):
            self.scene = Scene.LOGIN_BILIBILI
        elif self.find("login_bilibili_privacy"):
            self.scene = Scene.LOGIN_BILIBILI_PRIVACY
        elif self.find("login_captcha"):
            self.scene = Scene.LOGIN_CAPTCHA
        elif self.find("factory_dashboard"):
            self.scene = Scene.FACTORY_DASHBOARD
        elif self.find("factory_formula"):
            self.scene = Scene.FACTORY_FORMULA
        elif self.find("factory_product_collect"):
            self.scene = Scene.FACTORY_PRODUCT_COLLECT
        elif self.find("factory_tag"):
            self.scene = Scene.FACTORY_ROOM

        # 没弄完的
        # elif self.find("ope_elimi_finished"):
        #     self.scene = Scene.OPERATOR_ELIMINATE_FINISH
        # elif self.find("shop_assist"):
        #     self.scene = Scene.SHOP_ASSIST

        else:
            self.scene = Scene.UNKNOWN
            self.check_current_focus()

        logger.info(f"Scene {self.scene}: {SceneComment[self.scene]}")
        self.check_freeze(current_time)
        return self.scene

    def find_ra_battle_exit(self) -> bool:
        im = cv2.cvtColor(self.img, cv2.COLOR_RGB2HSV)
        im = cv2.inRange(im, (29, 0, 0), (31, 255, 255))
        score, scope = self.template_match(
            "ra/battle_exit", ((75, 47), (165, 126)), cv2.TM_CCOEFF_NORMED
        )
        return scope if score > 0.8 else None

    def detect_ra_adventure(self) -> bool:
        img = cropimg(self.gray, ((385, 365), (475, 465)))
        img = thres2(img, 250)
        res = loadres("ra/adventure", True)
        result = cv2.matchTemplate(img, res, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        logger.debug(f"{max_val=} {max_loc=}")
        return max_val >= 0.9

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
        elif self.find("loading"):
            self.scene = Scene.UNKNOWN
        elif self.find("loading4"):
            self.scene = Scene.UNKNOWN

        # 奇遇
        elif self.detect_ra_adventure():
            self.scene = Scene.RA_ADVENTURE

        # 快速跳过剧情对话
        elif self.find("ra/guide_dialog"):
            self.scene = Scene.RA_GUIDE_DIALOG

        # 快速退出作战
        elif self.find_ra_battle_exit():
            self.scene = Scene.RA_BATTLE
        elif self.find("ra/battle_exit_dialog"):
            self.scene = Scene.RA_BATTLE_EXIT_CONFIRM

        # 作战与分队
        elif self.find("ra/squad_edit"):
            self.scene = Scene.RA_SQUAD_EDIT
        elif self.find("ra/start_action"):
            if self.find("ra/action_points"):
                self.scene = Scene.RA_BATTLE_ENTRANCE
            else:
                self.scene = Scene.RA_GUIDE_BATTLE_ENTRANCE
        elif self.find("ra/get_item"):
            self.scene = Scene.RA_GET_ITEM
        elif self.find("ra/return_from_kitchen"):
            self.scene = Scene.RA_KITCHEN
        elif self.find("ra/squad_edit_confirm_dialog"):
            self.scene = Scene.RA_SQUAD_EDIT_DIALOG
        elif self.find("ra/enter_battle_confirm_dialog"):
            self.scene = Scene.RA_SQUAD_ABNORMAL
        elif self.find("ra/battle_complete"):
            self.scene = Scene.RA_BATTLE_COMPLETE

        # 结算界面
        elif self.find("ra/day_complete"):
            self.scene = Scene.RA_DAY_COMPLETE
        elif self.find("ra/period_complete") and self.find("ra/click_anywhere"):
            self.scene = Scene.RA_PERIOD_COMPLETE

        # 森蚺图耶对话
        elif self.find("ra/guide_entrance"):
            self.scene = Scene.RA_GUIDE_ENTRANCE

        # 存档操作
        elif self.find("ra/delete_save_confirm_dialog"):
            self.scene = Scene.RA_DELETE_SAVE_DIALOG

        # 地图识别
        elif self.find("ra/waste_time_button"):
            self.scene = Scene.RA_DAY_DETAIL
        elif self.find("ra/waste_time_dialog"):
            self.scene = Scene.RA_WASTE_TIME_DIALOG
        elif self.find("ra/map_back", thres=200) and self.color(1817, 333)[0] > 250:
            self.scene = Scene.RA_MAP

        # 一张便条
        elif self.find("ra/notice"):
            self.scene = Scene.RA_NOTICE

        # 一张便条
        elif self.find("ra/no_enough_drink"):
            self.scene = Scene.RA_INSUFFICIENT_DRINK

        # 从首页选择终端进入生息演算主页
        elif self.find("terminal_longterm"):
            self.scene = Scene.TERMINAL_LONGTERM
        elif self.find("ra/main_title"):
            self.scene = Scene.RA_MAIN
        elif self.detect_index_scene():
            self.scene = Scene.INDEX
        elif self.find("terminal_main"):
            self.scene = Scene.TERMINAL_MAIN
        else:
            self.scene = Scene.UNKNOWN
            self.check_current_focus()

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
        elif self.find("terminal_main"):
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
            self.check_current_focus()

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
        elif self.find("terminal_main") is not None:
            self.scene = Scene.TERMINAL_MAIN
        elif self.find("terminal_regular"):
            self.scene = Scene.TERMINAL_REGULAR
        elif self.find("sss/main"):
            self.scene = Scene.SSS_MAIN
        elif self.find("sss/start_button"):
            self.scene = Scene.SSS_START
        elif self.find("sss/ec_button"):
            self.scene = Scene.SSS_EC
        elif self.find("sss/device_button") or self.find("sss/next_step_button"):
            self.scene = Scene.SSS_DEVICE
        elif self.find("sss/squad_button"):
            self.scene = Scene.SSS_SQUAD
        elif self.find("sss/deploy_button"):
            self.scene = Scene.SSS_DEPLOY
        elif self.find("sss/redeploy_button"):
            self.scene = Scene.SSS_REDEPLOY
        elif self.find("sss/confirm"):
            self.scene = Scene.SSS_CONFIRM
        elif self.find("sss/loading"):
            self.scene = Scene.SSS_LOADING
        elif self.find("sss/close_button"):
            self.scene = Scene.SSS_GUIDE
        else:
            self.scene = Scene.UNKNOWN
            self.check_current_focus()

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
        elif self.find("infra_overview"):
            self.scene = Scene.INFRA_MAIN
        elif self.find("train_main"):
            self.scene = Scene.TRAIN_MAIN
        elif self.find("skill_collect_confirm"):
            self.scene = Scene.TRAIN_FINISH
        elif self.find("training_support"):
            self.scene = Scene.TRAIN_SKILL_SELECT
        elif self.find("upgrade_failure"):
            self.scene = Scene.TRAIN_SKILL_UPGRADE_ERROR
        elif self.find("skill_confirm"):
            self.scene = Scene.TRAIN_SKILL_UPGRADE
        else:
            self.scene = Scene.UNKNOWN
            self.check_current_focus()

        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def get_factory_scene(self) -> int:
        """
        加工站场景
        """
        if self.scene != Scene.UNDEFINED:
            return self.scene
        # 连接中，优先级最高
        if self.find("connecting"):
            self.scene = Scene.CONNECTING
        elif self.find("infra_overview"):
            self.scene = Scene.INFRA_MAIN
        elif self.find("factory_dashboard"):
            self.scene = Scene.FACTORY_DASHBOARD
        elif self.find("factory_formula"):
            # 这是一个filter ，鉴于自动的话不会动，用来识别界面
            self.scene = Scene.FACTORY_FORMULA
        elif self.find("factory_product_collect"):
            self.scene = Scene.FACTORY_PRODUCT_COLLECT
        elif self.find("factory_tag"):
            self.scene = Scene.FACTORY_ROOM
        else:
            self.scene = Scene.UNKNOWN
            self.check_current_focus()

        logger.info(f"Scene: {self.scene}: {SceneComment[self.scene]}")

        self.check_loading_time()

        return self.scene

    def is_black(self) -> None:
        """check if the current scene is all black"""
        return np.max(self.gray[:, 105:-105]) < 16

    def find(
        self,
        res: tp.Res,
        draw: bool = False,
        scope: tp.Scope | None = None,
        thres: int | None = None,
        judge: bool = True,
        strict: bool = False,
        threshold: float = 0.0,
    ) -> tp.Scope:
        logger.debug(f"find: {res}")
        normalized_res = str(res).replace("\\", "/")
        force_feature_match = "navigation/stage/" in normalized_res

        if not force_feature_match:
            from arknights_mower.utils.recognize.find_color import ColorMatcher

            result = ColorMatcher().match(res, draw, self)
            if result is not None:
                return result

        if not force_feature_match:
            from arknights_mower.utils.recognize.find_template import TemplateMatcher

            result = TemplateMatcher().match(res, self)
            if result is not None:
                return result

        from arknights_mower.utils.recognize.find_feature import FeatureMatcher

        ret = FeatureMatcher().match(res, draw, scope, thres, judge, threshold, force_feature_match, self)
        if strict and ret is None:
            raise RecognizeError(f"Can't find '{res}'")
        return ret

    def score(
        self,
        res: str,
        draw: bool = False,
        scope: tp.Scope = None,
        thres: int | None = None,
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

        res_img = loadres(res, True)
        if thres is not None:
            # 对图像二值化处理
            res_img = thres2(res_img, thres)
            gray_img = cropimg(self.gray, scope)
            matcher = Matcher(thres2(gray_img, thres))
        else:
            matcher = self.matcher
        score = matcher.score(res_img, draw=draw, scope=scope, only_score=True)
        return score

    def template_match(
        self,
        res: str,
        scope: Optional[tp.Scope] = None,
        method: int = cv2.TM_CCOEFF_NORMED,
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
