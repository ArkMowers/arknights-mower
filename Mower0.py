from __future__ import annotations
import copy
import ctypes
import colorlog
import cv2
import inspect
import json
import os
import pystray
import pathlib
import requests
import smtplib
import sys
import threading
import time
import warnings
import yaml
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from tkinter import *
from typing import Optional
from PIL import Image
from pystray import MenuItem, Menu
from arknights_mower.data import agent_list
from arknights_mower.utils import (character_recognize, config, detector, segment)
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.datetime import the_same_time
from arknights_mower.utils.device.adb_client import ADBClient
from arknights_mower.utils.device.minitouch import MiniTouch
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.log import init_fhlr, logger, save_screenshot
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.pipe import push_operators
from arknights_mower.utils.scheduler_task import SchedulerTask
from arknights_mower.utils.solver import BaseSolver
from arknights_mower.utils.recognize import Recognizer, RecognizeError
from ctypes import CFUNCTYPE, c_int, c_char_p, c_void_p


def warn(*args, **kwargs):
    pass


warnings.warn = warn

from paddleocr import PaddleOCR
from arknights_mower.strategy import Solver

源码日志 = '否'
ocr = None
任务提示 = str()
下个任务开始时间 = datetime.now()
字幕 = str()
已签到日期 = str()

with open('Mower0用户配置文件.yaml', 'r', encoding='utf-8') as f:
    用户配置 = yaml.load(f.read(), Loader=yaml.FullLoader)

服务器 = 'com.hypergryph.arknights'
if 用户配置['服务器'] == 'Bilibili服务器':    服务器 = 'com.hypergryph.arknights.bilibili'
弹窗提醒开关 = False
if 用户配置['弹窗提醒开关'] == '开':   弹窗提醒开关 = True
跑单提前运行时间 = 用户配置['跑单提前运行时间']
更换干员前缓冲时间 = 用户配置['更换干员前缓冲时间']
龙舌兰和但书休息 = False
if 用户配置['龙舌兰和但书休息'] == '开':     龙舌兰和但书休息 = True
悬浮字幕开关 = False
if 用户配置['悬浮字幕开关'] == '开':   悬浮字幕开关 = True
窗口 = Tk()
窗口宽度 = 窗口.winfo_screenwidth()
窗口高度 = 窗口.winfo_screenheight()
字幕字号 = 窗口.winfo_screenheight() // 22
if 用户配置['字幕字号'] != '默认':
    字幕字号 = int(用户配置['字幕字号'])
字幕颜色 = 用户配置['字幕颜色']
邮件设置 = 用户配置['邮件设置']
MAA设置 = 用户配置['MAA设置']


class 设备控制(object):
    class 操控(object):

        def __init__(self, device: 设备控制, client: ADBClient = None, touch_device: str = None) -> None:
            self.device = device
            self.minitouch = None
            self.scrcpy = None

            if config.ADB_CONTROL_CLIENT == 'minitouch':
                self.minitouch = MiniTouch(client, touch_device)
            elif config.ADB_CONTROL_CLIENT == 'scrcpy':
                self.scrcpy = Scrcpy(client)
            else:
                # MiniTouch does not support Android 10+
                if int(client.android_version().split('.')[0]) < 10:
                    self.minitouch = MiniTouch(client, touch_device)
                else:
                    self.scrcpy = Scrcpy(client)

        def tap(self, point: tuple[int, int]) -> None:
            if self.minitouch:
                self.minitouch.tap([point], self.device.display_frames())
            elif self.scrcpy:
                self.scrcpy.tap(point[0], point[1])
            else:
                raise NotImplementedError

        def swipe(self, start: tuple[int, int], end: tuple[int, int], duration: int) -> None:
            if self.minitouch:
                self.minitouch.swipe(
                    [start, end], self.device.display_frames(), duration=duration)
            elif self.scrcpy:
                self.scrcpy.swipe(
                    start[0], start[1], end[0], end[1], duration / 1000)
            else:
                raise NotImplementedError

        def swipe_ext(self, points: list[tuple[int, int]], durations: list[int], up_wait: int) -> None:
            if self.minitouch:
                self.minitouch.swipe(
                    points, self.device.display_frames(), duration=durations, up_wait=up_wait)
            elif self.scrcpy:
                total = len(durations)
                for idx, (S, E, D) in enumerate(zip(points[:-1], points[1:], durations)):
                    self.scrcpy.swipe(S[0], S[1], E[0], E[1], D / 1000,
                                      up_wait / 1000 if idx == total - 1 else 0,
                                      fall=idx == 0, lift=idx == total - 1)
            else:
                raise NotImplementedError

    def __init__(self, device_id: str = None, connect: str = None, touch_device: str = None) -> None:
        self.device_id = device_id
        self.connect = connect
        self.touch_device = touch_device
        self.client = None
        self.control = None
        self.start()

    def start(self) -> None:
        self.client = ADBClient(self.device_id, self.connect)
        self.control = 设备控制.操控(self, self.client)

    def run(self, cmd: str) -> Optional[bytes]:
        return self.client.run(cmd)

    def launch(self, app: str) -> None:
        """ launch the application """
        self.run(f'am start -n {app}')

    def exit(self, app: str) -> None:
        """ exit the application """
        self.run(f'am force-stop {app}')

    def send_keyevent(self, keycode: int) -> None:
        """ send a key event """
        logger.debug(f'keyevent: {keycode}')
        command = f'input keyevent {keycode}'
        self.run(command)

    def send_text(self, text: str) -> None:
        """ send a text """
        logger.debug(f'text: {repr(text)}')
        text = text.replace('"', '\\"')
        command = f'input text "{text}"'
        self.run(command)

    def screencap(self, save: bool = False) -> bytes:
        """ get a screencap """
        command = 'screencap -p 2>/dev/null'
        screencap = self.run(command)
        if save:
            save_screenshot(screencap)
        return screencap

    def current_focus(self) -> str:
        """ detect current focus app """
        command = 'dumpsys window | grep mCurrentFocus'
        line = self.run(command).decode('utf8')
        return line.strip()[:-1].split(' ')[-1]

    def display_frames(self) -> tuple[int, int, int]:
        """ get display frames if in compatibility mode"""
        if not config.MNT_COMPATIBILITY_MODE:
            return None

        command = 'dumpsys window | grep DisplayFrames'
        line = self.run(command).decode('utf8')
        """ eg. DisplayFrames w=1920 h=1080 r=3 """
        res = line.strip().replace('=', ' ').split(' ')
        return int(res[2]), int(res[4]), int(res[6])

    def tap(self, point: tuple[int, int]) -> None:
        """ tap """
        logger.debug(f'tap: {point}')
        self.control.tap(point)

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration: int = 100) -> None:
        """ swipe """
        logger.debug(f'swipe: {start} -> {end}, duration={duration}')
        self.control.swipe(start, end, duration)

    def swipe_ext(self, points: list[tuple[int, int]], durations: list[int], up_wait: int = 500) -> None:
        """ swipe_ext """
        logger.debug(
            f'swipe_ext: points={points}, durations={durations}, up_wait={up_wait}')
        self.control.swipe_ext(points, durations, up_wait)

    def check_current_focus(self):
        """ check if the application is in the foreground """
        if self.current_focus() != f"{config.APPNAME}/{config.APP_ACTIVITY_NAME}":
            self.launch(f"{config.APPNAME}/{config.APP_ACTIVITY_NAME}")
            # wait for app to finish launching
            time.sleep(10)


class 干员排序方式(Enum):
    工作状态 = 1
    技能 = 2
    心情 = 3
    信赖值 = 4


干员排序方式位置 = {
    干员排序方式.工作状态: (1560 / 2496, 96 / 1404),
    干员排序方式.技能: (1720 / 2496, 96 / 1404),
    干员排序方式.心情: (1880 / 2496, 96 / 1404),
    干员排序方式.信赖值: (2050 / 2496, 96 / 1404),
}


