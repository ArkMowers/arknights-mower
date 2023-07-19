from __future__ import annotations
from datetime import datetime, timedelta
from arknights_mower.utils import config
from arknights_mower.utils.device import Device
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.data import agent_list
from arknights_mower.utils import character_recognize, detector, segment
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.operators import Operators, Operator
from arknights_mower.utils.scheduler_task import SchedulerTask
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.pipe import push_operators
from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
from arknights_mower.utils.solver import BaseSolver
from arknights_mower.utils.datetime import get_server_weekday, the_same_time
from arknights_mower.utils.asst import Asst, Message
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import copy
import cv2
import json
import smtplib
import sys
import time
import warnings
# import winsound   # Windows 铃声


def warn(*args, **kwargs):
    pass

warnings.warn = warn

from paddleocr import PaddleOCR
from arknights_mower.strategy import Solver

官方服务器 = 'com.hypergryph.arknights'
Bilibili服务器 = 'com.hypergryph.arknights.bilibili'

################################################################################################
# # # # # # # # # # # # # # # # # # # # # # 用户设置区 # # # # # # # # # # # # # # # # # # # # # #
################################################################################################

服务器 = 官方服务器  # 服务器选择(官方服务器/Bilibili服务器)

跑单提前运行时间 = 300  # 秒
更换干员前缓冲时间 = 25  # 秒 需要严格大于一次跟服务器交换数据的时间

日志存储目录 = './log'
截图存储目录 = './screenshot'
每种截图的最大保存数量 = 10

排班 = {
    'room_1_1': [{'agent': '图耶', 'group': '', 'replacement': ['推进之王', '能天使', '海蒂', '雪雉']},
                 {'agent': '鸿雪', 'group': '', 'replacement': ['龙舌兰', '摩根', '能天使', '海蒂', '雪雉']},
                 {'agent': '泰拉大陆调查团', 'group': '', 'replacement': ['但书', '能天使', '海蒂', '雪雉']}
                 ],
    'room_2_1': [{'agent': '巫恋', 'group': '', 'replacement': ['孑']},
                 {'agent': '黑键', 'group': '', 'replacement': ['龙舌兰', '银灰']},
                 {'agent': '绮良', 'group': '', 'replacement': ['但书', '崖心']}],
}

邮件设置 = {
    '发信邮箱': "xxxxxxxxxx@qq.com",
    '授权码': 'xxxxxxxxxx',  # 在QQ邮箱“账户设置-账户-开启SMTP服务”中，按照指示开启服务获得授权码
    '收件人邮箱': ['langchuang@foxmail.com'],  # 收件人邮箱
    '邮件提醒开关': True,  # 是否启用邮件提醒
}

MAA设置 = {
    "MAA路径": 'K:\\MAA\\MAA-v4.10.5-win-x64',  # 请设置为存放 dll 文件及资源的路径
    "MAA_adb路径": "K:\\MuMuPlayer-12.0\\shell\\adb.exe",  # 请设置为模拟器的 adb 路径
    "MAA_adb地址": ['127.0.0.1:16384'],  # 请设置为模拟器的 adb 地址

    # 以下配置，第一个设置为true的首先生效
    "集成战略": True,  # 是否启动集成战略
    "生息演算": False,  # 是否启动生息演算
    "保全派驻": False,  # 是否启动保全派驻
    "上一次作战": None,
    "周计划": [{"日子": "周一", "关卡": ['(上次作战)'], "应急理智药": 0},
               {"日子": "周二", "关卡": ['(上次作战)'], "应急理智药": 0},
               {"日子": "周三", "关卡": ['(上次作战)'], "应急理智药": 0},
               {"日子": "周四", "关卡": ['(上次作战)'], "应急理智药": 0},
               {"日子": "周五", "关卡": ['(上次作战)'], "应急理智药": 0},
               {"日子": "周六", "关卡": ['(上次作战)'], "应急理智药": 0},
               {"日子": "周日", "关卡": ['(上次作战)'], "应急理智药": 0}]
}

