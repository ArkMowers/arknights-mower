from __future__ import annotations
import copy
import time
from enum import Enum
from datetime import datetime, timedelta
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..data import agent_list
from ..utils import character_recognize, detector, segment
from ..utils.operators import Operators, Operator, Dormitory
from ..utils import typealias as tp
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver
from ..utils.datetime import get_server_weekday
from paddleocr import PaddleOCR
import cv2

## Maa
from arknights_mower.utils.asst import Asst, Message
import json

ocr = None


class ArrangeOrder(Enum):
    STATUS = 1
    SKILL = 2
    FEELING = 3
    TRUST = 4


arrange_order_res = {
    ArrangeOrder.STATUS: (1560 / 2496, 96 / 1404),
    ArrangeOrder.SKILL: (1720 / 2496, 96 / 1404),
    ArrangeOrder.FEELING: (1880 / 2496, 96 / 1404),
    ArrangeOrder.TRUST: (2050 / 2496, 96 / 1404),
}


class BaseSchedulerSolver(BaseSolver):
    """
    收集基建的产物：物资、赤金、信赖
    """
    package_name = ''

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.op_data = None
        self.max_resting_count = 4
        self.party_time = None
        self.drone_time = None

    def run(self) -> None:
        """
        :param clue_collect: bool, 是否收取线索
        """
        self.currentPlan = self.global_plan[self.global_plan["default"]]
        self.error = False
        self.handle_error(True)
        if len(self.tasks) > 0:
            # 找到时间最近的一次单个任务
            self.task = self.tasks[0]
        else:
            self.task = None
        if self.party_time is not None and self.party_time<datetime.now():
            self.party_time = None
        self.todo_task = False
        self.planned = False
        if self.op_data is None:
            self.initialize_operators()
        return super().run()

    def get_group(self, rest_agent, agent, groupname, name):
        for element in agent:
            if element['group'] == groupname and name != element["agent"]:
                rest_agent.append(element)
                # 从大组里删除
                agent.remove(element)
        return

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
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
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

    def overtake_room(self):
        candidates = self.task['type'].split(',')
        # 在candidate 中，计算出需要的high free 和 Low free 数量
        _high_free = 0
        _low_free = 0
        for x in candidates:
            if self.op_data.operators[x].resting_priority == 'high':
                _high_free += 1
            else:
                _low_free += 1
        self.agent_get_mood(force=True)
        # 剩余高效组位置
        current_high = self.op_data.available_free(count=self.max_resting_count)
        # 剩余低效位置
        current_low = self.op_data.available_free('low', count=self.max_resting_count)
        if current_high >= _high_free and current_low >= _low_free:
            # 检查是否目前宿舍满足 low free 和high free 的数量需求，如果满足，则直接安排
            _plan = {}
            _replacement = []
            _replacement, _plan, current_high, current_low = self.get_resting_plan(candidates,
                                                                                   _replacement,
                                                                                   _plan,
                                                                                   current_high,
                                                                                   current_low)
            if len(_plan.items()) > 0:
                self.tasks.append({'time': datetime.now(), 'plan': _plan})
        else:
            # 如果不满足，则找到并且执行最近一个type 包含 超过数量的high free 和low free 的 任务并且 干员没有 exaust_require 词条
            task_index = -1
            current_high, current_low = 0, 0
            for idx, task in enumerate(self.tasks):
                if "type" in task.keys() and 'dorm' in task['type']:
                    # 检查数量
                    ids = [int(w[4:]) for w in task['type'].split(',')]
                    is_exhaust_require = False
                    for _id in ids:
                        if not is_exhaust_require:
                            if self.op_data.dorm[_id].name in self.op_data.exhaust_agent:
                                is_exhaust_require = True

                        if _id > self.max_resting_count - 1:
                            current_low += 1
                        else:
                            current_high += 1
                    # 休息满需要则跳过
                    if current_high >= _high_free and current_low >= _low_free and not is_exhaust_require:
                        task_index = idx
                    else:
                        current_low, current_high = 0, 0
            if task_index > -1:
                # 修改执行时间
                self.tasks[task_index]['time'] = datetime.now()
                # 执行完提前换班任务再次执行本任务
                self.tasks.append({'time': datetime.now(), 'plan': self.task['plan']})
            else:
                # 任务全清
                rooms = []
                remove_idx = []
                for idx, task in enumerate(self.tasks):
                    if "type" in task.keys() and 'dorm' in task['type']:
                        # 检查数量
                        ids = [int(w[4:]) for w in task['type'].split(',')]
                        is_exhaust_require = False
                        _rooms = []
                        for _id in ids:
                            if not is_exhaust_require:
                                if self.op_data.dorm[_id].name in self.op_data.exhaust_agent:
                                    is_exhaust_require = True
                            __room = self.op_data.operators[self.op_data.dorm[_id].name].room
                            if __room not in _rooms:
                                _rooms.append(__room)
                        # 跳过需要休息满
                        if not is_exhaust_require:
                            rooms.extend(__room)
                            remove_idx.append(idx)
                for idx in remove_idx:
                    del self.tasks[idx]
                plan = {}
                for room in rooms:
                    if room not in plan.keys():
                        plan[room] = [data["agent"] for data in self.currentPlan[room]]
                if len(plan.keys()) > 0:
                    self.tasks.append({'time': datetime.now(), 'plan': plan})
                    # 执行完提前换班任务再次执行本任务
                    self.tasks.append({'time': datetime.now(), 'plan': self.task['plan']})
            self.skip()
            return

    def handle_error(self, force=False):
        # 如果有任何报错，则生成一个空
        if self.scene() == Scene.UNKNOWN:
            self.device.exit(self.package_name)
        if self.error or force:
            # 如果没有任何时间小于当前时间的任务才生成空任务
            if (next((e for e in self.tasks if e['time'] < datetime.now()), None)) is None:
                room = next(iter(self.currentPlan.keys()))
                logger.debug("由于出现错误情况，生成一次空任务来执行纠错")
                self.tasks.append({'time': datetime.now(), 'plan': {}})
            # 如果没有任何时间小于当前时间的任务-10分钟 则清空任务
            if (next((e for e in self.tasks if e['time'] < datetime.now() - timedelta(seconds=600)), None)) is not None:
                logger.info("检测到执行超过10分钟的任务，清空全部任务")
                self.tasks = []
                self.op_data = None
        return True

    def plan_metadata(self):
        planned_index = []
        for t in self.tasks:
            if 'type' in t.keys() and 'dorm' in t['type']:
                planned_index.extend([int(w[4:]) for w in t['type'].split(',')])
        _time = datetime.max
        _plan = {}
        _type = []
        # 第一个心情低的且小于3 则只休息半小时
        short_rest = False
        self.total_agent = list(
            v for k, v in self.op_data.operators.items() if v.is_high() and not v.room.startswith('dorm') and not v.current_room.startswith('dorm'))
        self.total_agent.sort(key=lambda x: x.mood - x.lower_limit, reverse=False)
        if next((a for a in self.total_agent if (a.name not in self.op_data.exhaust_agent) and a.mood<=3),None) is not None:
            short_rest= True
        low_priority = []
        for idx, dorm in enumerate(self.op_data.dorm):
            # Filter out resting priority low
            if idx >= self.max_resting_count:
                break
            # 如果已经plan了，则跳过
            if idx in planned_index or idx in low_priority:
                continue
            _name = dorm.name
            if _name == '':
                continue
            # 如果是rest in full，则新增单独任务..
            if _name in self.op_data.operators.keys() and self.op_data.operators[_name].rest_in_full:
                __plan = {}
                __rest_agent = []
                __type = []
                if self.op_data.operators[dorm.name].group == "":
                    __rest_agent.append(dorm.name)
                else:
                    __rest_agent.extend(self.op_data.groups[self.op_data.operators[dorm.name].group])
                if dorm.time is not None:
                    __time = dorm.time
                else:
                    __time = datetime.max
                for x in __rest_agent:
                    # 如果同小组也是rest_in_full则取最大休息时间 否则忽略
                    _idx, __dorm = self.op_data.get_dorm_by_name(x)
                    if x in self.op_data.operators.keys() and self.op_data.operators[x].rest_in_full:
                        if __dorm is not None and __dorm.time is not None:
                            if __dorm.time > _time and self.op_data.operators[x].resting_priority == 'high':
                                _time = __dorm.time
                    if _idx is not None:
                        __type.append('dorm' + str(_idx))
                    planned_index.append(_idx)
                    __room = self.op_data.operators[x].room
                    if __room not in __plan.keys():
                        __plan[__room] = ['Current'] * len(self.currentPlan[__room])
                    __plan[__room][self.op_data.operators[x].index] = x
                if __time < datetime.now(): __time = datetime.now()
                self.tasks.append({"type": ','.join(__type), 'plan': __plan, 'time': __time})
            # 如果非 rest in full， 则同组取时间最小值
            else:
                if dorm.time is not None and dorm.time < _time:
                    _time = dorm.time
                __room = self.op_data.operators[_name].room
                __rest_agent = []
                if self.op_data.operators[_name].group == "":
                    __rest_agent.append(_name)
                else:
                    __rest_agent.extend(self.op_data.groups[self.op_data.operators[_name].group])
                for x in __rest_agent:
                    if x in low_priority:
                        continue
                    __room = self.op_data.operators[x].room
                    if __room not in _plan.keys():
                        _plan[__room] = ['Current'] * len(self.currentPlan[__room])
                    _plan[__room][self.op_data.operators[x].index] = x
                    _dorm_idx, __dorm = self.op_data.get_dorm_by_name(x)
                    if __dorm is not None:
                        _type.append('dorm' + str(_dorm_idx))
                        planned_index.append(_dorm_idx)
                        if __dorm.time is not None and __dorm.time < _time and self.op_data.operators[
                            x].resting_priority == 'high':
                            _time = __dorm.time
                    if x not in low_priority:
                        low_priority.append(x)
                # 生成单个任务
        if len(_plan.items()) > 0:
            _time -= timedelta(minutes=8)
            if _time < datetime.now(): _time = datetime.now()
            self.tasks.append({"type": ','.join(_type), 'plan': _plan,
                               'time': _time if not short_rest else (datetime.now() + timedelta(hours=0.5))})


    def infra_main(self):
        """ 位于基建首页 """
        if self.find('control_central') is None:
            self.back()
            return
        if self.task is not None:
            try:
                if len(self.task["plan"].keys()) > 0:
                    metadata = None
                    if 'metadata' in self.task.keys():
                        metadata = self.task['metadata']
                    self.agent_arrange(self.task["plan"], metadata)
                    if metadata is not None:
                        self.plan_metadata()
                # 如果任务名称包含干员名,则为动态生成的
                elif 'type' in self.task.keys() and self.task['type'].split(',')[0] in agent_list:
                    self.overtake_room()
                del self.tasks[0]
            except Exception as e:
                logger.exception(e)
                self.skip()
                self.error = True
            self.task = None
        elif not self.planned:
            try:
                # 如果有任何type 则会最后修正
                if self.read_mood:
                    mood_result = self.agent_get_mood(True)
                    if mood_result is not None:
                        return True
                self.plan_solver()
            except Exception as e:
                # 重新扫描
                self.error = True
                logger.exception({e})
            self.planned = True
        elif not self.todo_task:
            notification = detector.infra_notification(self.recog.img)
            if self.drone_room is not None:
                if self.drone_time is None or self.drone_time < datetime.now()- timedelta(hours=self.drone_execution_gap):
                    self.drone(self.drone_room)
                    logger.info(f"记录本次无人机使用时间为:{datetime.now()}")
                    self.drone_time = datetime.now()
            if self.party_time is None:
                self.clue()
            if notification is None:
                self.sleep(1)
                notification = detector.infra_notification(self.recog.img)
            if notification is not None:
                self.tap(notification)
            else:
                self.todo_task = True
        else:
            return self.handle_error()

    def agent_get_mood(self, skip_dorm=False, force=False):
        # 如果5分钟之内有任务则跳过心情读取
        if not force and next((k for k in self.tasks if k['time'] < datetime.now() + timedelta(seconds=300)),
                              None) is not None:
            logger.info('有未完成的任务，跳过纠错')
            self.skip()
            return
        logger.info('基建：记录心情')
        need_read = set(v.room for k, v in self.op_data.operators.items() if v.need_to_refresh())
        for room in need_read:
            error_count = 0
            while True:
                try:
                    self.enter_room(room)
                    self.current_base[room] = self.get_agent_from_room(room)
                    logger.info(f'房间 {room} 心情为：{self.current_base[room]}')
                    break
                except Exception as e:
                    if error_count > 3: raise e
                    logger.error(e)
                    error_count += 1
                    self.back()
                    continue
            self.back()
        logger.debug(self.op_data.print())
        for room in self.currentPlan.keys():
            for idx, item in enumerate(self.currentPlan[room]):
                _name = next((k for k, v in self.op_data.operators.items() if
                              v.current_room == room and v.current_index == idx),
                             None)
                if room not in self.current_base.keys():
                    self.current_base[room] = [''] * len(self.currentPlan[room])
                if _name is None or _name == '':
                    self.current_base[room][idx] = {"agent": "", "mood": -1}
                else:
                    self.current_base[room][idx] = {"mood": self.op_data.operators[_name].mood, "agent": _name}
        current_base = copy.deepcopy(self.current_base)
        plan = self.currentPlan
        fix_plan = {}
        for key in current_base:
            if key == 'train': continue
            need_fix = False
            for idx, operator in enumerate(current_base[key]):
                data = current_base[key][idx]
                # 如果是空房间
                if data["agent"] == '':
                    if not need_fix:
                        fix_plan[key] = ['Current'] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx]["agent"]
                    continue
                # 随意人员则跳过
                _name = data['agent']
                if plan[key][idx]["agent"] == 'Free':
                    continue
                if not (_name == plan[key][idx]['agent'] or (
                        (_name in plan[key][idx]["replacement"]) and len(plan[key][idx]["replacement"]) > 0) or not
                        self.op_data.operators[_name].need_to_refresh()):
                    if not need_fix:
                        fix_plan[key] = ['Current'] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx]["agent"]
        # 最后如果有任何高效组心情没有记录 或者高效组在宿舍
        miss_list = {k: v for (k, v) in self.op_data.operators.items() if v.not_valid()}
        if len(miss_list.keys()) > 0:
            # 替换到他应该的位置
            logger.debug(f"高效组心情没有记录{str(miss_list)}")
            for key in miss_list:
                _agent = miss_list[key]
                if _agent.group != '' and _agent.current_room.startswith("dorm"):
                    # 如果还有其他小组成员在休息且没满心情则忽略
                    if next((k for k, v in self.op_data.operators.items() if
                             v.group == _agent.group and not v.not_valid() and v.current_room.startswith(
                                 "dorm")), None) is not None:
                        continue
                elif _agent.group != '':
                    # 把所有小组成员都移到工作站
                    agents = self.op_data.groups[_agent.group]
                    for a in agents:
                        __agent = self.op_data.operators[a]
                        if __agent.room not in fix_plan.keys():
                            fix_plan[__agent.room] = ['Current'] * len(self.currentPlan[__agent.room])
                        fix_plan[__agent.room][__agent.index] = a
                if _agent.room not in fix_plan.keys():
                    fix_plan[_agent.room] = ['Current'] * len(self.currentPlan[_agent.room])
                fix_plan[_agent.room][_agent.index] = key
                # 如果是错位：
                if (_agent.current_index != -1 and _agent.current_index != _agent.index) or (_agent.current_room !=""and _agent.room != _agent.current_room):
                    moved_room = _agent.current_room
                    moved_index = _agent.current_index
                    if moved_room not in fix_plan.keys():
                        fix_plan[moved_room] = ['Current'] * len(self.currentPlan[moved_room])
                    fix_plan[moved_room][moved_index] = self.currentPlan[moved_room][moved_index]["agent"]
        if len(fix_plan.keys()) > 0:
            # 不能在房间里安排同一个人 如果有重复则换成Free
            # 还要修复确保同一组在同时上班
            fix_agents = []
            remove_keys = []
            logger.debug(f"Fix_plan {str(fix_plan)}")
            for key in fix_plan:
                if 'dormitory' in key:
                    # 如果宿舍差Free干员  则跳过
                    if next((e for e in fix_plan[key] if e not in ['Free', 'Current']),
                            None) is None and skip_dorm:
                        remove_keys.append(key)
                        continue
            if len(remove_keys) > 0:
                for item in remove_keys:
                    del fix_plan[item]
            if len(fix_plan.keys()) > 0:
                self.tasks.append({"plan": fix_plan, "time": datetime.now()})
                logger.info(f'纠错任务为-->{fix_plan}')
                return "self_correction"

    def plan_solver(self):
        plan = self.currentPlan
        # 如果下个 普通任务 <10 分钟则跳过 plan
        if (
                next((e for e in self.tasks if e['time'] < datetime.now() + timedelta(seconds=600)),
                     None)) is not None:
            return
        if len(self.check_in_and_out()) > 0:
            # 处理龙舌兰和但书的插拔
            for room in self.check_in_and_out():
                if any(room in obj["plan"].keys() and 'type' not in obj.keys() for obj in self.tasks): continue;
                in_out_plan = {}
                in_out_plan[room] = ['Current'] * len(plan[room])
                for idx, x in enumerate(plan[room]):
                    if '但书' in x['replacement'] or '龙舌兰' in x['replacement']:
                        in_out_plan[room][idx] = x['replacement'][0]
                self.tasks.append({"time": self.get_run_roder_time(room), "plan": in_out_plan})
        # 准备数据
        logger.debug(self.op_data.print())
        if self.read_mood:
            # 根据剩余心情排序
            self.total_agent = list(
                v for k, v in self.op_data.operators.items() if v.is_high() and not v.room.startswith('dorm'))
            self.total_agent.sort(key=lambda x: x.mood - x.lower_limit, reverse=False)
            # 目前有换班的计划后面改
            logger.debug(f'当前基地数据--> {self.total_agent}')
            fia_plan, fia_room = self.check_fia()
            if fia_room is not None and fia_plan is not None:
                if not any(fia_room in obj["plan"].keys() and len(obj["plan"][fia_room]) == 2 for obj in self.tasks):
                    fia_idx = self.op_data.operators['菲亚梅塔'].current_index if self.op_data.operators[
                                                                                  '菲亚梅塔'].current_index != -1 else \
                        self.op_data.operators['菲亚梅塔'].index
                    result = [{}] * (fia_idx + 1)
                    result[fia_idx]['time'] = datetime.now()
                    if self.op_data.operators["菲亚梅塔"].mood != 24:
                        self.enter_room(fia_room)
                        result = self.get_agent_from_room(fia_room, [fia_idx])
                        self.back()
                    logger.info('下一次进行菲亚梅塔充能：' + result[fia_idx]['time'].strftime("%H:%M:%S"))
                    self.tasks.append({"time": result[fia_idx]['time'], "plan": {fia_room: [
                        next(obj for obj in self.total_agent if obj.name in fia_plan).name,
                        "菲亚梅塔"]}})
            try:
                # 自动生成任务
                self.plan_metadata()
                # 剩余高效组位置
                high_free = self.op_data.available_free(count=self.max_resting_count)
                # 剩余低效位置
                low_free = self.op_data.available_free('low', count=self.max_resting_count)
                _replacement = []
                _plan = {}
                for op in self.total_agent:
                    # 忽略掉菲亚梅塔充能的干员
                    if high_free == 0 or low_free == 0:
                        break
                    if fia_room is not None and op.name in self.op_data.operators['菲亚梅塔'].replacement:
                        continue
                    # 忽略掉正在休息的
                    if op.current_room.startswith("dorm") or op.current_room in ['factory']:
                        continue
                    # 忽略掉心情值没低于上限的的
                    if op.mood > int((op.upper_limit - op.lower_limit) * self.resting_treshhold + op.lower_limit):
                        continue
                    if op.name in self.op_data.exhaust_agent:
                        if op.mood <= 2:
                            if next((e for e in self.tasks if 'type' in e.keys() and op.name in e['type']),
                                    None) is None:
                                self.enter_room(op.current_room)
                                result = self.get_agent_from_room(op.current_room, [op.current_index])
                                _time = datetime.now()
                                if result[op.current_index]['time'] is not None:
                                    _time = result[op.current_index]['time']
                                self.back()
                                # plan 是空的是因为得动态生成
                                exhaust_type = op.name
                                if op.group != '':
                                    exhaust_type = ','.join(self.op_data.groups[op.group])
                                if _time<datetime.now() and op.mood>0:
                                    continue
                                elif _time >= datetime.now() or (_time<datetime.now() and op.mood==0):
                                    self.tasks.append({"time": _time,"plan": {}, "type": exhaust_type})
                                    # 防止和其他排班冲突
                                    if _time<datetime.now() and op.mood==0:
                                        break
                        continue
                    if op.group != '':
                        # 如果在group里则同时上下班
                        group_resting = self.op_data.groups[op.group]
                        _replacement, _plan, high_free, low_free = self.get_resting_plan(
                            group_resting, _replacement, _plan, high_free, low_free)
                    else:
                        _replacement, _plan, high_free, low_free = self.get_resting_plan([op.name],
                                                                                         _replacement,
                                                                                         _plan,
                                                                                         high_free,
                                                                                         low_free)
                if len(_plan.keys()) > 0:
                    self.tasks.append({'plan': _plan, 'time': datetime.now(),
                                       'metadata': {}})
            except Exception as e:
                logger.exception(e)
                # 如果下个 普通任务 >5 分钟则补全宿舍
            logger.debug('tasks:'+str(self.tasks))
            if (next((e for e in self.tasks if e['time'] < datetime.now() + timedelta(seconds=300)),
                     None)) is None:
                self.agent_get_mood()

    def get_resting_plan(self, agents, exist_replacement, plan, high_free, low_free):
        _low, _high = 0, 0
        __replacement = []
        __plan = {}
        for x in agents:
            if self.op_data.operators[x].resting_priority == 'low':
                _low += 1
            else:
                _high += 1
        # 排序
        agents.sort(key=lambda x: self.op_data.operators[x].mood)
        # 进行位置数量的初步判定
        # 对于252可能需要进行额外判定，由于 low_free 性质等同于 high_free
        success = True
        if high_free - _high >= 0 and low_free - _low >= 0:
            for agent in agents:
                if not success:
                    break
                x = self.op_data.operators[agent]
                _rep = next((obj for obj in x.replacement if (not (
                        self.op_data.operators[obj].current_room != '' and not self.op_data.operators[
                    obj].current_room.startswith('dormitory'))) and obj not in ['但书',
                                                                                '龙舌兰'] and obj not in exist_replacement and obj not in __replacement),
                            None)
                if _rep is not None:
                    __replacement.append(_rep)
                    if x.room not in __plan.keys():
                        __plan[x.room] = ['Current'] * len(self.currentPlan[x.room])
                    __plan[x.room][x.index] = _rep
                else:
                    success = False
            if success:
                # 记录替换组
                exist_replacement.extend(__replacement)
                for x in agents:
                    _dorm = self.op_data.assign_dorm(x)
                    if _dorm.position[0] not in plan.keys():
                        plan[_dorm.position[0]] = ['Current'] * 5
                    plan[_dorm.position[0]][_dorm.position[1]] = _dorm.name
                for k, v in __plan.items():
                    if k not in plan.keys():
                        plan[k] = __plan[k]
                    for idx, name in enumerate(__plan[k]):
                        if plan[k][idx] == 'Current' and name != 'Current':
                            plan[k][idx] = name
        else:
            success = False
        if not success:
            _high, _low = 0, 0
        return exist_replacement, plan, high_free - _high, low_free - _low

    def initialize_operators(self):
        plan = self.currentPlan
        self.op_data = Operators(self.agent_base_config, self.max_resting_count)
        for room in plan.keys():
            for idx, data in enumerate(plan[room]):
                self.op_data.add(Operator(data["agent"], room, idx, data["group"], data["replacement"], 'high',
                                          operator_type="high"))
                # 菲亚梅塔替换组做特例判断
                if "replacement" in data.keys() and data["agent"] != '菲亚梅塔':
                    for _replacement in data["replacement"]:
                        self.op_data.add(Operator(_replacement, ""))
        dorm_names = [k for k in plan.keys() if k.startswith("dorm")]
        dorm_names.sort(key=lambda x: x, reverse=False)
        added = []
        # 竖向遍历出效率高到低
        for dorm in dorm_names:
            for _idx, _dorm in enumerate(plan[dorm]):
                if _dorm['agent'] == 'Free' and (dorm + str(_idx)) not in added and len(added) < self.max_resting_count:
                    self.op_data.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
                    break
        # VIP休息位用完后横向遍历
        for dorm in dorm_names:
            for _idx, _dorm in enumerate(plan[dorm]):
                if _dorm['agent'] == 'Free' and (dorm + str(_idx)) not in added:
                    self.op_data.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
        # low_free 的排序
        self.op_data.dorm[self.max_resting_count:len(self.op_data.dorm)] = sorted(
            self.op_data.dorm[self.max_resting_count:len(self.op_data.dorm)],
            key=lambda k: (k.position[0], k.position[1]), reverse=True)

    def check_in_and_out(self):
        res = {}
        for x, y in self.currentPlan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                res[x] = y
        return res

    def check_fia(self):
        if '菲亚梅塔' in self.op_data.operators.keys() and self.op_data.operators['菲亚梅塔'].room.startswith('dormitory'):
            return self.op_data.operators['菲亚梅塔'].replacement, self.op_data.operators['菲亚梅塔'].room
        return None, None

    def get_run_roder_time(self, room):
        logger.info('基建：读取插拔时间')
        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        error_count = 0
        while self.find('bill_accelerate') is None:
            if error_count > 5:
                raise Exception('未成功进入无人机界面')
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=1)
            error_count += 1
        execute_time = self.double_read_time((int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404),
                                              int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)))
        execute_time = execute_time - timedelta(seconds=(60*self.run_order_delay))
        logger.info('下一次进行插拔的时间为：' + execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)
        return execute_time

    def double_read_time(self, cord, upperLimit=None):
        if upperLimit is not None and upperLimit < 36000:
            upperLimit = 36000
        self.recog.update()
        time_in_seconds = self.read_time(cord, upperLimit)
        if time_in_seconds is None:
            return datetime.now()
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds))
        return execute_time

    def initialize_paddle(self):
        global ocr
        if ocr is None:
            ocr = PaddleOCR(enable_mkldnn=True, use_angle_cls=False)

    def read_screen(self, img, type="mood", limit=24, cord=None, change_color=False):
        if cord is not None:
            img = img[cord[1]:cord[3], cord[0]:cord[2]]
        if 'mood' in type or type == "time":
            # 心情图片太小，复制8次提高准确率
            for x in range(0, 4):
                img = cv2.vconcat([img, img])
        if change_color: img[img == 137] = 255
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
            if len(line_conf) == 0 and 'mood' in type: return -1
            x = [i[0] for i in line_conf]
            __str = max(set(x), key=x.count)
            print(__str)
            if "mood" in type:
                if '.' in __str:
                    __str = __str.replace(".", "")
                number = int(__str[0:__str.index('/')])
                return number
            elif 'time' in type:
                if '.' in __str:
                    __str = __str.replace(".", ":")
            return __str
        except Exception as e:
            logger.exception(e)
            return limit

    def read_time(self, cord, upperlimit, error_count=0):
        # 刷新图片
        self.recog.update()
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
                return self.read_time(cord, upperlimit, error_count + 1)

    def todo_list(self) -> None:
        """ 处理基建 Todo 列表 """
        tapped = False
        trust = self.find('infra_collect_trust')
        if trust is not None:
            logger.info('基建：干员信赖')
            self.tap(trust)
            tapped = True
        bill = self.find('infra_collect_bill')
        if bill is not None:
            logger.info('基建：订单交付')
            self.tap(bill)
            tapped = True
        factory = self.find('infra_collect_factory')
        if factory is not None:
            logger.info('基建：可收获')
            self.tap(factory)
            tapped = True
        if not tapped:
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95))
            self.todo_task = True

    def clue(self) -> None:
        # 一些识别时会用到的参数
        global x1, x2, x3, x4, y0, y1, y2
        x1, x2, x3, x4 = 0, 0, 0, 0
        y0, y1, y2 = 0, 0, 0

        logger.info('基建：线索')

        # 进入会客室
        self.enter_room('meeting')

        # 点击线索详情
        self.tap((self.recog.w * 0.1, self.recog.h * 0.9), interval=3)

        # 如果是线索交流的报告则返回
        self.find('clue_summary') and self.back()

        # 识别右侧按钮
        (x0, y0), (x1, y1) = self.find('clue_func', strict=True)

        logger.info('接收线索')
        self.tap(((x0 + x1) // 2, (y0 * 3 + y1) // 4), interval=3, rebuild=False)
        self.tap((self.recog.w - 10, self.recog.h - 10), interval=3, rebuild=False)
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3, rebuild=False)

        logger.info('领取会客室线索')
        self.tap(((x0 + x1) // 2, (y0 * 5 - y1) // 4), interval=3)
        obtain = self.find('clue_obtain')
        if obtain is not None and self.get_color(self.get_pos(obtain, 0.25, 0.5))[0] < 20:
            self.tap(obtain, interval=2)
            if self.find('clue_full') is not None:
                self.back()
        else:
            self.back()

        logger.info('放置线索')
        clue_unlock = self.find('clue_unlock')
        if clue_unlock is not None:
            # 当前线索交流未开启
            self.tap_element('clue', interval=3)

            # 识别阵营切换栏
            self.recog_bar()

            # 点击总览
            self.tap(((x1 * 7 + x2) // 8, y0 // 2), rebuild=False)

            # 获得和线索视图相关的数据
            self.recog_view(only_y2=False)

            # 检测是否拥有全部线索
            get_all_clue = True
            for i in range(1, 8):
                # 切换阵营
                self.tap(self.switch_camp(i), rebuild=False)

                # 清空界面内被选中的线索
                self.clear_clue_mask()

                # 获得和线索视图有关的数据
                self.recog_view()

                # 检测该阵营线索数量为 0
                if len(self.ori_clue()) == 0:
                    logger.info(f'无线索 {i}')
                    get_all_clue = False
                    break

            # 检测是否拥有全部线索
            if get_all_clue:
                for i in range(1, 8):
                    # 切换阵营
                    self.tap(self.switch_camp(i), rebuild=False)

                    # 获得和线索视图有关的数据
                    self.recog_view()

                    # 放置线索
                    logger.info(f'放置线索 {i}')
                    self.tap(((x1 + x2) // 2, y1 + 3), rebuild=False)

            # 返回线索主界面
            self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3, rebuild=False)

        # 线索交流开启
        if clue_unlock is not None and get_all_clue:
            self.tap(clue_unlock)
            self.party_time = datetime.now() + timedelta(days=1)
            logger.info("为期一天的趴体开始")
        elif clue_unlock is None:
            # 记录趴体时间
            self.back(interval=2)
            self.party_time = self.double_read_time((1765, 422, 1920, 515))
            logger.info(f"趴体结束时间为： {self.party_time}")
        else:
            self.back(interval=2)
        logger.info('返回基建主界面')
        self.back(interval=2)

    def switch_camp(self, id: int) -> tuple[int, int]:
        """ 切换阵营 """
        x = ((id + 0.5) * x2 + (8 - id - 0.5) * x1) // 8
        y = (y0 + y1) // 2
        return x, y

    def recog_bar(self) -> None:
        """ 识别阵营选择栏 """
        global x1, x2, y0, y1

        (x1, y0), (x2, y1) = self.find('clue_nav', strict=True)
        while int(self.recog.img[y0, x1 - 1].max()) - int(self.recog.img[y0, x1].max()) <= 1:
            x1 -= 1
        while int(self.recog.img[y0, x2].max()) - int(self.recog.img[y0, x2 - 1].max()) <= 1:
            x2 += 1
        while abs(int(self.recog.img[y1 + 1, x1].max()) - int(self.recog.img[y1, x1].max())) <= 1:
            y1 += 1
        y1 += 1

        logger.debug(f'recog_bar: x1:{x1}, x2:{x2}, y0:{y0}, y1:{y1}')

    def recog_view(self, only_y2: bool = True) -> None:
        """ 识别另外一些和线索视图有关的数据 """
        global x1, x2, x3, x4, y0, y1, y2

        # y2: 线索底部
        y2 = self.recog.h
        while self.recog.img[y2 - 1, x1:x2].ptp() <= 24:
            y2 -= 1
        if only_y2:
            logger.debug(f'recog_view: y2:{y2}')
            return y2
        # x3: 右边黑色 mask 边缘
        x3 = self.recog_view_mask_right()
        # x4: 用来区分单个线索
        x4 = (54 * x1 + 25 * x2) // 79

        logger.debug(f'recog_view: y2:{y2}, x3:{x3}, x4:{x4}')

    def recog_view_mask_right(self) -> int:
        """ 识别线索视图中右边黑色 mask 边缘的位置 """
        x3 = x2
        while True:
            max_abs = 0
            for y in range(y1, y2):
                max_abs = max(max_abs,
                              abs(int(self.recog.img[y, x3 - 1, 0]) - int(self.recog.img[y, x3 - 2, 0])))
            if max_abs <= 5:
                x3 -= 1
            else:
                break
        flag = False
        for y in range(y1, y2):
            if int(self.recog.img[y, x3 - 1, 0]) - int(self.recog.img[y, x3 - 2, 0]) == max_abs:
                flag = True
        if not flag:
            self.tap(((x1 + x2) // 2, y1 + 10), rebuild=False)
            x3 = x2
            while True:
                max_abs = 0
                for y in range(y1, y2):
                    max_abs = max(max_abs,
                                  abs(int(self.recog.img[y, x3 - 1, 0]) - int(self.recog.img[y, x3 - 2, 0])))
                if max_abs <= 5:
                    x3 -= 1
                else:
                    break
            flag = False
            for y in range(y1, y2):
                if int(self.recog.img[y, x3 - 1, 0]) - int(self.recog.img[y, x3 - 2, 0]) == max_abs:
                    flag = True
            if not flag:
                x3 = None
        return x3

    def get_clue_mask(self) -> None:
        """ 界面内是否有被选中的线索 """
        try:
            mask = []
            for y in range(y1, y2):
                if int(self.recog.img[y, x3 - 1, 0]) - int(self.recog.img[y, x3 - 2, 0]) > 20 and np.ptp(
                        self.recog.img[y, x3 - 2]) == 0:
                    mask.append(y)
            if len(mask) > 0:
                logger.debug(np.average(mask))
                return np.average(mask)
            else:
                return None
        except Exception as e:
            raise RecognizeError(e)

    def clear_clue_mask(self) -> None:
        """ 清空界面内被选中的线索 """
        try:
            while True:
                mask = False
                for y in range(y1, y2):
                    if int(self.recog.img[y, x3 - 1, 0]) - int(self.recog.img[y, x3 - 2, 0]) > 20 and np.ptp(
                            self.recog.img[y, x3 - 2]) == 0:
                        self.tap((x3 - 2, y + 1), rebuild=True)
                        mask = True
                        break
                if mask:
                    continue
                break
        except Exception as e:
            raise RecognizeError(e)

    def ori_clue(self):
        """ 获取界面内有多少线索 """
        clues = []
        y3 = y1
        status = -2
        for y in range(y1, y2):
            if self.recog.img[y, x4 - 5:x4 + 5].max() < 192:
                if status == -1:
                    status = 20
                if status > 0:
                    status -= 1
                if status == 0:
                    status = -2
                    clues.append(segment.get_poly(x1, x2, y3, y - 20))
                    y3 = y - 20 + 5
            else:
                status = -1
        if status != -2:
            clues.append(segment.get_poly(x1, x2, y3, y2))

        # 忽视一些只有一半的线索
        clues = [x.tolist() for x in clues if x[1][1] - x[0][1] >= self.recog.h / 5]
        logger.debug(clues)
        return clues

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
        self.tap(_room[0], interval=3)
        while self.find('control_central') is not None:
            self.tap(_room[0], interval=3)

    def drone(self, room: str, not_customize=False, not_return=False):
        logger.info('基建：无人机加速')
        all_in = 0
        if not not_customize:
            all_in = len(self.check_in_and_out())
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

        accelerate = self.find('factory_accelerate')
        if accelerate:
            drone_count = self.read_screen(self.recog.img, type='drone_mood', cord=(
                int(self.recog.w * 1150 / 1920), int(self.recog.h * 35 / 1080), int(self.recog.w * 1295 / 1920),
                int(self.recog.h * 72 / 1080)), limit=201)
            logger.info(f'当前无人机数量为：{drone_count}')
            if drone_count< self.drone_count_limit :
                logger.info(f"无人机数量小于{self.drone_count_limit}->停止")
                return
            logger.info('制造站加速')
            self.tap(accelerate)
            # self.tap_element('all_in')
            # 如果不是全部all in
            if all_in > 0:
                tap_times = drone_count - self.drone_count_limit  # 修改为无人机阈值
                _count = 0
                while _count < tap_times:
                    self.tap((self.recog.w * 0.7, self.recog.h * 0.5), interval=0.1, rebuild=False)
                    _count += 1
            else:
                self.tap_element('all_in')
            self.tap(accelerate, y_rate=1)
        else:
            accelerate = self.find('bill_accelerate')
            while accelerate:
                logger.info('贸易站加速')
                self.tap(accelerate)
                self.tap_element('all_in')
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8))
                while self.get_infra_scene() == Scene.CONNECTING:
                    self.sleep(3)
                if self.drone_room is not None:
                    break
                if not_customize:
                    drone_count = self.read_screen(self.recog.img, type='drone_mood', cord=(
                        int(self.recog.w * 1150 / 1920), int(self.recog.h * 35 / 1080), int(self.recog.w * 1295 / 1920),
                        int(self.recog.h * 72 / 1080)), limit=200)
                    logger.info(f'当前无人机数量为：{drone_count}')
                    self.recog.update()
                    self.recog.save_screencap('run_order')
                    # 200 为识别错误
                    if drone_count < self.drone_count_limit:
                        logger.info(f"无人机数量小于{self.drone_count_limit}->停止")
                        break
                st = accelerate[1]  # 起点
                ed = accelerate[0]  # 终点
                # 0.95, 1.05 are offset compensations
                self.swipe_noinertia(st, (ed[0] * 0.95 - st[0] * 1.05, 0), rebuild=True)
                accelerate = self.find('bill_accelerate')
        if not_return: return
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
                    self.tap((y[1][0]))
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
                self.sleep(3)
                return self.scan_agant(agent, error_count, max_agent_count)
            else:
                raise e

    def get_order(self, name):
        if (name in self.agent_base_config.keys()):
            if "ArrangeOrder" in self.agent_base_config[name].keys():
                return True, self.agent_base_config[name]["ArrangeOrder"]
            else:
                return False, self.agent_base_config["Default"]["ArrangeOrder"]
        return False, self.agent_base_config["Default"]["ArrangeOrder"]

    def detail_filter(self, turn_on, type="not_in_dorm"):
        logger.info(f'开始 {("打开" if turn_on else "关闭")} {type} 筛选')
        self.tap((self.recog.w * 0.95, self.recog.h * 0.05), interval=1)
        if type == "not_in_dorm":
            not_in_dorm = self.find('arrange_non_check_in', score=0.85)
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
            # 如果是宿舍且干员不为高效组，则改为Free 加速换班时间
            elif room.startswith('dorm'):
                if n not in self.op_data.operators.keys():
                    agents[idx] = 'Free'
                elif not self.op_data.operators[n].is_high():
                    agents[idx] = 'Free'
        agent = copy.deepcopy(agents)
        logger.info(f'安排干员 ：{agent}')
        # 若不是空房间，则清空工作中的干员
        is_dorm = room.startswith("dorm")
        h, w = self.recog.h, self.recog.w
        first_time = True
        # 在 agent 中 'Free' 表示任意空闲干员
        free_num = agent.count('Free')
        for i in range(agent.count("Free")):
            agent.remove("Free")
        index_change = False
        pre_order = [2, False]
        right_swipe = 0
        retry_count = 0
        # 如果重复进入宿舍则需要排序
        selected = []
        logger.info(f'上次进入房间为：{self.last_room},本次房间为：{room}')
        if self.last_room.startswith('dorm') and is_dorm:
            self.detail_filter(False)
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
                # 清空
                if is_dorm:
                    self.switch_arrange_order(3, "true")
                    pre_order = [3, 'true']
                self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
                changed, ret = self.scan_agant(agent)
                if changed:
                    selected.extend(changed)
                    if len(agent) == 0: break
                    index_change = True

            # 如果选中了人，则可能需要重新排序
            if index_change or first_time:
                # 第一次则调整
                is_custom, arrange_type = self.get_order(agent[0])
                if is_dorm and not (
                        agent[0] in self.op_data.operators.keys() and self.op_data.operators[agent[0]].room.startswith(
                    'dormitory')):
                    arrange_type = (3, 'true')
                # 如果重新排序则滑到最左边
                if pre_order[0] != arrange_type[0] or pre_order[1] != arrange_type[1]:
                    self.switch_arrange_order(arrange_type[0], arrange_type[1])
                    # 滑倒最左边
                    self.sleep(interval=0.5, rebuild=True)
                    right_swipe = self.swipe_left(right_swipe, w, h)
                    pre_order = arrange_type
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

        # 安排空闲干员
        if free_num:
            if free_num == len(agents):
                self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            if not first_time:
                # 滑动到最左边
                self.sleep(interval=0.5, rebuild=False)
                right_swipe = self.swipe_left(right_swipe, w, h)
            self.detail_filter(True)
            self.switch_arrange_order(3, "true")
            # 只选择在列表里面的
            # 替换组小于20才休息，防止进入就满心情进行网络连接
            free_list = [v.name for k, v in self.op_data.operators.items() if
                         v.name not in agents and v.operator_type != 'high']
            free_list.extend([_name for _name in agent_list if _name not in self.op_data.operators.keys()])
            free_list = list(set(free_list) - set(self.free_blacklist))
            while free_num:
                selected_name, ret = self.scan_agant(free_list, max_agent_count=free_num)
                selected.extend(selected_name)
                free_num -= len(selected_name)
                while len(selected_name) > 0:
                    agents[agents.index('Free')] = selected_name[0]
                    selected_name.remove(selected_name[0])
                if free_num == 0:
                    break
                else:
                    st = ret[-2][1][2]  # 起点
                    ed = ret[0][1][1]  # 终点
                    self.swipe_noinertia(st, (ed[0] - st[0], 0))
                    right_swipe += 1
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

    def get_agent_from_room(self, room, read_time_index=None):
        if read_time_index is None:
            read_time_index = []
        error_count = 0
        if room == 'meeting':
            time.sleep(3)
        while self.find('room_detail') is None:
            if error_count > 3:
                raise Exception('未成功进入房间')
            self.tap((self.recog.w * 0.05, self.recog.h * 0.4), interval=0.5)
            error_count += 1
        length = len(self.currentPlan[room])
        if length > 3: self.swipe((self.recog.w * 0.8, self.recog.h * 0.8), (0, self.recog.h * 0.4), interval=1,
                                  rebuild=True)
        name_p = [((1460, 155), (1700, 210)), ((1460, 370), (1700, 420)), ((1460, 585), (1700, 630)),
                  ((1460, 560), (1700, 610)), ((1460, 775), (1700, 820))]
        time_p = [((1650, 270, 1780, 305)), ((1650, 480, 1780, 515)), ((1650, 690, 1780, 725)),
                  ((1650, 665, 1780, 700)), ((1650, 875, 1780, 910))]
        mood_p = [((1685, 213, 1780, 256)), ((1685, 422, 1780, 465)), ((1685, 632, 1780, 675)),
                  ((1685, 612, 1780, 655)), ((1685, 822, 1780, 865))]
        result = []
        swiped = False
        for i in range(0, length):
            if i >= 3 and not swiped:
                self.swipe((self.recog.w * 0.8, self.recog.h * 0.8), (0, -self.recog.h * 0.4), interval=1, rebuild=True)
                swiped = True
            data = {}
            _name = character_recognize.agent_name(
                self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]], self.recog.h * 1.1)
            error_count = 0
            while i >= 3 and _name != '' and (
                    next((e for e in result if e['agent'] == _name), None)) is not None:
                logger.warning("检测到滑动可能失败")
                self.swipe((self.recog.w * 0.8, self.recog.h * 0.8), (0, -self.recog.h * 0.4), interval=1, rebuild=True)
                _name = character_recognize.agent_name(
                    self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]],
                    self.recog.h * 1.1)
                error_count += 1
                if error_count > 4:
                    raise Exception("超过出错上限")
            _mood = 24
            # 如果房间不为空
            if _name != '':
                if _name not in self.op_data.operators.keys() and _name in agent_list:
                    self.op_data.add(Operator(_name, ""))
                update_time=False
                if self.op_data.operators[_name].need_to_refresh():
                    _mood = self.read_screen(self.recog.img, cord=mood_p[i], change_color=True)
                    update_time = True
                else:
                    _mood = self.op_data.operators[_name].mood
                high_no_time = self.op_data.update_detail(_name, _mood, room, i,update_time)
                if high_no_time is not None:
                    logger.debug(f"检测到高效组休息时间数据不存在:{room},{high_no_time}")
                    read_time_index.append(high_no_time)
            else:
                _mood = -1
            data['agent'] = _name
            data['mood'] = _mood
            if i in read_time_index:
                if _mood in [24] or (_mood == 0 and not room.startswith('dorm')):
                    data['time'] = datetime.now()
                else:
                    upperLimit = 21600
                    if _name in ['菲亚梅塔'] or _name in self.op_data.exhaust_agent:
                        upperLimit = 43200
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

    def agent_arrange(self, plan: tp.BasePlan, metadata=None):
        logger.info('基建：排班')
        in_and_out = []
        fia_data = None
        rooms = list(plan.keys())
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
                    update_base = False
                    if ('但书' in plan[room] or '龙舌兰' in plan[room]) and not \
                            room.startswith('dormitory') and room not in in_and_out:
                        in_and_out.append(room)
                        update_base = True
                    if '菲亚梅塔' in plan[room] and len(plan[room]) == 2:
                        fia_data = (room, plan[room][0])
                        update_base = True
                    if update_base or 'Current' in plan[room]:
                        self.current_base[room] = self.get_agent_from_room(room)
                        # 纠错 因为网络连接导致房间移位
                        if 'Current' in plan[room]:
                            # replace current
                            for current_idx, _name in enumerate(plan[room]):
                                if _name == 'Current':
                                    current_name = self.current_base[room][current_idx]["agent"]
                                    if current_name in agent_list:
                                        plan[room][current_idx] = current_name
                                    else:
                                        # 如果空房间或者名字错误，则使用default干员
                                        plan[room][current_idx] = \
                                            self.currentPlan[room][current_idx]["agent"]
                    while self.find('arrange_order_options') is None:
                        if error_count > 3:
                            raise Exception('未成功进入干员选择界面')
                        self.tap((self.recog.w * 0.82, self.recog.h * 0.2), interval=1)
                        error_count += 1
                    self.choose_agent(plan[room], room)
                    self.recog.update()
                    self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
                    if self.get_infra_scene() == Scene.INFRA_ARRANGE_CONFIRM:
                        x0 = self.recog.w // 3 * 2  # double confirm
                        y0 = self.recog.h - 10
                        self.tap((x0, y0), rebuild=True)
                    read_time_index = []
                    if metadata is not None:
                        read_time_index = self.op_data.get_refresh_index(room, plan[room])
                    if fia_data is not None:
                        # 移除时间以刷新心情
                        self.op_data.operators['菲亚梅塔'].time_stamp = None
                        self.op_data.operators[fia_data[1]].time_stamp = None
                    current = self.get_agent_from_room(room, read_time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]['agent'] != name:
                            logger.error(f'检测到的干员{current[idx]["agent"]},需要安排的干员{name}')
                            raise Exception('检测到安排干员未成功')
                    finished = True
                    # 如果完成则移除该任务
                    del plan[room]
                    # back to 基地主界面
                    while self.scene() == Scene.CONNECTING:
                        self.sleep(3)
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
        if len(in_and_out) > 0:
            replace_plan = {}
            for room in in_and_out:
                logger.info("开始插拔")
                self.drone(room, True, True)
                in_and_out_plan = [data["agent"] for data in self.current_base[room]]
                # 防止由于意外导致的死循环
                if '但书' in in_and_out_plan or '龙舌兰' in in_and_out_plan:
                    in_and_out_plan = [data["agent"] for data in self.currentPlan[room]]
                replace_plan[room] = in_and_out_plan
                self.back(interval=0.5)
                self.back(interval=0.5)
            self.tasks.append({'time': self.tasks[0]['time'], 'plan': replace_plan})
            self.skip()
        if fia_data is not None:
            replace_agent = fia_data[1]
            fia_change_room = self.op_data.operators[replace_agent].room
            fia_room_plan = [data["agent"] for data in self.current_base[fia_data[0]]]
            fia_change_room_plan = ['Current'] * len(self.currentPlan[fia_change_room])
            fia_change_room_plan[self.op_data.operators[replace_agent].index] = replace_agent
            self.tasks.append(
                {'time': self.tasks[0]['time'],
                 'plan': {fia_data[0]: fia_room_plan, fia_change_room: fia_change_room_plan}})
            # 急速换班
            self.skip()
        logger.info('返回基建主界面')

    def skip(self):
        self.todo_task = True
        self.planned = True

    @Asst.CallBackType
    def log_maa(msg, details, arg):
        m = Message(msg)
        d = json.loads(details.decode('utf-8'))
        logger.debug(d)
        logger.debug(m)
        logger.debug(arg)

    def inialize_maa(self):
        # 若需要获取详细执行信息，请传入 callback 参数
        # 例如 asst = Asst(callback=my_callback)
        Asst.load(path=self.maa_config['maa_path'])
        self.MAA = Asst(callback=self.log_maa)
        # self.MAA.set_instance_option(2, 'maatouch')
        # 请自行配置 adb 环境变量，或修改为 adb 可执行程序的路径
        # logger.info(self.device.client.device_id)
        if self.MAA.connect(self.maa_config['maa_adb_path'], self.device.client.device_id):
            logger.info("MAA 连接成功")
        else:
            logger.info("MAA 连接失败")
            raise Exception("MAA 连接失败")

    def maa_plan_solver(self):

        try:
            if self.maa_config['last_execution'] is not None and datetime.now() - timedelta(
                    seconds=self.maa_config['maa_execution_gap'] * 3600) < self.maa_config['last_execution']:
                logger.info("间隔未超过设定时间，不启动maa")
            else:
                self.send_email('启动MAA')
                self.back_to_index()
                # 任务及参数请参考 docs/集成文档.md
                self.inialize_maa()
                self.MAA.append_task('StartUp')
                _plan = self.maa_config['weekly_plan'][get_server_weekday()]
                logger.info(f"现在服务器是{_plan['weekday']}")
                fights = []
                for stage in _plan["stage"]:
                    logger.info(f"添加关卡:{stage}")
                    self.MAA.append_task('Fight', {
                        # 空值表示上一次
                        # 'stage': '',
                        'stage': stage,
                        'medicine': _plan["medicine"],
                        'stone': 0,
                        'times': 999,
                        'report_to_penguin': True,
                        'client_type': '',
                        'penguin_id': '',
                        'DrGrandet': False,
                        'server': 'CN'
                    })
                    fights.append(stage)
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
                self.MAA.append_task('Visit')
                self.MAA.append_task('Mall', {
                    'shopping': True,
                    'buy_first': ['龙门币', '赤金'],
                    'blacklist': ['家具', '碳', '加急'],
                    'credit_fight': fights[len(fights) - 1] != ''
                })
                self.MAA.append_task('Award')
                # asst.append_task('Copilot', {
                #     'stage_name': '千层蛋糕',
                #     'filename': './GA-EX8-raid.json',
                #     'formation': False

                # })
                self.MAA.start()
                logger.info(f"MAA 启动")
                hard_stop = False
                while self.MAA.running():
                    # 5分钟之前就停止
                    if (self.tasks[0]["time"] - datetime.now()).total_seconds() < 300:
                        self.MAA.stop()
                        hard_stop = True
                    else:
                        time.sleep(0)
                self.send_email('MAA停止')
                if hard_stop:
                    logger.info(f"由于maa任务并未完成，等待3分钟重启软件")
                    time.sleep(180)
                    self.device.exit(self.package_name)
                else:
                    logger.info(f"记录MAA 本次执行时间")
                    self.maa_config['last_execution'] = datetime.now()
                    logger.info(self.maa_config['last_execution'])
            if self.maa_config['roguelike'] or self.maa_config['reclamation_algorithm'] or self.maa_config[
                'stationary_security_service']:
                while (self.tasks[0]["time"] - datetime.now()).total_seconds() > 30:
                    self.MAA = None
                    self.inialize_maa()
                    if self.maa_config['roguelike']:
                        self.MAA.append_task('Roguelike', {
                            'mode': 0,
                            'starts_count': 9999999,
                            'investment_enabled': True,
                            'investments_count': 9999999,
                            'stop_when_investment_full': False,
                            'squad': '指挥分队',
                            'roles': '取长补短',
                            'theme': 'Mizuki',
                            'core_char': '海沫'
                        })
                    elif self.maa_config['reclamation_algorithm']:
                        self.back_to_maa_config['reclamation_algorithm']()
                        self.MAA.append_task('ReclamationAlgorithm')
                    # elif self.maa_config['stationary_security_service'] :
                    #     self.MAA.append_task('SSSCopilot', {
                    #         'filename': "F:\\MAA-v4.10.5-win-x64\\resource\\copilot\\SSS_阿卡胡拉丛林.json",
                    #         'formation': False,
                    #         'loop_times':99
                    #     })
                    self.MAA.start()
                    while self.MAA.running():
                        if (self.tasks[0]["time"] - datetime.now()).total_seconds() < 30:
                            self.MAA.stop()
                            break
                        else:
                            time.sleep(0)
                    self.device.exit(self.package_name)
            # 生息演算逻辑 结束
            remaining_time = (self.tasks[0]["time"] - datetime.now()).total_seconds()
            subject = f"开始休息 {'%.2f' % (remaining_time / 60)} 分钟，到{self.tasks[0]['time'].strftime('%H:%M:%S')}"
            context = f"下一次任务:{self.tasks[0]['plan']}"
            logger.info(context)
            logger.info(subject)
            self.send_email(context, subject)
            time.sleep(remaining_time)
            self.MAA = None
        except Exception as e:
            logger.error(e)
            self.MAA = None
            remaining_time = (self.tasks[0]["time"] - datetime.now()).total_seconds()
            if remaining_time > 0:
                logger.info(f"开始休息 {'%.2f' % (remaining_time / 60)} 分钟，到{self.tasks[0]['time'].strftime('%H:%M:%S')}")
                time.sleep(remaining_time)
            self.device.exit(self.package_name)

    def send_email(self, context, subject=''):
        if 'mail_enable' in self.email_config.keys() and self.email_config['mail_enable'] == 0:
            logger.info('邮件功能未开启')
            return
        try:
            msg = MIMEMultipart()
            msg.attach(MIMEText(str(context), 'plain', 'utf-8'))
            msg['Subject'] = self.email_config['subject'] + (str(subject) if subject else '')
            msg['From'] = self.email_config['account']
            s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10.0)
            # 登录邮箱
            s.login(self.email_config['account'], self.email_config['pass_code'])
            # 开始发送
            s.sendmail(self.email_config['account'], self.email_config['receipts'], msg.as_string())
            logger.info("邮件发送成功")
        except Exception as e:
            logger.error("邮件发送失败")
            logger.exception(e)
