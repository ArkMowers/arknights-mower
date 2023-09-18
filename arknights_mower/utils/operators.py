from datetime import datetime, timedelta
from ..data import agent_list
from ..solvers.record import save_action_to_sqlite_decorator
from ..utils.log import logger

class Operators(object):
    config = None
    operators = None
    exhaust_agent = []
    exhaust_group = []
    groups = None
    dorm = []
    max_resting_count = 4
    plan = None

    def __init__(self, config, max_resting_count, plan):
        self.config = config
        self.operators = {}
        self.groups = {}
        self.exhaust_agent = []
        self.exhaust_group = []
        self.dorm = []
        self.max_resting_count = max_resting_count
        self.workaholic_agent = []
        self.plan = plan
        self.run_order_rooms = {}
        self.clues = []

    def __repr__(self):
        return f'Operators(operators={self.operators})'

    def init_and_validate(self):
        for room in self.plan.keys():
            for idx, data in enumerate(self.plan[room]):
                if data["agent"] not in agent_list and data['agent'] != 'Free':
                    return f'干员名输入错误: 房间->{room}, 干员->{data["agent"]}'
                if data["agent"] in ['龙舌兰', '但书']:
                    return f'高效组不可用龙舌兰，但书 房间->{room}, 干员->{data["agent"]}'
                if data["agent"] == '菲亚梅塔' and idx == 1:
                    return f'菲亚梅塔不能安排在2号位置 房间->{room}, 干员->{data["agent"]}'
                if data["agent"] == 'Free' and not room.startswith('dorm'):
                    return f'Free只能安排在宿舍 房间->{room}, 干员->{data["agent"]}'
                if data["agent"] in self.operators and data["agent"] != "Free":
                    return f'高效组干员不可重复 房间->{room},{self.operators[data["agent"]].room}, 干员->{data["agent"]}'
                self.add(Operator(data["agent"], room, idx, data["group"], data["replacement"], 'high',
                                  operator_type="high"))
        missing_replacements = []
        for room in self.plan.keys():
            if room.startswith("dorm") and len(self.plan[room]) != 5:
                return f'宿舍 {room} 人数少于5人'
            for idx, data in enumerate(self.plan[room]):
                # 菲亚梅塔替换组做特例判断
                if "龙舌兰" in data["replacement"] and "但书" in data["replacement"]:
                    return f'替换组不可同时安排龙舌兰和但书 房间->{room}, 干员->{data["agent"]}'
                if "菲亚梅塔" in data["replacement"]:
                    return f'替换组不可安排菲亚梅塔 房间->{room}, 干员->{data["agent"]}'
                r_count = len(data["replacement"])
                if "龙舌兰" in data["replacement"] or "但书" in data["replacement"]:
                    r_count -= 1
                if r_count <= 0 and data['agent'] != 'Free' and (not room.startswith("dorm")):
                    missing_replacements.append(data["agent"])
                for _replacement in data["replacement"]:
                    if _replacement not in agent_list and data['agent'] != 'Free':
                        return f'干员名输入错误: 房间->{room}, 干员->{_replacement}'
                    if data["agent"] != '菲亚梅塔':
                        # 普通替换
                        if _replacement in self.operators and self.operators[_replacement].is_high():
                            return f'替换组不可用高效组干员: 房间->{room}, 干员->{_replacement}'
                        self.add(Operator(_replacement, ""))
                    else:
                        if _replacement not in self.operators:
                            return f'菲亚梅塔替换不在高效组列: 房间->{room}, 干员->{_replacement}'
                        if _replacement in self.operators and not self.operators[_replacement].is_high():
                            return f'菲亚梅塔替换只能高效组干员: 房间->{room}, 干员->{_replacement}'
                        if _replacement in self.operators and self.operators[_replacement].group != '':
                            return f'菲亚梅塔替换不可分组: 房间->{room}, 干员->{_replacement}'
        # 判定替换缺失
        if "菲亚梅塔" in missing_replacements:
            return f'菲亚梅塔替换缺失'
        if '菲亚梅塔' in self.operators:
            for _agent in missing_replacements[:]:
                if _agent in self.operators['菲亚梅塔'].replacement[:-1]:
                    missing_replacements.remove(_agent)
        if len(missing_replacements):
            return f'以下干员替换组缺失：{",".join(missing_replacements)}'
        dorm_names = [k for k in self.plan.keys() if k.startswith("dorm")]
        dorm_names.sort(key=lambda d: d, reverse=False)
        added = []
        # 竖向遍历出效率高到低
        for dorm in dorm_names:
            free_found = False
            for _idx, _dorm in enumerate(self.plan[dorm]):
                if _dorm['agent'] == 'Free' and _idx <= 1:
                    return f'宿舍必须安排2个宿管'
                if _dorm['agent'] != 'Free' and free_found:
                    return f'Free必须连续且安排在宿管后'
                if _dorm['agent'] == 'Free' and not free_found and (dorm + str(_idx)) not in added and len(
                        added) < self.max_resting_count:
                    self.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
                    free_found = True
                    continue
            if not free_found:
                return f'宿舍必须安排至少一个Free'
        # VIP休息位用完后横向遍历
        for dorm in dorm_names:
            for _idx, _dorm in enumerate(self.plan[dorm]):
                if _dorm['agent'] == 'Free' and (dorm + str(_idx)) not in added:
                    self.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
        if len(self.dorm) < self.max_resting_count:
            return f'宿舍Free总数 {len(self.dorm)}小于最大分组数 {self.max_resting_count}'
        # low_free 的排序
        # self.dorm[self.max_resting_count:len(self.dorm)] = sorted(
        #     self.dorm[self.max_resting_count:len(self.dorm)],
        #     key=lambda k: (k.position[0], k.position[1]), reverse=True)
        # 跑单
        for x, y in self.plan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj['replacement'] or '龙舌兰' in obj['replacement']) for obj in y):
                self.run_order_rooms[x] = {}
        # 判定分组排班可能性
        current_high = self.available_free()
        current_low = self.available_free('low')
        for key in self.groups:
            high_count = 0
            low_count = 0
            _replacement = []
            for name in self.groups[key]:
                _candidate = next(
                    (r for r in self.operators[name].replacement if r not in _replacement and r not in ['龙舌兰', '但书']),
                    None)
                if _candidate is None:
                    return f'{key} 分组无法排班,替换组数量不够'
                else:
                    _replacement.append(_candidate)
                if self.operators[name].resting_priority == 'high':
                    high_count += 1
                else:
                    low_count += 1
            if high_count > current_high or low_count > current_low:
                return f'{key} 分组无法排班,宿舍可用高优先{current_high},低优先{current_low}->分组需要高优先{high_count},低优先{low_count}'

    def get_current_room(self, room, bypass=False, current_index=None):
        room_data = {v.current_index: v for k, v in self.operators.items() if v.current_room == room}
        res = [obj['agent'] for obj in self.plan[room]]
        not_found = False
        for idx, op in enumerate(res):
            if idx in room_data:
                res[idx] = room_data[idx].name
            else:
                res[idx] = ''
                if current_index is not None and idx not in current_index:
                    continue
                not_found = True
        if not_found and not bypass:
            return None
        else:
            return res

    def predict_fia(self, operators, fia_mood, hours=240):
        recover_hours = (24 - fia_mood) / 2
        for agent in operators:
            agent.mood -= agent.depletion_rate * recover_hours
            if agent.mood < 0.0:
                return False
        if recover_hours >= hours or 0 < recover_hours < 1:
            return True
        operators.sort(key=lambda x: (x.mood - x.lower_limit) / (x.upper_limit - x.lower_limit), reverse=False)
        fia_mood = operators[0].mood
        operators[0].mood = 24
        return self.predict_fia(operators, fia_mood, hours - recover_hours)

    def reset_dorm_time(self):
        for name in self.operators.keys():
            agent = self.operators[name]
            if agent.room.startswith("dorm"):
                agent.time_stamp = None

    @save_action_to_sqlite_decorator
    def update_detail(self, name, mood, current_room, current_index, update_time=False):
        agent = self.operators[name]
        if update_time:
            if agent.time_stamp is not None and agent.mood > mood:
                agent.depletion_rate = (agent.mood - mood) * 3600 / (
                    (datetime.now() - agent.time_stamp).total_seconds())
            agent.time_stamp = datetime.now()
        # 如果移出宿舍，则清除对应宿舍数据 且重新记录高效组心情
        if agent.current_room.startswith('dorm') and not current_room.startswith('dorm') and agent.is_high():
            self.refresh_dorm_time(agent.current_room, agent.current_index, {'agent': ''})
            if update_time:
                self.time_stamp = datetime.now()
            else:
                self.time_stamp = None
            agent.depletion_rate = 0
        if self.get_dorm_by_name(name)[0] is not None and not current_room.startswith('dorm') and agent.is_high():
            _dorm = self.get_dorm_by_name(name)[1]
            _dorm.name = ''
            _dorm.time = None
        agent.current_room = current_room
        agent.current_index = current_index
        agent.mood = mood
        # 如果是高效组且没有记录时间，则返还index
        if agent.current_room.startswith('dorm') and agent.is_high():
            for dorm in self.dorm:
                if dorm.position[0] == current_room and dorm.position[1] == current_index and dorm.time is None:
                    return current_index
        if agent.name == "菲亚梅塔" and (
                self.operators["菲亚梅塔"].time_stamp is None or self.operators["菲亚梅塔"].time_stamp < datetime.now()):
            return current_index

    def refresh_dorm_time(self, room, index, agent):
        for idx, dorm in enumerate(self.dorm):
            # Filter out resting priority low
            # if idx >= self.max_resting_count:
            #     break
            if dorm.position[0] == room and dorm.position[1] == index:
                # 如果人为高效组，则记录时间
                _name = agent['agent']
                if _name in self.operators.keys() and self.operators[_name].is_high():
                    dorm.name = _name
                    _agent = self.operators[_name]
                    # 如果干员有心情上限，则按比例修改休息时间
                    if _agent.mood != 24:
                        sec_remaining = (_agent.upper_limit - _agent.mood) * (
                            (agent['time'] - _agent.time_stamp).total_seconds()) / (24 - _agent.mood)
                        dorm.time = _agent.time_stamp + timedelta(seconds=sec_remaining)
                    else:
                        dorm.time = agent['time']
                else:
                    dorm.name = ''
                    dorm.time = None
                break

    def correct_dorm(self):
        for idx, dorm in enumerate(self.dorm):
            if dorm.name != "" and dorm.name in self.operators.keys():
                op = self.operators[dorm.name]
                if not (dorm.position[0] == op.current_room and dorm.position[1] == op.current_index):
                    self.dorm[idx].name = ""
                    self.dorm[idx].time = None

    def get_refresh_index(self, room, plan):
        ret = []
        for idx, dorm in enumerate(self.dorm):
            # Filter out resting priority low
            if idx >= self.max_resting_count:
                break
            if dorm.position[0] == room:
                for i, _name in enumerate(plan):
                    if _name in self.operators.keys() and self.operators[_name].is_high() and self.operators[
                        _name].resting_priority == 'high' and not self.operators[_name].room.startswith('dorm'):
                        ret.append(i)
                break
        return ret

    def get_dorm_by_name(self, name):
        for idx, dorm in enumerate(self.dorm):
            if dorm.name == name:
                return idx, dorm
        return None, None

    def add(self, operator):
        if operator.name not in agent_list:
            return
        if operator.name in self.config.keys() and 'RestingPriority' in self.config[operator.name].keys():
            operator.resting_priority = self.config[operator.name]['RestingPriority']
        if operator.name in self.config.keys() and 'ExhaustRequire' in self.config[operator.name].keys():
            operator.exhaust_require = self.config[operator.name]['ExhaustRequire']
        if operator.name in self.config.keys() and 'RestInFull' in self.config[operator.name].keys():
            operator.rest_in_full = self.config[operator.name]['RestInFull']
        if operator.name in self.config.keys() and 'LowerLimit' in self.config[operator.name].keys():
            operator.lower_limit = self.config[operator.name]['LowerLimit']
        if operator.name in self.config.keys() and 'UpperLimit' in self.config[operator.name].keys():
            operator.upper_limit = self.config[operator.name]['UpperLimit']
        if operator.name in self.config.keys() and 'Workaholic' in self.config[operator.name].keys():
            operator.workaholic = self.config[operator.name]['Workaholic']
        self.operators[operator.name] = operator
        # 需要用尽心情干员逻辑
        if (operator.exhaust_require or operator.group in self.exhaust_group) \
                and operator.name not in self.exhaust_agent:
            self.exhaust_agent.append(operator.name)
            if operator.group != '':
                self.exhaust_group.append(operator.group)
        # 干员分组逻辑
        if operator.group != "":
            if operator.group not in self.groups.keys():
                self.groups[operator.group] = [operator.name]
            else:
                self.groups[operator.group].append(operator.name)
        if operator.workaholic and operator.name not in self.workaholic_agent:
            self.workaholic_agent.append(operator.name)

    def available_free(self, free_type='high'):
        ret = 0
        if free_type == 'high':
            idx = 0
            for dorm in self.dorm:
                if dorm.name == '' or (dorm.name in self.operators.keys() and not self.operators[dorm.name].is_high()):
                    ret += 1
                elif dorm.time is not None and dorm.time < datetime.now():
                    logger.info("检测到房间休息完毕，释放Free位")
                    dorm.name = ''
                    ret += 1
                if idx == self.max_resting_count - 1:
                    break
                else:
                    idx += 1
        else:
            idx = self.max_resting_count
            for i in range(idx, len(self.dorm)):
                dorm = self.dorm[i]
                # 释放满休息位
                # TODO 高效组且低优先可以相互替换
                if dorm.name == '' or (dorm.name in self.operators.keys() and not self.operators[dorm.name].is_high()):
                    dorm.name = ''
                    ret += 1
                elif dorm.time is not None and dorm.time < datetime.now():
                    logger.info("检测到房间休息完毕，释放Free位")
                    dorm.name = ''
                    ret += 1
        return ret

    def assign_dorm(self, name):
        is_high = self.operators[name].resting_priority == 'high'
        if is_high:
            _room = next(obj for obj in self.dorm if
                         obj.name not in self.operators.keys() or not self.operators[obj.name].is_high())
        else:
            _room = None
            for i in range(self.max_resting_count, len(self.dorm)):
                if self.dorm[i].name == '':
                    _room = self.dorm[i]
                    break
        _room.name = name
        return _room

    def print(self):
        ret = "{"
        op = []
        dorm = []
        for k, v in self.operators.items():
            op.append("'" + k + "': " + str(vars(v)))
        ret += "'operators': {" + ','.join(op) + "},"
        for v in self.dorm:
            dorm.append(str(vars(v)))
        ret += "'dorms': [" + ','.join(dorm) + "]}"
        return ret


