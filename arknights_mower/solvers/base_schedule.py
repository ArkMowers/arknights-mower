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

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

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
        self.todo_task = False
        self.planned = False
        if len(self.operators.keys()) == 0:
            self.get_agent()
        if len(self.scan_time.keys()) == 0:
            self.scan_time = {k: None for k, v in self.currentPlan.items()}
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
        name = self.task['type']
        candidate = []
        if self.operators[name]['group'] != '':
            candidate.extend([v['name'] for k, v in self.operators.items() if
                              'group' in v.keys() and v['group'] == self.operators[name]['group']])
        else:
            candidate.append(name)
        operators = []
        for i in candidate:
            _room = self.operators[name]['current_room']
            idx = [a['agent'] for a in self.current_base[_room]].index(i)
            operators.append({'agent': i, 'current_room': _room, 'room_index': idx})
            # if 'resting_priority' in self.operators[i].keys() and self.operators[i]['resting_priority']=='high':
            #     room_need+=1
        resting_dorm = []
        ignore = []
        if next((e for e in self.tasks if 'type' in e.keys() and e['type'].startswith("dorm")), None) is not None:
            # 出去需要休息满的人其他清空
            for task in [e for e in self.tasks if 'type' in e.keys() and e['type'].startswith("dorm")]:
                for k, v in task['plan'].items():
                    for a in v:
                        if a == "Current":
                            continue
                        elif 'exhaust_require' in self.operators[a].keys() and self.operators[a]['exhaust_require']:
                            ignore.append(a)
        resting_dorm.extend([self.operators[a]['current_room'] for a in ignore])
        # 执行全部任务
        for task in self.tasks:
            if 'type' in task.keys() and 'dorm' in task['type'] and 'plan' in task.keys():
                # TODO 移除 resting_room 的干员比如说有巫恋在休息
                self.agent_arrange(task['plan'])
                self.tasks.remove(task)
        self.get_swap_plan(resting_dorm, operators, False)
    def handle_error(self,force = False):
        # 如果有任何报错，则生成一个空
        if self.scene() == Scene.UNKNOWN:
            self.device.exit('com.hypergryph.arknights')
        if self.error or force:
            # 如果没有任何时间小于当前时间的任务才生成空任务
            if (next((e for e in self.tasks if e['time'] < datetime.now()), None)) is None:
                room = next(iter(self.currentPlan.keys()))
                logger.info("由于出现错误情况，生成一次空任务来执行纠错")
                self.tasks.append({'time': datetime.now(), 'plan': {room: ['Current'] * len(self.currentPlan[room])}})
            # 如果没有任何时间小于当前时间的任务-10分钟 则清空任务
            if (next((e for e in self.tasks if e['time'] < datetime.now() - timedelta(seconds=600)), None)) is not None:
                logger.info("检测到执行超过10分钟的任务，清空全部任务")
                self.tasks = []
                self.scan_time = {}
                self.operators = {}
        return True

    def plan_metadata(self, time_result):
        group_info = self.task['metadata']['plan']
        read_time_rooms = self.task['metadata']['room']
        if time_result is None:
            time_result = {}
        for key, _plan in group_info.items():
            if 'default' != key:
                _plan["time"] = time_result[_plan["type"]]
                self.tasks.append({"type": _plan['type'], 'plan': _plan['plan'], 'time': _plan['time']})
            else:
                # 合在一起则取最小恢复时间
                min_time = datetime.max
                __time = datetime.now()
                if len(self.task['metadata']['room']) == 0:
                    # 如果没有读取任何时间，则只休息1小时替换下一组
                    _plan["time"] = __time + timedelta(seconds=(3600))
                else:
                    for dorm in _plan["type"].split(','):
                        if dorm not in read_time_rooms:
                            continue
                        if dorm in time_result.keys() and min_time > time_result[dorm]:
                            min_time = time_result[dorm]
                    _plan["time"] = min_time
                # 如果有任何已有plan
                existing_plan = next(
                    (e for e in self.tasks if 'type' in e.keys() and e['type'].startswith('dormitory')), None)
                if existing_plan is not None and existing_plan['time'] < _plan["time"]:
                    for k in _plan['plan']:
                        if k not in existing_plan['plan']:
                            existing_plan['plan'][k] = _plan['plan'][k]
                        else:
                            for idx, _a in enumerate(_plan['plan'][k]):
                                if _plan['plan'][k][idx] != 'Current':
                                    existing_plan['plan'][k][idx] = _plan['plan'][k][idx]
                    existing_plan['type'] = existing_plan['type'] + ',' + _plan["type"]
                else:
                    self.tasks.append({"type": _plan['type'], 'plan': _plan['plan'], 'time': _plan['time']})

    def infra_main(self):
        """ 位于基建首页 """
        if self.find('control_central') is None:
            self.back()
            return
        if self.task is not None:
            try:
                if len(self.task["plan"].keys()) > 0:
                    read_time_room = []
                    if 'metadata' in self.task.keys():
                        read_time_room = self.task['metadata']['room']
                    time_result = self.agent_arrange(self.task["plan"], read_time_room)
                    if 'metadata' in self.task.keys():
                        self.plan_metadata(time_result)
                else:
                    self.overtake_room()
                del self.tasks[0]
            except Exception as e:
                logger.exception(e)
                self.planned = True
                self.todo_task = True
                self.error = True
            self.task = None
        elif not self.todo_task:
            # 处理基建 Todo
            notification = detector.infra_notification(self.recog.img)
            if notification is None:
                self.sleep(1)
                notification = detector.infra_notification(self.recog.img)
            if notification is not None:
                self.tap(notification)
            else:
                self.todo_task = True
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
        else:
            return self.handle_error()

    def get_plan(self, room, index=-1):
        # -1 就是不换人
        result = []
        for data in self.currentPlan[room]:
            result.append(data["agent"])
        return result

    def agent_get_mood(self,skip_dorm = False):
        # 如果5分钟之内有任务则跳过心情读取
        if next((k for k in self.tasks if k['time'] <datetime.now()+ timedelta(seconds=300)),None) is not None:
            logger.info('有未完成的任务，跳过纠错')
            return
        logger.info('基建：记录心情')
        need_read = set(list(k for k, v in self.scan_time.items() if not (v is not None and v > (
                datetime.now() - timedelta(seconds=5400)))))
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
        if '' in self.operators.keys(): self.operators['']['current_room'] = ''
        logger.info(self.operators)
        for room in self.currentPlan.keys():
            for idx, item in enumerate(self.currentPlan[room]):
                _name = next((k for k, v in self.operators.items() if
                              v['current_room'] == room and 'current_index' in v.keys() and v['current_index'] == idx),
                             None)
                if room not in self.current_base.keys():
                    self.current_base[room] = [''] * len(self.currentPlan[room])
                if _name is None or _name == '':
                    self.current_base[room][idx] = {"agent": "", "mood": -1}
                else:
                    self.current_base[room][idx] = {"mood": self.operators[_name]['mood'], "agent": _name}
        current_base = copy.deepcopy(self.current_base)
        plan = self.currentPlan
        self.total_agent = []
        fix_plan = {}
        for key in current_base:
            if (key == 'train'): continue
            need_fix = False
            for idx, operator in enumerate(current_base[key]):
                data = current_base[key][idx]
                # 如果是空房间
                if data["agent"] == '':
                    if not need_fix:
                        fix_plan[key] = [''] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx]["agent"]
                    continue
                if (data["agent"] in self.agent_base_config.keys()):
                    # 如果有设置下限，则减去下限值 eg: 令
                    if ("LowerLimit" in self.agent_base_config[current_base[key][idx]["agent"]]):
                        data["mood"] = data["mood"] - self.agent_base_config[current_base[key][idx]["agent"]]["LowerLimit"]
                # 把额外数据传过去
                data["current_room"] = key
                data["room_index"] = idx
                # 记录数据
                self.total_agent.append(data)
                # 随意人员则跳过
                if plan[key][idx]["agent"] == 'Free':
                    continue
                if not (data['agent'] == plan[key][idx]['agent'] or (
                        (data["agent"] in plan[key][idx]["replacement"]) and len(plan[key][idx]["replacement"]) > 0)):
                    if not need_fix:
                        fix_plan[key] = [''] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx]["agent"]
                elif need_fix:
                    fix_plan[key][idx] = data["agent"]
            # 检查是否有空名
            if need_fix:
                for idx, fix_agent in enumerate(fix_plan[key]):
                    if fix_plan[key][idx] == '':
                        # 则使用当前干员
                        fix_plan[key][idx] = 'Current'
        # 最后如果有任何高效组心情没有记录 或者高效组在宿舍
        miss_list = {k: v for (k, v) in self.operators.items() if
                     (v['type'] == 'high' and ('mood' not in v.keys() or (v['mood'] == -1 or (v['mood'] == 24) and v['current_room'].startswith('dormitory'))))}
        if len(miss_list.keys()) > 0:
            # 替换到他应该的位置
            for key in miss_list:
                if miss_list[key]['group'] != '':
                    # 如果还有其他小组成员没满心情则忽略
                    if next((k for k, v in self.operators.items() if
                             v['group'] == miss_list[key]['group'] and v['current_room'].startswith(
                                     'dormitory') and not (v['mood'] == -1 or v['mood'] == 24)), None) is not None:
                        continue
                if miss_list[key]['room'] not in fix_plan.keys():
                    fix_plan[miss_list[key]['room']] = [x['agent'] for x in current_base[miss_list[key]['room']]]
                fix_plan[miss_list[key]['room']][miss_list[key]['index']] = key
        if len(fix_plan.keys()) > 0:
            # 不能在房间里安排同一个人 如果有重复则换成Free
            # 还要修复确保同一组在同时上班
            fix_agents = []
            remove_keys = []
            for key in fix_plan:
                if skip_dorm and 'dormitory' in key:
                    remove_keys.append(key)
                for idx, fix_agent in enumerate(fix_plan[key]):
                    if fix_agent not in fix_agents:
                        fix_agents.append(fix_agent)
                    else:
                        fix_plan[key][idx] = "Free" if fix_plan[key][idx] not in ['Free', 'Current'] else \
                            fix_plan[key][idx]
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
        next((e for e in self.tasks if 'type' not in e.keys() and e['time'] < datetime.now() + timedelta(seconds=600)),
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
                self.tasks.append({"time": self.get_in_and_out_time(room), "plan": in_out_plan})
        # 准备数据
        if self.read_mood:
            # 根据剩余心情排序
            self.total_agent.sort(key=lambda x: x["mood"], reverse=False)
            # 目前有换班的计划后面改
            logger.info(f'当前基地数据--> {self.total_agent}')
            exclude_list = []
            fia_plan, fia_room = self.check_fia()
            if fia_room is not None and fia_plan is not None:
                exclude_list = copy.deepcopy(fia_plan)
                if not any(fia_room in obj["plan"].keys() and len(obj["plan"][fia_room]) == 2 for obj in self.tasks):
                    fia_idx = self.operators['菲亚梅塔']['index']
                    result = [{}]*(fia_idx+1)
                    result[fia_idx]['time'] =datetime.now()
                    if self.operators["菲亚梅塔"]["mood"] != 24:
                        self.enter_room(fia_room)
                        result = self.get_agent_from_room(fia_room, [fia_idx])
                        self.back()
                    logger.info('下一次进行菲亚梅塔充能：' + result[fia_idx]['time'].strftime("%H:%M:%S"))
                    self.tasks.append({"time": result[fia_idx]['time'], "plan": {fia_room: [
                        next(obj for obj in self.total_agent if obj["agent"] in fia_plan)["agent"],
                        "菲亚梅塔"]}})
                exclude_list.append("菲亚梅塔")
            try:
                exaust_rest = []
                if len(self.exaust_agent) > 0:
                    for _exaust in self.exaust_agent:
                        i = self.operators[_exaust]
                        if 'current_room' in i.keys() and i['current_room'].startswith('dormitory') and i[
                            'resting_priority'] == 'high' and next(
                                (k for k in self.tasks if 'type' in k.keys() and i['current_room'] in k["type"]),
                                None) is None:
                            exaust_rest.append(i['name'])
                        if _exaust not in exclude_list:
                            exclude_list.append(_exaust)
                # 如果exaust_agent<2 则读取
                logger.info(f'安排干员黑名单为：{exclude_list}')
                # 先计算需要休息满的人
                total_exaust_plan = []
                for agent in exaust_rest:
                    error_count = 0
                    time_result = None
                    # 读取时间
                    __index = self.operators[agent]['current_index']
                    while error_count < 3:
                        try:
                            self.enter_room(self.operators[agent]['current_room'])
                            time_result = self.get_agent_from_room(self.operators[agent]['current_room'],[__index])
                            if time_result is None:
                                raise Exception("读取时间失败")
                            else:
                                break
                        except Exception as e:
                            self.back_to_index()
                            if self.scene() == Scene.INDEX:
                                self.tap_element('index_infrastructure', interval=5)
                            self.recog.update()
                            logger.exception(e)
                            error_count += 1
                            continue
                    # 5分钟gap
                    time_result = time_result[__index]['time'] - timedelta(seconds=(300))
                    # 如果已经有现有plan 则比对时间
                    if next((k for k in total_exaust_plan if
                             next((k for k, v in k['plan'].items() if agent in v), None) is not None),
                            None) is not None:
                        _exaust_plan = next(
                            k for k in total_exaust_plan if next((k for k, v in k['plan'].items() if agent in v), None))
                        if self.operators[agent]['current_room'] not in _exaust_plan['type']:
                            _exaust_plan['type'] += ',' + self.operators[agent]['current_room']
                        if time_result > _exaust_plan['time']:
                            _exaust_plan['time'] = time_result
                        continue
                    exaust_plan = {'plan': {}, 'time': time_result, 'type': self.operators[agent]['current_room']}
                    # 如果有组，则生成小组上班 否则则单人上班
                    bundle = []
                    if self.operators[agent]['group'] != '':
                        bundle.extend([v['name'] for k, v in self.operators.items() if
                                       'group' in v.keys() and v['group'] == self.operators[agent]['group']])
                    else:
                        bundle.append(agent)
                    for planned in bundle:
                        if self.operators[planned]['room'] not in exaust_plan['plan']:
                            exaust_plan['plan'][self.operators[planned]['room']] = [
                                                                                       'Current'] * len(
                                self.currentPlan[self.operators[planned]['room']])
                        exaust_plan['plan'][self.operators[planned]['room']][
                            self.operators[planned]['index']] = planned
                    total_exaust_plan.append(exaust_plan)
                    self.back()
                self.tasks.extend(total_exaust_plan)
                resting_dorm = []
                for task in self.tasks:
                    if 'type' in task.keys() and task['type'].startswith("dorm"):
                        resting_dorm.extend(task["type"].split(','))
                actuall_resting = len(resting_dorm)

                if len(resting_dorm) < self.dorm_count:
                    need_to_rest = []
                    # 根据使用宿舍数量，输出需要休息的干员列表
                    number_of_dorm = self.dorm_count

                    min_mood = -99
                    for agent in self.total_agent:
                        if actuall_resting >= number_of_dorm:
                            if min_mood == -99:
                                min_mood = agent['mood']
                            break
                        if (len([value for value in need_to_rest if value["agent"] == agent["agent"]]) > 0):
                            continue
                        # 心情耗尽组如果心情 小于2 则记录时间
                        if agent['agent'] in self.exaust_agent and agent['mood'] < 3 and not \
                        self.operators[agent['agent']]['current_room'].startswith('dormitory'):
                            if next((e for e in self.tasks if 'type' in e.keys() and e['type'] == agent['agent']),
                                    None) is None:
                                __agent = self.operators[agent['agent']]
                                self.enter_room(__agent['current_room'])
                                result = self.get_agent_from_room(__agent['current_room'], [__agent['current_index']])
                                self.back()
                                # plan 是空的是因为得动态生成
                                self.tasks.append({"time": result[__agent['current_index']]['time'], "plan": {}, "type": __agent['name']})
                            else:
                                continue
                        # 忽略掉菲亚梅塔充能的干员
                        if agent['agent'] in exclude_list:
                            continue
                        # 忽略掉低效率的干员
                        if agent['agent'] in self.operators.keys() and self.operators[agent['agent']]['type'] != 'high':
                            continue
                        if 'resting_priority' in self.operators.keys() and self.operators[agent['agent']]['resting_priority'] != 'high':
                            continue
                        # 忽略掉正在休息的
                        if agent['current_room'] in resting_dorm or agent['current_room'] in ['factory']:
                            continue
                        # 忽略掉心情值没低于上限的8的
                        if agent['mood'] > int(self.operators[agent['agent']]["upper_limit"] * self.resting_treshhold):
                            continue
                        if agent['agent'] in self.operators.keys() and self.operators[agent['agent']]['group'] != '':
                            # 如果在group里则同时上下班
                            group_resting = [x for x in self.total_agent if
                                             self.operators[x['agent']]['group'] == self.operators[agent['agent']][
                                                 'group']]
                            group_restingCount = 0
                            for x in group_resting:
                                if self.operators[x['agent']]['resting_priority'] == 'low':
                                    continue
                                else:
                                    group_restingCount += 1
                            if group_restingCount + actuall_resting <= self.dorm_count:
                                need_to_rest.extend(group_resting)
                                actuall_resting += group_restingCount
                            else:
                                # 因为人数不够而跳过记录心情
                                min_mood = agent['mood']
                                continue
                        else:
                            need_to_rest.append(agent)
                            actuall_resting += 1
                    #      输出转换后的换班plan
                    logger.info(f'休息人选为->{need_to_rest}')
                    if len(need_to_rest) > 0:
                        self.get_swap_plan(resting_dorm, need_to_rest, min_mood < 3 and min_mood != -99)
                    # 如果下个 普通任务 >5 分钟则补全宿舍
                if (next((e for e in self.tasks if e['time'] < datetime.now() + timedelta(seconds=300)),
                             None)) is None:
                    self.agent_get_mood()
            except Exception as e:
                logger.exception(f'计算排班计划出错->{e}')

    def get_swap_plan(self, resting_dorm, operators, skip_read_time):
        result = {}
        agents = copy.deepcopy(operators)
        # 替换计划
        for a in operators:
            if a['current_room'] not in result.keys():
                result[a['current_room']] = ['Current'] * len(self.currentPlan[a['current_room']])
            # 获取替换组且没有在上班的 排除但书或者龙舌兰
            __replacement = next((obj for obj in self.operators[a['agent']]['replacement'] if (not (
                    self.operators[obj]['current_room'] != '' and not self.operators[obj][
                'current_room'].startswith('dormitory'))) and obj not in ['但书', '龙舌兰']), None)
            if __replacement is not None:
                self.operators[__replacement]['current_room'] = a['current_room']
                result[a['current_room']][a['room_index']] = __replacement
            else:
                raise Exception(f"{a['agent']} 没有足够的替换组可用")
        group_info = {}
        read_time_rooms = []
        need_recover_room = []
        # 从休息计划里 规划出排班计划 并且立刻执行
        for room in [k for k, v in self.currentPlan.items() if (k not in resting_dorm) and k.startswith('dormitory')]:
            # 记录房间可以放几个干员：
            dorm_plan = [data["agent"] for data in self.currentPlan[room]]
            # 塞一个最优组进去
            next_agent = next((obj for obj in agents if self.operators[obj["agent"]]['resting_priority'] == 'high'),
                              None)
            planned_agent = []
            if next_agent is not None:
                dorm_plan[dorm_plan.index('Free')] = next_agent["agent"]
                planned_agent.append(next_agent["agent"])
                agents.remove(next_agent)
            else:
                break
            if skip_read_time:
                if 'rest_in_full' in self.operators[next_agent['agent']].keys() and \
                        self.operators[next_agent['agent']]["rest_in_full"]:
                    need_recover_room.append(room)
                    read_time_rooms.append((room))
            else:
                if 'rest_in_full' in self.operators[next_agent['agent']].keys() and \
                        self.operators[next_agent['agent']]["rest_in_full"]:
                    skip_read_time = True
                read_time_rooms.append(room)
            free_num = dorm_plan.count('Free')
            while free_num > 0:
                next_agent_low = next(
                    (obj for obj in agents if self.operators[obj["agent"]]['resting_priority'] == 'low'), None)
                if next_agent_low is not None:
                    dorm_plan[dorm_plan.index('Free')] = next_agent_low["agent"]
                    planned_agent.append(next_agent_low["agent"])
                    agents.remove(next_agent_low)
                    free_num -= 1
                else:
                    break
            result[room] = dorm_plan
            # 如果有任何正在休息的最优组
            for item in self.current_base[room]:
                if 'agent' in item.keys():
                    _item_name = item['agent']
                    if _item_name in self.operators.keys() and self.operators[_item_name]['type'] == 'high' and not \
                    self.operators[_item_name]['room'].startswith(
                            'dormitory'):
                        # 如果是高效干员
                        _room = self.operators[_item_name]['room']
                        if _room not in result.keys():
                            result[_room] = ['Current'] * len(self.currentPlan[_room])
                        result[_room][self.operators[_item_name]['index']] = _item_name
            if room in need_recover_room:
                group_name = self.operators[next_agent['agent']]["name"]
            else:
                # 未分组则强制分组
                group_name = 'default'
            if not group_name in group_info.keys():
                group_info[group_name] = {'type': room, 'plan': {}}
            else:
                group_info[group_name]['type'] += ',' + room
            for planned in planned_agent:
                if self.operators[planned]['current_room'] not in group_info[group_name]['plan']:
                    group_info[group_name]['plan'][self.operators[planned]['current_room']] = ['Current'] * len(
                        self.currentPlan[self.operators[planned]['room']])
                group_info[group_name]['plan'][self.operators[planned]['current_room']][
                    self.operators[planned]['index']] = planned
            # group_info[group_name]['plan'][room]=[x['agent'] for x in self.currentPlan[room]]
        logger.info(f'生成的分组计划:{group_info}')
        logger.info(f'生成的排班计划为->{result}')
        self.tasks.append(
            {'plan': result, 'time': datetime.now(), 'metadata': {'plan': group_info, 'room': read_time_rooms}})

    def get_agent(self):
        plan = self.currentPlan
        high_production = []
        replacements = []
        for room in plan.keys():
            for idx, data in enumerate(plan[room]):
                __high = {"name": data["agent"], "room": room, "index": idx, "group": data["group"],
                          'replacement': data["replacement"], 'resting_priority': 'high', 'current_room': '',
                          'exhaust_require': False, "upper_limit": 24,"rest_in_full":False}
                if __high['name'] in self.agent_base_config.keys() and 'RestingPriority' in self.agent_base_config[
                    __high['name']].keys() and self.agent_base_config[__high['name']]['RestingPriority'] == 'low':
                    __high["resting_priority"] = 'low'
                if __high['name'] in self.agent_base_config.keys() and 'ExhaustRequire' in self.agent_base_config[
                    __high['name']].keys() and self.agent_base_config[__high['name']]['ExhaustRequire'] == True:
                    __high["exhaust_require"] = True
                if __high['name'] in self.agent_base_config.keys() and 'UpperLimit' in self.agent_base_config[
                    __high['name']].keys():
                    __high["upper_limit"] = self.agent_base_config[__high['name']]['UpperLimit']
                if __high['name'] in self.agent_base_config.keys() and 'RestInFull' in self.agent_base_config[
                    __high['name']].keys() and self.agent_base_config[__high['name']]['RestInFull'] == True:
                    __high["rest_in_full"] = True
                high_production.append(__high)
                if "replacement" in data.keys() and data["agent"] != '菲亚梅塔':
                    replacements.extend(data["replacement"])
        for agent in high_production:
            if agent["room"].startswith('dormitory'):
                agent["type"] = "low"
            else:
                agent["type"] = "high"
            self.operators[agent["name"]] = agent
        for agent in replacements:
            if agent in self.operators.keys():
                if 'type' in self.operators[agent].keys() and self.operators[agent]['type'] == 'high':
                    continue
                else:
                    self.operators[agent] = {"type": "low", "name": agent, "group": '', 'resting_priority': 'low',
                                             "index": -1, 'current_room': '', 'mood': 24, "upper_limit": 24,"rest_in_full":False}
            else:
                self.operators[agent] = {"type": "low", "name": agent, "group": '', 'current_room': '',
                                         'resting_priority': 'low', "index": -1, 'mood': 24, "upper_limit": 24,"rest_in_full":False}
        self.exaust_agent = []
        if next((k for k, v in self.operators.items() if 'exhaust_require' in v.keys() and v["exhaust_require"]),
                None) is not None:
            exhaust_require = [v for k, v in self.operators.items() if
                              'exhaust_require' in v.keys() and v["exhaust_require"]]
            for i in exhaust_require:
                if i['name'] in self.exaust_agent: continue
                if 'group' in i.keys() and i['group'] != '':
                    self.exaust_agent.extend([v['name'] for k, v in self.operators.items() if
                                              'group' in v.keys() and v['group'] == i['group']])
                else:
                    self.exaust_agent.append(i['name'])
        logger.info(f'需要用尽心情的干员为: {self.exaust_agent}')

    def check_in_and_out(self):
        res = {}
        for x, y in self.currentPlan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                res[x] = y
        return res

    def check_fia(self):
        res = {}
        if '菲亚梅塔' in self.operators.keys() and self.operators['菲亚梅塔']['room'].startswith('dormitory'):
            if 'replacement' in self.operators['菲亚梅塔'].keys():
                return self.operators['菲亚梅塔']['replacement'], self.operators['菲亚梅塔']['room']
        return None, None

    def get_in_and_out_time(self, room):
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
        execute_time = execute_time - timedelta(seconds=(600))
        logger.info('下一次进行插拔的时间为：' + execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)
        return execute_time

    def double_read_time(self, cord,upperLimit = 9000):
        self.recog.update()
        time_in_seconds = self.read_time(cord,upperLimit)
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds))
        return execute_time


    def initialize_paddle(self):
        global ocr
        if ocr is None:
            ocr = PaddleOCR(use_angle_cls=True, lang='en')

    def read_screen(self,img, type="mood",limit=24, cord=None, change_color=False):
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
                if 'mood' in type :
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
                number = int(__str[0:__str.index('/')])
                return number
            elif 'time' in type:
                if '.' in __str:
                    __str = __str.replace(".", ":")
            return __str
        except Exception as e :
            logger.exception(e)
            return limit

    def read_time(self, cord,upperlimit, error_count=0):
        # 刷新图片
        self.recog.update()
        time_str = self.read_screen(self.recog.img, type='time', cord=cord)
        logger.debug(time_str)
        try:
            h, m, s = time_str.split(':')
            if int(m)>60 or int(s)>60:
                raise Exception(f"读取错误")
            res =  int(h) * 3600 + int(m) * 60 + int(s)
            if res>upperlimit:
                raise Exception(f"超过读取上限")
            else :return res
        except:
            logger.error("读取失败" + "--> " + time_str)
            if error_count > 50:
                raise Exception(f"读取失败{error_count}次超过上限")
            else:
                return self.read_time(cord,upperlimit, error_count + 1)

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

        logger.info('接收赠送线索')
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
        else:
            self.back(interval=2, rebuild=False)

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

    def drone(self, room: str, one_time=False, not_return=False):
        logger.info('基建：无人机加速')

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
            logger.info('制造站加速')
            self.tap(accelerate)
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
                if one_time:
                    drone_count = self.read_screen(self.recog.img, type='drone_mood', cord=(
                        int(self.recog.w * 1150 / 1920), int(self.recog.h * 35 / 1080), int(self.recog.w * 1295 / 1920),
                        int(self.recog.h * 72 / 1080)), limit=200)
                    logger.info(f'当前无人机数量为：{drone_count}')
                    self.recog.update()
                    self.recog.save_screencap('run_order')
                    # 200 为识别错误
                    if drone_count < 100 or drone_count ==200:
                        logger.info(f"无人机数量小于92->停止")
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
        # if best_score < 0.6:
        #     raise RecognizeError
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
            agent_name = set([x[0] for x in ret])
            agent_size = len(agent)
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
            not_in_dorm = self.find('not_in_dorm')
            if turn_on ^ (not_in_dorm is not None):
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
                if is_dorm and not (agent[0] in self.operators.keys() and
                        'room' in self.operators[agent[0]].keys() and self.operators[agent[0]]['room'].startswith(
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
            free_list = [v["name"] for k, v in self.operators.items() if
                         v["name"] not in agents and v["type"] != 'high']
            free_list.extend([_name for _name in agent_list if _name not in self.operators.keys()])
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

    def get_agent_from_room(self, room, read_time_index=[]):
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
            data['agent'] = character_recognize.agent_name(
                self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]], self.recog.h*1.1)
            error_count = 0
            while i>=3 and data['agent'] !='' and (next((e for e in result if e['agent'] == data['agent']), None)) is not None:
                logger.warning("检测到滑动可能失败")
                self.swipe((self.recog.w * 0.8, self.recog.h * 0.8), (0, -self.recog.h * 0.4), interval=1, rebuild=True)
                data['agent'] = character_recognize.agent_name(
                    self.recog.img[name_p[i][0][1]:name_p[i][1][1], name_p[i][0][0]:name_p[i][1][0]], self.recog.h*1.1)
                error_count+=1
                if error_count>4:
                    raise Exception("超过出错上限")
            data['mood'] = self.read_screen(self.recog.img, cord=mood_p[i], change_color=True)
            if data['agent'] not in self.operators.keys():
                self.operators[data['agent']] = {"type": "low", "name": data['agent'], "group": '', 'current_room': '',
                                                 'resting_priority': 'low', "index": -1, 'mood': data['mood'],
                                                 "upper_limit": 24}
            else:
                self.operators[data['agent']]['mood'] = data['mood']
            self.operators[data['agent']]['current_index'] = i
            self.operators[data['agent']]['current_room'] = room
            if i in read_time_index:
                if data['mood'] in [24] or (data['mood'] == 0 and not room.startswith('dorm')):
                    data['time'] = datetime.now()
                else:
                    upperLimit = 21600
                    if data['agent']in ['菲亚梅塔','刻俄柏']:
                        upperLimit = 43200
                    data['time'] = self.double_read_time(time_p[i],upperLimit=upperLimit)
            result.append(data)
        self.scan_time[room] = datetime.now()
        # update current_room
        for item in result:
            operator = item['agent']
            if operator in self.operators.keys():
                self.operators[operator]['current_room'] = room
        for _operator in self.operators.keys():
            if 'current_room' in self.operators[_operator].keys() and self.operators[_operator][
                'current_room'] == room and _operator not in [res['agent'] for res in result] :
                self.operators[_operator]['current_room'] = ''
                logger.info(f'重设 {_operator} 至空闲')
        return result

    def agent_arrange(self, plan: tp.BasePlan, read_time_room=[]):
        logger.info('基建：排班')
        in_and_out = []
        fia_room = ""
        rooms = list(plan.keys())
        # 优先替换工作站再替换宿舍
        rooms.sort(key=lambda x: x.startswith('dorm'), reverse=False)
        time_result = {}
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
                        fia_room = room
                        update_base = True
                    # 如果需要更新当前阵容
                    self.scan_time[room] = None
                    # 是否该干员变动影响其他房间
                    update_room = []
                    for operator in (plan[room]):
                        if operator in self.operators.keys() and self.operators[operator]['current_room'] != '' and \
                                self.operators[operator]['current_room'] != room:
                            update_room.append(self.operators[operator]['current_room'])
                    for __room in update_room:
                        self.scan_time[__room] = None
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
                            self.scan_time[room] = None
                    while self.find('arrange_order_options') is None:
                        if error_count > 3:
                            raise Exception('未成功进入干员选择界面')
                        self.tap((self.recog.w * 0.82, self.recog.h * 0.2), interval=1)
                        error_count += 1
                    error_count = 0
                    self.choose_agent(plan[room], room)
                    self.recog.update()
                    self.tap_element('confirm_blue', detected=True, judge=False, interval=3)
                    if self.get_infra_scene() == Scene.INFRA_ARRANGE_CONFIRM:
                        x0 = self.recog.w // 3 * 2  # double confirm
                        y0 = self.recog.h - 10
                        self.tap((x0, y0), rebuild=True)
                    time_index = []
                    # 如果需要读取时间
                    if room in read_time_room:
                        time_index = [[data["agent"] for data in self.currentPlan[room]].index('Free')]
                    current = self.get_agent_from_room(room, time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]['agent'] != name:
                            raise Exception('检测到安排干员未成功')
                    #  如果不匹配，则退出主界面再重新进房间一次
                    if room in read_time_room:
                        __name = plan[room][[data["agent"] for data in self.currentPlan[room]].index('Free')]
                        time_result[room] = current[time_index[0]]['time']
                        if not self.operators[__name]['exhaust_require']:
                            time_result[room] = time_result[room] - timedelta(seconds=600)
                    finished = True
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
                        back_count+=1
                        if back_count>3:
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
            # 急速换班
            self.todo_task = True
            self.planned = True
        if fia_room != '':
            replace_agent = plan[fia_room][0]
            fia_change_room = self.operators[replace_agent]["room"]
            fia_room_plan = [data["agent"] for data in self.current_base[fia_room]]
            fia_change_room_plan = ['Current']*len(self.currentPlan[fia_change_room])
            fia_change_room_plan[self.operators[replace_agent]["index"]] = replace_agent
            self.tasks.append(
                {'time': self.tasks[0]['time'], 'plan': {fia_room: fia_room_plan, fia_change_room: fia_change_room_plan}})
            # 急速换班
            self.todo_task = True
            self.planned = True
        logger.info('返回基建主界面')
        if len(read_time_room) > 0:
            return time_result

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
        if self.MAA.connect(self.maa_config['maa_adb_path'], self.ADB_CONNECT):
            logger.info("MAA 连接成功")
        else:
            logger.info("MAA 连接失败")
            raise Exception("MAA 连接失败")

    def maa_plan_solver(self):
        try:
            if self.maa_config['last_execution'] is not None and datetime.now() - timedelta(seconds=self.maa_config['maa_execution_gap']*3600)< self.maa_config['last_execution']:
                logger.info("间隔未超过设定时间，不启动maa")
            else:
                self.send_email('休息时长超过9分钟，启动MAA')
                self.back_to_index()
                # 任务及参数请参考 docs/集成文档.md
                self.inialize_maa()
                self.MAA.append_task('StartUp')
                _plan= self.maa_config['weekly_plan'][get_server_weekday()]
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
                    'refresh': True
                })
                self.MAA.append_task('Visit')
                self.MAA.append_task('Mall', {
                    'shopping': True,
                    'buy_first': ['龙门币', '赤金'],
                    'blacklist': ['家具', '碳', '加急'],
                    'credit_fight':fights[len(fights)-1]!=''
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
                    self.device.exit('com.hypergryph.arknights')
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
                    self.device.exit('com.hypergryph.arknights')
            # 生息演算逻辑 结束
            remaining_time = (self.tasks[0]["time"] - datetime.now()).total_seconds()
            logger.info(f"开始休息 {remaining_time} 秒")
            self.send_email("脚本停止")
            time.sleep(remaining_time)
            self.MAA = None
        except Exception as e:
            logger.error(e)
            self.MAA = None
            remaining_time = (self.tasks[0]["time"] - datetime.now()).total_seconds()
            if remaining_time > 0:
                logger.info(f"开始休息 {remaining_time} 秒")
                time.sleep(remaining_time)
            self.device.exit('com.hypergryph.arknights')

    def send_email(self, tasks):
        try:
            msg = MIMEMultipart()
            conntent = str(tasks)
            msg.attach(MIMEText(conntent, 'plain', 'utf-8'))
            msg['Subject'] = self.email_config['subject']
            msg['From'] = self.email_config['account']
            s = smtplib.SMTP_SSL("smtp.qq.com", 465)
            # 登录邮箱
            s.login(self.email_config['account'], self.email_config['pass_code'])
            # 开始发送
            s.sendmail(self.email_config['account'], self.email_config['receipts'], msg.as_string())
            logger.info("邮件发送成功")
        except Exception as e:
            logger.error("邮件发送失败")