def 日志设置():
    config.LOGFILE_PATH = 用户配置['日志存储目录']
    config.SCREENSHOT_PATH = 用户配置['截图存储目录']
    config.SCREENSHOT_MAXNUM = 用户配置['每种截图的最大保存数量'] - 1
    config.MAX_RETRYTIME = 10
    日志全局格式 = '%(blue)s%(asctime)s - %(log_color)s%(funcName)s - %(log_color)s%(message)s'
    if 源码日志 == '是':
        日志全局格式 = '%(blue)s%(asctime)s %(white)s- %(relativepath)s:%(lineno)d - %(log_color)s%(funcName)s - %(message)s'
    for 日志格式 in logger.handlers:
        日志格式.setFormatter(colorlog.ColoredFormatter(日志全局格式, '%m-%d %H:%M:%S'))


def 森空岛签到():
    global 已签到日期
    header = {
        'cred': '',
        'User-Agent': 'Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0',
        'Accept-Encoding': 'gzip',
        'Connection': 'close'
    }
    header_login = {
        'User-Agent': 'Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0',
        'Accept-Encoding': 'gzip',
        'Connection': 'close'
    }

    def get_token(resp):
        if resp['status'] != 0:
            raise Exception(f'获得token失败：{resp["msg"]}')
        return resp['data']['token']

    def get_grant_code(token):
        resp = requests.post("https://as.hypergryph.com/user/oauth2/v2/grant", json={
            'appCode': '4ca99fa6b56cc2ba',
            'token': token,
            'type': 0
        }, headers=header_login).json()
        if resp['status'] != 0:
            raise Exception(f'获得认证代码失败：{resp["msg"]}')
        return resp['data']['code']

    def get_cred(grant):
        resp = requests.post("https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code", json={
            'code': grant,
            'kind': 1
        }, headers=header_login).json()
        if resp['code'] != 0:
            raise Exception(f'获得cred失败：{resp["messgae"]}')
        return resp['data']['cred']

    def get_binding_list():
        v = []
        resp = requests.get(url="https://zonai.skland.com/api/v1/game/player/binding", headers=header).json()
        if resp['code'] != 0:
            print(f"请求角色列表出现问题：{resp['message']}")
            if resp.get('message') == '用户未登录':
                logger.warning(f'用户登录可能失效了，请重新运行签到程序！')
                return []
        for i in resp['data']['list']:
            if i.get('appCode') != 'arknights':
                continue
            v.extend(i.get('bindingList'))
        return v

    try:
        header['cred'] = get_cred(get_grant_code(get_token(requests.post(
            "https://as.hypergryph.com/user/auth/v1/token_by_phone_password",
            json={"phone": 用户配置['手机号'], "password": 用户配置['密码']}, headers=header_login).json())))
        characters = get_binding_list()
        for 角色 in characters:
            body = {
                'uid': 角色.get('uid'),
                'gameId': 角色.get("channelMasterId")
            }
            响应 = requests.post(
                "https://zonai.skland.com/api/v1/game/attendance", headers=header, json=body).json()
            if 响应['code'] == 10001:
                logger.info("森空岛今天已经签到")
                已签到日期 = datetime.now().strftime('%Y-%m-%d')
            elif 响应['code'] == 0:
                for 奖励 in 响应['data']['awards']:
                    资源 = 奖励['resource']
                    logger.warning(
                        f'{角色.get("nickName")}({角色.get("channelName")})签到成功，获得了{资源["name"]} × {奖励.get("count") or 1}'
                    )
                    if 弹窗提醒开关:
                        托盘图标.notify(
                            f'森空岛签到成功!\n本次签到获得了 {资源["name"]} × {奖励.get("count") or 1}', "森空岛签到")
                已签到日期 = datetime.now().strftime('%Y-%m-%d')
            else:
                logger.warning(
                    f'{角色.get("nickName")}({角色.get("channelName")})签到失败了！原因：{响应.get("message")}')
                continue
    except Exception as ex:
        logger.warning(f'签到失败，原因：{str(ex)}')


