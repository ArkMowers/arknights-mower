import random
import sys
import time
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Literal, Optional, Tuple

import cv2
import numpy as np

from arknights_mower.data import scene_list
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.const import KeyCode
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.email import send_message
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
from arknights_mower.utils.simulator import restart_simulator
from arknights_mower.utils.traceback import caller_info


class StrategyError(Exception):
    """Strategy Error"""

    pass


class BaseSolver:
    """Base class, provide basic operation"""

    tap_info = None, None
    waiting_scene = [
        Scene.CONNECTING,
        Scene.UNKNOWN,
        Scene.LOADING,
        Scene.LOGIN_LOADING,
        Scene.LOGIN_MAIN_NOENTRY,
        Scene.OPERATOR_ONGOING,
    ]

    def __init__(
        self,
        device: Device | None = None,
        recog: Recognizer | None = None,
    ) -> None:
        # self.device = device if device is not None else (recog.device if recog is not None else Device())
        if device is None and recog is not None:
            raise RuntimeError
        if device is not None:
            self.device = device
        else:
            while True:
                try:
                    self.device = Device()
                    self.device.client.check_server_alive()
                    Session().connect(config.conf.adb)
                    if not self.device.check_resolution():
                        raise MowerExit
                    if config.conf.droidcast.enable:
                        self.device.start_droidcast()
                    if config.conf.touch_method == "scrcpy":
                        self.device.control.scrcpy = Scrcpy(self.device.client)
                    break
                except MowerExit:
                    raise
                except Exception as e:
                    logger.exception(e)
                    restart_simulator()

        self.recog = recog if recog is not None else Recognizer(self.device)

    def run(self) -> None:
        self.check_current_focus()
        retry_times = config.MAX_RETRYTIME
        result = None
        start_time = datetime.now()
        recruit_timeout_limit = 300  # 获取超时限制 300s
        from arknights_mower.solvers.recruit import RecruitSolver

        while retry_times > 0:
            try:
                if isinstance(self, RecruitSolver):
                    if datetime.now() - start_time > timedelta(
                        seconds=recruit_timeout_limit
                    ):
                        raise Exception("任务超时,强制停止")
                result = self.transition()
                if result:
                    return result
            except MowerExit:
                raise
            except RecognizeError as e:
                logger.exception(f"识别出了点小差错 qwq: {e}")
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                logger.exception(e)
                raise e
            retry_times = config.MAX_RETRYTIME

    @abstractmethod
    def transition(self) -> bool:
        # the change from one state to another is called transition
        return True  # means task completed

    def get_color(self, pos: tp.Coordinate) -> tp.Pixel:
        """get the color of the pixel"""
        return self.recog.color(pos[0], pos[1])

    @staticmethod
    def get_pos(
        poly: tp.Location, x_rate: float = 0.5, y_rate: float = 0.5
    ) -> tp.Coordinate:
        """get the pos form tp.Location"""
        if poly is None:
            raise RecognizeError("poly is empty")
        elif len(poly) == 4:
            # tp.Rectangle
            x = (
                poly[0][0] * (1 - x_rate)
                + poly[1][0] * (1 - x_rate)
                + poly[2][0] * x_rate
                + poly[3][0] * x_rate
            ) / 2
            y = (
                poly[0][1] * (1 - y_rate)
                + poly[3][1] * (1 - y_rate)
                + poly[1][1] * y_rate
                + poly[2][1] * y_rate
            ) / 2
        elif len(poly) == 2 and isinstance(poly[0], (list, tuple)):
            # tp.Scope
            x = poly[0][0] * (1 - x_rate) + poly[1][0] * x_rate
            y = poly[0][1] * (1 - y_rate) + poly[1][1] * y_rate
        else:
            # tp.Coordinate
            x, y = poly
        return (int(x), int(y))

    def sleep(self, interval: float = 1) -> None:
        """sleeping for a interval"""
        csleep(interval)
        self.recog.update()

    def input(self, referent: str, input_area: tp.Scope, text: str = None) -> None:
        """input text"""
        logger.debug(f"input: {referent} {input_area}")
        self.device.tap(self.get_pos(input_area))
        time.sleep(0.5)
        if text is None:
            text = input(referent).strip()
        self.device.send_text(str(text))
        self.device.tap((0, 0))

    def find(
        self,
        res: tp.Res,
        draw: bool = False,
        scope: tp.Scope = None,
        thres: int = None,
        judge: bool = True,
        strict: bool = False,
        score=0.0,
    ) -> tp.Scope:
        return self.recog.find(res, draw, scope, thres, judge, strict, score)

    def tap(
        self,
        poly: tp.Location,
        x_rate: float = 0.5,
        y_rate: float = 0.5,
        interval: float = 1,
    ) -> None:
        """tap"""
        if config.stop_mower.is_set():
            raise MowerExit
        pos = self.get_pos(poly, x_rate, y_rate)
        self.device.tap(pos)
        if interval > 0:
            self.sleep(interval)

    def ctap(self, pos: tp.Location, max_seconds: int = 10):
        id = caller_info()
        logger.debug(id)
        now = datetime.now()
        lid, ltime = self.tap_info
        if lid != id or (lid == id and now - ltime > timedelta(seconds=max_seconds)):
            self.tap_info = id, now
            self.tap(pos)
        else:
            self.sleep()

    def check_current_focus(self):
        self.recog.check_current_focus()

    def restart_game(self):
        self.device.exit()
        self.device.launch()
        self.recog.update()

    def tap_element(
        self,
        element_name: tp.Res,
        x_rate: float = 0.5,
        y_rate: float = 0.5,
        interval: float = 1,
        score: float = 0.0,
        draw: bool = False,
        scope: tp.Scope = None,
        judge: bool = True,
        detected: bool = False,
        thres: Optional[int] = None,
    ) -> bool:
        """tap element"""
        element = self.find(
            element_name, draw, scope, judge=judge, score=score, thres=thres
        )
        if detected and element is None:
            return False
        self.tap(element, x_rate, y_rate, interval)
        return True

    def tap_index_element(
        self,
        name: Literal[
            "friend",
            "infrastructure",
            "mission",
            "recruit",
            "shop",
            "terminal",
            "warehouse",
            "headhunting",
            "mail",
        ],
    ):
        pos = {
            "friend": (544, 862),  # 好友
            "infrastructure": (1410, 870),  # 基建
            "mission": (1201, 904),  # 任务
            "recruit": (1507, 774),  # 公开招募
            "shop": (1251, 727),  # 采购中心
            "terminal": (1458, 297),  # 终端
            "warehouse": (1788, 973),  # 仓库
            "headhunting": (1749, 783),  # 干员寻访
            "mail": (292, 62),  # 邮件
        }
        self.ctap(pos[name])

    def tap_nav_element(
        self,
        name: Literal[
            "index",
            "terminal",
            "infrastructure",
            "recruit",
            "headhunting",
            "shop",
            "mission",
            "friend",
        ],
    ):
        pos = {
            "index": (140, 365),  # 首页
            "terminal": (793, 163),  # 终端
            "infrastructure": (1030, 163),  # 基建
            "recruit": (1435, 365),  # 公开招募
            "headhunting": (1623, 364),  # 干员寻访
            "shop": (1804, 362),  # 采购中心
            "mission": (1631, 53),  # 任务
            "friend": (1801, 53),  # 好友
        }
        self.ctap(pos[name])

    def tap_terminal_button(
        self,
        name: Literal[
            "main",
            "main_theme",
            "intermezzi",
            "biography",
            "collection",
            "regular",
            "longterm",
            "contract",
        ],
    ):
        y = 1005
        pos = {
            "main": (115, y),  # 首页
            "main_theme": (356, y),  # 主题曲
            "intermezzi": (596, y),  # 插曲
            "biography": (836, y),  # 别传
            "collection": (1077, y),  # 资源收集
            "regular": (1317, y),  # 常态事务
            "longterm": (1556, y),  # 长期探索
            "contract": (1796, y),  # 危机合约
        }
        self.ctap(pos[name])

    def template_match(
        self,
        res: str,
        scope: Optional[tp.Scope] = None,
        method: int = cv2.TM_CCOEFF_NORMED,
    ) -> Tuple[float, tp.Scope]:
        return self.recog.template_match(res, scope, method)

    def swipe(
        self,
        start: tp.Coordinate,
        movement: tp.Coordinate,
        duration: int = 100,
        interval: float = 1,
    ) -> None:
        """swipe"""
        if config.stop_mower.is_set():
            raise MowerExit
        end = (start[0] + movement[0], start[1] + movement[1])
        self.device.swipe(start, end, duration=duration)
        if interval > 0:
            self.sleep(interval)

    def swipe_only(
        self,
        start: tp.Coordinate,
        movement: tp.Coordinate,
        duration: int = 100,
        interval: float = 1,
    ) -> None:
        """swipe only, no rebuild and recapture"""
        if config.stop_mower.is_set():
            raise MowerExit
        end = (start[0] + movement[0], start[1] + movement[1])
        self.device.swipe(start, end, duration=duration)
        if interval > 0:
            csleep(interval)

    # def swipe_seq(self, points: list[tp.Coordinate], duration: int = 100, interval: float = 1, rebuild: bool = True) -> None:
    #     """ swipe with point sequence """
    #     self.device.swipe(points, duration=duration)
    #     if interval > 0:
    #         self.sleep(interval, rebuild)

    # def swipe_move(self, start: tp.Coordinate, movements: list[tp.Coordinate], duration: int = 100, interval: float = 1, rebuild: bool = True) -> None:
    #     """ swipe with start and movement sequence """
    #     points = [start]
    #     for move in movements:
    #         points.append((points[-1][0] + move[0], points[-1][1] + move[1]))
    #     self.device.swipe(points, duration=duration)
    #     if interval > 0:
    #         self.sleep(interval, rebuild)

    def swipe_noinertia(
        self,
        start: tp.Coordinate,
        movement: tp.Coordinate,
        duration: int = 20,
        interval: float = 0.2,
    ) -> None:
        """swipe with no inertia (movement should be vertical)"""
        if config.stop_mower.is_set():
            raise MowerExit
        points = [start]
        if movement[0] == 0:
            dis = abs(movement[1])
            points.append((start[0] + 100, start[1]))
            points.append((start[0] + 100, start[1] + movement[1]))
            points.append((start[0], start[1] + movement[1]))
        else:
            dis = abs(movement[0])
            points.append((start[0], start[1] + 100))
            points.append((start[0] + movement[0], start[1] + 100))
            points.append((start[0] + movement[0], start[1]))
        self.device.swipe_ext(points, durations=[200, dis * duration // 100, 200])
        if interval > 0:
            self.sleep(interval)

    def back(self, interval: float = 1) -> None:
        """send back keyevent"""
        self.device.send_keyevent(KeyCode.KEYCODE_BACK)
        self.sleep(interval)

    def scene(self) -> int:
        """get the current scene in the game"""
        return self.recog.get_scene()

    def ra_scene(self) -> int:
        """
        生息演算场景识别
        """
        return self.recog.get_ra_scene()

    def sf_scene(self) -> int:
        """
        隐秘战线场景识别
        """
        return self.recog.get_sf_scene()

    def sss_scene(self) -> int:
        """
        保全导航场景识别
        """
        return self.recog.get_sss_scene()

    def train_scene(self) -> int:
        """
        训练室景识别
        """
        return self.recog.get_train_scene()

    def is_login(self):
        """check if you are logged in"""
        return not (
            (scene := self.scene()) // 100 == 1 or scene // 100 == 99 or scene == -1
        )

    def solve_captcha(self, refresh=False):
        th = thres2(self.recog.gray, 254)
        pos = np.nonzero(th)
        offset_x = pos[1].min()
        offset_y = pos[0].min()
        img_scope = ((offset_x, offset_y), (pos[1].max(), pos[0].max()))
        img = cropimg(self.recog.img, img_scope)
        h = img.shape[0]

        def _t(ratio):
            return int(h * ratio)

        def _p(ratio_x, ratio_y):
            return _t(ratio_x), _t(ratio_y)

        if refresh:
            logger.info("刷新验证码")
            self.tap((offset_x + _t(0.189), offset_y + _t(0.916)), interval=3)
            img = cropimg(self.recog.img, img_scope)

        left_part = cropimg(img, (_p(0.032, 0.032), _p(0.202, 0.591)))
        hsv = cv2.cvtColor(left_part, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (25, 0, 0), (35, 255, 255))

        tpl_width = _t(0.148)
        tpl_height = _t(0.135)
        tpl_border = _t(0.0056)
        tpl_padding = _t(0.018)
        tpl = np.zeros((tpl_height, tpl_width), np.uint8)
        tpl[:] = (255,)
        tpl[
            tpl_border : tpl_height - tpl_border,
            tpl_border : tpl_width - tpl_border,
        ] = (0,)

        result = cv2.matchTemplate(mask, tpl, cv2.TM_SQDIFF, None, tpl)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        x, y = min_loc

        source_p = (
            (x + tpl_padding, y + tpl_padding),
            (x + tpl_width - tpl_padding, y + tpl_height - tpl_padding),
        )
        source = cropimg(left_part, source_p)
        mask = cropimg(mask, source_p)
        right_part = cropimg(
            img,
            (
                (_t(0.201), _t(0.032) + source_p[0][1]),
                (_t(0.94), _t(0.032) + source_p[1][1]),
            ),
        )

        for _y in range(source.shape[0]):
            for _x in range(source.shape[1]):
                for _c in range(source.shape[2]):
                    source[_y, _x, _c] = np.clip(source[_y, _x, _c] * 0.7 - 23, 0, 255)

        mask = cv2.bitwise_not(mask)
        result = cv2.matchTemplate(right_part, source, cv2.TM_SQDIFF_NORMED, None, mask)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        x = _t(0.201) + min_loc[0] - _t(0.032) - x - tpl_padding + _t(0.128)
        x += random.choice([-4, -3, -2, 2, 3, 4])

        def _rb(R, r):
            return random.random() * _t(R) + _t(r)

        btn_x = _rb(0.1, 0.01)
        start = offset_x + btn_x + _t(0.128), offset_y + _rb(0.1, 0.01) + _t(0.711)
        end = offset_x + btn_x + x, offset_y + _rb(0.1, 0.01) + _t(0.711)
        p1 = end[0] + _rb(0.1, 0.02), end[1] + _rb(0.05, 0.02)
        p2 = end[0] + _rb(0.1, 0.02), end[1] + _rb(0.05, 0.02)

        logger.info("滑动验证码")
        self.device.swipe_ext(
            (start, p1, p2, end, end),
            durations=[
                random.randint(400, 600),
                random.randint(200, 300),
                random.randint(200, 300),
                random.randint(200, 300),
            ],
        )

    def bilibili(self):
        """B服登录/隐私政策界面点击确认/同意"""
        img = cv2.cvtColor(self.recog.img, cv2.COLOR_RGB2HSV)
        img = cv2.inRange(img, (96, 150, 0), (100, 255, 255))
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        if len(rect) == 0:
            self.sleep()
            return
        rect.sort(key=lambda c: c[2], reverse=True)
        x, y, w, h = rect[0]
        self.tap(((x, y), (x + w, y + h)))

    def login(self):
        """
        登录进游戏
        """
        retry_times = config.MAX_RETRYTIME
        while retry_times and not self.is_login():
            try:
                if (scene := self.scene()) == Scene.LOGIN_START:
                    # 应对两种情况：
                    # 1. 点击左上角“网络检测”后出现“您即将进行一次网络拨测，该操作将采集您的网络状态并上报，点击确认继续”，点x
                    # 2. 点击左上角“清除缓存”之后取消
                    self.tap((665, 741))
                elif scene == Scene.LOGIN_NEW:
                    self.tap_element("login_new")
                elif scene == Scene.LOGIN_BILIBILI:
                    self.bilibili()
                elif scene == Scene.LOGIN_BILIBILI_PRIVACY:
                    self.bilibili()
                elif scene == Scene.LOGIN_QUICKLY:
                    self.tap_element("login_awake")
                elif scene == Scene.LOGIN_MAIN:
                    self.tap_element("login_account", 0.25)
                elif scene == Scene.LOGIN_REGISTER:
                    self.back(2)
                elif scene == Scene.LOGIN_CAPTCHA:
                    captcha_times = 3
                    while captcha_times > 0:
                        self.solve_captcha(captcha_times < 3)
                        self.sleep(5)
                        if self.find("login_captcha"):
                            captcha_times -= 1
                        else:
                            break
                    if captcha_times <= 0:
                        send_message(
                            "验证码自动滑动失败，退出游戏，停止运行mower", level="ERROR"
                        )
                        self.device.exit()
                        sys.exit()
                elif scene == Scene.LOGIN_INPUT:
                    input_area = self.find("login_username")
                    if input_area is not None:
                        self.input("Enter username: ", input_area, config.USERNAME)
                    input_area = self.find("login_password")
                    if input_area is not None:
                        self.input("Enter password: ", input_area, config.PASSWORD)
                    self.tap_element("login_button")
                elif scene == Scene.LOGIN_ANNOUNCE:
                    self.tap_element("login_iknow")
                elif scene in self.waiting_scene:
                    self.waiting_solver()
                elif scene == Scene.CONFIRM:
                    self.tap((960, 740))
                elif scene == Scene.LOGIN_CADPA_DETAIL:
                    self.back(2)
                elif scene == Scene.UNKNOWN:
                    raise RecognizeError("Unknown scene")
                else:
                    raise RecognizeError("Unanticipated scene")
            except MowerExit:
                raise
            except RecognizeError as e:
                logger.exception(f"识别出了点小差错 qwq: {e}")
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                logger.exception(e)
                raise e
            retry_times = config.MAX_RETRYTIME

        if not self.is_login():
            raise StrategyError

    def get_navigation(self):
        """
        判断是否存在导航栏，若存在则打开
        """
        retry_times = config.MAX_RETRYTIME
        while retry_times:
            if self.scene() == Scene.NAVIGATION_BAR:
                return True
            elif not self.tap_element("nav_button", detected=True):
                return False
            retry_times -= 1

    def back_to_infrastructure(self):
        self.back_to_index()
        self.tap_index_element("infrastructure")

    def back_to_index(self):
        """
        返回主页
        """
        logger.info("back to index")
        retry_times = config.MAX_RETRYTIME
        pre_scene = None
        while retry_times and (scene := self.scene()) != Scene.INDEX:
            try:
                if self.get_navigation():
                    self.tap_nav_element("index")
                elif scene == Scene.RIIC_REPORT:
                    self.tap((100, 60))
                elif scene == Scene.ANNOUNCEMENT:
                    self.tap(self.recog.check_announcement())
                elif scene == Scene.MATERIEL:
                    self.tap_element("materiel_ico")
                elif scene // 100 == 1:
                    self.login()
                elif scene == Scene.CONFIRM:
                    self.tap((960, 740))
                elif scene in self.waiting_scene:
                    self.waiting_solver()
                elif scene == Scene.SKIP:
                    self.tap_element("skip")
                elif scene == Scene.OPERATOR_ONGOING:
                    self.sleep(10)
                elif scene == Scene.OPERATOR_FINISH:
                    self.tap((self.recog.w // 2, 10))
                elif scene == Scene.OPERATOR_ELIMINATE_FINISH:
                    self.tap((self.recog.w // 2, 10))
                elif scene in [
                    Scene.DOUBLE_CONFIRM,
                    Scene.EXIT_GAME,
                    Scene.BACK_TO_FRIEND_LIST,
                    Scene.OPERATOR_GIVEUP,
                    Scene.LEAVE_INFRASTRUCTURE,
                    Scene.REFRESH_TAGS,
                ]:
                    self.tap_element("double_confirm/main", x_rate=1)
                elif scene == Scene.RECRUIT_AGENT:
                    self.tap((self.recog.w // 2, self.recog.h // 2))
                elif scene == Scene.MAIL:
                    self.back()
                elif scene == Scene.INFRA_ARRANGE_CONFIRM:
                    self.tap((self.recog.w // 3, self.recog.h - 10))
                elif scene == Scene.UNKNOWN:
                    raise RecognizeError("Unknown scene")
                elif pre_scene is None or pre_scene != scene:
                    pre_scene = scene
                    self.back()
                else:
                    raise RecognizeError("Unanticipated scene")
            except MowerExit:
                raise
            except RecognizeError as e:
                logger.exception(f"识别出了点小差错 qwq: {e}")
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                logger.exception(e)
                raise e
            retry_times = config.MAX_RETRYTIME

        if self.scene() != Scene.INDEX:
            raise StrategyError

    def to_sss(self):
        """保全导航"""
        logger.info("保全导航")
        start_time = datetime.now()

        while (scene := self.sss_scene()) not in [Scene.SSS_DEPLOY, Scene.SSS_REDEPLOY]:
            if datetime.now() - start_time > timedelta(minutes=1):
                return "保全导航超时"
            try:
                if scene == Scene.INDEX:
                    self.tap_index_element("terminal")
                elif scene == Scene.TERMINAL_MAIN:
                    self.tap_terminal_button("regular")
                elif scene == Scene.TERMINAL_REGULAR:
                    self.tap((1548, 870))
                elif scene == Scene.SSS_MAIN:
                    self.tap((384, 324) if config.conf.sss.type == 1 else (768, 648))
                elif scene == Scene.SSS_START:
                    self.tap_element("sss/start_button")
                elif scene == Scene.SSS_EC:
                    if config.conf.sss.ec == 1:
                        ec_x = 576
                    elif config.conf.sss.ec == 2:
                        ec_x = 960
                    else:
                        ec_x = 1860
                    self.tap((ec_x, 540))
                    self.tap_element("sss/ec_button")
                elif scene == Scene.SSS_DEVICE:
                    self.tap_element("sss/device_button")
                elif scene == Scene.SSS_SQUAD:
                    self.tap_element("sss/squad_button")
                elif scene == Scene.SSS_GUIDE:
                    self.tap_element("sss/close_button")
                else:
                    self.sleep()
            except MowerExit:
                raise
            except Exception as e:
                logger.exception(f"保全导航出错：{e}")
        logger.info(
            f"保全导航成功，用时{(datetime.now() - start_time).total_seconds():.0f}秒"
        )

    def waiting_solver(self):
        """需要等待的页面解决方法。触发超时重启会返回False"""
        scene = self.scene()
        sleep_time, wait_count = getattr(
            config.conf.waiting_scene, scene_list[str(scene)]["label"]
        )
        for _ in range(wait_count):
            self.sleep(sleep_time)
            if self.scene() != scene:
                return True
        logger.warning("相同场景等待超时")
        self.device.exit()
        csleep(3)
        self.check_current_focus()
        return False