class Dormitory(object):

    def __init__(self, position, name='', time=None):
        self.position = position
        self.name = name
        self.time = time

    def __repr__(self):
        return f"Dormitory(position={self.position},name='{self.name}',time='{self.time}')"


class Operator(object):
    time_stamp = None
    depletion_rate = 0
    workaholic = False

    def __init__(self, name, room, index=-1, group='', replacement=[], resting_priority='low', current_room='',
                 exhaust_require=False,
                 mood=24, upper_limit=24, rest_in_full=False, current_index=-1, lower_limit=0, operator_type="low",
                 depletion_rate=0, time_stamp=None):
        self.name = name
        self.room = room
        self.operator_type = operator_type
        self.index = index
        self.group = group
        self.replacement = replacement
        self.resting_priority = resting_priority
        self.current_room = current_room
        self.exhaust_require = exhaust_require
        self.upper_limit = upper_limit
        self.rest_in_full = rest_in_full
        self.mood = mood
        self.current_index = current_index
        self.lower_limit = lower_limit
        self.depletion_rate = depletion_rate
        self.time_stamp = time_stamp

    def is_high(self):
        return self.operator_type == 'high'

    def need_to_refresh(self, h=2, r=""):
        # 是否需要读取心情
        if self.operator_type == 'high':
            if self.time_stamp is None or (
                    self.time_stamp is not None and self.time_stamp + timedelta(hours=h) < datetime.now()) or (
                    r.startswith("dorm") and not self.room.startswith("dorm")):
                return True
        return False

    def not_valid(self):
        if self.workaholic:
            return False
        if self.operator_type == 'high':
            if not self.room.startswith("dorm") and self.current_room.startswith("dorm"):
                if self.mood == -1 or self.mood == 24:
                    return True
                else:
                    return False
            return self.need_to_refresh(2.5) or self.current_room != self.room or self.index != self.current_index
        return False

    def current_mood(self):
        predict = self.mood
        if self.time_stamp is not None:
            predict = self.mood - self.depletion_rate * (datetime.now() - self.time_stamp).total_seconds() / 3600
        if 0 <= predict <= 24:
            return predict
        else:
            return self.mood

    def __repr__(self):
        return f"Operator(name='{self.name}', room='{self.room}', index={self.index}, group='{self.group}', replacement={self.replacement}, resting_priority='{self.resting_priority}', current_room='{self.current_room}',exhaust_require={self.exhaust_require},mood={self.mood}, upper_limit={self.upper_limit}, rest_in_full={self.rest_in_full}, current_index={self.current_index}, lower_limit={self.lower_limit}, operator_type='{self.operator_type}',depletion_rate={self.depletion_rate},time_stamp='{self.time_stamp}')"