class 项目经理(BaseSolver):
    服务器 = ''

    def __init__(self, device: 设备控制 = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.plan = None
        self.planned = None
        self.todo_task = None
        self.邮件设置 = None
        self.干员信息 = None
        self.跑单提前运行时间 = 300
        self.digit_reader = DigitReader()
        self.error = False
        self.任务列表 = []
        self.run_order_rooms = {}

    def 返回基主界面(self):
        logger.info('返回基建主界面')
        while self.get_infra_scene() != 201:
            if self.find('index_infrastructure') is not None:
                self.tap_element('index_infrastructure')
            elif self.find('12cadpa') is not None:
                self.device.tap((self.recog.w // 2, self.recog.h // 2))
            else:
                self.back()
            self.recog.update()

    def run(self) -> None:
        self.error = False
        if len(self.任务列表) == 0:
            self.recog.update()
            time.sleep(1)
        self.handle_error(True)
        if len(self.任务列表) > 0:
            # 找到时间最近的一次单个任务
            self.任务 = self.任务列表[0]
        else:
            self.任务 = None
        self.todo_task = False
        self.collect_notification = False
        self.planned = False
        if self.干员信息 is None or self.干员信息.operators is None:
            self.initialize_operators()
        return super().run()

    def transition(self) -> None:
        self.recog.update()
        if self.scene() == 1:
            self.tap_element('index_infrastructure')
        elif self.scene() == 201:
            return self.infra_main()
        elif self.scene() == 202:
            return self.收获()
        elif self.scene() == 205:
            self.back()
        elif self.scene() == 9998:
            time.sleep(1)
        elif self.scene() == 9:
            time.sleep(1)
        elif self.get_navigation():
            self.tap_element('nav_infrastructure')
        elif self.scene() == 207:
            self.tap_element('arrange_blue_yes')
        elif self.scene() != -1:
            self.back_to_index()
            self.last_room = ''
        else:
            raise RecognizeError('Unknown scene')

    def find_next_task(self, compare_time=None, task_type='', compare_type='<'):
        if compare_type == '=':
            return next((e for e in self.任务列表 if the_same_time(e.time, compare_time) and (
                True if task_type == '' else task_type in e.type)), None)
        elif compare_type == '>':
            return next((e for e in self.任务列表 if (True if compare_time is None else e.time > compare_time) and (
                True if task_type == '' else task_type in e.type)), None)
        else:
            return next((e for e in self.任务列表 if (True if compare_time is None else e.time < compare_time) and (
                True if task_type == '' else task_type in e.type)), None)

    def handle_error(self, force=False):
        while self.scene() == -1:
            self.recog.update()
            logger.info('返回基建主界面')
            unknown_count = 0
            while self.get_infra_scene() != 201 and unknown_count < 5:
                logger.warning(f'未知界面{unknown_count}')
                if self.find('index_infrastructure') is not None:
                    self.tap_element('index_infrastructure')
                elif self.find('12cadpa') is not None:
                    self.device.tap((self.recog.w // 2, self.recog.h // 2))
                else:
                    self.back()
                self.recog.update()
                time.sleep(1)
                unknown_count += 1
            self.device.exit(self.服务器)
        if self.error or force:
            # 如果没有任何时间小于当前时间的任务才生成空任务
            if self.find_next_task(datetime.now()) is None:
                logger.debug("由于出现错误情况，生成一次空任务来执行纠错")
                self.任务列表.append(SchedulerTask())
            # 如果没有任何时间小于当前时间的任务-10分钟 则清空任务
            if self.find_next_task(datetime.now() - timedelta(seconds=900)) is not None:
                logger.info("检测到执行超过15分钟的任务，清空全部任务")
                self.任务列表 = []
        elif self.find_next_task(datetime.now() + timedelta(hours=2.5)) is None:
            logger.debug("2.5小时内没有其他任务，生成一个空任务")
            self.任务列表.append(SchedulerTask(time=datetime.now() + timedelta(hours=2.5)))
        return True

    def infra_main(self):
        """ 位于基建首页 """
        if self.find('control_central') is None:
            self.back()
            return
        if self.任务 is not None:
            try:
                if len(self.任务.plan.keys()) > 0:
                    get_time = False
                    if "Shift_Change" == self.任务.type:
                        get_time = True
                    self.跑单(self.任务.plan, get_time)
                    if get_time:
                        self.plan_metadata()
                # elif self.任务.type == 'impart':
                #     self.skip(['planned', 'collect_notification'])
                del self.任务列表[0]
            except Exception as e:
                logger.exception(e)
                self.skip()
                self.error = True
            self.任务 = None
        elif not self.planned:
            try:
                self.plan_solver()
            except Exception as e:
                # 重新扫描
                self.error = True
                logger.exception({e})
            self.planned = True
        elif not self.todo_task:
            self.todo_task = True
        elif not self.collect_notification:
            notification = detector.infra_notification(self.recog.img)
            if notification is None:
                time.sleep(1)
                notification = detector.infra_notification(self.recog.img)
            if notification is not None:
                self.tap(notification)
            self.collect_notification = True
        else:
            return self.handle_error()

    def plan_solver(self):
        plan = self.plan
        # 如果下个 普通任务 <10 分钟则跳过 plan
        if self.find_next_task(datetime.now() + timedelta(seconds=600)) is not None:
            return
        if len(self.run_order_rooms) > 0:
            for k, v in self.run_order_rooms.items():
                # 如果没有当前房间数据
                if 'plan' not in v.keys():
                    v['plan'] = self.干员信息.get_current_room(k)
                if self.find_next_task(task_type=k) is not None: continue;
                in_out_plan = {k: ['Current'] * len(plan[k])}
                for idx, x in enumerate(plan[k]):
                    if '但书' in x['replacement'] or '龙舌兰' in x['replacement']:
                        in_out_plan[k][idx] = x['replacement'][0]
                self.任务列表.append(
                    SchedulerTask(time=self.读取接单时间(k), task_plan=in_out_plan, task_type=k))
        # 准备数据
        logger.debug(self.干员信息.print())

    def initialize_operators(self):
        plan = self.plan
        self.干员信息 = Operators({}, 4, plan)
        for room in plan.keys():
            for idx, data in enumerate(plan[room]):
                self.干员信息.add(Operator(data["agent"], room, idx, data["group"], data["replacement"], 'high',
                                           operator_type="high"))
        # 跑单
        for x, y in self.plan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                self.run_order_rooms[x] = {}

    def 读取接单时间(self, room):
        logger.info(f'读取贸易站 B{room[5]}0{room[7]} 接单时间')
        # 点击进入该房间
        self.进入房间(room)
        # 进入房间详情
        error_count = 0
        while self.find('bill_accelerate') is None:
            if error_count > 5:
                raise Exception('未成功进入订单界面')
            self.tap((self.recog.w // 20, self.recog.h * 19 // 20), interval=1)
            error_count += 1
        execute_time = self.double_read_time((self.recog.w * 650 // 2496, self.recog.h * 660 // 1404,
                                              self.recog.w * 815 // 2496, self.recog.h * 710 // 1404),
                                             use_digit_reader=True)
        logger.info(f'贸易站 B{room[5]}0{room[7]} 接单时间为 {execute_time.strftime("%H:%M:%S")}')
        execute_time = execute_time - timedelta(seconds=(self.跑单提前运行时间))
        self.recog.update()
        self.返回基主界面()
        return execute_time

    def double_read_time(self, cord, upperLimit=None, use_digit_reader=False):
        if upperLimit is not None and upperLimit < 36000:
            upperLimit = 36000
        self.recog.update()
        time_in_seconds = self.read_time(cord, upperLimit, use_digit_reader)
        if time_in_seconds is None:
            return datetime.now()
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds))
        return execute_time

    def initialize_paddle(self):
        global ocr
        if ocr is None:
            ocr = PaddleOCR(enable_mkldnn=False, use_angle_cls=False, cls=False, show_log=False)

    def read_screen(self, img, type="mood", limit=24, cord=None):
        if cord is not None:
            img = img[cord[1]:cord[3], cord[0]:cord[2]]
        if 'mood' in type or type == "time":
            # 心情图片太小，复制8次提高准确率
            for x in range(0, 4):
                img = cv2.vconcat([img, img])
        try:
            self.initialize_paddle()
            rets = ocr.ocr(img, cls=False)
            line_conf = []
            for idx in range(len(rets[0])):
                res = rets[0][idx]
                if 'mood' in type:
                    # 筛选掉不符合规范的结果
                    if ('/' + str(limit)) in res[1][0]:
                        line_conf.append(res[1])
                else:
                    line_conf.append(res[1])
            logger.debug(line_conf)
            if len(line_conf) == 0:
                if 'mood' in type:
                    return -1
                elif 'name' in type:
                    logger.debug("使用老版识别")
                    return character_recognize.agent_name(img, self.recog.h)
                else:
                    return ""
            x = [i[0] for i in line_conf]
            __str = max(set(x), key=x.count)
            if "mood" in type:
                if '.' in __str:
                    __str = __str.replace(".", "")
                number = int(__str[0:__str.index('/')])
                return number
            elif 'time' in type:
                if '.' in __str:
                    __str = __str.replace(".", ":")
            elif 'name' in type and __str not in agent_list:
                logger.debug("使用老版识别")
                __str = character_recognize.agent_name(img, self.recog.h)
            logger.debug(__str)
            return __str
        except Exception as e:
            logger.exception(e)
            return limit + 1

    def read_time(self, cord, upperlimit, error_count=0, use_digit_reader=False):
        # 刷新图片
        self.recog.update()
        if use_digit_reader:
            time_str = self.digit_reader.get_time(self.recog.gray, self.recog.h, self.recog.w)
        else:
            time_str = self.read_screen(self.recog.img, type='time', cord=cord)
        try:
            h, m, s = str(time_str).split(':')
            if int(m) > 60 or int(s) > 60:
                raise Exception(f"读取错误")
            res = int(h) * 3600 + int(m) * 60 + int(s)
            if upperlimit is not None and res > upperlimit:
                raise Exception(f"超过读取上限")
            else:
                return res
        except:
            logger.error("读取失败")
            if error_count > 3:
                logger.exception(f"读取失败{error_count}次超过上限")
                return None
            else:
                return self.read_time(cord, upperlimit, error_count + 1, use_digit_reader)

    def 收获(self) -> None:
        """ 处理基建收获产物列表 """
        tapped = False
        trust = self.find('infra_collect_trust')
        if trust is not None:
            logger.info('干员信赖')
            self.tap(trust)
            tapped = True
        bill = self.find('infra_collect_bill')
        if bill is not None:
            logger.info('订单交付')
            self.tap(bill)
            tapped = True
        factory = self.find('infra_collect_factory')
        if factory is not None:
            logger.info('可收获')
            self.tap(factory)
            tapped = True
        if not tapped:
            self.tap((self.recog.w // 20, self.recog.h * 19 // 20))
            self.todo_task = True

    def 进入房间(self, room: str) -> tp.Rectangle:
        """ 获取房间的位置并进入 """

        # 获取基建各个房间的位置
        base_room = segment.base(self.recog.img, self.find('control_central', strict=True))
        # 将画面外的部分删去
        _room = base_room[room]

        for i in range(4):
            _room[i, 0] = max(_room[i, 0], 0)
            _room[i, 0] = min(_room[i, 0], self.recog.w)
            _room[i, 1] = max(_room[i, 1], 0)
            _room[i, 1] = min(_room[i, 1], self.recog.h)

        # 点击进入
        self.tap(_room[0], interval=1)
        while self.find('control_central') is not None:
            self.tap(_room[0], interval=1)
        if room.startswith('room'):
            logger.info(f'进入房间 B{room[5]}0{room[7]}')
        elif room == 'dormitory_4':
            logger.info('进入房间 B401')
        else:
            logger.info(f'进入房间 B{room[10]}04')

    def 无人机加速(self, room: str, not_customize=False, not_return=False):
        # 点击进入该房间
        self.进入房间(room)
        while self.get_infra_scene() == 9:
            time.sleep(1)
            self.recog.update()
        # 进入房间详情
        self.tap((self.recog.w // 20, self.recog.h * 19 // 20), interval=3)
        # 关闭掉房间总览
        error_count = 0
        while self.find('factory_accelerate') is None and self.find('bill_accelerate') is None:
            if error_count > 5:
                raise Exception('未成功进入无人机界面')
            self.tap((self.recog.w // 20, self.recog.h * 19 //20), interval=3)
            error_count += 1
        accelerate = self.find('bill_accelerate')
        if accelerate:
            while (self.任务列表[1].time - self.任务列表[0].time).total_seconds() < self.跑单提前运行时间:
                logger.info(f'房间 B{room[5]}0{room[7]}')
                self.tap(accelerate)
                while self.get_infra_scene() == 9:
                    time.sleep(1)
                    self.recog.update()
                self.device.tap((self.recog.w * 1320 // 1920, self.recog.h * 502 // 1080))
                time.sleep(1)
                while self.get_infra_scene() == 9:
                    time.sleep(1)
                    self.recog.update()
                self.tap((self.recog.w * 3 // 4, self.recog.h * 4 // 5))
                while self.get_infra_scene() == 9:
                    time.sleep(1)
                    self.recog.update()
                while self.find('bill_accelerate') is None:
                    if error_count > 5:
                        raise Exception('未成功进入订单界面')
                    self.tap((self.recog.w // 20, self.recog.h * 19 // 20), interval=1)
                    error_count += 1
                加速后接单时间 = self.double_read_time((self.recog.w * 650 // 2496, self.recog.h * 660 // 1404,
                                                        self.recog.w * 815 // 2496, self.recog.h * 710 // 1404),
                                                       use_digit_reader=True)
                self.任务列表[0].time = 加速后接单时间 - timedelta(seconds=(self.跑单提前运行时间))
                logger.info(f'房间 B{room[5]}0{room[7]} 无人机加速后接单时间为 {加速后接单时间.strftime("%H:%M:%S")}')
                if not_customize:
                    无人机数量 = self.digit_reader.get_drone(self.recog.gray, self.recog.h, self.recog.w)
                    logger.info(f'当前无人机数量为 {无人机数量}')
                while self.find('bill_accelerate') is None:
                    if error_count > 5:
                        raise Exception('未成功进入订单界面')
                    self.tap((self.recog.w // 20, self.recog.h * 19 // 20), interval=1)
                    error_count += 1
        if not_return: return
        self.recog.update()
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)

    def get_arrange_order(self) -> 干员排序方式:
        best_score, best_order = 0, None
        for order in 干员排序方式:
            score = self.recog.score(干员排序方式位置[order][0])
            if score is not None and score[0] > best_score:
                best_score, best_order = score[0], order
        logger.debug((best_score, best_order))
        return best_order

    def switch_arrange_order(self, index: int, asc="false") -> None:
        self.tap((self.recog.w * 干员排序方式位置[干员排序方式(index)][0],
                  self.recog.h * 干员排序方式位置[干员排序方式(index)][1]), interval=0, rebuild=False)
        # 点个不需要的
        if index < 4:
            self.tap((self.recog.w * 干员排序方式位置[干员排序方式(index + 1)][0],
                      self.recog.h * 干员排序方式位置[干员排序方式(index)][1]), interval=0, rebuild=False)
        else:
            self.tap((self.recog.w * 干员排序方式位置[干员排序方式(index - 1)][0],
                      self.recog.h * 干员排序方式位置[干员排序方式(index)][1]), interval=0, rebuild=False)
        # 切回来
        self.tap((self.recog.w * 干员排序方式位置[干员排序方式(index)][0],
                  self.recog.h * 干员排序方式位置[干员排序方式(index)][1]), interval=0.2, rebuild=True)
        # 倒序
        if asc != "false":
            self.tap((self.recog.w * 干员排序方式位置[干员排序方式(index)][0],
                      self.recog.h * 干员排序方式位置[干员排序方式(index)][1]), interval=0.2, rebuild=True)

    def scan_agant(self, agent: list[str], error_count=0, max_agent_count=-1):
        try:
            # 识别干员
            self.recog.update()
            ret = character_recognize.agent(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            select_name = []
            for y in ret:
                name = y[0]
                if name in agent:
                    select_name.append(name)
                    self.tap((y[1][0]), interval=0)
                    agent.remove(name)
                    # 如果是按照个数选择 Free
                    if max_agent_count != -1:
                        if len(select_name) >= max_agent_count:
                            return select_name, ret
            return select_name, ret
        except Exception as e:
            error_count += 1
            if error_count < 3:
                logger.exception(e)
                time.sleep(1)
                return self.scan_agant(agent, error_count, max_agent_count)
            else:
                raise e

    def detail_filter(self, turn_on, type="not_in_dorm"):
        logger.info(f'开始 {("打开" if turn_on else "关闭")} {type} 筛选')
        self.tap((self.recog.w * 19 // 20, self.recog.h // 20), interval=1)
        if type == "not_in_dorm":
            not_in_dorm = self.find('arrange_non_check_in', score=0.9)
            if turn_on ^ (not_in_dorm is None):
                self.tap((self.recog.w * 3 // 10, self.recog.h // 2), interval=0.5)
        # 确认
        self.tap((self.recog.w * 4 // 5, self.recog.h * 4 // 5), interval=0.5)

    def 换上干员(self, agents: list[str], room: str) -> None:
        """
        :param order: 干员排序方式, 选择干员时右上角的排序功能
        """
        first_name = ''
        max_swipe = 50
        for 序号, 干员名 in enumerate(agents):
            if 干员名 == '':
                logger.error(f'''
                用 Mower0 跑单的话平时就不要让龙舌兰和但书上班了 \n
                毕竟龙舌兰和但书的意义在于提高订单收益，只要接单时在贸易站就行 \n
                本身不提供贸易站效率，平时在贸易站无法加速订单的获取 \n
                不如平时把提供订单效率的干员放在贸易站，这也正是跑单这一行为的意义所在 \n
                请修改贸易站平时的上班干员后重新运行 Mower0！
                ''')
                托盘图标.notify(f'''
                用 Mower0 跑单的话平时就不要让龙舌兰和但书上班了 \n
                请修改贸易站平时的上班干员后重新运行 Mower0！
                ''', "请修改贸易站干员后再重新运行 Mower0")
                退出程序()
        agent = copy.deepcopy(agents)
        换上干员名单 = str()
        for 干员名 in agent:
            if not 换上干员名单 == '':    换上干员名单 += '、'
            换上干员名单 += 干员名
        if room.startswith('room') and ('但书' in agent or '龙舌兰' in agent):
            logger.info(f'{换上干员名单} 进驻房间 B{room[5]}0{room[7]} 时间为 {(self.任务列表[0].time + timedelta(seconds=(self.跑单提前运行时间 - self.更换干员前缓冲时间))).strftime("%H:%M:%S")}')
        else:   logger.info(f'换上 {换上干员名单}')
        h, w = self.recog.h, self.recog.w
        first_time = True
        right_swipe = 0
        retry_count = 0
        # 如果重复进入宿舍则需要排序
        selected = []
        if room.startswith('room'):
            self.switch_arrange_order(2, "asc")
        else:
            self.switch_arrange_order(3, "asc")
        while len(agent) > 0:
            if retry_count > 3: raise Exception(f"到达最大尝试次数 3次")
            if right_swipe > max_swipe:
                # 到底了则返回再来一次
                for _ in range(right_swipe):
                    self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                right_swipe = 0
                max_swipe = 50
                retry_count += 1
                self.detail_filter(False)
            if first_time:
                self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
                changed, ret = self.scan_agant(agent)
                if changed:
                    selected.extend(changed)
                    if len(agent) == 0: break
            first_time = False

            changed, ret = self.scan_agant(agent)
            if changed:
                selected.extend(changed)
            else:
                # 如果没找到 而且右移次数大于5
                if ret[0][0] == first_name and right_swipe > 5:
                    max_swipe = right_swipe
                else:
                    first_name = ret[0][0]
                st = ret[-2][1][2]  # 起点
                ed = ret[0][1][1]  # 终点
                self.swipe_noinertia(st, (ed[0] - st[0], 0))
                right_swipe += 1
            if len(agent) == 0: break;

        # 排序
        if len(agents) != 1:
            # 左移
            self.swipe_left(right_swipe, w, h)
            self.tap((self.recog.w * 干员排序方式位置[干员排序方式.技能][0],
                      self.recog.h * 干员排序方式位置[干员排序方式.技能][1]), interval=0.5, rebuild=False)
            position = [(0.35, 0.35), (0.35, 0.75), (0.45, 0.35), (0.45, 0.75), (0.55, 0.35)]
            not_match = False
            for idx, item in enumerate(agents):
                if agents[idx] != selected[idx] or not_match:
                    not_match = True
                    p_idx = selected.index(agents[idx])
                    self.tap((self.recog.w * position[p_idx][0], self.recog.h * position[p_idx][1]), interval=0.5,
                             rebuild=False)
                    self.tap((self.recog.w * position[p_idx][0], self.recog.h * position[p_idx][1]), interval=0.5,
                             rebuild=False)
        self.last_room = room

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    @push_operators
    def 撤下干员(self, room, read_time_index=None):
        if read_time_index is None:
            read_time_index = []
        error_count = 0
        while self.find('room_detail') is None:
            if error_count > 3:
                raise Exception('未成功进入房间')
            self.tap((self.recog.w // 20, self.recog.h * 2 // 5), interval=0.5)
            error_count += 1
        length = len(self.plan[room])
        if length > 3: self.swipe((self.recog.w * 4 // 5, self.recog.h // 2), (0, self.recog.h * 9 // 20), duration=500,
                                  interval=1,
                                  rebuild=True)
        name_p = [((self.recog.w * 1460 // 1920, self.recog.h * 155 // 1080),
                   (self.recog.w * 1700 // 1920, self.recog.h * 210 // 1080)),
                  ((self.recog.w * 1460 // 1920, self.recog.h * 370 // 1080),
                   (self.recog.w * 1700 // 1920, self.recog.h * 420 // 1080)),
                  ((self.recog.w * 1460 // 1920, self.recog.h * 585 // 1080),
                   (self.recog.w * 1700 // 1920, self.recog.h * 630 // 1080)),
                  ((self.recog.w * 1460 // 1920, self.recog.h * 560 // 1080),
                   (self.recog.w * 1700 // 1920, self.recog.h * 610 // 1080)),
                  ((self.recog.w * 1460 // 1920, self.recog.h * 775 // 1080),
                   (self.recog.w * 1700 // 1920, self.recog.h * 820 // 1080))]
        result = []
        swiped = False
        for i in range(0, length):
            if i >= 3 and not swiped:
                self.swipe((self.recog.w * 4 // 5, self.recog.h // 2), (0, -self.recog.h * 9 // 20), duration=500,
                           interval=1, rebuild=True)
                swiped = True
            data = {}
            _name = self.read_screen(self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]],
                                     type="name")
            error_count = 0
            while i >= 3 and _name != '' and (
                    next((e for e in result if e['agent'] == _name), None)) is not None:
                logger.warning("检测到滑动可能失败")
                self.swipe((self.recog.w * 4 // 5, self.recog.h // 2), (0, -self.recog.h * 9 // 20), duration=500,
                           interval=1, rebuild=True)
                _name = self.read_screen(
                    self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]], type="name")
                error_count += 1
                if error_count > 1:
                    raise Exception("超过出错上限")
            # 如果房间不为空
            if _name != '':
                if _name not in self.干员信息.operators.keys() and _name in agent_list:
                    self.干员信息.add(Operator(_name, ""))
                update_time = False
                if self.干员信息.operators[_name].need_to_refresh(r=room):
                    update_time = True
                high_no_time = self.干员信息.update_detail(_name, 24, room, i, update_time)
                data['depletion_rate'] = self.干员信息.operators[_name].depletion_rate
            data['agent'] = _name
            if i in read_time_index:
                data['time'] = datetime.now()
                self.干员信息.refresh_dorm_time(room, i, data)
                logger.debug(f"停止记录时间:{str(data)}")
            result.append(data)
        撤下干员名单 = '撤下'
        for _operator in self.干员信息.operators.keys():
            if self.干员信息.operators[_operator].current_room == room and _operator not in [res['agent'] for res in
                                                                                             result]:
                self.干员信息.operators[_operator].current_room = ''
                self.干员信息.operators[_operator].current_index = -1
                if 撤下干员名单 == '撤下':
                    撤下干员名单 += ' '
                else:
                    撤下干员名单 += '、'
                撤下干员名单 += _operator
        if not 撤下干员名单 == '撤下':
            logger.info(撤下干员名单)
        return result

    def refresh_current_room(self, room):
        _current_room = self.干员信息.get_current_room(room)
        if _current_room is None:
            self.撤下干员(room)
            _current_room = self.干员信息.get_current_room(room, True)
        return _current_room

    def 跑单(self, plan: tp.BasePlan, get_time=False):
        rooms = list(plan.keys())
        new_plan = {}
        # 优先替换工作站再替换宿舍
        rooms.sort(key=lambda x: x.startswith('dorm'), reverse=False)
        for room in rooms:
            finished = False
            choose_error = 0
            while not finished:
                try:
                    error_count = 0
                    self.进入房间(room)
                    while self.find('room_detail') is None:
                        if error_count > 3:
                            raise Exception('未成功进入房间')
                        self.tap((self.recog.w // 20, self.recog.h * 2 // 5), interval=0.5)
                        error_count += 1
                    error_count = 0
                    if choose_error == 0:
                        if '但书' in plan[room] or '龙舌兰' in plan[room]:
                            new_plan[room] = self.refresh_current_room(room)
                        if 'Current' in plan[room]:
                            self.refresh_current_room(room)
                            for current_idx, _name in enumerate(plan[room]):
                                if _name == 'Current':
                                    plan[room][current_idx] = self.干员信息.get_current_room(room, True)[current_idx]
                        if room in self.run_order_rooms and len(new_plan) == 0:
                            if ('plan' in self.run_order_rooms[room] and
                                    plan[room] != self.run_order_rooms[room]['plan']):
                                run_order_task = self.find_next_task(
                                    compare_time=datetime.now() + timedelta(minutes=10),
                                    task_type=room, compare_type=">")
                                if run_order_task is not None:
                                    logger.info("检测到跑单房间人员变动！")
                                    self.任务列表.remove(run_order_task)
                                    del self.run_order_rooms[room]['plan']
                    while self.find('arrange_order_options') is None:
                        if error_count > 3:
                            raise Exception('未成功进入干员选择界面')
                        self.tap((self.recog.w * 41 // 50, self.recog.h // 5), interval=1)
                        error_count += 1
                    self.换上干员(plan[room], room)
                    self.recog.update()
                    if room.startswith('room'):
                        龙舌兰_但书进驻前的等待时间 = round(((self.任务列表[0].time - datetime.now()).total_seconds() +
                                                       self.跑单提前运行时间 - self.更换干员前缓冲时间), 1)
                        if 龙舌兰_但书进驻前的等待时间 > 0:
                            logger.info(f'龙舌兰、但书进驻前等待 {str(龙舌兰_但书进驻前的等待时间)} 秒')
                            time.sleep(龙舌兰_但书进驻前的等待时间)
                    self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
                    self.recog.update()
                    if self.get_infra_scene() == 206:
                        x0 = self.recog.w * 2 // 3  # double confirm
                        y0 = self.recog.h - 10
                        self.tap((x0, y0), rebuild=True)
                    read_time_index = []
                    if get_time:
                        read_time_index = self.干员信息.get_refresh_index(room, plan[room])
                    current = self.撤下干员(room, read_time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]['agent'] != name:
                            logger.error(f'检测到的干员{current[idx]["agent"]},需要上岗的干员{name}')
                            raise Exception('检测到安排干员未成功')
                    finished = True
                    # 如果完成则移除该任务
                    del plan[room]
                    if room.startswith('room'):
                        # 截图
                        while self.find('bill_accelerate') is None:
                            if error_count > 5:
                                raise Exception('未成功进入订单界面')
                            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
                            error_count += 1
                        修正后的接单时间 = self.double_read_time(
                            (self.recog.w * 650 // 2496, self.recog.h * 660 // 1404,
                             self.recog.w * 815 // 2496, self.recog.h * 710 //1404),
                            use_digit_reader=True)
                        截图等待时间 = round((修正后的接单时间 - datetime.now()).total_seconds(), 1)
                        if (截图等待时间 > 0) and (截图等待时间 < 1000):
                            logger.info(f'房间 B{room[5]}0{room[7]} 修正后的接单时间为 {修正后的接单时间.strftime("%H:%M:%S")}')
                            logger.info(f'等待截图时间为 {str(截图等待时间)} 秒')
                            time.sleep(截图等待时间)
                            logger.info('保存截图')
                            self.recog.update()
                            self.recog.save_screencap('run_order')
                    while self.scene() == 9:
                        time.sleep(1)
                        self.recog.update()
                except Exception as e:
                    logger.exception(e)
                    choose_error += 1
                    self.recog.update()
                    back_count = 0
                    while self.get_infra_scene() != 201:
                        self.back()
                        self.recog.update()
                        back_count += 1
                        if back_count > 3:
                            raise e
                    if choose_error > 3:
                        raise e
                    else:
                        continue
            self.back(0.5)
        if len(new_plan) == 1 and self.任务列表[0].type.startswith('room'):
            # 防止由于意外导致的死循环
            run_order_room = next(iter(new_plan))
            if '但书' in new_plan[run_order_room] or '龙舌兰' in new_plan[run_order_room]:
                new_plan[run_order_room] = [data["agent"] for data in self.plan[room]]
            # 返回基建主界面
            self.recog.update()
            self.返回基主界面()
            self.任务列表.append(SchedulerTask(time=self.任务列表[0].time, task_plan=new_plan))
            if 龙舌兰和但书休息:
                宿舍 = {}
                宿舍[龙舌兰和但书休息宿舍] = [data["agent"] for data in self.plan[龙舌兰和但书休息宿舍]]
                self.任务列表.append(SchedulerTask(time=self.任务列表[0].time, task_plan=宿舍))
                self.skip(['planned', 'todo_task'])

    def skip(self, task_names='All'):
        if task_names == 'All':
            task_names = ['planned', 'collect_notification', 'todo_task']
        if 'planned' in task_names:
            self.planned = True
        if 'todo_task':
            self.todo_task = True
        if 'collect_notification':
            self.collect_notification = True


    @CFUNCTYPE(None, c_int, c_char_p, c_void_p)
    def log_maa(msg, details, arg):
        m = Message(msg)
        d = json.loads(details.decode('utf-8'))
        logger.debug(d)
        logger.debug(m)
        logger.debug(arg)


    def MAA初始化(self):
        asst_path = os.path.dirname(pathlib.Path(self.MAA设置['MAA路径']) / "Python" / "asst")
        if asst_path not in sys.path:
            sys.path.append(asst_path)
        from asst.asst import Asst

        Asst.load(path=self.MAA设置['MAA路径'])
        self.MAA = Asst(callback=self.log_maa)
        self.关卡列表 = []
        if self.MAA.connect(self.MAA设置['MAA_adb路径'], self.device.client.device_id):
            logger.info("MAA 连接成功")
        else:
            logger.info("MAA 连接失败")
            raise Exception("MAA 连接失败")


    def append_maa_task(self, type):
        if type in ['StartUp', 'Visit', 'Award']:
            self.MAA.append_task(type)
        elif type == 'Fight':
            关卡 = self.MAA设置['消耗理智关卡']
            if 关卡 == '上一次作战':   关卡 = ''
            self.MAA.append_task('Fight', {
                'stage': 关卡,
                'medicine': MAA设置['使用理智药数量'],
                'stone': 0,
                'times': 999,
                'report_to_penguin': True,
                'client_type': '',
                'penguin_id': '',
                'DrGrandet': False,
                'server': 'CN',
                'expiring_medicine': 9999
            })
            self.关卡列表.append(关卡)
        # elif type == 'Recruit':
        #     self.MAA.append_task('Recruit', {
        #         'select': [4],
        #         'confirm': [3, 4],
        #         'times': 4,
        #         'refresh': True,
        #         "recruitment_time": {
        #             "3": 460,
        #             "4": 540
        #         }
        #     })
        # elif type == 'Mall':
        #     credit_fight = False
        #     if len(self.关卡列表) > 0 and self.关卡列表[- 1] != '':
        #         credit_fight = True
        #     self.MAA.append_task('Mall', {
        #         'shopping': True,
        #         'buy_first': ['招聘许可'],
        #         'blacklist': ['家具', '碳', '加急许可'],
        #         'credit_fight': credit_fight
        #     })

    def maa_plan_solver(self, 任务列表=['Fight'], one_time=False):
        try:
            self.send_email('启动MAA')
            self.back_to_index()
            # 任务及参数请参考 docs/集成文档.md
            self.MAA初始化()
            if 任务列表 == 'All':
                任务列表 = ['StartUp', 'Fight', 'Recruit', 'Visit', 'Mall', 'Award']
            for maa_task in 任务列表:
                self.append_maa_task(maa_task)
            # asst.append_task('Copilot', {
            #     'stage_name': '千层蛋糕',
            #     'filename': './GA-EX8-raid.json',
            #     'formation': False

            # })
            self.MAA.start()
            stop_time = None
            if one_time:
                stop_time = datetime.now() + timedelta(minutes=5)
            logger.info(f"MAA 启动")
            hard_stop = False
            while self.MAA.running():
                # 单次任务默认5分钟
                if one_time and stop_time < datetime.now():
                    self.MAA.stop()
                    hard_stop = True
                # 5分钟之前就停止
                elif not one_time and (self.任务列表[0].time - datetime.now()).total_seconds() < 300:
                    self.MAA.stop()
                    hard_stop = True
                else:
                    time.sleep(0)
            self.send_email('MAA 停止')
            if hard_stop:
                logger.info(f"由于 MAA 任务并未完成，等待3分钟重启软件")
                time.sleep(180)
                self.device.exit(self.服务器)
            if self.MAA设置['集成战略'] == '开' or self.MAA设置['生息演算'] == '开':
                while (self.任务列表[0].time - datetime.now()).total_seconds() > 30:
                    self.MAA = None
                    self.MAA初始化()
                    if self.MAA设置['集成战略'] == '开':
                        if self.MAA设置['集成战略主题'] == '傀影与猩红孤钻':
                            主题 = 'Phantom'
                        elif self.MAA设置['集成战略主题'] == '水月与深蓝之树':
                            主题 = 'Mizuki'
                        elif self.MAA设置['集成战略主题'] == '探索者的银凇止境':
                            主题 = 'Sami'
                        self.MAA.append_task('Roguelike', {
                            'theme': self.MAA设置['集成战略主题'],
                            'mode': 主题,
                            'starts_count': 9999999,
                            'investment_enabled': True,
                            'investments_count': 9999999,
                            'stop_when_investment_full': False,
                            'squad': self.MAA设置['集成战略分队'],
                            'roles': self.MAA设置['集成战略开局招募组合'],
                            'core_char': self.MAA设置['集成战略开局干员']
                        })
                    elif self.MAA设置['生息演算'] == '开':
                        self.back_to_MAA设置['生息演算']()
                        self.MAA.append_task('ReclamationAlgorithm')
                    # elif self.MAA设置['保全派驻'] :
                    #     self.MAA.append_task('SSSCopilot', {
                    #         'filename': "F:\\MAA-v4.10.5-win-x64\\resource\\copilot\\SSS_阿卡胡拉丛林.json",
                    #         'formation': False,
                    #         'loop_times':99
                    #     })
                    self.MAA.start()
                    while self.MAA.running():
                        if (self.任务列表[0].time - datetime.now()).total_seconds() < 30:
                            self.MAA.stop()
                            break
                        else:
                            time.sleep(0)
                    self.device.exit(self.服务器)
            # 生息演算逻辑 结束
            if one_time:
                if len(self.任务列表) > 0:
                    del self.任务列表[0]
                self.MAA = None
                if self.find_next_task(datetime.now() + timedelta(seconds=900)) is None:
                    # 未来10分钟没有任务就新建
                    self.任务列表.append(SchedulerTask())
                return
            remaining_time = (self.任务列表[0].time - datetime.now()).total_seconds()
            subject = f"开始休息 {'%.2f' % (remaining_time / 60)} 分钟，到{self.任务列表[0].time.strftime('%H:%M:%S')}"
            context = f"下一次任务:{self.任务列表[0].plan if len(self.任务列表[0].plan) != 0 else '空任务' if self.任务列表[0].type == '' else self.任务列表[0].type}"
            logger.info(context)
            logger.info(subject)
            self.send_email(context, subject)
            if remaining_time > 0:
                time.sleep(remaining_time)
            self.MAA = None
        except Exception as e:
            logger.error(e)
            self.MAA = None
            remaining_time = (self.任务列表[0].time - datetime.now()).total_seconds()
            if remaining_time > 0:
                logger.info(
                    f"开始休息 {'%.2f' % (remaining_time / 60)} 分钟，到{self.任务列表[0].time.strftime('%H:%M:%S')}")
                time.sleep(remaining_time)
            self.device.exit(self.服务器)

    def send_email(self, context=None, subject='', retry_time=3):
        global 任务
        if not self.邮件设置['邮件提醒开关'] == '开':
            logger.info('邮件功能未开启')
            return
        while retry_time > 0:
            try:
                msg = MIMEMultipart()
                if context is None:
                    context = """
                    <html>
                        <body>
                        <table border="1">
                        <tr><th>时间</th><th>房间</th></tr>                    
                    """
                    for 任务 in self.任务列表:
                        context += f"""
                                        <tr><td>{任务.time.strftime('%Y-%m-%d %H:%M:%S')}</td>
                                        <td>B{任务.type[5]}0{任务.type[7]}</td></tr>    
                                    """
                    context += "</table></body></html>"
                    msg.attach(MIMEText(context, 'html'))
                else:
                    msg.attach(MIMEText(str(context), 'plain', 'utf-8'))
                msg['Subject'] = ('将在 ' + self.任务列表[0].time.strftime('%H:%M:%S') +
                                  ' 于房间 B' + self.任务列表[0].type[5] + '0' + self.任务列表[0].type[7] + ' 进行跑单')
                msg['From'] = self.邮件设置['发信邮箱']
                s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10.0)
                # 登录邮箱
                s.login(self.邮件设置['发信邮箱'], self.邮件设置['授权码'])
                # 开始发送
                s.sendmail(self.邮件设置['发信邮箱'], self.邮件设置['收件人邮箱'], msg.as_string())
                break
            except Exception as e:
                logger.error("邮件发送失败")
                logger.exception(e)
                retry_time -= 1
                time.sleep(1)


def 初始化(任务列表, scheduler=None):
    config.ADB_DEVICE = [用户配置['adb地址']]
    config.ADB_CONNECT = [用户配置['adb地址']]
    config.APPNAME = 服务器
    config.TAP_TO_LAUNCH = [{"enable": "false", "x": "0", "y": "0"}]
    init_fhlr()
    device = 设备控制()
    cli = Solver(device)
    if scheduler is None:
        当前项目 = 项目经理(cli.device, cli.recog)
        logger.info(f'当前模拟器分辨率为 {当前项目.recog.w} × {当前项目.recog.h}')
        if 当前项目.recog.w * 9 != 当前项目.recog.h * 16:
            logger.error('请将模拟器分辨率设置为 16:9 再重新运行 Mower0!')
            托盘图标.notify('请将模拟器分辨率设置为 16:9 \n再重新运行 Mower0!', "分辨率检验")
            退出程序()
        当前项目.服务器 = 服务器
        当前项目.operators = {}
        当前项目.plan = {}
        当前项目.current_base = {}
        for 房间 in 用户配置['跑单位置设置']:
            当前项目.plan[f'room_{房间[1]}_{房间[3]}'] = []
            for 干员 in 用户配置['跑单位置设置'][房间]:
                当前项目.plan[f'room_{房间[1]}_{房间[3]}'].append(
                    {'agent': '', 'group': '', 'replacement': [干员]})
        if 龙舌兰和但书休息:
            global 龙舌兰和但书休息宿舍
            for 宿舍 in 用户配置['宿舍设置']:
                if 宿舍 == 'B401':
                    龙舌兰和但书休息宿舍 = 'dormitory_4'
                else:
                    龙舌兰和但书休息宿舍 = 'dormitory_' + 宿舍[1]
                当前项目.plan[龙舌兰和但书休息宿舍] = []
                for 干员 in 用户配置['宿舍设置'][宿舍]:
                    if 干员 == '当前休息干员':  干员 = 'Current'
                    if 干员 == '自动填充干员':  干员 = 'Free'
                    当前项目.plan[龙舌兰和但书休息宿舍].append({'agent': 干员, 'group': '', 'replacement': ''})
        当前项目.任务列表 = 任务列表
        当前项目.last_room = ''
        当前项目.MAA = None
        当前项目.邮件设置 = 邮件设置
        当前项目.ADB_CONNECT = config.ADB_CONNECT[0]
        当前项目.MAA设置 = MAA设置
        当前项目.error = False
        当前项目.跑单提前运行时间 = 跑单提前运行时间
        当前项目.更换干员前缓冲时间 = 更换干员前缓冲时间
        return 当前项目
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler


class 线程(threading.Thread):

    def __init__(self, *args, **kwargs):
        super(线程, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def run(self):
        self.Mower0()

    def Mower0(self):
        global ope_list, 当前项目, 任务提示, 下个任务开始时间, 已签到日期
        # 第一次执行任务
        日志设置()
        任务列表 = []
        for t in 任务列表:
            t.time = datetime.strptime(str(t.time), '%m-%d %H:%M:%S.%f')
        重连次数上限 = 10
        重连次数 = 0
        当前项目 = 初始化(任务列表)
        if 用户配置['森空岛签到开关'] == '开':
            森空岛签到()
        当前项目.device.launch(f"{服务器}/{config.APP_ACTIVITY_NAME}")
        当前项目.initialize_operators()
        while True:
            try:
                if len(当前项目.任务列表) > 0:
                    当前项目.任务列表.sort(key=lambda x: x.time, reverse=False)  # 任务按时间排序
                    # 如果订单间的时间差距小，无人机加速拉开订单间的时间差距
                    if (len(任务列表) > 1 and (任务列表[0].time - datetime.now()).total_seconds()
                            > 当前项目.跑单提前运行时间 > (任务列表[1].time - 任务列表[0].time).total_seconds()):
                        logger.warning("两个订单时间太接近了，准备用无人机加速拉开订单间时间差距")
                        当前项目.无人机加速(任务列表[0].type, True, True)
                    下个任务开始时间 = 任务列表[0].time
                    当前项目.recog.update()
                    当前项目.返回基主界面()
                    任务间隔 = (当前项目.任务列表[0].time - datetime.now()).total_seconds()
                    if 任务间隔 > 0:
                        当前项目.send_email()
                        任务提示 = str()
                        for i in range(len(任务列表)):
                            logger.warning(
                                f'房间 B{任务列表[i].type[5]}0{任务列表[i].type[7]} 开始跑单的时间为 {任务列表[i].time.strftime("%H:%M:%S")}')
                        无人机数量 = 当前项目.digit_reader.get_drone(当前项目.recog.gray, 当前项目.recog.h, 当前项目.recog.w)
                        if 无人机数量 > 168:
                            logger.warning(f'现在有 {无人机数量} 个无人机，请尽快使用，避免溢出！')
                            任务提示 += f'现在有 {无人机数量} 个无人机，请尽快使用！\n'
                        for i in range(len(任务列表)):
                            任务提示 += f'房间 B{任务列表[i].type[5]}0{任务列表[i].type[7]} 开始跑单的时间为 {任务列表[i].time.strftime("%H:%M:%S")}\n'
                        if 弹窗提醒开关:    托盘图标.notify(任务提示, "Mower跑单提醒")

                    # 如果有高强度重复MAA任务,任务间隔超过10分钟则启动MAA
                    if MAA设置['作战开关'] == '开' and (任务间隔 > 600):
                        当前项目.maa_plan_solver()
                    elif 任务间隔 > 0:
                        if 用户配置['任务结束后退出游戏'] == '是' and 任务间隔 > 跑单提前运行时间:
                            当前项目.device.exit(当前项目.服务器)
                            if 用户配置['森空岛签到开关'] == '开' and 已签到日期 != datetime.now().strftime('%Y-%m-%d'):
                                森空岛签到()
                            time.sleep(任务间隔 - 跑单提前运行时间)
                            if 弹窗提醒开关:
                                托盘图标.notify("跑单时间快到了喔，请放下游戏中正在做的事，或者手动关闭Mower", "Mower跑单提醒")
                            time.sleep(跑单提前运行时间)
                            if 弹窗提醒开关:    托盘图标.notify("开始跑单！", "Mower跑单提醒")
                        else:
                            time.sleep(任务间隔)
                            当前项目.back_to_index()

                if len(当前项目.任务列表) > 0 and 当前项目.任务列表[0].type.split('_')[0] == 'maa':
                    当前项目.maa_plan_solver((当前项目.任务列表[0].type.split('_')[1]).split(','), one_time=True)
                    continue
                当前项目.run()
                重连次数 = 0
            except ConnectionError as e:
                重连次数 += 1
                if 重连次数 < 重连次数上限:
                    logger.warning(f'连接端口断开...正在重连...')
                    连接状态 = False
                    while not 连接状态:
                        try:
                            当前项目 = 初始化([], 当前项目)
                            break
                        except Exception as ce:
                            logger.error(ce)
                            time.sleep(1)
                            continue
                    continue
                else:
                    raise Exception(e)
            except Exception as E:
                logger.exception(f"程序出错--->{E}")


def 终止线程报错(tid, exctype):
    """raises the exception, performs cleanup if needed"""
    tid = ctypes.c_long(tid)
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


def 显示字幕():
    窗口.deiconify()


def 选中窗口(event):
    global 鼠标水平初始位置, 鼠标竖直初始位置

    鼠标水平初始位置 = event.x  # 获取鼠标相对于窗体左上角的X坐标
    鼠标竖直初始位置 = event.y  # 获取鼠标相对于窗左上角体的Y坐标


def 拖动窗口(event):
    窗口.geometry(f'+{event.x_root - 鼠标水平初始位置}+{event.y_root - 鼠标竖直初始位置}')


def 关闭窗口(icon: pystray.Icon):
    窗口.withdraw()


def 缩放字幕(event):
    global 字幕字号
    if event.delta > 0:
        字幕字号 += 1
    else:
        字幕字号 -= 1
    if 字幕字号 < 1:
        字幕字号 = 1


def 跑单任务查询(icon: pystray.Icon):
    icon.notify(任务提示, "Mower跑单任务列表")


def 重新运行Mower():
    global Mower
    try:
        Mower._stop_event.set()
        终止线程报错(Mower.ident, SystemExit)
        logger.warning('Mower已停止，准备重新运行')
    except:
        pass
    Mower = 线程()
    Mower.start()


def 停止运行Mower():
    Mower._stop_event.set()
    终止线程报错(Mower.ident, SystemExit)
    logger.warning('Mower已停止')


def 退出程序():
    pid = os.getpid()  # 获取当前进程ID
    logger.error('退出 Mower')
    os.system('taskkill -f -pid %s' % pid)


def 更新字幕():
    global 字幕
    任务倒计时 = (下个任务开始时间 - datetime.now()).total_seconds()
    字幕 = 'Mower的回合！'
    if 任务倒计时 > 0:
        字幕 = f'Mower将在{int(任务倒计时/60)}分钟后开始跑单'
        if 任务倒计时 <= 跑单提前运行时间:
            字幕 += '\n跑单即将开始！'
    label.config(text=字幕, font=(用户配置['字幕字体'], 字幕字号, 'bold'), bg=字幕颜色,
                 fg=字幕颜色[:6] + str(int(字幕颜色[5] == '0')))
    窗口.after(100, 更新字幕)


托盘菜单 = (MenuItem('森空岛签到', 森空岛签到, visible=True),
            MenuItem(任务提示, 跑单任务查询, default=True, visible=False),
            MenuItem('显示字幕', 显示字幕, visible=悬浮字幕开关),
            MenuItem('重新运行Mower', 重新运行Mower, visible=True),
            MenuItem('停止运行Mower', 停止运行Mower, visible=True),
            Menu.SEPARATOR, MenuItem('退出', 退出程序))
托盘图标 = pystray.Icon("Mower 纯跑单", Image.open("logo.png"), "Mower 纯跑单", 托盘菜单)
if 悬浮字幕开关:
    窗口.geometry("%dx%d+%d+%d" % (窗口宽度, 窗口高度,
                                   (窗口.winfo_screenwidth() - 窗口宽度) / 2,
                                   窗口.winfo_screenheight() * 3 / 4 - 窗口高度 / 2))
    窗口.overrideredirect(True)
    窗口.title("窗口")
    窗口.attributes("-topmost", 1)
    窗口.wm_attributes("-transparentcolor", 字幕颜色)

    # 添加一个标签小部件
    label = Label(窗口)
    label.pack(side="top", fill="both", expand=True)
    label.bind("<Button-1>", 选中窗口)
    label.bind("<B1-Motion>", 拖动窗口)
    label.bind("<Double-Button-1>", 关闭窗口)
    label.bind("<MouseWheel>", 缩放字幕)

if __name__ == "__main__":
    threading.Thread(target=托盘图标.run, daemon=False).start()
    Mower = 线程()
    Mower.start()
    if 悬浮字幕开关:
        窗口.after(100, 更新字幕)
        窗口.mainloop()
