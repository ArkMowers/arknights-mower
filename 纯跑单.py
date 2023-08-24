from __future__ import annotations
import copy
import ctypes
import cv2
import inspect
import json
import os
import pystray
import smtplib
import sys
import threading
import time
import warnings
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
from arknights_mower.utils.asst import Asst, Message
from arknights_mower.utils.datetime import get_server_weekday, the_same_time
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


def warn(*args, **kwargs):
    pass


warnings.warn = warn

from paddleocr import PaddleOCR
from arknights_mower.strategy import Solver

官方服务器 = 'com.hypergryph.arknights'
Bilibili服务器 = 'com.hypergryph.arknights.bilibili'

窗口 = Tk()
################################################################################################
# # # # # # # # # # # # # # # # # # # # # # 用户设置区 # # # # # # # # # # # # # # # # # # # # # #
################################################################################################

服务器 = 官方服务器  # 服务器选择 (官方服务器/Bilibili服务器)

跑单提前运行时间 = 300  # 秒
更换干员前缓冲时间 = 30  # 秒 需要严格大于一次跟服务器交换数据的时间 建议大于等于15秒

# 设置贸易站的房间以及跑单干员的具体位置
# 请注意手动换班后记得重新运行程序
跑单位置设置 = {
    'B101': ['', '龙舌兰', '但书'],
    'B201': ['', '龙舌兰', '但书'],
}

# 龙舌兰、但书休息设置
龙舌兰和但书休息 = True
宿舍设置 = {'B401': ['当前休息干员', '当前休息干员', '当前休息干员', '龙舌兰', '但书']}

日志存储目录 = './log'
截图存储目录 = './screenshot'
每种截图的最大保存数量 = 10
任务结束后退出游戏 = True

跑单弹窗提醒开关 = True

# 悬浮字幕窗口设置
# 双击字幕可关闭字幕 在托盘可重新打开
悬浮字幕开关 = True
窗口宽度 = 窗口.winfo_screenwidth() / 3
窗口高度 = 窗口.winfo_screenheight() / 7
字幕字号 = str(int(窗口.winfo_screenheight() / 30))  # '50'
字幕字体 = '楷体'
字幕颜色 = '#9966FF'  # 16进制颜色代码

邮件设置 = {
    '邮件提醒开关': True,
    '发信邮箱': "qqqqqqqqqqqqq@qq.com",
    '授权码': 'xxxxxxxxxxxxxxxx',  # 在QQ邮箱“账户设置-账户-开启SMTP服务”中，按照指示开启服务获得授权码
    '收件人邮箱': ['name@example.com']  # 收件人邮箱
}

MAA设置 = {
    'MAA路径': 'K:/MAA',  # 请设置为存放 dll 文件及资源的路径
    'MAA_adb路径': 'C:/Program Files/BlueStacks_bgp64/./HD-Adb.exe',  # 请设置为模拟器的 adb 应用程序路径
    'MAA_adb地址': ['127.0.0.1:5555'],  # 请设置为模拟器的 adb 地址

    # 以下配置，第一个设置为开的首先生效
    '集成战略': False,  # 集成战略开关
    '生息演算': False,  # 生息演算开关
    '保全派驻': False,  # 保全派驻开关
    '周计划': [
        {'日子': '周一', '关卡': ['集成战略'], '应急理智药': 0},
        {'日子': '周二', '关卡': ['集成战略'], '应急理智药': 0},
        {'日子': '周三', '关卡': ['集成战略'], '应急理智药': 0},
        {'日子': '周四', '关卡': ['集成战略'], '应急理智药': 0},
        {'日子': '周五', '关卡': ['集成战略'], '应急理智药': 0},
        {'日子': '周六', '关卡': ['集成战略'], '应急理智药': 0},
        {'日子': '周日', '关卡': ['集成战略'], '应急理智药': 0}
    ]
}


################################################################################################
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
################################################################################################
ocr = None
任务提示 = str()
下个任务开始时间 = datetime.now()
字幕 = "Mower的准备阶段..."


class 设备控制(object):
    class Control(object):

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
        self.control = 设备控制.Control(self, self.client)

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