################################################################################################
class ArrangeOrder(Enum):
    STATUS = 1
    SKILL = 2
    FEELING = 3
    TRUST = 4


ocr = None

arrange_order_res = {
    ArrangeOrder.STATUS: (1560 / 2496, 96 / 1404),
    ArrangeOrder.SKILL: (1720 / 2496, 96 / 1404),
    ArrangeOrder.FEELING: (1880 / 2496, 96 / 1404),
    ArrangeOrder.TRUST: (2050 / 2496, 96 / 1404),
}


def 调试输出():
    logger.handlers[0].setLevel('DEBUG')


def 日志设置():
    config.LOGFILE_PATH = 日志存储目录
    config.SCREENSHOT_PATH = 截图存储目录
    config.SCREENSHOT_MAXNUM = 每种截图的最大保存数量
    config.MAX_RETRYTIME = 10


class BaseSchedulerSolver(BaseSolver):
    服务器 = ''

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.planned = None
        self.todo_task = None
        self.邮件设置 = None
        self.op_data = None
        self.跑单提前运行时间 = 300
        self.digit_reader = DigitReader()
        self.error = False
        self.任务列表 = []
        self.run_order_rooms = {}

    def run(self) -> None:
        self.error = False
        if len(self.任务列表) == 0:
            self.recog.update()
            self.sleep()
        self.handle_error(True)
        if len(self.任务列表) > 0:
            # 找到时间最近的一次单个任务
            self.任务 = self.任务列表[0]
        else:
            self.任务 = None
        self.todo_task = False
        self.collect_notification = False
        self.planned = False
        if self.op_data is None or self.op_data.operators is None:
            self.initialize_operators()
        return super().run()

    def transition(self) -> None:
        self.recog.update()
        if self.scene() == Scene.INDEX:
            self.tap_element('index_infrastructure')
        elif self.scene() == Scene.INFRA_MAIN:
            return self.infra_main()
        elif self.scene() == Scene.INFRA_TODOLIST:
            return self.todo_list()
        elif self.scene() == Scene.INFRA_DETAILS:
            self.back()
        elif self.scene() == Scene.LOADING:
            self.sleep()
        elif self.scene() == Scene.CONNECTING:
            self.sleep()
        elif self.get_navigation():
            self.tap_element('nav_infrastructure')
        elif self.scene() == Scene.INFRA_ARRANGE_ORDER:
            self.tap_element('arrange_blue_yes')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
            self.last_room = ''
            logger.info("重设上次房间为空")
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
        if self.scene() == Scene.UNKNOWN:
            self.recog.update()
            # logger.info('返回基建主界面')
            # while self.get_infra_scene() != Scene.INFRA_MAIN:
            #     self.back()
            #     self.recog.update()
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
                    self.agent_arrange(self.任务.plan, get_time)
                    if get_time:
                        self.plan_metadata()
                # 如果任务名称包含干员名,则为动态生成的
                elif self.任务.type.split(',')[0] in agent_list:
                    self.overtake_room()
                elif self.任务.type == 'impart':
                    self.skip(['planned', 'collect_notification'])
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
                self.sleep()
                notification = detector.infra_notification(self.recog.img)
            if notification is not None:
                self.tap(notification)
            self.collect_notification = True
        else:
            return self.handle_error()

    def plan_solver(self):
        plan = self.排班
        # 如果下个 普通任务 <10 分钟则跳过 plan
        if self.find_next_task(datetime.now() + timedelta(seconds=600)) is not None:
            return
        if len(self.run_order_rooms) > 0:
            # 处理龙舌兰和但书的跑单
            for k, v in self.run_order_rooms.items():
                # 如果没有当前房间数据
                if 'plan' not in v.keys():
                    v['plan'] = self.op_data.get_current_room(k)
                if self.find_next_task(task_type=k) is not None: continue;
                in_out_plan = {k: ['Current'] * len(plan[k])}
                for idx, x in enumerate(plan[k]):
                    if '但书' in x['replacement'] or '龙舌兰' in x['replacement']:
                        in_out_plan[k][idx] = x['replacement'][0]
                self.任务列表.append(
                    SchedulerTask(time=self.读取接单时间(k), task_plan=in_out_plan, task_type=k))
        # 准备数据
        logger.debug(self.op_data.print())

    def initialize_operators(self):
        plan = self.排班
        # self.op_data = Operators(self.agent_base_config, self.max_resting_count, plan)
        self.op_data = Operators({}, 4, plan)
        for room in plan.keys():
            for idx, data in enumerate(plan[room]):
                self.op_data.add(Operator(data["agent"], room, idx, data["group"], data["replacement"], 'high',
                                          operator_type="high"))
        added = []
        # 跑单
        for x, y in self.排班.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                self.run_order_rooms[x] = {}

    def 读取接单时间(self, room):
        logger.info('读取接单时间')
        # 点击进入该房间
        self.enter_room(room)
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
        logger.warning(room + ' 接单时间为：' + execute_time.strftime("%H:%M:%S"))
        execute_time = execute_time - timedelta(seconds=(self.跑单提前运行时间))
        self.recog.update()
        logger.info('返回基建主界面')
        while self.get_infra_scene() != Scene.INFRA_MAIN:
            self.back()
            self.recog.update()
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

    def todo_list(self) -> None:
        """ 处理基建 Todo 列表 """
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

    def enter_room(self, room: str) -> tp.Rectangle:
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

    def drone(self, room: str, not_customize=False, not_return=False):
        logger.info('无人机加速')
        all_in = 0
        if not not_customize:
            all_in = len(self.run_order_rooms)
        # 点击进入该房间
        self.enter_room(room)
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
            # while (self.任务列表[1].time - self.任务列表[0].time).total_seconds() < 140:
            while (self.任务列表[1].time - self.任务列表[0].time).total_seconds() < self.跑单提前运行时间:
                logger.info(room + ' 加速')
                self.tap(accelerate)
                self.device.tap((1320, 502))
                self.sleep()
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8))
                while self.get_infra_scene() == Scene.CONNECTING:
                    self.sleep()
                while self.find('bill_accelerate') is None:
                    if error_count > 5:
                        raise Exception('未成功进入订单界面')
                    self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
                    error_count += 1
                加速后接单时间 = self.double_read_time((int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404),
                                                        int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
                                                       use_digit_reader=True)
                self.任务列表[0].time = 加速后接单时间 - timedelta(seconds=(self.跑单提前运行时间))
                logger.info(room + ' 加速后接单时间为：' + 加速后接单时间.strftime("%H:%M:%S"))
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

    def get_arrange_order(self) -> ArrangeOrder:
        best_score, best_order = 0, None
        for order in ArrangeOrder:
            score = self.recog.score(arrange_order_res[order][0])
            if score is not None and score[0] > best_score:
                best_score, best_order = score[0], order
        logger.debug((best_score, best_order))
        return best_order

    def switch_arrange_order(self, index: int, asc="false") -> None:
        self.tap((self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                  self.recog.h * arrange_order_res[ArrangeOrder(index)][1]), interval=0, rebuild=False)
        # 点个不需要的
        if index < 4:
            self.tap((self.recog.w * arrange_order_res[ArrangeOrder(index + 1)][0],
                      self.recog.h * arrange_order_res[ArrangeOrder(index)][1]), interval=0, rebuild=False)
        else:
            self.tap((self.recog.w * arrange_order_res[ArrangeOrder(index - 1)][0],
                      self.recog.h * arrange_order_res[ArrangeOrder(index)][1]), interval=0, rebuild=False)
        # 切回来
        self.tap((self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                  self.recog.h * arrange_order_res[ArrangeOrder(index)][1]), interval=0.2, rebuild=True)
        # 倒序
        if asc != "false":
            self.tap((self.recog.w * arrange_order_res[ArrangeOrder(index)][0],
                      self.recog.h * arrange_order_res[ArrangeOrder(index)][1]), interval=0.2, rebuild=True)

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
                self.sleep()
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

    def choose_agent(self, agents: list[str], room: str) -> None:
        """
        :param order: ArrangeOrder, 选择干员时右上角的排序功能
        """
        first_name = ''
        max_swipe = 50
        for idx, n in enumerate(agents):
            if n == '':
                agents[idx] = 'Free'
        agent = copy.deepcopy(agents)
        logger.info(f'安排干员 ：{agent}')
        logger.warning(room + ' 进驻时间为：' + (self.任务列表[0].time + timedelta(
            seconds=(self.跑单提前运行时间 - self.更换干员前缓冲时间))).strftime("%H:%M:%S"))
        h, w = self.recog.h, self.recog.w
        first_time = True
        index_change = False
        pre_order = [2, False]
        right_swipe = 0
        retry_count = 0
        # 如果重复进入宿舍则需要排序
        selected = []
        logger.info(f'上次进入房间为：{self.last_room},本次房间为：{room}')
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
                    index_change = True

            # 如果选中了人，则可能需要重新排序
            # if index_change or first_time:
            # 第一次则调整
            # is_custom, arrange_type = self.get_order(agent[0])
            # 如果重新排序则滑到最左边
            # if pre_order[0] != arrange_type[0] or pre_order[1] != arrange_type[1]:
            #     self.switch_arrange_order(arrange_type[0], arrange_type[1])
            #     # 滑倒最左边
            #     self.sleep(interval=0.5, rebuild=True)
            #     right_swipe = self.swipe_left(right_swipe, w, h)
            #     pre_order = arrange_type
            first_time = False

            changed, ret = self.scan_agant(agent)
            if changed:
                selected.extend(changed)
                # 如果找到了
                index_change = True
            else:
                # 如果没找到 而且右移次数大于5
                if ret[0][0] == first_name and right_swipe > 5:
                    max_swipe = right_swipe
                else:
                    first_name = ret[0][0]
                index_change = False
                st = ret[-2][1][2]  # 起点
                ed = ret[0][1][1]  # 终点
                self.swipe_noinertia(st, (ed[0] - st[0], 0))
                right_swipe += 1
            if len(agent) == 0: break;

        # 排序
        if len(agents) != 1:
            # 左移
            self.swipe_left(right_swipe, w, h)
            self.tap((self.recog.w * arrange_order_res[ArrangeOrder.SKILL][0],
                      self.recog.h * arrange_order_res[ArrangeOrder.SKILL][1]), interval=0.5, rebuild=False)
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
        logger.info(f"设置上次房间为{self.last_room}")

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    def read_accurate_mood(self, img, cord):
        try:
            img = img[cord[1]:cord[3], cord[0]:cord[2]]
            # Convert the image to grayscale
            gray_image = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            blurred_image = cv2.GaussianBlur(gray_image, (5, 5), 0)

            # Threshold the image to isolate the progress bar region
            contours, hierarchy = cv2.findContours(blurred_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Calculate the bounding box of the progress bar
            x, y, w, h = cv2.boundingRect(contours[0])

            # Crop the progress bar region
            progress_bar = img[y:y + h, x:x + w]

            # Convert the progress bar to grayscale
            gray_pb = cv2.cvtColor(progress_bar, cv2.COLOR_BGR2GRAY)

            # Threshold the progress bar to isolate the gray fill
            ret, thresh_pb = cv2.threshold(gray_pb, 137, 255, cv2.THRESH_BINARY)

            # Calculate the ratio of colored pixels to the total number of pixels in the progress bar region
            total_pixels = w * h
            colored_pixels = cv2.countNonZero(thresh_pb)
            return colored_pixels / total_pixels * 24

        except Exception:
            return 24

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
        length = len(self.排班[room])
        if length > 3: self.swipe((self.recog.w * 0.8, self.recog.h * 0.5), (0, self.recog.h * 0.45), duration=500,
                                  interval=1,
                                  rebuild=True)
        name_p = [((1460, 155), (1700, 210)), ((1460, 370), (1700, 420)), ((1460, 585), (1700, 630)),
                  ((1460, 560), (1700, 610)), ((1460, 775), (1700, 820))]
        time_p = [((1650, 270, 1780, 305)), ((1650, 480, 1780, 515)), ((1650, 690, 1780, 725)),
                  ((1650, 665, 1780, 700)), ((1650, 875, 1780, 910))]
        mood_p = [((1470, 219, 1780, 221)), ((1470, 428, 1780, 430)), ((1470, 637, 1780, 639)),
                  ((1470, 615, 1780, 617)), ((1470, 823, 1780, 825))]
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
            _mood = 24
            # 如果房间不为空
            if _name != '':
                if _name not in self.op_data.operators.keys() and _name in agent_list:
                    self.op_data.add(Operator(_name, ""))
                update_time = False
                if self.op_data.operators[_name].need_to_refresh(r=room):
                    _mood = self.read_accurate_mood(self.recog.img, cord=mood_p[i])
                    update_time = True
                else:
                    _mood = self.op_data.operators[_name].current_mood()
                high_no_time = self.op_data.update_detail(_name, _mood, room, i, update_time)
                data['depletion_rate'] = self.op_data.operators[_name].depletion_rate
                if high_no_time is not None:
                    logger.debug(f"检测到高效组休息时间数据不存在:{room},{high_no_time}")
                    read_time_index.append(high_no_time)
            else:
                _mood = -1
            data['agent'] = _name
            data['mood'] = _mood
            if i in read_time_index:
                if _mood == 24:
                    data['time'] = datetime.now()
                else:
                    upperLimit = 21600
                    logger.debug(f"开始记录时间:{room},{i}")
                    data['time'] = self.double_read_time(time_p[i], upperLimit=upperLimit)
                self.op_data.refresh_dorm_time(room, i, data)
                logger.debug(f"停止记录时间:{str(data)}")
            result.append(data)
        for _operator in self.op_data.operators.keys():
            if self.op_data.operators[_operator].current_room == room and _operator not in [res['agent'] for res in
                                                                                            result]:
                self.op_data.operators[_operator].current_room = ''
                self.op_data.operators[_operator].current_index = -1
                logger.info(f'重设 {_operator} 至空闲')
        return result

    def refresh_current_room(self, room):
        _current_room = self.op_data.get_current_room(room)
        if _current_room is None:
            self.get_agent_from_room(room)
            _current_room = self.op_data.get_current_room(room, True)
        return _current_room

    def agent_arrange(self, plan: tp.BasePlan, get_time=False):
        logger.info('排班')
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
                    self.enter_room(room)
                    while self.find('room_detail') is None:
                        if error_count > 3:
                            raise Exception('未成功进入房间')
                        self.tap((self.recog.w * 0.05, self.recog.h * 0.4), interval=0.5)
                        error_count += 1
                    error_count = 0
                    if choose_error == 0:
                        if ('但书' in plan[room] or '龙舌兰' in plan[room]) and not \
                                room.startswith('dormitory'):
                            new_plan[room] = self.refresh_current_room(room)
                        if 'Current' in plan[room]:
                            self.refresh_current_room(room)
                            for current_idx, _name in enumerate(plan[room]):
                                if _name == 'Current':
                                    plan[room][current_idx] = self.op_data.get_current_room(room, True)[current_idx]
                        if room in self.run_order_rooms and len(new_plan) == 0:
                            if 'plan' in self.run_order_rooms[room] and plan[room] != self.run_order_rooms[room][
                                'plan']:
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
                    self.choose_agent(plan[room], room)
                    self.recog.update()
                    if len(new_plan) == 1:
                        龙舌兰_但书进驻前的等待时间 = (self.任务列表[
                                                           0].time - datetime.now()).total_seconds() + self.跑单提前运行时间 - self.更换干员前缓冲时间
                        if 龙舌兰_但书进驻前的等待时间 > 0:
                            logger.info('龙舌兰、但书进驻前的等待时间为：' + str(龙舌兰_但书进驻前的等待时间) + ' 秒')
                            self.sleep(龙舌兰_但书进驻前的等待时间)
                            # self.sleep()  # 调试
                    self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
                    self.recog.update()
                    if self.get_infra_scene() == Scene.INFRA_ARRANGE_CONFIRM:
                        x0 = self.recog.w // 3 * 2  # double confirm
                        y0 = self.recog.h - 10
                        self.tap((x0, y0), rebuild=True)
                    read_time_index = []
                    if get_time:
                        read_time_index = self.op_data.get_refresh_index(room, plan[room])
                    if len(new_plan) > 1:
                        self.op_data.operators[plan[room][0]].time_stamp = None
                    current = self.get_agent_from_room(room, read_time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]['agent'] != name:
                            logger.error(f'检测到的干员{current[idx]["agent"]},需要安排的干员{name}')
                            raise Exception('检测到安排干员未成功')
                    finished = True
                    # 如果完成则移除该任务
                    del plan[room]
                    # back to 基地主界面
                    if len(new_plan) == 1:
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
                        logger.warning(room + ' 修正后的接单时间为：' + 修正后的接单时间.strftime("%H:%M:%S"))
                        截图等待时间 = (修正后的接单时间 - datetime.now()).total_seconds()
                        if (截图等待时间 > 0) and (截图等待时间 < 1000):
                            logger.info("等待截图时间为：" + str(截图等待时间) + ' 秒')
                            self.sleep(截图等待时间)
                        self.recog.save_screencap('run_order')
                    while self.scene() == Scene.CONNECTING:
                        self.sleep()
                except Exception as e:
                    logger.exception(e)
                    choose_error += 1
                    self.recog.update()
                    back_count = 0
                    while self.get_infra_scene() != Scene.INFRA_MAIN:
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
        if len(new_plan) == 1:
            # 防止由于意外导致的死循环
            run_order_room = next(iter(new_plan))
            if '但书' in new_plan[run_order_room] or '龙舌兰' in new_plan[run_order_room]:
                new_plan[run_order_room] = [data["agent"] for data in self.排班[room]]
            # 返回基建主界面
            self.recog.update()
            while self.get_infra_scene() != Scene.INFRA_MAIN:
                self.back()
                self.recog.update()
            self.任务列表.append(SchedulerTask(time=self.任务列表[0].time, task_plan=new_plan))
            self.skip(['planned', 'todo_task'])
        elif len(new_plan) > 1:
            self.任务列表.append(SchedulerTask(time=self.任务列表[0].time, task_plan=new_plan))
            # 急速换班
            self.skip()
        logger.info('返回基建主界面')

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
        elif type == 'Recruit':
            self.MAA.append_task('Recruit', {
                'select': [4],
                'confirm': [3, 4],
                'times': 4,
                'refresh': True,
                "recruitment_time": {
                    "3": 460,
                    "4": 540
                }
            })
        elif type == 'Mall':
            credit_fight = False
            if len(self.关卡列表) > 0 and self.关卡列表[- 1] != '':
                credit_fight = True
            self.MAA.append_task('Mall', {
                'shopping': True,
                'buy_first': ['招聘许可'],
                'blacklist': ['家具', '碳', '加急许可'],
                'credit_fight': credit_fight
            })

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
                logger.info(f"由于maa任务并未完成，等待3分钟重启软件")
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
                            'mode': 0,
                            'starts_count': 9999999,
                            'investment_enabled': True,
                            'investments_count': 9999999,
                            'stop_when_investment_full': False,
                            'squad': '指挥分队',
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
                        <tr><th>房间</th><th>时间</th></tr>                    
                    """
                    for 任务 in self.任务列表:
                        context += f"""<tr><td>{任务.type}</td>
                                    <td>{任务.time.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>    
                                """
                    context += "</table></body></html>"
                    msg.attach(MIMEText(context, 'html'))
                else:
                    msg.attach(MIMEText(str(context), 'plain', 'utf-8'))
                msg['Subject'] = '下一次进行跑单的房间为：' + 任务.type + '，时间为：' + 任务.time.strftime(
                    '%Y-%m-%d %H:%M:%S')
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

    init_fhlr()
    device = Device()
    cli = Solver(device)
    if scheduler is None:
        base_scheduler = BaseSchedulerSolver(cli.device, cli.recog)
        base_scheduler.服务器 = 服务器
        base_scheduler.operators = {}
        base_scheduler.current_base = {}
        base_scheduler.排班 = 排班
        base_scheduler.任务列表 = 任务列表
        base_scheduler.last_room = ''
        base_scheduler.MAA = None
        base_scheduler.邮件设置 = 邮件设置
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.MAA设置 = MAA设置
        base_scheduler.error = False
        base_scheduler.跑单提前运行时间 = 跑单提前运行时间
        base_scheduler.更换干员前缓冲时间 = 更换干员前缓冲时间
        return base_scheduler
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler


def 运行():
    global ope_list, base_scheduler
    # 第一次执行任务
    任务列表 = []
    for t in 任务列表:
        t.time = datetime.strptime(str(t.time), '%Y-%m-%d %H:%M:%S.%f')
    reconnect_max_tries = 10
    reconnect_tries = 0
    base_scheduler = 初始化(任务列表)
    base_scheduler.device.launch(f"{服务器}/{config.APP_ACTIVITY_NAME}")
    base_scheduler.initialize_operators()
    while True:
        try:
            if len(base_scheduler.任务列表) > 0:
                base_scheduler.任务列表.sort(key=lambda x: x.time, reverse=False)
                if len(任务列表) > 1 and (
                        任务列表[0].time - datetime.now()).total_seconds() > base_scheduler.跑单提前运行时间 > (
                        任务列表[1].time - 任务列表[0].time).total_seconds():
                    logger.warning("无人机加速拉开订单间的时间差距")
                    base_scheduler.drone(任务列表[0].type, True, True)
                    # 返回基建主界面
                base_scheduler.recog.update()
                while base_scheduler.get_infra_scene() != Scene.INFRA_MAIN:
                    base_scheduler.back()
                    base_scheduler.recog.update()
                sleep_time = (base_scheduler.任务列表[0].time - datetime.now()).total_seconds()
                if (base_scheduler.任务列表[0].time - datetime.now()).total_seconds() > 0:
                    base_scheduler.send_email()
                    for i in range(len(任务列表)):
                        logger.warning(任务列表[i].type + ' 开始跑单的时间为：' + 任务列表[i].time.strftime("%H:%M:%S"))

                # # 如果任务间隔时间超过5分钟则关闭游戏
                # if sleep_time > 300:
                #     base_scheduler.device.exit(base_scheduler.服务器)

                # logger.info('||'.join([str(t) for t in base_scheduler.任务列表]))

                # 如果任务间隔时间超过9分钟则启动MAA
                if sleep_time > 540:
                    base_scheduler.maa_plan_solver()
                elif sleep_time > 0:
                # if sleep_time > 0:
                    time.sleep(sleep_time)

                # # 任务开始前铃声提醒
                # if sleep_time > 150:
                #     time.sleep(sleep_time - 150)
                #     winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
                #     winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
                #     time.sleep(150)
                #     winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
                # elif sleep_time > 0:
                #     time.sleep(sleep_time)

            if len(base_scheduler.任务列表) > 0 and base_scheduler.任务列表[0].type.split('_')[0] == 'maa':
                base_scheduler.maa_plan_solver((base_scheduler.任务列表[0].type.split('_')[1]).split(','),
                                               one_time=True)
                continue
            base_scheduler.run()
            reconnect_tries = 0
        except ConnectionError as e:
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning(f'连接端口断开...正在重连...')
                connected = False
                while not connected:
                    try:
                        base_scheduler = 初始化([], base_scheduler)
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


日志设置()
运行()
