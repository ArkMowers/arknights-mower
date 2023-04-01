from datetime import datetime, timedelta
from ..data import agent_list


class Operators(object):
    config = None
    operators = None
    exhaust_agent = []
    exhaust_group = []
    groups = None
    dorm = []
    max_resting_count = 4

    def __init__(self, config,max_resting_count):
        self.config = config
        self.operators = {}
        self.groups = {}
        self.exhaust_agent = []
        self.exhaust_group = []
        self.dorm = []
        self.max_resting_count = max_resting_count

    def update_detail(self,name, mood, current_room, current_index):
        agent = self.operators[name]

        agent.time_stamp = datetime.now()
        # 如果移出宿舍，则清除对应宿舍数据 且重新记录高效组心情
        if agent.current_room.startswith('dorm') and not current_room.startswith('dorm') and agent.is_high():
            self.refresh_dorm_time(agent.current_room,agent.current_index,{'agent':''})
            agent.time_stamp = None
        agent.current_room = current_room
        agent.current_index = current_index
        agent.mood = mood
        # 如果是高效组且没有记录时间，则返还index
        if agent.current_room.startswith('dorm') and agent.is_high():
            for dorm in self.dorm:
                if dorm.position[0] == current_room and dorm.position[1] == current_index and dorm.time is None:
                    return current_index

    def refresh_dorm_time(self,room,index, agent):
        for idx, dorm in enumerate(self.dorm):
            # Filter out resting priority low
            # if idx >= self.max_resting_count:
            #     break
            if dorm.position[0] == room and dorm.position[1] == index:
                # 如果人为高效组，则记录时间
                _name = agent['agent']
                if _name in self.operators.keys() and self.operators[_name].is_high():
                    dorm.name = _name
                    dorm.time = agent['time']
                else:
                    dorm.name = ''
                    dorm.time = None
                break

    def get_refresh_index(self,room,plan):
        ret = []
        for idx, dorm in enumerate(self.dorm):
            # Filter out resting priority low
            if idx >= self.max_resting_count:
                break
            if dorm.position[0] == room:
                for i,_name in enumerate(plan):
                    if _name in self.operators.keys() and self.operators[_name].is_high() and self.operators[_name].resting_priority=='high' and not self.operators[_name].room.startswith('dorm'):
                        ret.append(i)
                break
        return ret

    def get_dorm_by_name(self,name):
        for idx, dorm in enumerate(self.dorm):
            if dorm.name == name:
                return idx, dorm
        return None,None

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

    def available_free(self, free_type='high', count=4):
        ret = 0
        if free_type == 'high':
            idx = 0
            for dorm in self.dorm:
                if dorm.name =='' or (dorm.name in self.operators.keys() and not self.operators[dorm.name].is_high()):
                    ret += 1
                if idx == count - 1:
                    break
                else:
                    idx += 1
        else:
            idx = -1
            while idx < 0:
                dorm = self.dorm[idx]
                if dorm.name =='' or (dorm.name in self.operators.keys() and not self.operators[dorm.name].is_high()):
                    ret += 1
                if idx == count - len(self.dorm):
                    break
                else:
                    idx -= 1
        return ret

    def assign_dorm(self,name):
        is_high = self.operators[name].resting_priority=='high'
        if is_high:
            _room = next(obj for obj in self.dorm if obj.name not in self.operators.keys() or not self.operators[obj.name].is_high())
        else:
            _room = None
            idx = -1
            while idx < 0:
                if self.dorm[idx].name=='':
                    _room = self.dorm[idx]
                    break
                else:
                    idx -= 1
        _room.name = name
        return _room

    def print(self):
        ret = "{"
        op = []
        dorm = []
        for k, v in self.operators.items():
            op.append("'"+k+"': "+ str(vars(v)))
        ret += "'operators': {" + ','.join(op)+"},"
        for v in self.dorm:
            dorm.append(str(vars(v)))
        ret += "'dorms': [" + ','.join(dorm) + "]}"
        return ret


class Dormitory(object):

    def __init__(self, position, name='', time=None):
        self.position = position
        self.name = name
        self.time = time


class Operator(object):
    time_stamp = None

    def __init__(self, name, room, index=-1, group='', replacement=[], resting_priority='low', current_room='',
                 exhaust_require=False,
                 mood=24, upper_limit=24, rest_in_full=False, current_index=-1, lower_limit=0, operator_type="low"):
        self.name = name
        self.room = room
        self.operator_type = operator_type
        # if room.startswith('dormitory'):
        #     self.operator_type = "low"
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

    def is_high(self):
        return self.operator_type =='high'

    def need_to_refresh(self, h=2):
        # 是否需要读取心情
        if self.operator_type == 'high':
            if self.time_stamp is None or (
                    self.time_stamp is not None and self.time_stamp + timedelta(hours=h) < datetime.now()):
                return True
        return False

    def not_valid(self):
        if self.operator_type == 'high':
            if not self.room.startswith("dorm") and self.current_room.startswith("dorm"):
                if self.mood == -1 or self.mood == 24:
                    return True
                else:
                    return False
            return self.need_to_refresh() or self.current_room != self.room or self.index != self.current_index
        return False