def 调试输出():
    logger.handlers[0].setLevel('DEBUG')


def 日志设置():
    config.LOGFILE_PATH = 日志存储目录
    config.SCREENSHOT_PATH = 截图存储目录
    config.SCREENSHOT_MAXNUM = 每种截图的最大保存数量 - 1
    config.MAX_RETRYTIME = 10


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
            return self.收获产物()
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
                if self.find('index_infrastructure') is not None:
                    self.tap_element('index_infrastructure')
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
        added = []
        # 跑单
        for x, y in self.plan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                self.run_order_rooms[x] = {}

    def 读取接单时间(self, room):
        logger.info('读取接单时间')
        # 点击进入该房间
        self.进入房间(room)
        # 进入房间详情
        error_count = 0
        while self.find('bill_accelerate') is None:
            if error_count > 5:
                raise Exception('未成功进入订单界面')
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
            error_count += 1
        execute_time = self.double_read_time((int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404),
                                              int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
                                             use_digit_reader=True)
        logger.warning('房间 B' + room[5] + '0' + room[7] + ' 接单时间为 ' + execute_time.strftime("%H:%M:%S"))
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
            # mac 平台不支持 mkldnn 加速，关闭以修复 mac 运行时错误
            if sys.platform == 'darwin':
                ocr = PaddleOCR(enable_mkldnn=False, use_angle_cls=False, show_log=False)
            else:
                ocr = PaddleOCR(enable_mkldnn=True, use_angle_cls=False, show_log=False)

    def read_screen(self, img, type="mood", limit=24, cord=None):
        if cord is not None:
            img = img[cord[1]:cord[3], cord[0]:cord[2]]
        if 'mood' in type or type == "time":
            # 心情图片太小，复制8次提高准确率
            for x in range(0, 4):
                img = cv2.vconcat([img, img])
        try:
            self.initialize_paddle()
            rets = ocr.ocr(img, cls=True)
            line_conf = []
            for idx in range(len(rets[0])):
                res = rets[0][idx]
                if 'mood' in type:
                    # filter 掉不符合规范的结果
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
            time_str = self.digit_reader.get_time(self.recog.gray)
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

    def 收获产物(self) -> None:
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
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95))
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

    def 无人机加速(self, room: str, not_customize=False, not_return=False):
        logger.info('无人机加速')
        # 点击进入该房间
        self.进入房间(room)
        # 进入房间详情
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
        # 关闭掉房间总览
        error_count = 0
        while self.find('factory_accelerate') is None and self.find('bill_accelerate') is None:
            if error_count > 5:
                raise Exception('未成功进入无人机界面')
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
            error_count += 1
        accelerate = self.find('bill_accelerate')
        if accelerate:
            while (self.任务列表[1].time - self.任务列表[0].time).total_seconds() < self.跑单提前运行时间:
                logger.info(room + ' 加速')
                self.tap(accelerate)
                self.device.tap((1320, 502))
                time.sleep(1)
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8))
                while self.get_infra_scene() == 9:
                    time.sleep(1)
                while self.find('bill_accelerate') is None:
                    if error_count > 5:
                        raise Exception('未成功进入订单界面')
                    self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
                    error_count += 1
                加速后接单时间 = self.double_read_time((int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404),
                                                        int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
                                                       use_digit_reader=True)
                self.任务列表[0].time = 加速后接单时间 - timedelta(seconds=(self.跑单提前运行时间))
                logger.info(
                    '房间 B' + room[5] + '0' + room[7] + ' 加速后接单时间为 ' + 加速后接单时间.strftime("%H:%M:%S"))
                if not_customize:
                    drone_count = self.digit_reader.get_drone(self.recog.gray)
                    logger.info(f'当前无人机数量为：{drone_count}')
                while self.find('bill_accelerate') is None:
                    if error_count > 5:
                        raise Exception('未成功进入订单界面')
                    self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
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
                    # self.get_agent_detail((y[1][0]))
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
        self.tap((self.recog.w * 0.95, self.recog.h * 0.05), interval=1)
        if type == "not_in_dorm":
            not_in_dorm = self.find('arrange_non_check_in', score=0.9)
            if turn_on ^ (not_in_dorm is None):
                self.tap((self.recog.w * 0.3, self.recog.h * 0.5), interval=0.5)
        # 确认
        self.tap((self.recog.w * 0.8, self.recog.h * 0.8), interval=0.5)

    def 安排干员(self, agents: list[str], room: str) -> None:
        """
        :param order: 干员排序方式, 选择干员时右上角的排序功能
        """
        first_name = ''
        max_swipe = 50
        for idx, n in enumerate(agents):
            if n == '':
                agents[idx] = 'Free'
        agent = copy.deepcopy(agents)
        logger.info(f'安排干员 ：{agent}')
        if room.startswith('room'):
            logger.warning('房间 B' + room[5] + '0' + room[7] + ' 进驻时间为 ' + (self.任务列表[0].time + timedelta(
                seconds=(self.跑单提前运行时间 - self.更换干员前缓冲时间))).strftime("%H:%M:%S"))
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
                    self.tap((self.recog.w * position[p_idx][0], self.recog.h * position[p_idx][1]), interval=0,
                             rebuild=False)
                    self.tap((self.recog.w * position[p_idx][0], self.recog.h * position[p_idx][1]), interval=0,
                             rebuild=False)
        self.last_room = room

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    @push_operators
    def get_agent_from_room(self, room, read_time_index=None):
        if read_time_index is None:
            read_time_index = []
        error_count = 0
        while self.find('room_detail') is None:
            if error_count > 3:
                raise Exception('未成功进入房间')
            self.tap((self.recog.w * 0.05, self.recog.h * 0.4), interval=0.5)
            error_count += 1
        length = len(self.plan[room])
        if length > 3: self.swipe((self.recog.w * 0.8, self.recog.h * 0.5), (0, self.recog.h * 0.45), duration=500,
                                  interval=1,
                                  rebuild=True)
        name_p = [((1460, 155), (1700, 210)), ((1460, 370), (1700, 420)), ((1460, 585), (1700, 630)),
                  ((1460, 560), (1700, 610)), ((1460, 775), (1700, 820))]
        result = []
        swiped = False
        for i in range(0, length):
            if i >= 3 and not swiped:
                self.swipe((self.recog.w * 0.8, self.recog.h * 0.5), (0, -self.recog.h * 0.45), duration=500,
                           interval=1, rebuild=True)
                swiped = True
            data = {}
            _name = self.read_screen(self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]],
                                     type="name")
            error_count = 0
            while i >= 3 and _name != '' and (
                    next((e for e in result if e['agent'] == _name), None)) is not None:
                logger.warning("检测到滑动可能失败")
                self.swipe((self.recog.w * 0.8, self.recog.h * 0.5), (0, -self.recog.h * 0.45), duration=500,
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
        for _operator in self.干员信息.operators.keys():
            if self.干员信息.operators[_operator].current_room == room and _operator not in [res['agent'] for res in
                                                                                         result]:
                self.干员信息.operators[_operator].current_room = ''
                self.干员信息.operators[_operator].current_index = -1
                logger.info(f'重设 {_operator} 至空闲')
        return result

    def refresh_current_room(self, room):
        _current_room = self.干员信息.get_current_room(room)
        if _current_room is None:
            self.get_agent_from_room(room)
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
                        self.tap((self.recog.w * 0.05, self.recog.h * 0.4), interval=0.5)
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
                        self.tap((self.recog.w * 0.82, self.recog.h * 0.2), interval=1)
                        error_count += 1
                    self.安排干员(plan[room], room)
                    self.recog.update()
                    if room.startswith('room'):
                        龙舌兰_但书进驻前的等待时间 = ((self.任务列表[0].time - datetime.now()).total_seconds() +
                                                       self.跑单提前运行时间 - self.更换干员前缓冲时间)
                        if 龙舌兰_但书进驻前的等待时间 > 0:
                            logger.info('龙舌兰、但书进驻前的等待时间为 ' + str(龙舌兰_但书进驻前的等待时间) + ' 秒')
                            time.sleep(龙舌兰_但书进驻前的等待时间)
                    self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
                    self.recog.update()
                    if self.get_infra_scene() == 206:
                        x0 = self.recog.w // 3 * 2  # double confirm
                        y0 = self.recog.h - 10
                        self.tap((x0, y0), rebuild=True)
                    read_time_index = []
                    if get_time:
                        read_time_index = self.干员信息.get_refresh_index(room, plan[room])
                    current = self.get_agent_from_room(room, read_time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]['agent'] != name:
                            logger.error(f'检测到的干员{current[idx]["agent"]},需要安排的干员{name}')
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
                            (int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404),
                             int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
                            use_digit_reader=True)
                        logger.warning('房间 B' + room[5] + '0' + room[7] +
                                       ' 修正后的接单时间为 ' + 修正后的接单时间.strftime("%H:%M:%S"))
                        截图等待时间 = (修正后的接单时间 - datetime.now()).total_seconds()
                        if (截图等待时间 > 0) and (截图等待时间 < 1000):
                            logger.info("等待截图时间为 " + str(截图等待时间) + ' 秒')
                            time.sleep(截图等待时间)
                        self.recog.save_screencap('run_order')
                    while self.scene() == 9:
                        time.sleep(1)
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

    @Asst.CallBackType
    def log_maa(msg, details, arg):
        m = Message(msg)
        d = json.loads(details.decode('utf-8'))
        logger.debug(d)
        logger.debug(m)
        logger.debug(arg)

    def MAA初始化(self):
        # 若需要获取详细执行信息，请传入 callback 参数
        # 例如 asst = Asst(callback=my_callback)
        Asst.load(path=self.MAA设置['MAA路径'])
        self.MAA = Asst(callback=self.log_maa)
        self.关卡列表 = []
        # self.MAA.set_instance_option(2, 'maatouch')
        # 请自行配置 adb 环境变量，或修改为 adb 可执行程序的路径
        # logger.info(self.device.client.device_id)
        if self.MAA.connect(self.MAA设置['MAA_adb路径'], self.device.client.device_id):
            logger.info("MAA 连接成功")
        else:
            logger.info("MAA 连接失败")
            raise Exception("MAA 连接失败")

    def append_maa_task(self, type):
        if type in ['StartUp', 'Visit', 'Award']:
            self.MAA.append_task(type)
        elif type == 'Fight':
            _plan = self.MAA设置['周计划'][get_server_weekday()]
            logger.info(f"现在服务器是{_plan['日子']}")
            for stage in _plan["关卡"]:
                logger.info(f"添加关卡:{stage}")
                self.MAA.append_task('Fight', {
                    # 空值表示上一次
                    # 'stage': '',
                    'stage': stage,
                    '应急理智药': _plan["应急理智药"],
                    'stone': 0,
                    'times': 999,
                    'report_to_penguin': True,
                    'client_type': '',
                    'penguin_id': '',
                    'DrGrandet': False,
                    'server': 'CN',
                    'expiring_medicine': 9999
                })
                self.关卡列表.append(stage)
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

    # def maa_plan_solver(self, 任务列表='All', one_time=False):
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
            self.send_email('MAA停止')
            if hard_stop:
                logger.info(f"由于MAA任务并未完成，等待3分钟重启软件")
                time.sleep(180)
                self.device.exit(self.服务器)
            elif not one_time:
                logger.info(f"记录MAA 本次执行时间")
                self.MAA设置['上一次作战'] = datetime.now()
                logger.info(self.MAA设置['上一次作战'])
            if self.MAA设置['集成战略'] or self.MAA设置['生息演算'] or self.MAA设置['保全派驻']:
                while (self.任务列表[0].time - datetime.now()).total_seconds() > 30:
                    self.MAA = None
                    self.MAA初始化()
                    if self.MAA设置['集成战略']:
                        self.MAA.append_task('Roguelike', {
                            'mode': 1,
                            'starts_count': 9999999,
                            'investment_enabled': True,
                            'investments_count': 9999999,
                            'stop_when_investment_full': False,
                            'squad': '后勤分队',
                            'roles': '取长补短',
                            'theme': 'Sami',
                            'core_char': ''
                        })
                    elif self.MAA设置['生息演算']:
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
        if '邮件提醒' in self.邮件设置.keys() and self.邮件设置['邮件提醒'] == 0:
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
                        context += f"""<tr><td>{任务.time.strftime('%Y-%m-%d %H:%M:%S')}</td>
                                            <td>{任务.type}</td></tr>    
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
    config.ADB_DEVICE = MAA设置['MAA_adb地址']
    config.ADB_CONNECT = MAA设置['MAA_adb地址']
    config.APPNAME = 服务器
    config.TAP_TO_LAUNCH = [{"enable": "false", "x": "0", "y": "0"}]
    init_fhlr()
    device = 设备控制()
    cli = Solver(device)
    if scheduler is None:
        当前项目 = 项目经理(cli.device, cli.recog)
        当前项目.服务器 = 服务器
        当前项目.operators = {}
        当前项目.plan = {}
        当前项目.current_base = {}
        for 房间 in 跑单位置设置:
            当前项目.plan['room_' + 房间[1] + '_' + 房间[3]] = []
            for 干员 in 跑单位置设置[房间]:
                当前项目.plan['room_' + 房间[1] + '_' + 房间[3]].append(
                    {'agent': '', 'group': '', 'replacement': [干员]})
        if 龙舌兰和但书休息:
            global 龙舌兰和但书休息宿舍
            for 宿舍 in 宿舍设置:
                if 宿舍 == 'B401':
                    龙舌兰和但书休息宿舍 = 'dormitory_4'
                else:
                    龙舌兰和但书休息宿舍 = 'dormitory_' + 宿舍[1]
                当前项目.plan[龙舌兰和但书休息宿舍] = []
                for 干员 in 宿舍设置[宿舍]:
                    if 干员 == '当前休息干员':  干员 = 'Current'
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
        global ope_list, 当前项目, 任务提示, 下个任务开始时间
        # 第一次执行任务
        任务列表 = []
        for t in 任务列表:
            t.time = datetime.strptime(str(t.time), '%Y-%m-%d %H:%M:%S.%f')
        reconnect_max_tries = 10
        reconnect_tries = 0
        当前项目 = 初始化(任务列表)
        当前项目.device.launch(f"{服务器}/{config.APP_ACTIVITY_NAME}")
        当前项目.initialize_operators()
        while True:
            try:
                if len(当前项目.任务列表) > 0:
                    当前项目.任务列表.sort(key=lambda x: x.time, reverse=False)    # 任务按时间排序
                    # 如果订单间的时间差距小，无人机加速拉开订单间的时间差距
                    if (len(任务列表) > 1 and (任务列表[0].time - datetime.now()).total_seconds()
                            > 当前项目.跑单提前运行时间 > (任务列表[1].time - 任务列表[0].time).total_seconds()):
                        logger.warning("无人机加速拉开订单间的时间差距")
                        当前项目.无人机加速(任务列表[0].type, True, True)
                    下个任务开始时间 = 任务列表[0].time
                    当前项目.recog.update()
                    当前项目.返回基主界面()
                    任务间隔 = (当前项目.任务列表[0].time - datetime.now()).total_seconds()
                    if (当前项目.任务列表[0].time - datetime.now()).total_seconds() > 0:
                        当前项目.send_email()
                        任务提示 = str()
                        for i in range(len(任务列表)):
                            任务提示 += ('房间 B' + 任务列表[i].type[5] + '0' + 任务列表[i].type[7]
                                         + ' 开始跑单的时间为 ' + 任务列表[i].time.strftime("%H:%M:%S") + '\n')
                        if 跑单弹窗提醒开关:    托盘.notify(任务提示, "Mower跑单提醒")
                        托盘.notify(任务提示, "Mower跑单提醒")
                        for i in range(len(任务列表)):
                            logger.warning('房间 B' + 任务列表[i].type[5] + '0' + 任务列表[i].type[7] +
                                           ' 开始跑单的时间为 ' + 任务列表[i].time.strftime("%H:%M:%S"))

                    # 如果有高强度重复MAA任务,任务间隔超过10分钟则启动MAA
                    if (MAA设置['集成战略'] or MAA设置['生息演算']) and (任务间隔 > 600):
                        当前项目.maa_plan_solver()
                    elif 任务间隔 > 0:
                        if 任务结束后退出游戏 and 任务间隔 > 跑单提前运行时间:
                            当前项目.device.exit(当前项目.服务器)
                            time.sleep(任务间隔 - 跑单提前运行时间)
                            if 跑单弹窗提醒开关:
                                托盘.notify("跑单时间快到了喔，请放下游戏中正在做的事，或者手动关闭Mower", "Mower跑单提醒")
                            time.sleep(跑单提前运行时间)
                            if 跑单弹窗提醒开关:    托盘.notify("开始跑单！", "Mower跑单提醒")
                        else:
                            time.sleep(任务间隔)
                            当前项目.back_to_index()

                if len(当前项目.任务列表) > 0 and 当前项目.任务列表[0].type.split('_')[0] == 'maa':
                    当前项目.maa_plan_solver((当前项目.任务列表[0].type.split('_')[1]).split(','), one_time=True)
                    continue
                当前项目.run()
                reconnect_tries = 0
            except ConnectionError as e:
                reconnect_tries += 1
                if reconnect_tries < reconnect_max_tries:
                    logger.warning(f'连接端口断开...正在重连...')
                    connected = False
                    while not connected:
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


def 跑单任务查询(icon: pystray.Icon):
    icon.notify(任务提示, "Mower跑单任务列表")


def 重新运行Mower():
    global Mower
    try:
        Mower._stop_event.set()
        终止线程报错(Mower.ident, SystemExit)
    except:
        pass
    Mower = 线程()
    Mower.start()


def 停止运行Mower():
    Mower._stop_event.set()
    终止线程报错(Mower.ident, SystemExit)
    logger.info('Mower已停止')


def 退出程序(icon, item):
    icon.stop()  # 对象停止方法
    pid = os.getpid()  # 获取当前进程ID
    try:  # 杀掉后台进程
        if 悬浮字幕开关:  窗口.destroy()
        os.system('taskkill -f -pid %s' % pid)
    except:
        pass


def 更新字幕():
    global 字幕
    任务倒计时 = int((下个任务开始时间 - datetime.now()).total_seconds() / 60)
    字幕 = 'Mower的回合！'
    if 任务倒计时 >= 0:
        字幕 = 'Mower将在' + str(任务倒计时) + '分钟后开始跑单'
        if 任务倒计时 <= 5:
            字幕 += '\n跑单即将开始！'
    label.config(text=字幕, font=(字幕字体 + ' ' + 字幕字号), bg=字幕颜色,
                 fg=字幕颜色[:6] + str(int(字幕颜色[5] == '0')))
    窗口.after(5000, 更新字幕)


托盘菜单 = (MenuItem(任务提示, 跑单任务查询, default=True, visible=False),
            MenuItem('显示字幕', 显示字幕, visible=悬浮字幕开关),
            MenuItem('重新运行Mower', 重新运行Mower, visible=True),
            MenuItem('停止运行Mower', 停止运行Mower, visible=True),
            Menu.SEPARATOR, MenuItem('退出', 退出程序))
托盘 = pystray.Icon("Mower 纯跑单", Image.open("logo.png"), "Mower 纯跑单", 托盘菜单)
if 悬浮字幕开关:
    窗口.geometry("%dx%d+%d+%d" % (窗口宽度, 窗口高度,
                                   (窗口.winfo_screenwidth() - 窗口宽度) / 2,
                                   (窗口.winfo_screenheight() - 窗口高度) / 2))
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

if __name__ == "__main__":
    日志设置()
    threading.Thread(target=托盘.run, daemon=False).start()
    Mower = 线程()
    Mower.start()
    if 悬浮字幕开关:
        窗口.after(5000, 更新字幕)
        窗口.mainloop()
