from __future__ import annotations
from abc import abstractmethod

import time
import traceback

from . import config
from . import detector
from .device import Device, KeyCode
from .log import logger
from .recognize import Recognizer, Scene, RecognizeError
from ..utils import typealias as tp


class StrategyError(Exception):
    """ Strategy Error """
    pass


class BaseSolver:
    """ Base class, provide basic operation """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        # self.device = device if device is not None else (recog.device if recog is not None else Device())
        if device is None and recog is not None:
            raise RuntimeError
        self.device = device if device is not None else Device()
        self.recog = recog if recog is not None else Recognizer(self.device)
        self.device.check_current_focus()

    def run(self) -> None:
        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                if self.transition():
                    break
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
                self.recog.save_screencap('failure')
                retry_times -= 1
                self.sleep(3)
                continue
            except StrategyError as e:
                logger.error(e)
                logger.debug(traceback.format_exc())
                return
            except Exception as e:
                raise e
            retry_times = config.MAX_RETRYTIME

    @abstractmethod
    def transition(self) -> bool:
        # the change from one state to another is called transition
        return True  # means task completed

    def get_color(self, pos: tp.Coordinate) -> tp.Pixel:
        """ get the color of the pixel """
        return self.recog.color(pos[0], pos[1])

    def get_pos(self, poly: tp.Location, x_rate: float = 0.5, y_rate: float = 0.5) -> tp.Coordinate:
        """ get the pos form tp.Location """
        if poly is None:
            raise RecognizeError('poly is empty')
        elif len(poly) == 4:
            # tp.Rectangle
            x = (poly[0][0] * (1-x_rate) + poly[1][0] * (1-x_rate) +
                 poly[2][0] * x_rate + poly[3][0] * x_rate) / 2
            y = (poly[0][1] * (1-y_rate) + poly[3][1] * (1-y_rate) +
                 poly[1][1] * y_rate + poly[2][1] * y_rate) / 2
        elif len(poly) == 2 and isinstance(poly[0], (list, tuple)):
            # tp.Scope
            x = poly[0][0] * (1-x_rate) + poly[1][0] * x_rate
            y = poly[0][1] * (1-y_rate) + poly[1][1] * y_rate
        else:
            # tp.Coordinate
            x, y = poly
        return (int(x), int(y))

    def sleep(self, interval: float = 1, rebuild: bool = True) -> None:
        """ sleeping for a interval """
        time.sleep(interval)
        self.recog.update(rebuild=rebuild)

    def input(self, referent: str, input_area: tp.Scope, text: str = None) -> None:
        """ input text """
        logger.debug(f'input: {referent} {input_area}')
        self.device.tap(self.get_pos(input_area))
        time.sleep(0.5)
        if text is None:
            text = input(referent).strip()
        self.device.send_text(str(text))
        self.device.tap((0, 0))

    def find(self, res: str, draw: bool = False, scope: tp.Scope = None, thres: int = None, judge: bool = True, strict: bool = False) -> tp.Scope:
        return self.recog.find(res, draw, scope, thres, judge, strict)

    def tap(self, poly: tp.Location, x_rate: float = 0.5, y_rate: float = 0.5, interval: float = 1, rebuild: bool = True) -> None:
        """ tap """
        pos = self.get_pos(poly, x_rate, y_rate)
        self.device.tap(pos)
        if interval > 0:
            self.sleep(interval, rebuild)

    def tap_element(self, element_name: str, x_rate: float = 0.5, y_rate: float = 0.5, interval: float = 1, rebuild: bool = True,
                    draw: bool = False, scope: tp.Scope = None, judge: bool = True, detected: bool = False) -> bool:
        """ tap element """
        if element_name == 'nav_button':
            element = self.recog.nav_button()
        else:
            element = self.find(element_name, draw, scope, judge=judge)
        if detected and element is None:
            return False
        self.tap(element, x_rate, y_rate, interval, rebuild)
        return True

    def swipe(self, start: tp.Coordinate, movement: tp.Coordinate, duration: int = 100, interval: float = 1, rebuild: bool = True) -> None:
        """ swipe """
        end = (start[0] + movement[0], start[1] + movement[1])
        self.device.swipe(start, end, duration=duration)
        if interval > 0:
            self.sleep(interval, rebuild)

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

    def swipe_noinertia(self, start: tp.Coordinate, movement: tp.Coordinate, duration: int = 100, interval: float = 1, rebuild: bool = False) -> None:
        """ swipe with no inertia (movement should be vertical) """
        points = [start]
        if movement[0] == 0:
            dis = abs(movement[1])
            points.append((start[0]+100, start[1]))
            points.append((start[0]+100, start[1]+movement[1]))
            points.append((start[0], start[1]+movement[1]))
        else:
            dis = abs(movement[0])
            points.append((start[0], start[1]+100))
            points.append((start[0]+movement[0], start[1]+100))
            points.append((start[0]+movement[0], start[1]))
        self.device.swipe_ext(points, durations=[200, dis*duration//100, 200])
        if interval > 0:
            self.sleep(interval, rebuild)

    def back(self, interval: float = 1, rebuild: bool = True) -> None:
        """ send back keyevent """
        self.device.send_keyevent(KeyCode.KEYCODE_BACK)
        self.sleep(interval, rebuild)

    def scene(self) -> int:
        """ get the current scene in the game """
        return self.recog.get_scene()

    def is_login(self):
        """ check if you are logged in """
        return not (self.scene() // 100 == 1 or self.scene() // 100 == 99 or self.scene() == -1)

    def login(self):
        """
        登录进游戏
        """
        retry_times = config.MAX_RETRYTIME
        while retry_times and not self.is_login():
            try:
                if self.scene() == Scene.LOGIN_START:
                    self.tap((self.recog.w // 2, self.recog.h - 10), 3)
                elif self.scene() == Scene.LOGIN_QUICKLY:
                    self.tap_element('login_awake')
                elif self.scene() == Scene.LOGIN_MAIN:
                    self.tap_element('login_account', 0.25)
                elif self.scene() == Scene.LOGIN_REGISTER:
                    self.back(2)
                elif self.scene() == Scene.LOGIN_CAPTCHA:
                    exit()
                    # self.back(600)  # TODO: Pending
                elif self.scene() == Scene.LOGIN_INPUT:
                    input_area = self.find('login_username')
                    if input_area is not None:
                        self.input('Enter username: ', input_area, config.USERNAME)
                    input_area = self.find('login_password')
                    if input_area is not None:
                        self.input('Enter password: ', input_area, config.PASSWORD)
                    self.tap_element('login_button')
                elif self.scene() == Scene.LOGIN_ANNOUNCE:
                    self.tap_element('login_iknow')
                elif self.scene() == Scene.LOGIN_LOADING:
                    self.sleep(3)
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.scene() == Scene.CONNECTING:
                    self.sleep(3)
                elif self.scene() == Scene.CONFIRM:
                    self.tap(detector.confirm(self.recog.img))
                elif self.scene() == Scene.UNKNOWN:
                    raise RecognizeError('Unknown scene')
                else:
                    raise RecognizeError('Unanticipated scene')
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
                self.recog.save_screencap('failure')
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
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
            elif not self.tap_element('nav_button', detected=True):
                return False
            retry_times -= 1

    def back_to_index(self):
        """
        返回主页
        """
        logger.info('back to index')
        retry_times = config.MAX_RETRYTIME
        pre_scene = None
        while retry_times and self.scene() != Scene.INDEX:
            try:
                if self.get_navigation():
                    self.tap_element('nav_index')
                elif self.scene() == Scene.ANNOUNCEMENT:
                    self.tap(detector.announcement_close(self.recog.img))
                elif self.scene() == Scene.MATERIEL:
                    self.tap_element('materiel_ico')
                elif self.scene() // 100 == 1:
                    self.login()
                elif self.scene() == Scene.CONFIRM:
                    self.tap(detector.confirm(self.recog.img))
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.scene() == Scene.CONNECTING:
                    self.sleep(3)
                elif self.scene() == Scene.SKIP:
                    self.tap_element('skip')
                elif self.scene() == Scene.OPERATOR_ONGOING:
                    self.sleep(10)
                elif self.scene() == Scene.OPERATOR_FINISH:
                    self.tap((self.recog.w // 2, 10))
                elif self.scene() == Scene.OPERATOR_ELIMINATE_FINISH:
                    self.tap((self.recog.w // 2, 10))
                elif self.scene() == Scene.DOUBLE_CONFIRM:
                    self.tap_element('double_confirm', 0.8)
                elif self.scene() == Scene.MAIL:
                    mail = self.find('mail')
                    mid_y = (mail[0][1] + mail[1][1]) // 2
                    self.tap((mid_y, mid_y))
                elif self.scene() == Scene.INFRA_ARRANGE_CONFIRM:
                    self.tap((self.recog.w // 3, self.recog.h - 10))
                elif self.scene() == Scene.UNKNOWN:
                    raise RecognizeError('Unknown scene')
                elif pre_scene is None or pre_scene != self.scene():
                    pre_scene = self.scene()
                    self.back()
                else:
                    raise RecognizeError('Unanticipated scene')
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
                self.recog.save_screencap('failure')
                retry_times -= 1
                self.sleep(3)
                continue
            except Exception as e:
                raise e
            retry_times = config.MAX_RETRYTIME

        if self.scene() != Scene.INDEX:
            raise StrategyError
