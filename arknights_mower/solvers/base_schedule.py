from __future__ import annotations
import copy
from ..data import agent_base_config, agent_list

from enum import Enum
from datetime import datetime, timedelta
import numpy as np

from ..data import base_room_list
from ..utils import character_recognize, detector, segment
from ..utils import typealias as tp
from ..utils.device import Device
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Recognizer, Scene
from ..utils.solver import BaseSolver


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
        if len(self.tasks) > 0:
            # 找到时间最近的一次单个任务
            self.task = self.tasks[0]
            if 'type' in self.task.keys():
                self.task_type = self.task
            else:
                self.task_type = None
        else:
            self.task = None
            self.task_type = None
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

        # if next((e for e in self.tasks if 'type'in e.keys() and e['type'].startswith("dorm")), None) is not None:
        #
        # else :
        #     # 则入住第一个宿舍并且清空其他宿舍:
        #     self.agent_arrange()
        return


    def infra_main(self):
        """ 位于基建首页 """
        if self.find('control_central') is None:
            self.back()
            return
        if self.task is not None:
            try:
                if len(self.task["plan"].keys())>0:
                    self.agent_arrange(self.task["plan"])
                else:
                    self.overtake_room()
                del self.tasks[0]
            except Exception as e:
                logger.exception(e)
                self.planned = True
                self.todo_task = True
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
                    mood_result = self.agent_get_mood()
                    if mood_result is not None:
                        return True
                self.plan_solver()
            except Exception as e:
                # 重新扫描
                self.scan_time = {}
                logger.exception({e})
            self.planned = True
        else:
            return True

    def get_plan(self, room, index=-1):
        # -1 就是不换人
        result = []
        for data in self.currentPlan[room]:
            result.append(data["agent"])
        return result

    def agent_get_mood(self):
        self.tap_element('infra_overview', interval=2)
        logger.info('基建：记录心情')
        room_total = len(base_room_list)
        idx = 0
        pre_result = []
        room_total = len(base_room_list)
        need_read = set(list(k for k,v in self.scan_time.items() if not (v is not None and v>(
                            datetime.now() - timedelta(seconds=5400)))))
        while idx < room_total:
            ret, switch, mode = segment.worker(self.recog.img)
            if len(ret) == 0:
                raise RecognizeError('未识别到进驻总览中的房间列表')
            # 关闭撤下干员按钮
            if mode:
                self.tap((switch[0][0] + 5, switch[0][1] + 5), rebuild=False)
                continue

            if room_total - idx < len(ret):
                # 已经滑动到底部
                ret = ret[-(room_total - idx):]
            for block in ret:
                if base_room_list[idx] in need_read:
                    y = (block[0][1] + block[2][1]) // 2
                    x = (block[2][0] - block[0][0]) // 7 + block[0][0]
                    while True:
                        self.tap((x, y), interval=0.1, rebuild=True)
                        self.current_base[base_room_list[idx]] = character_recognize.agent_with_mood(self.recog.img,
                                                                                                     length=len(
                                                                                                         self.currentPlan[
                                                                                                             base_room_list[
                                                                                                                 idx]]))
                        logger.info(f'房间 {base_room_list[idx]} 心情为：{ self.current_base[base_room_list[idx]]}')
                        self.scan_time[base_room_list[idx]] = datetime.now()
                        # 纠错，防止出现点击因为网络连接失败的情况
                        if len(pre_result) == len(self.current_base[base_room_list[idx]]) and len(pre_result) > 0 and \
                                pre_result[0]["agent"] == self.current_base[base_room_list[idx]][0]["agent"]:
                            self.sleep(2)
                            continue
                        else:
                            pre_result = copy.deepcopy(self.current_base[base_room_list[idx]])
                            break
                idx += 1
            # 识别结束
            if idx == room_total or len(need_read) == 0:
                break
            block = ret[-1]
            top = switch[2][1]
            self.swipe_noinertia(tuple(block[1]), (0, top - block[1][1]))
        logger.info('心情记录完毕')
        self.back()
        current_base = copy.deepcopy(self.current_base)
        plan = self.currentPlan
        self.total_agent = []
        fix_plan = {}
        logger.info(f'当前基地心情--> {current_base}')
        # 清空已有心情
        for key in self.operators:
            if self.operators[key]['type'] == 'high':
                self.operators[key]['mood'] = -1
            self.operators[key]['current_room'] = ''
        for key in current_base:
            if (key == 'train' or key == 'factory'): continue
            need_fix = False
            for idx, operator in enumerate(current_base[key]):
                data = current_base[key][idx]
                # 如果是空房间
                if data["mood"] == -1:
                    data["agent"] = ''
                    if not need_fix:
                        fix_plan[key] = [''] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx]["agent"]
                    continue
                if (data["agent"] in agent_base_config.keys()):
                    # 如果有设置下限，则减去下限值 eg: 令
                    if ("LowerLimit" in agent_base_config[current_base[key][idx]["agent"]]):
                        data["mood"] = data["mood"] - agent_base_config[current_base[key][idx]["agent"]]["LowerLimit"]
                # 把额外数据传过去
                data["current_room"] = key
                data["room_index"] = idx
                # 记录数据
                if data["agent"] not in self.operators.keys():
                    # 如果出现没预设的干员则新建
                    self.operators[data["agent"]] = {"type": "low", "name": data["agent"], "group": '',
                                                     'resting_priority': 'low'}
                self.operators[data["agent"]]['mood'] = data["mood"]
                self.operators[data["agent"]]['current_room'] = key
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
                     (v['type'] == 'high' and (v['mood'] == -1 or (v['mood'] == 24) and v['current_room'].startswith('dormitory')))}
        if len(miss_list.keys()) > 0:
            # 替换到他应该的位置
            for key in miss_list:
                if miss_list[key]['group'] !='':
                    # 如果还有其他小组成员没满心情则忽略
                    if next((k for k,v in self.operators.items() if v['group'] == miss_list[key]['group'] and not (v['mood'] == -1 or v['mood'] == 24)), None) is not None:
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
                # 如果 type有，则跳过宿舍的纠错（会触发plan_solver）
                if self.task_type is not None and key.startswith('dormitory'):
                    remove_keys.append(key)
                else:
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
        if (next((e for e in self.tasks if 'type' not in e.keys() and e['time'] < datetime.now() + timedelta(seconds=600)),
              None)) is not None:
             return
        if len(self.check_in_and_out()) > 0:
            # 处理龙舌兰和但书的插拔
            for room in self.check_in_and_out():
                if any(room in obj["plan"].keys() and 'type' not in obj.keys() for obj in self.tasks): continue;
                in_out_plan = {}
                in_out_plan[room] = []
                for idx, x in enumerate(plan[room]):
                    if '但书' in x['replacement'] or '龙舌兰' in x['replacement']:
                        in_out_plan[room].append(x['replacement'][0])
                    # 如果有现有计划则保持目前基地不变
                    elif room in self.currentPlan.keys():
                        in_out_plan[room].append(self.currentPlan[room][idx]["agent"])
                    else:
                        in_out_plan[room].append(x["agent"])
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
                    if self.operators["菲亚梅塔"]["mood"] == 24:
                        change_time = datetime.now()
                    else:
                        change_time = self.get_time(fia_room, '菲亚梅塔')
                    logger.info('下一次进行菲亚梅塔充能：' + change_time.strftime("%H:%M:%S"))
                    self.tasks.append({"time": change_time, "plan": {fia_room: [
                        next(obj for obj in self.total_agent if obj["agent"] in fia_plan)["agent"],
                        "菲亚梅塔"]}})
                exclude_list.append("菲亚梅塔")
            try:
                exaust_agent = []
                exaust_rest = []
                if next((k for k, v in self.operators.items() if 'exaust_require' in v.keys() and v["exaust_require"]),
                        None) is not None:
                    exaust_require = [v for k, v in self.operators.items() if
                                      'exaust_require' in v.keys() and v["exaust_require"]]
                    for i in exaust_require:
                        if 'group' in i.keys() and i['group'] != '':
                            exaust_agent.extend([v['name'] for k, v in self.operators.items() if
                                                 'group' in v.keys() and v['group'] == i['group']])
                        else:
                            exaust_agent.append(i['name'])
                        if 'current_room' in i.keys() and i['current_room'].startswith('dormitory') and next((k for k, v in self.tasks.items() if 'type' in v.keys() and i['current_room'] in v["type"]),None) is None:
                            exaust_rest.append([i['name']])
                exclude_list.extend(exaust_agent)
                # 如果exaust_agent<2 则读取
                logger.info(f'安排干员黑名单为：{exclude_list}')
                # 先计算需要休息满的人
                for agent in exaust_rest:
                    error_count = 0
                    time_result = None
                    while error_count < 3:
                        try:
                            time_result = self.agent_arrange(self.current, self.operators[agent]['current_room'])
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
                    exaust_plan = {'plan': {}, 'time': time_result, 'type': self.operators[agent]['current_room']}
                    # 如果有组，则生成小组上班 否则则单人上班
                    bundle = []
                    if self.operators[agent]['group'] != '':
                        bundle.extend([v['name'] for k, v in self.operators.items() if
                                       'group' in v.keys() and v['group'] == i['group']])
                    else:
                        bundle.append(agent)
                    for planned in bundle:
                        if self.operators[planned]['current_room'] not in exaust_plan['plan']:
                            exaust_plan['plan'][self.operators[planned]['current_room']] = [
                                                                                               'Current'] * len(
                                self.currentPlan[self.operators[planned]['room']])
                        exaust_plan['plan'][self.operators[planned]['current_room']][
                            self.operators[planned]['index']] = planned
                    self.tasks.append(exaust_plan)
                resting_dorm = []
                for task in self.tasks:
                    if 'type' in task.keys() and task['type'].startswith("dorm"):
                        resting_dorm.extend(task["type"].split(','))
                actuall_resting = len(resting_dorm)

                if len(resting_dorm) < self.dorm_count:
                    need_to_rest = []
                    # 根据使用宿舍数量，输出需要休息的干员列表
                    number_of_dorm = self.dorm_count

                    min_mood = -1
                    for agent in self.total_agent:
                        if actuall_resting >= number_of_dorm:
                            if min_mood == -1:
                                min_mood = agent['mood']
                            break
                        if (len([value for value in need_to_rest if value["agent"] == agent["agent"]]) > 0):
                            continue
                        # 心情耗尽组如果心情 小于2 则记录时间
                        if agent['agent'] in exaust_agent and agent['mood']<2:
                            if next((e for e in self.tasks if 'type'in e.keys() and e['type']==agent['agent']), None) is None:
                                rest_time = self.get_time(agent['agent']['current_room'], agent['agent'],adjustment=-600)
                                # plan 是空的是因为得动态生成
                                self.tasks.append({"time": rest_time, "plan": {},"type":agent['agent']} )
                            else:
                                continue
                        # 忽略掉菲亚梅塔充能的干员
                        if agent['agent'] in exclude_list:
                            continue
                        # 忽略掉低效率的干员
                        if agent['agent'] in self.operators.keys() and self.operators[agent['agent']]['type']=='low':
                            continue
                        # 忽略掉正在休息的
                        if agent['current_room'] in resting_dorm:
                            continue
                        # 忽略掉心情值没低于上限的8的
                        if agent['mood']> self.operators[agent['agent']]["upper_limit"]-8:
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
                    if len(need_to_rest)>0:
                        self.get_swap_plan(resting_dorm, need_to_rest, min_mood < 3)
                    # 关闭跳过宿舍
                    self.task_type = None
                    self_correction = self.agent_get_mood()
                    if self_correction is not None:
                        return
            except Exception as e:
                # 清空出错的任务
                for task in self.tasks:
                    if 'type' in task.keys():
                        self.tasks.remove(task)
                logger.exception(f'计算排班计划出错->{e}')
                self.agent_get_mood()
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
        need_recover_room=[]
        # 从休息计划里 规划出排班计划 并且立刻执行
        for room in [k for k, v in self.currentPlan.items() if (k not in resting_dorm) and k.startswith('dormitory')]:
            # 记录房间可以放几个干员：
            need_full = False
            dorm_plan = [data["agent"] for data in self.currentPlan[room]]
            # 塞一个最优组进去
            next_agent = next((obj for obj in agents if self.operators[obj["agent"]]['resting_priority'] == 'high'),
                              None)
            if skip_read_time:
                if 'exaust_require' in self.operators[next_agent['agent']].keys() and \
                        self.operators[next_agent['agent']]["exaust_require"]:
                    need_recover_room.append(room)
                    read_time_rooms.append((room))
            else:
                read_time_rooms.append(room)
            planned_agent = []
            if next_agent is not None:
                dorm_plan[dorm_plan.index('Free')] = next_agent["agent"]
                planned_agent.append(next_agent["agent"])
                agents.remove(next_agent)
            else:
                break
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
                    if _item_name in self.operators.keys() and  self.operators[_item_name]['type'] == 'high' and not self.operators[_item_name]['room'].startswith(
                            'dormitory'):
                        # 如果是高效干员
                        _room = self.operators[_item_name]['room']
                        if _room not in result.keys():
                            result[_room] = ['Current'] * len(self.currentPlan[_room])
                        result[_room][self.operators[_item_name]['index']] = _item_name
            if room in need_recover_room:
                group_name = self.operators[next_agent['agent']]["agent"]
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
        logger.info(f'生成的分组计划:{group_info}')
        error_count = 0
        time_result = {}
        logger.info(f'生成的排班计划为->{result}')
        while error_count < 3:
            try:
                time_result = self.agent_arrange(result, read_time_rooms)
                if time_result is None and len(read_time_rooms) > 0:
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
        for key, _plan in group_info.items():

            if 'default' != key:
                _plan["time"] = time_result[_plan["type"]]
                self.tasks.append({"type": _plan['type'], 'plan': _plan['plan'],'time':_plan['time']})
            else:
                # 合在一起则取最小恢复时间
                min_time = datetime.max
                __time = datetime.now()
                for dorm in _plan["type"].split(','):
                    if dorm not in read_time_rooms:
                        # 如果没有读取任何时间，则只休息1小时替换下一组
                        time_result[_plan["type"]] = __time + timedelta(seconds=(3600))
                    if min_time > time_result[dorm]:
                        min_time = time_result[dorm]
                _plan["time"] = min_time
                # 如果有任何已有plan
                existing_plan = next((e for e in self.tasks if 'type' in e.keys() and e['type'].startswith('dormitory')), None)
                if existing_plan is not None and existing_plan['time']<_plan["time"]:
                    for k in _plan['plan']:
                        if k not in existing_plan['plan']:
                            existing_plan['plan'][k]= _plan['plan'][k]
                        else:
                            for idx,_a in enumerate( _plan['plan'][k]):
                                if _plan['plan'][k][idx]!='Current':
                                    existing_plan['plan'][k][idx] = _plan['plan'][k][idx]
                    existing_plan['type']=existing_plan['type']+','+_plan["type"]
                else:
                    self.tasks.append({"type": _plan['type'], 'plan': _plan['plan'], 'time': _plan['time']})

    def get_agent(self):
        plan = self.currentPlan
        high_production = []
        replacements = []
        for room in plan.keys():
            for idx, data in enumerate(plan[room]):
                __high = {"name": data["agent"], "room": room, "index": idx, "group": data["group"],
                          'replacement': data["replacement"], 'resting_priority': 'high', 'current_room': '',
                          'exaust_require': False,"upper_limit":24}
                if __high['name'] in agent_base_config.keys() and 'RestingPriority' in agent_base_config[
                    __high['name']].keys() and agent_base_config[__high['name']]['RestingPriority'] == 'low':
                    __high["resting_priority"] = 'low'
                if __high['name'] in agent_base_config.keys() and 'ExaustRequire' in agent_base_config[
                    __high['name']].keys() and agent_base_config[__high['name']]['ExaustRequire'] == True:
                    __high["exaust_require"] = True
                if __high['name'] in agent_base_config.keys() and 'UpperLimit' in agent_base_config[
                    __high['name']].keys():
                    __high["upper_limit"] = agent_base_config[__high['name']]['UpperLimit']
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
                                             "index": -1, 'current_room': '', 'mood': 24,"upper_limit":24}
            else:
                self.operators[agent] = {"type": "low", "name": agent, "group": '', 'current_room': '',
                                         'resting_priority': 'low', "index": -1, 'mood': 24,"upper_limit":24}

    def check_in_and_out(self):
        res = {}
        for x, y in self.currentPlan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                res[x] = y
        return res

    def check_fia(self):
        res = {}
        if '菲亚梅塔' in self.operators.keys() and self.operators['菲亚梅塔']['room'].startswith('dormitory') :
            if 'replacement' in self.operators['菲亚梅塔'].keys():
                return self.operators['菲亚梅塔']['replacement'],self.operators['菲亚梅塔']['room']
        return None, None

    def get_time(self, room, name, adjustment=0, skip_enter_room=False):
        if not skip_enter_room:
            self.enter_room(room)
            self.tap((self.recog.w * 0.05, self.recog.h * 0.2), interval=0.2)
            self.tap((self.recog.w * 0.05, self.recog.h * 0.4), interval=0.2)
            self.tap((self.recog.w * 0.82, self.recog.h * 0.2), interval=0.2)
        self.choose_agent([name], room, read_time=True)
        if "菲亚梅塔" == name:
            upperLimit = 43200
        else:
            upperLimit = 21600
        time_in_seconds = self.read_time((int(self.recog.w * 540 / 2496), int(self.recog.h * 380 / 1404),
                                          int(self.recog.w * 710 / 2496), int(self.recog.h * 430 / 1404)), upperLimit)
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds + adjustment))
        logger.info(name + ' 心情恢复时间为：' + execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        if not skip_enter_room:
            self.back(interval=2, rebuild=True)
        return execute_time

    def get_in_and_out_time(self, room):
        logger.info('基建：读取插拔时间')
        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
        time_in_seconds = self.read_time((int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404),
                                          int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)))
        execute_time = datetime.now() + timedelta(seconds=(time_in_seconds - 600))
        logger.info('下一次进行插拔的时间为：' + execute_time.strftime("%H:%M:%S"))
        logger.info('返回基建主界面')
        self.back(interval=2, rebuild=False)
        self.back(interval=2)
        return execute_time

    def read_time(self, cord, upperlimit=8800, error_count=0):
        # 刷新图片
        self.recog.update()
        time_str = segment.read_screen(self.recog.img, type='time', cord=cord)
        try:
            h, m, s = time_str.split(':')
            seconds = int(h) * 3600 + int(m) * 60 + int(s)
            if seconds > upperlimit:
                logger.error("数值超出最大值" + "--> " + str(seconds))
                raise RecognizeError("")
            else:
                return seconds
        except:
            logger.error("读取失败" + "--> " + time_str)
            if error_count > 50:
                raise Exception(f"读取失败{error_count}次超过上限")
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
        self.last_room =room

    def drone(self, room: str, one_time=False, not_return=False):
        logger.info('基建：无人机加速')

        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)

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
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8), interval=3)  # relative position 0.75, 0.8
                if one_time:
                    drone_count = segment.read_screen(self.recog.img, type='mood', cord=(
                    int(self.recog.w * 1150 / 1920), int(self.recog.h * 35 / 1080), int(self.recog.w * 1300 / 1920),
                    int(self.recog.h * 68 / 1080)), limit=200)
                    logger.info(f'当前无人机数量为：{drone_count}')
                    if drone_count<92:
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

    def scan_agant(self, agent: list[str], order_matters=False, error_count=0, max_agent_count=-1):
        try:
            # 识别干员
            self.recog.update()
            ret = character_recognize.agent(self.recog.img)  # 返回的顺序是从左往右从上往下
            # 提取识别出来的干员的名字
            agent_name = set([x[0] for x in ret])
            agent_size = len(agent)
            select_name = []
            if order_matters:
                # 按照顺序
                while len(agent) > 0:
                    if any(agent[0] == obj for obj in agent_name):
                        y = next((e for e in ret if e[0] == agent[0]), None)
                        self.tap((y[1][0]), interval=0.5, rebuild=False)
                        agent.remove(agent[0])
                        continue
                    break
            else:
                # 任意顺序
                for y in ret:
                    name = y[0]
                    if name in agent:
                        self.tap((y[1][0]), interval=0.5, rebuild=False)
                        agent.remove(name)
                        # 如果是按照个数选择 Free
                        if max_agent_count != -1:
                            select_name.append(name)
                            if len(select_name) >= max_agent_count:
                                return select_name, ret
                if max_agent_count != -1:
                    return select_name, ret
            return agent_size != len(agent), ret
        except Exception as e:
            error_count += 1
            if error_count < 3:
                logger.exception(e)
                self.sleep(3)
                return self.scan_agant(agent, order_matters, error_count, max_agent_count)
            else:
                raise e

    def get_order(self, name):
        if (name in agent_base_config.keys()):
            if "ArrangeOrder" in agent_base_config[name].keys():
                return True, agent_base_config[name]["ArrangeOrder"]
            else:
                return False, agent_base_config["Default"]["ArrangeOrder"]
        return False, agent_base_config["Default"]["ArrangeOrder"]

    def choose_agent(self, agents: list[str], room: str, read_time=False) -> None:
        """
        :param order: ArrangeOrder, 选择干员时右上角的排序功能
        """
        agent = copy.deepcopy(agents)
        logger.info(f'{"安排干员" if not read_time else "读取心情"}：{agent}')
        # 若不是空房间，则清空工作中的干员
        is_dorm = room.startswith("dorm")
        h, w = self.recog.h, self.recog.w
        first_time = True
        # 在 agent 中 'Free' 表示任意空闲干员
        free_num = agent.count('Free')
        for i in range(agent.count("Free")):
            agent.remove("Free")
        order_matters = True
        is_clear = False
        index_change = False
        pre_order = [2, False]
        right_swipe = 0
        if read_time:
            # 不需要排序
            self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            self.scan_agant(agent)
            return
        # 如果重复进入宿舍则需要排序
        logger.info(f'上次进入房间为：{self.last_room},本次房间为：{room}')
        if self.last_room.startswith('dorm') and is_dorm:
            self.tap((self.recog.w * 0.95, self.recog.h * 0.05), interval=0.1)
            self.recog.update()
            if self.find('not_in_dorm') is not None:
                self.tap((self.recog.w * 0.3, self.recog.h * 0.5), interval=0.1)
            # 确认
            self.tap((self.recog.w * 0.8, self.recog.h * 0.8), interval=0.1)
        while len(agent) > 0:
            if right_swipe > 50:
                # 到底了则返回再来一次
                for _ in range(right_swipe):
                    self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
                right_swipe = 0
            if first_time:
                # 清空
                if is_dorm:
                    self.switch_arrange_order(3, "true")
                    pre_order = [3, 'true']
                self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
                changed, ret = self.scan_agant(agent)
                if changed:
                    if len(agent) == 0: break;
                    index_change = True

            # 如果选中了人，则可能需要重新排序
            if index_change or first_time:
                # 第一次则调整
                is_custom, arrange_type = self.get_order(agent[0])
                if is_dorm and not is_custom:
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
            if len(agent) == 0: break;
            if not changed:
                # 如果没找到
                index_change = False
                st = ret[-2][1][2]  # 起点
                ed = ret[0][1][1]  # 终点
                self.swipe_noinertia(st, (ed[0] - st[0], 0))
                right_swipe += 1
            else:
                # 如果找到了
                index_change = True
        # 安排空闲干员
        if free_num:
            if free_num == len(agents):
                self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            if not first_time:
                # 滑动到最左边
                self.sleep(interval=0.5, rebuild=False)
                right_swipe = self.swipe_left(right_swipe, w, h)
            self.tap((self.recog.w * 0.95, self.recog.h * 0.05), interval=0.1)
            self.recog.update()
            if self.find('not_in_dorm') is None:
                self.tap((self.recog.w * 0.3, self.recog.h * 0.5), interval=0.1)
            # 确认
            self.tap((self.recog.w * 0.8, self.recog.h * 0.8), interval=0.1)
            self.switch_arrange_order(3, "true")
            # 只选择在列表里面的
            # 替换组小于20才休息，防止进入就满心情进行网络连接
            free_list = [v["name"] for k, v in self.operators.items() if
                         v["name"] not in agents and v["type"] == 'low' and 'mood' in v.keys() and v["mood"] < 20]
            free_list.extend([_name for _name in agent_list if _name not in self.operators.keys()])
            while free_num:
                selected_name, ret = self.scan_agant(free_list, max_agent_count=free_num)
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
        if order_matters and len(agents) != 1:
            right_swipe = self.swipe_left(right_swipe, w, h)
            agent_with_order = copy.deepcopy(agents)
            if "菲亚梅塔" in agent_with_order:
                self.switch_arrange_order(2, "true")
            else:
                self.switch_arrange_order(3)
            self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            self.scan_agant(agent_with_order, True, 0)

    def swipe_left(self, right_swipe, w, h):
        for _ in range(right_swipe):
            self.swipe_only((w // 2, h // 2), (w // 2, 0), interval=0.5)
        return 0

    def agent_arrange(self, plan: tp.BasePlan, read_time_room=[]):
        """ 基建排班 """
        # 单独逻辑块适配需要心情归零的干员:
        # if len(plan.keys())==0 and self.task_type is not None:
        #     # 寻找他是否有group 有group 则全组下班
        #     logger.info(f'开始为{self.task_type} 生成任务')
        #     new_plan = []
        #     if self.operators[self.task_type]['group'] !='':
        logger.info('基建：排班')
        in_and_out = []
        fia_room = ""
        # 进入进驻总览
        self.tap_element('infra_overview', interval=2)
        time_result = {}
        logger.info('安排干员工作……')
        idx = 0
        room_total = len(base_room_list)
        need_empty = set(list(plan.keys()))
        while idx < room_total:
            ret, switch, mode = segment.worker(self.recog.img)
            if len(ret) == 0:
                raise RecognizeError('未识别到进驻总览中的房间列表')

            # 关闭撤下干员按钮
            if mode:
                self.tap((switch[0][0] + 5, switch[0][1] + 5), rebuild=False)
                continue

            if room_total - idx < len(ret):
                # 已经滑动到底部
                ret = ret[-(room_total - idx):]

            for block in ret:
                if base_room_list[idx] in need_empty:
                    need_empty.remove(base_room_list[idx])
                    # 对这个房间进行换班
                    finished = len(plan[base_room_list[idx]]) == 0
                    error_count = 0
                    while not finished:
                        # 插拔逻辑
                        update_base = False
                        if ('但书' in plan[base_room_list[idx]] or '龙舌兰' in plan[base_room_list[idx]]) and not \
                                base_room_list[idx].startswith('dormitory'):
                            in_and_out.append(base_room_list[idx])
                            update_base = True
                        if '菲亚梅塔' in plan[base_room_list[idx]] and len(plan[base_room_list[idx]]) == 2:
                            fia_room = base_room_list[idx]
                            update_base = True
                        x = (7 * block[0][0] + 3 * block[2][0]) // 10
                        y = (block[0][1] + block[2][1]) // 2

                        # 如果需要更新当前阵容
                        self.scan_time[base_room_list[idx]] = None
                        # 是否该干员变动影响其他房间
                        update_room = []
                        for operator in (plan[base_room_list[idx]]):
                            if operator in self.operators.keys() and self.operators[operator]['current_room'] != \
                                    base_room_list[idx]:
                                update_room.append(self.operators[operator]['current_room'])
                        for __room in update_room:
                            self.scan_time[__room] = None
                        if update_base or 'Current' in plan[base_room_list[idx]]:
                            y0 = (block[0][1] + block[2][1]) // 2
                            x0 = (block[2][0] - block[0][0]) // 7 + block[0][0]
                            self.tap((x0, y0), rebuild=False)
                            self.current_base[base_room_list[idx]]= character_recognize.agent_with_mood(
                                self.recog.img, length=len(self.currentPlan[base_room_list[idx]]))
                            # 纠错 因为网络连接导致房间移位
                            if 'Current' in plan[base_room_list[idx]]:
                                # replace current
                                for current_idx, _name in enumerate(plan[base_room_list[idx]]):
                                    if _name == 'Current':
                                        current_name = self.current_base[base_room_list[idx]][current_idx]["agent"]
                                        if current_name in agent_list:
                                            plan[base_room_list[idx]][current_idx] = current_name
                                        else:
                                        # 如果空房间或者名字错误，则使用default干员
                                            plan[base_room_list[idx]][current_idx] =self.currentPlan[base_room_list[idx]][current_idx]["agent"]
                                self.scan_time[base_room_list[idx]] = None
                        try:
                            # 如果是单人房间则外部撤下干员
                            if len(plan[base_room_list[idx]]) == 1:
                                self.tap((switch[0][0] + 5, switch[0][1] + 5), rebuild=False)
                                self.tap((block[2][0], y), interval=0.5, rebuild=False)
                                # 确认
                                self.recog.update()
                                if self.find('double_confirm') is not None:
                                    self.tap_element('double_confirm', 1, detected=False, judge=False, interval=3)
                                self.tap((switch[0][0] + 5, switch[0][1] + 5), rebuild=False)
                            self.tap((x, y))
                            self.choose_agent(
                                plan[base_room_list[idx]], base_room_list[idx])
                        except RecognizeError as e:
                            error_count += 1
                            if error_count >= 3:
                                raise e
                            # 返回基建干员进驻总览
                            self.recog.update()
                            while self.scene() not in [Scene.INFRA_ARRANGE,
                                                       Scene.INFRA_MAIN] and self.scene() // 100 != 1:
                                pre_scene = self.scene()
                                self.back(interval=3)
                                if self.scene() == pre_scene:
                                    break
                            if self.scene() != Scene.INFRA_ARRANGE:
                                raise e
                            continue
                        self.recog.update()
                        self.tap_element(
                            'confirm_blue', detected=True, judge=False, interval=3)
                        if self.scene() == Scene.INFRA_ARRANGE_CONFIRM:
                            x0 = self.recog.w // 3 * 2  # double confirm
                            y0 = self.recog.h - 10
                            self.tap((x0, y0), rebuild=True)
                        # 如果需要读取时间
                        if base_room_list[idx] in read_time_room:
                            self.tap((x, y))
                            index = [data["agent"] for data in self.currentPlan[base_room_list[idx]]].index('Free')
                            adj = 0 if self.operators[plan[base_room_list[idx]][index]]["exaust_require"] else -600
                            time = self.get_time(base_room_list[idx], plan[base_room_list[idx]][index], adjustment=adj,
                                                 skip_enter_room=True)
                            time_result[base_room_list[idx]] = time
                            self.recog.update()
                        # update current_room
                        for operator in (plan[base_room_list[idx]]):
                            if operator in self.operators.keys():
                                self.operators[operator]['current_room']=base_room_list[idx]
                        finished = True
                        while self.scene() == Scene.CONNECTING:
                            self.sleep(3)
                    self.last_room = base_room_list[idx]
                    logger.info(f"设置上次房间为{self.last_room}")
                idx += 1

            # 换班结束
            if idx == room_total or len(need_empty) == 0:
                break
            block = ret[-1]
            top = switch[2][1]
            self.swipe_noinertia(tuple(block[1]), (0, top - block[1][1]))
        if len(in_and_out) > 0:
            self.back()
            replace_plan = {}
            for room in in_and_out:
                logger.info("开始插拔")
                self.drone(room, True, True)
                self.tap((self.recog.w * 0.22, self.recog.h * 0.95), interval=0.5)
                in_and_out_plan = [data["agent"] for data in self.current_base[room]]
                replace_plan[room] = in_and_out_plan
                self.back(interval=2)
            self.tasks.append({'time': self.tasks[0]['time'], 'plan': replace_plan})
            # 急速换班
            self.todo_task = True
            self.planned = True
        if fia_room != '':
            replace_agent = plan[fia_room][0]
            fia_change_room = self.operators[replace_agent]["room"]
            self.back(interval=2)
            if len(self.current_base.keys()) > 3:
                fia_room_plan = [data["agent"] for data in self.current_base[fia_room]]
                fia_change_room_plan = [data["agent"] for data in self.current_base[fia_change_room]]
            else:
                fia_room_plan = [data["agent"] for data in self.currentPlan[fia_room]]
                fia_change_room_plan = [data["agent"] for data in self.currentPlan[fia_change_room]]
            self.tasks.append(
                {'time': datetime.now(), 'plan': {fia_room: fia_room_plan, fia_change_room: fia_change_room_plan}})
            # 急速换班
            self.todo_task = True
            self.planned = True
        logger.info('返回基建主界面')
        self.back()
        if len(read_time_room) > 0:
            return time_result
