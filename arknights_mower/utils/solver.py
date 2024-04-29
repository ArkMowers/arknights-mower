from __future__ import annotations
from typing import Optional, Tuple

import sys
import random
import cv2

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import time
import traceback
import requests
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from abc import abstractmethod

from ..utils import typealias as tp
from . import config, detector
from .device import Device, KeyCode
from .log import logger
from .recognize import RecognizeError, Recognizer, Scene

from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.matcher import Matcher
import numpy as np

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
        if self.device.check_current_focus():
            self.recog.update()

    def run(self) -> None:
        retry_times = config.MAX_RETRYTIME
        result = None
        while retry_times > 0:
            try:
                result = self.transition()
                if result:
                    return result
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
            x = (poly[0][0] * (1 - x_rate) + poly[1][0] * (1 - x_rate) +
                 poly[2][0] * x_rate + poly[3][0] * x_rate) / 2
            y = (poly[0][1] * (1 - y_rate) + poly[3][1] * (1 - y_rate) +
                 poly[1][1] * y_rate + poly[2][1] * y_rate) / 2
        elif len(poly) == 2 and isinstance(poly[0], (list, tuple)):
            # tp.Scope
            x = poly[0][0] * (1 - x_rate) + poly[1][0] * x_rate
            y = poly[0][1] * (1 - y_rate) + poly[1][1] * y_rate
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

    def find(self, res: str, draw: bool = False, scope: tp.Scope = None, thres: int = None, judge: bool = True,
             strict: bool = False, score=0.0) -> tp.Scope:
        return self.recog.find(res, draw, scope, thres, judge, strict, score)

    def tap(self, poly: tp.Location, x_rate: float = 0.5, y_rate: float = 0.5, interval: float = 1,
            rebuild: bool = True) -> None:
        """ tap """
        pos = self.get_pos(poly, x_rate, y_rate)
        self.device.tap(pos)
        if interval > 0:
            self.sleep(interval, rebuild)

    def tap_element(self, element_name: str, x_rate: float = 0.5, y_rate: float = 0.5, interval: float = 1,
                    rebuild: bool = True, score: float = 0.0,
                    draw: bool = False, scope: tp.Scope = None, judge: bool = True, detected: bool = False) -> bool:
        """ tap element """
        if element_name == 'nav_button':
            element = self.recog.nav_button()
        else:
            element = self.find(element_name, draw, scope, judge=judge, score=score)
        if detected and element is None:
            return False
        self.tap(element, x_rate, y_rate, interval, rebuild)
        return True

    def tap_index_element(self, name):
        pos = {
            "friend": (544, 862),
            "infrastructure": (1545, 948),
            "mission": (1201, 904),
            "recruit": (1507, 774),
            "shop": (1251, 727),
            "terminal": (1458, 297),
            "warehouse": (1788, 973),
        }
        self.tap(pos[name], interval=2)

    def template_match(self, res: str, scope: Optional[tp.Scope] = None, method: int = cv2.TM_CCOEFF) -> Tuple[float, tp.Scope]:
        return self.recog.template_match(res, scope, method)

    def swipe(self, start: tp.Coordinate, movement: tp.Coordinate, duration: int = 100, interval: float = 1,
              rebuild: bool = True) -> None:
        """ swipe """
        end = (start[0] + movement[0], start[1] + movement[1])
        self.device.swipe(start, end, duration=duration)
        if interval > 0:
            self.sleep(interval, rebuild)

    def swipe_only(self, start: tp.Coordinate, movement: tp.Coordinate, duration: int = 100,
                   interval: float = 1) -> None:
        """ swipe only, no rebuild and recapture """
        end = (start[0] + movement[0], start[1] + movement[1])
        self.device.swipe(start, end, duration=duration)
        if interval > 0:
            time.sleep(interval)

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

    def swipe_noinertia(self, start: tp.Coordinate, movement: tp.Coordinate, duration: int = 50, interval: float = 0.2,
                        rebuild: bool = False) -> None:
        """ swipe with no inertia (movement should be vertical) """
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
            self.sleep(interval, rebuild)

    def back(self, interval: float = 1, rebuild: bool = True) -> None:
        """ send back keyevent """
        self.device.send_keyevent(KeyCode.KEYCODE_BACK)
        self.sleep(interval, rebuild)

    def scene(self) -> int:
        """ get the current scene in the game """
        return self.recog.get_scene()

    def get_infra_scene(self) -> int:
        """ get the current scene in the infra """
        return self.recog.get_infra_scene()
    
    def ra_scene(self) -> int:
        """
        生息演算场景识别
        """
        return self.recog.get_ra_scene()
    
    def sss_scene(self) -> int:
        """
        保全导航场景识别
        """
        return self.recog.get_sss_scene()

    def clue_scene(self) -> int:
        """
        线索场景识别
        """
        return self.recog.get_clue_scene()

    def is_login(self):
        """ check if you are logged in """
        return not ((scene := self.scene()) // 100 == 1 or scene // 100 == 99 or scene == -1)

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
        tpl[tpl_border:tpl_height - tpl_border, tpl_border:tpl_width - tpl_border] = (0,)

        result = cv2.matchTemplate(mask, tpl, cv2.TM_SQDIFF, None, tpl)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        x, y = min_loc

        source_p = (x + tpl_padding, y + tpl_padding), (x + tpl_width - tpl_padding, y + tpl_height - tpl_padding)
        source = cropimg(left_part, source_p)
        mask = cropimg(mask, source_p)
        right_part = cropimg(img, ((_t(0.201), _t(0.032) + source_p[0][1]), (_t(0.94), _t(0.032) + source_p[1][1])))

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
        self.device.swipe_ext((start, p1, p2, end, end), durations=[random.randint(400, 600), random.randint(200, 300), random.randint(200, 300), random.randint(200, 300)])

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
                    self.tap((665, 741), 3)
                elif scene == Scene.LOGIN_NEW:
                    self.tap_element('login_new')
                elif scene == Scene.LOGIN_BILIBILI:
                    self.tap_element('login_bilibili_entry')
                elif scene == Scene.LOGIN_BILIBILI_PRIVACY:
                    self.tap_element('login_bilibili_privacy_accept')
                elif scene == Scene.LOGIN_QUICKLY:
                    self.tap_element('login_awake')
                elif scene == Scene.LOGIN_MAIN:
                    self.tap_element('login_account', 0.25)
                elif scene == Scene.LOGIN_REGISTER:
                    self.back(2)
                elif scene == Scene.LOGIN_CAPTCHA:
                    captcha_times = 3
                    while captcha_times > 0:
                        self.solve_captcha(captcha_times < 3)
                        self.sleep(5)
                        if self.find('login_captcha'):
                            captcha_times -= 1
                        else:
                            break
                    if captcha_times <= 0:
                        self.send_message("验证码自动滑动失败，退出游戏，停止运行mower")
                        self.device.exit()
                        sys.exit()
                elif scene == Scene.LOGIN_INPUT:
                    input_area = self.find('login_username')
                    if input_area is not None:
                        self.input('Enter username: ', input_area, config.USERNAME)
                    input_area = self.find('login_password')
                    if input_area is not None:
                        self.input('Enter password: ', input_area, config.PASSWORD)
                    self.tap_element('login_button')
                elif scene == Scene.LOGIN_ANNOUNCE:
                    self.tap_element('login_iknow')
                elif scene == Scene.LOGIN_LOADING:
                    self.waiting_solver(Scene.LOGIN_LOADING)
                elif scene == Scene.LOADING:
                    self.waiting_solver(Scene.LOADING)
                elif scene == Scene.CONNECTING:
                    self.waiting_solver(Scene.CONNECTING)
                elif scene == Scene.CONFIRM:
                    self.tap(detector.confirm(self.recog.img))
                elif scene == Scene.LOGIN_MAIN_NOENTRY:
                    self.waiting_solver(Scene.LOGIN_MAIN_NOENTRY)
                elif scene == Scene.LOGIN_CADPA_DETAIL:
                    self.back(2)
                elif scene == Scene.NETWORK_CHECK:
                    self.tap_element('double_confirm', 0.2)
                elif scene == Scene.UNKNOWN:
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

    def back_to_infrastructure(self):
        self.back_to_index()
        self.tap_index_element('infrastructure')

    def back_to_index(self):
        """
        返回主页
        """
        logger.info('back to index')
        retry_times = config.MAX_RETRYTIME
        pre_scene = None
        while retry_times and (scene := self.scene()) != Scene.INDEX:
            try:
                if self.get_navigation():
                    self.tap_element('nav_index')
                elif scene == Scene.CLOSE_MINE:
                    self.tap_element('close_mine')
                elif scene == Scene.CHECK_IN:
                    self.tap_element('check_in')
                elif scene == Scene.RIIC_REPORT:
                    self.tap((100, 60))
                elif scene == Scene.ANNOUNCEMENT:
                    self.tap(self.recog.check_announcement())
                elif scene == Scene.MATERIEL:
                    self.tap_element('materiel_ico')
                elif scene // 100 == 1:
                    self.login()
                elif scene == Scene.CONFIRM:
                    self.tap(detector.confirm(self.recog.img))
                elif scene == Scene.LOADING:
                    self.waiting_solver(Scene.LOADING)
                elif scene == Scene.CONNECTING:
                    self.waiting_solver(Scene.CONNECTING)
                elif scene == Scene.SKIP:
                    self.tap_element('skip')
                elif scene == Scene.OPERATOR_ONGOING:
                    self.sleep(10)
                elif scene == Scene.OPERATOR_FINISH:
                    self.tap((self.recog.w // 2, 10))
                elif scene == Scene.OPERATOR_ELIMINATE_FINISH:
                    self.tap((self.recog.w // 2, 10))
                elif scene == Scene.DOUBLE_CONFIRM:
                    self.tap_element('double_confirm', 0.8)
                elif scene == Scene.NETWORK_CHECK:
                    self.tap_element('double_confirm', 0.2)
                elif scene == Scene.RECRUIT_AGENT:
                    self.tap((self.recog.w // 2, self.recog.h // 2))
                elif scene == Scene.MAIL:
                    mail = self.find('mail')
                    mid_y = (mail[0][1] + mail[1][1]) // 2
                    self.tap((mid_y, mid_y))
                elif scene == Scene.INFRA_ARRANGE_CONFIRM:
                    self.tap((self.recog.w // 3, self.recog.h - 10))
                elif scene == Scene.UNKNOWN:
                    raise RecognizeError('Unknown scene')
                elif pre_scene is None or pre_scene != scene:
                    pre_scene = scene
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

    def to_sss(self, sss_type, ec_type=3):
        """保全导航"""
        logger.info('保全导航')
        start_time = datetime.now()

        while (scene := self.sss_scene()) not in [Scene.SSS_DEPLOY, Scene.SSS_REDEPLOY]:
            if scene == Scene.INDEX:
                self.tap_index_element("terminal")
            elif scene == Scene.TERMINAL_MAIN:
                self.tap((1317, 1005))
            elif scene == Scene.TERMINAL_REGULAR:
                self.tap((1548, 870))
            elif scene == Scene.SSS_MAIN:
                self.tap((384, 324) if sss_type == 1 else (768, 648))
            elif scene == Scene.SSS_START:
                self.tap_element("sss/start_button")
            elif scene == Scene.SSS_EC:
                if ec_type == 1:
                    ec_x = 576
                elif ec_type == 2:
                    ec_x = 960
                else:
                    ec_x = 1344
                self.tap((ec_x, 540))
                self.tap_element("sss/ec_button")
            elif scene == Scene.SSS_DEVICE:
                self.tap_element("sss/device_button")
            elif scene == Scene.SSS_SQUAD:
                self.tap_element("sss/squad_button")
            elif scene == Scene.SSS_GUIDE:
                self.tap_element("sss/close_button")
            now = datetime.now()
            if now - start_time > timedelta(minutes=1):
                return "保全导航失败"
            self.sleep()
        logger.info(f"保全导航成功，用时{(datetime.now() - start_time).total_seconds():.0f}秒")

    def waiting_solver(self, scenes, wait_count=20, sleep_time=3):
        """需要等待的页面解决方法。触发超时重启会返回False
        """
        while wait_count > 0:
            self.sleep(sleep_time)
            if self.scene() != scenes and self.get_infra_scene() != scenes:
                return True
            wait_count -= 1
        logger.warning("同一等待界面等待超时，重启方舟。")
        self.device.exit()
        time.sleep(3)
        if self.device.check_current_focus():
            self.recog.update()
        return False

    def wait_for_scene(self, scene, method, wait_count=10, sleep_time=1):
        """等待某个页面载入
        """
        while wait_count > 0:
            self.sleep(sleep_time)
            if method == "get_infra_scene":
                if self.get_infra_scene() == scene:
                    return True
            elif method == "scene":
                if self.scene() == scene:
                    return True
            wait_count -= 1
        raise Exception("等待超时")

    # 将html表单转化为通用markdown格式（为了避免修改之前email内容，采用基于之前数据格式进行加工的方案）
    def html_to_markdown(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')

        markdown_output = ""

        # 提取标题
        title = soup.find('title')
        if title:
            markdown_output += f"## {title.get_text()}\n\n"

        # 提取表格
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            header_processed = False  # 标记是否已经处理过列头
            for row in rows:
                columns = row.find_all(['td', 'th'])
                line_data = []
                for col in columns:
                    colspan = int(col.get('colspan', 1))
                    content = col.get_text().strip() + ' ' * (colspan - 1)
                    line_data.append(content)
                markdown_output += "| " + " | ".join(line_data) + " |\n"

                # 仅为首个列头添加分隔线
                if any(cell.name == 'th' for cell in columns) and not header_processed:
                    line_separators = []
                    for col in columns:
                        colspan = int(col.get('colspan', 1))
                        line_separators.extend(['---'] * colspan)
                    markdown_output += "| " + " | ".join(line_separators) + " |\n"
                    header_processed = True

        return markdown_output.strip()

    # 指数退避策略逐渐增加等待时间
    def exponential_backoff(self, initial_delay=1, max_retries=3, factor=2):
        """ Implement exponential backoff for retries. """
        delay = initial_delay
        retries = 0
        while retries < max_retries:
            yield delay
            delay *= factor
            retries += 1

    # QQ邮件异常处理
    def handle_email_error(self, email_config, msg):
        for delay in self.exponential_backoff():
            try:
                if email_config["custom_smtp_server"]["enable"]:
                    smtp_server = email_config["custom_smtp_server"]["server"]
                    ssl_port = email_config["custom_smtp_server"]["ssl_port"]
                    if email_config["custom_smtp_server"]["encryption"] == "starttls":
                        # 使用STARTTLS加密
                        s = smtplib.SMTP(smtp_server, ssl_port, timeout=10.0)
                        s.starttls()
                    else:
                        # 使用TLS加密
                        s = smtplib.SMTP_SSL(smtp_server, ssl_port, timeout=10.0)
                else:
                    s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10.0)
                s.login(email_config['account'], email_config['pass_code'])
                s.sendmail(email_config['account'], email_config.get('recipients', []), msg.as_string())
                s.close()
                logger.info("邮件发送成功")
                break
            except Exception as e:
                logger.error("邮件发送失败")
                logger.exception(e)
                time.sleep(delay)

    # Server酱异常处理
    def handle_serverJang_error(self, url, data):
        for delay in self.exponential_backoff():
            try:
                response = requests.post(url, data=data)
                json_data = response.json()
                if json_data.get('code') == 0:
                    logger.info('Server酱通知发送成功')
                    break
                else:
                    logger.error(f"Server酱通知发送失败，错误信息：{json_data.get('message')}")
                    time.sleep(delay)
            except Exception as e:
                logger.error("Server酱通知发送失败")
                logger.exception(e)
                time.sleep(delay)

    # 消息发送 原Email发送 EightyDollars
    def send_message(self, body='', subject='', subtype='plain', retry_times=3):
        send_message_config = getattr(self, 'send_message_config', None)
        if not send_message_config:
            logger.error("send_message_config 未在配置中定义!")
            return

        failed_methods = []

        if subtype == 'plain' and subject == '':
            subject = body

        # markdown格式的消息体
        mkBody = body
        # 如果body是HTML内容，转换为Markdown格式
        if subtype == 'html':
            mkBody = self.html_to_markdown(body)

        # 获取QQ邮件配置
        email_config = send_message_config.get('email_config')
        # 获取Server酱配置
        serverJang_push_config = send_message_config.get('serverJang_push_config')

        # 邮件通知部分
        if email_config and email_config.get('mail_enable', 0):
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, subtype))
            msg['Subject'] = email_config.get('subject', '') + subject
            msg['From'] = email_config.get('account', '')
            msg['To'] = ", ".join(email_config.get('recipients', []))

            try:
                self.handle_email_error(email_config, msg)  # 第一次尝试
            except Exception as e:
                failed_methods.append(('email', email_config, msg))

        # Server酱通知部分
        if serverJang_push_config and serverJang_push_config.get('server_push_enable', False):
            send_key = serverJang_push_config.get('sendKey')
            if not send_key:
                logger.error('Server酱的sendKey未配置')
                return

            url = f'https://sctapi.ftqq.com/{send_key}.send'
            data = {
                'title': '[Mower通知]' + subject,
                'desp': mkBody
            }

            try:
                self.handle_serverJang_error(url, data)  # 第一次尝试
            except Exception as e:
                failed_methods.append(('serverJang', url, data))

        # 处理失败的方法
        for method, *args in failed_methods:
            if method == 'email':
                for _ in range(retry_times):
                    try:
                        self.handle_email_error(*args)
                        break
                    except:
                        time.sleep(1)
            elif method == 'serverJang':
                for _ in range(retry_times):
                    try:
                        self.handle_serverJang_error(*args)
                        break
                    except:
                        time.sleep(1)
