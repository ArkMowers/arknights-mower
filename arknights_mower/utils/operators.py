from datetime import datetime, timedelta
from ..data import agent_list, agent_arrange_order, base_room_list
from ..solvers.record import save_action_to_sqlite_decorator
from ..utils.log import logger
import copy
from evalidate import Expr, base_eval_model


class SkillUpgradeSupport(object):
    support_class = None
    level = 1
    efficiency = 0
    half_off = False
    add_on = False
    match = False
    use_booster = True
    name = ''
    swap_name = ''

    def __init__(self, name, skill_level, efficiency, match, swap_name='艾丽妮'):
        self.name = name
        self.level = skill_level
        self.efficiency = efficiency
        self.match = match
        if self.level > 1:
            self.half_off = True
        self.swap_name = swap_name

class Operators(object):
    config = None
    operators = None
    exhaust_agent = []
    exhaust_group = []
    groups = None
    dorm = []
    plan = None

    global_plan = None
    plan_condition = []
    shadow_copy = {}
    current_room_changed_callback = None
    first_init = True
    skill_upgrade_supports = []

    def __init__(self, plan):
        self.operators = {}
        self.groups = {}
        self.exhaust_agent = []
        self.exhaust_group = []
        self.dorm = []
        self.workaholic_agent = []
        self.free_blacklist = []
        self.global_plan = plan
        self.backup_plans = plan["backup_plans"]
        # 切换默认排班
        self.swap_plan([False] * (len(self.backup_plans)))
        self.run_order_rooms = {}
        self.clues = []
        self.current_room_changed_callback = None
        self.party_time = None

        self.eval_model = base_eval_model.clone()
        self.eval_model.nodes.extend(["Call", "Attribute"])
        self.eval_model.attributes.extend(
            ["operators", "party_time", "is_working", "is_resting", "current_mood", "current_room"])

    def __repr__(self):
        return f'Operators(operators={self.operators})'

    def calculate_switch_time(self, support: SkillUpgradeSupport):
        hour = 0
        half_off = support.half_off
        level = support.level
        match = support.match
        efficiency = support.efficiency
        same = support.name == support.swap_name
        if level == 1:
            half_off = False
        # if left_minutes > 0 or left_hours > 0:
        #     hour = left_minutes / 60 + left_hours
        # 基本5%
        basic = 5
        if support.add_on:
            # 阿斯卡伦
            basic += 5
        if hour == 0:
            hour = level * 8
        if half_off:
            hour = hour / 2
        left = 0
        if not same:
            left = 5 * (100 + basic + (30 if match else 0)) / 100
            left = hour - left
        else:
            left = hour
        return left * 100 / (100 + efficiency + basic)

    def swap_plan(self, condition, refresh=False):
        self.plan = copy.deepcopy(self.global_plan["default_plan"].plan)
        self.config = copy.deepcopy(self.global_plan["default_plan"].config)
        for index, success in enumerate(condition):
            if success:
                self.plan, self.config = self.merge_plan(index, self.config, self.plan)
        self.plan_condition = condition
        if refresh:
            self.first_init = True
            error = self.init_and_validate(True)
            self.first_init = False
            if error:
                return error

    def merge_plan(self, idx, ext_config, default_plan=None):
        if default_plan is None:
            default_plan = copy.deepcopy(self.global_plan["default_plan"].plan)
        plan = copy.deepcopy(self.global_plan["backup_plans"][idx])
        # 更新切换排班表
        for key, value in plan.plan.items():
            if key in default_plan:
                for idx, operator in enumerate(value):
                    if operator.agent != "Current":
                        default_plan[key][idx] = operator
        return default_plan, ext_config.merge_config(plan.config)

    def generate_conditions(self, n):
        if n == 1:
            return [[True], [False]]
        else:
            prev_conditions = self.generate_conditions(n - 1)
            conditions = []
            for condition in prev_conditions:
                conditions.append(condition + [True])
                conditions.append(condition + [False])
            return conditions

    def init_and_validate(self, update=False):
        self.groups = {}
        self.exhaust_agent = []
        self.exhaust_group = []
        self.workaholic_agent = []
        self.shadow_copy = copy.deepcopy(self.operators)
        self.operators = {}
        for room in self.plan.keys():
            for idx, data in enumerate(self.plan[room]):
                if data.agent not in agent_list and data.agent != 'Free':
                    return f'干员名输入错误: 房间->{room}, 干员->{data.agent}'
                if data.agent in ['龙舌兰', '但书']:
                    return f'高效组不可用龙舌兰，但书 房间->{room}, 干员->{data.agent}'
                if data.agent == '菲亚梅塔' and idx == 1:
                    return f'菲亚梅塔不能安排在2号位置 房间->{room}, 干员->{data.agent}'
                if data.agent == '菲亚梅塔' and not room.startswith('dorm'):
                    return f'菲亚梅塔必须安排在宿舍'
                if data.agent == 'Free' and not room.startswith('dorm'):
                    return f'Free只能安排在宿舍 房间->{room}, 干员->{data.agent}'
                if data.agent in self.operators and data.agent != "Free":
                    return f'高效组干员不可重复 房间->{room},{self.operators[data.agent].room}, 干员->{data.agent}'
                self.add(Operator(data.agent, room, idx, data.group, data.replacement, 'high',
                                  operator_type="high"))
        missing_replacements = []
        for room in self.plan.keys():
            if room.startswith("dorm") and len(self.plan[room]) != 5:
                return f'宿舍 {room} 人数少于5人'
            for idx, data in enumerate(self.plan[room]):
                # 菲亚梅塔替换组做特例判断
                if "龙舌兰" in data.replacement and "但书" in data.replacement:
                    return f'替换组不可同时安排龙舌兰和但书 房间->{room}, 干员->{data.agent}'
                if "菲亚梅塔" in data.replacement:
                    return f'替换组不可安排菲亚梅塔 房间->{room}, 干员->{data.agent}'
                r_count = len(data.replacement)
                if "龙舌兰" in data.replacement or "但书" in data.replacement:
                    r_count -= 1
                if r_count <= 0 and ((data.agent != 'Free' and (not room.startswith("dorm"))) or data.agent == "菲亚梅塔"):
                    missing_replacements.append(data.agent)
                for _replacement in data.replacement:
                    if _replacement not in agent_list and data.agent != 'Free':
                        return f'干员名输入错误: 房间->{room}, 干员->{_replacement}'
                    if data.agent != '菲亚梅塔':
                        # 普通替换
                        if _replacement in self.operators and self.operators[_replacement].is_high():
                            return f'替换组不可用高效组干员: 房间->{room}, 干员->{_replacement}'
                        self.add(Operator(_replacement, ""))
                    else:
                        if _replacement not in self.operators:
                            return f'菲亚梅塔替换不在高效组列: 房间->{room}, 干员->{_replacement}'
                        if _replacement in self.operators and not self.operators[_replacement].is_high():
                            return f'菲亚梅塔替换只能为高效组干员: 房间->{room}, 干员->{_replacement}'
        # 判定替换缺失
        if "菲亚梅塔" in missing_replacements:
            return f'菲亚梅塔替换缺失'
        if len(missing_replacements):
            return f'以下干员替换组缺失：{",".join(missing_replacements)}'
        dorm_names = [k for k in self.plan.keys() if k.startswith("dorm")]
        dorm_names.sort(key=lambda d: d, reverse=False)
        added = []
        # 竖向遍历出效率高到低
        if not update:
            for dorm in dorm_names:
                free_found = False
                for _idx, _dorm in enumerate(self.plan[dorm]):
                    if _dorm.agent == 'Free' and _idx <= 1:
                        if "波登可" not in [_agent.agent for _agent in self.plan[dorm]]:
                            return f'宿舍必须安排2个宿管'
                    if _dorm.agent != 'Free' and free_found:
                        return f'Free必须连续且安排在宿管后'
                    if _dorm.agent == 'Free' and not free_found and (dorm + str(_idx)) not in added and len(
                            added) < self.config.max_resting_count:
                        self.dorm.append(Dormitory((dorm, _idx)))
                        added.append(dorm + str(_idx))
                        free_found = True
                        continue
                if not free_found:
                    return f'宿舍必须安排至少一个Free'
            # VIP休息位用完后横向遍历
            for dorm in dorm_names:
                for _idx, _dorm in enumerate(self.plan[dorm]):
                    if _dorm.agent == 'Free' and (dorm + str(_idx)) not in added:
                        self.dorm.append(Dormitory((dorm, _idx)))
                        added.append(dorm + str(_idx))
        else:
            for key, value in self.shadow_copy.items():
                if key not in self.operators:
                    self.add(Operator(key, ""))
        if len(self.dorm) < self.config.max_resting_count:
            return f'宿舍Free总数 {len(self.dorm)}小于最大分组数 {self.config.max_resting_count}'
        # 跑单
        for x, y in self.plan.items():
            if not x.startswith('room'): continue
            if any(('但书' in obj.replacement or '龙舌兰' in obj.replacement) for obj in y):
                self.run_order_rooms[x] = {}
        # 判定分组排班可能性
        current_high = self.config.max_resting_count
        current_low = len(self.dorm) - self.config.max_resting_count
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
                if self.operators[name].workaholic: continue
                if self.operators[name].resting_priority == 'high':
                    high_count += 1
                else:
                    low_count += 1
            if high_count > current_high or low_count > current_low:
                return f'{key} 分组无法排班,宿舍可用高优先{current_high},低优先{current_low}->分组需要高优先{high_count},低优先{low_count}'
        # 设定令夕模式的心情阈值
        self.init_mood_limit()
        for name in self.workaholic_agent:
            if name not in self.config.free_blacklist:
                self.config.free_blacklist.append(name)
        logger.info('宿舍黑名单：' + str(self.config.free_blacklist))

    def set_mood_limit(self, name, upper_limit=24, lower_limit=0):
        if name in self.operators:
            self.operators[name].upper_limit = upper_limit
            self.operators[name].lower_limit = lower_limit
            logger.info(f"自动设置{name}心情下限为{lower_limit},上限为{upper_limit}")

    def init_mood_limit(self):
        # 设置心情阈值 for 夕，令，
        if self.config.ling_xi == 1:
            self.set_mood_limit('令', upper_limit=12)
            self.set_mood_limit('夕', lower_limit=12)
        elif self.config.ling_xi == 2:
            self.set_mood_limit('夕', upper_limit=12)
            self.set_mood_limit('令', lower_limit=12)
        elif self.config.ling_xi == 0:
            self.set_mood_limit('夕')
            self.set_mood_limit('令')
        # 设置同组心情阈值
        finished = []
        for name in ["夕", "令"]:
            if name in self.operators and self.operators[name].group != "" and self.operators[
                name].group not in finished:
                for group_name in self.groups[self.operators[name].group]:
                    if group_name not in ["夕", "令"]:
                        if self.config.ling_xi in [1, 2]:
                            self.set_mood_limit(group_name, lower_limit=12)
                        elif self.config.ling_xi == 0:
                            self.set_mood_limit(group_name, lower_limit=0)
                finished.append(self.operators[name].group)

        # 设置铅踝心情阈值
        # 三种情况：
        # 1. 铅踝不是主力：不管
        # 2. 铅踝是红云组主力，设置心情上限 12、下限 8，效率 37%
        # 3. 铅踝是普通主力：设置心情下限 20，效率 30%
        TOTTER = "铅踝"
        VERMEIL = "红云"
        if TOTTER in self.operators and self.operators[TOTTER].operator_type == "high":
            if VERMEIL in self.operators and self.operators[VERMEIL].operator_type == "high" and self.operators[
                VERMEIL].room == self.operators[TOTTER].room:
                self.set_mood_limit(TOTTER, upper_limit=12, lower_limit=8)
            else:
                self.set_mood_limit(TOTTER, upper_limit=24, lower_limit=20)

    def evaluate_expression(self, expression):
        try:
            result = Expr(expression, self.eval_model).eval({"op_data": self})
            return result
        except Exception as e:
            logger.exception(f"Error evaluating expression: {e}")
            return None

    def get_current_room(self, room, bypass=False, current_index=None):
        room_data = {v.current_index: v for k, v in self.operators.items() if v.current_room == room}
        res = [obj.agent for obj in self.plan[room]]
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
        # 如果移出宿舍，则清除对应宿舍数据 且重新记录高效组心情（如果有备用班，则跳过高效组判定）
        if agent.current_room.startswith('dorm') and not current_room.startswith('dorm') and (
                agent.is_high() or self.backup_plans):
            self.refresh_dorm_time(agent.current_room, agent.current_index, {'agent': ''})
            if update_time:
                self.time_stamp = datetime.now()
            else:
                self.time_stamp = None
            agent.depletion_rate = 0
        if self.get_dorm_by_name(name)[0] is not None and not current_room.startswith('dorm') and (
                agent.is_high() or self.backup_plans):
            _dorm = self.get_dorm_by_name(name)[1]
            _dorm.name = ''
            _dorm.time = None
        agent.current_room = current_room
        agent.current_index = current_index
        agent.mood = mood
        # 如果是高效组且没有记录时间，则返还index
        if agent.current_room.startswith('dorm') and (agent.is_high() or self.backup_plans):
            for dorm in self.dorm:
                if dorm.position[0] == current_room and dorm.position[1] == current_index and dorm.time is None:
                    return current_index
        if agent.name == "菲亚梅塔" and (
                self.operators["菲亚梅塔"].time_stamp is None or self.operators["菲亚梅塔"].time_stamp < datetime.now()):
            return current_index

    def refresh_dorm_time(self, room, index, agent):
        for idx, dorm in enumerate(self.dorm):
            # Filter out resting priority low
            # if idx >= self.config.max_resting_count:
            #     break
            if dorm.position[0] == room and dorm.position[1] == index:
                # 如果人为高效组，则记录时间
                _name = agent["agent"]
                if _name in self.operators.keys() and (self.operators[_name].is_high() or self.config.free_room):
                    dorm.name = _name
                    _agent = self.operators[_name]
                    # 如果干员有心情上限，则按比例修改休息时间
                    if _agent.mood != 24:
                        sec_remaining = (_agent.upper_limit - _agent.mood) * (
                            (agent['time'] - _agent.time_stamp).total_seconds()) / (24 - _agent.mood)
                        dorm.time = _agent.time_stamp + timedelta(seconds=sec_remaining)
                    else:
                        dorm.time = agent['time']
                elif _name in agent_list:
                    self.add(Operator(_name, ""))
                    dorm.name = _name
                    dorm.time = agent['time']
                break

    def correct_dorm(self):
        for idx, dorm in enumerate(self.dorm):
            if dorm.name != "" and dorm.name in self.operators.keys():
                op = self.operators[dorm.name]
                if not (dorm.position[0] == op.current_room and dorm.position[1] == op.current_index):
                    self.dorm[idx].name = ""
                    self.dorm[idx].time = None

    def get_train_support(self):
        for name in self.operators.keys():
            agent = self.operators[name]
            if agent.current_room == 'train' and agent.current_index == 0:
                return agent.name
        return None

    def get_refresh_index(self, room, plan):
        ret = []
        if room.startswith("dorm") and self.config.free_room:
            return [i for i, x in enumerate(self.plan[room]) if x == "Free"]
        for idx, dorm in enumerate(self.dorm):
            # Filter out resting priority low
            if idx >= self.config.max_resting_count:
                if not self.config.free_room:
                    break
            if dorm.position[0] == room:
                for i, _name in enumerate(plan):
                    if _name not in self.operators.keys():
                        self.add(Operator(_name, ""))
                    if not self.config.free_room:
                        if self.operators[_name].is_high() and not self.operators[
                            _name].room.startswith('dorm'):
                            ret.append(i)
                    elif not self.operators[
                        _name].room.startswith('dorm'):
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
        if self.config.get_config(operator.name, 3):
            operator.resting_priority = "low"
        operator.exhaust_require = self.config.get_config(operator.name, 1)
        operator.rest_in_full = self.config.get_config(operator.name, 0)
        operator.workaholic = self.config.get_config(operator.name, 2)
        operator.refresh_order_room = self.config.get_config(operator.name, 5)
        if operator.name in agent_arrange_order:
            operator.arrange_order = agent_arrange_order[operator.name]
        # 复制基建数据
        if operator.name in self.shadow_copy:
            exist = self.shadow_copy[operator.name]
            operator.mood = exist.mood
            operator.time_stamp = exist.time_stamp
            operator.depletion_rate = exist.depletion_rate
            operator.current_room = exist.current_room
            operator.current_index = exist.current_index
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
        freeName = []
        if free_type == 'high':
            idx = 0
            for dorm in self.dorm:
                if dorm.name == '' or (dorm.name in self.operators.keys() and not self.operators[dorm.name].is_high()):
                    ret += 1
                elif dorm.time is not None and dorm.time < datetime.now():
                    logger.info(f"检测到房间休息完毕，释放{dorm.name}宿舍位")
                    freeName.append(dorm.name)
                    dorm.name = ''
                    ret += 1
                if idx == self.config.max_resting_count - 1:
                    break
                else:
                    idx += 1
        else:
            idx = self.config.max_resting_count
            for i in range(idx, len(self.dorm)):
                dorm = self.dorm[i]
                # 释放满休息位
                # TODO 高效组且低优先可以相互替换
                if dorm.name == '' or (dorm.name in self.operators.keys() and not self.operators[dorm.name].is_high()):
                    dorm.name = ''
                    ret += 1
                elif dorm.time is not None and dorm.time < datetime.now():
                    logger.info(f"检测到房间休息完毕，释放{dorm.name}宿舍位")
                    freeName.append(dorm.name)
                    dorm.name = ''
                    ret += 1
        if len(freeName) > 0:
            for name in freeName:
                if name in agent_list:
                    self.operators[name].mood = 24
                    self.operators[name].depletion_rate = 0
                    self.operators[name].time_stamp = datetime.now()
        return ret

    def assign_dorm(self, name):
        is_high = self.operators[name].resting_priority == 'high'
        if is_high:
            _room = next(obj for obj in self.dorm if
                         obj.name not in self.operators.keys() or not self.operators[obj.name].is_high())
        else:
            _room = None
            for i in range(self.config.max_resting_count, len(self.dorm)):
                if self.dorm[i].name == '':
                    _room = self.dorm[i]
                    break
        _room.name = name
        return _room

    def get_current_operator(self, room, index):
        for key, value in self.operators.items():
            if value.current_room == room and value.current_index == index:
                return value
        return None

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
    arrange_order = [2, "false"]

    def __init__(self, name, room, index=-1, group='', replacement=[], resting_priority='low', current_room='',
                 exhaust_require=False,
                 mood=24, upper_limit=24, rest_in_full=False, current_index=-1, lower_limit=0, operator_type="low",
                 depletion_rate=0, time_stamp=None, refresh_order_room=None):
        if refresh_order_room is not None:
            self.refresh_order_room = refresh_order_room
        self.refresh_order_room = [False, []]
        self.name = name
        self.room = room
        self.operator_type = operator_type
        self.index = index
        self.group = group
        self.replacement = replacement
        self.resting_priority = resting_priority
        self._current_room = None
        self.current_room = current_room
        self.exhaust_require = exhaust_require
        self.upper_limit = upper_limit
        self.rest_in_full = rest_in_full
        self.mood = mood
        self.current_index = current_index
        self.lower_limit = lower_limit
        self.depletion_rate = depletion_rate
        self.time_stamp = time_stamp

    @property
    def current_room(self):
        return self._current_room

    @current_room.setter
    def current_room(self, value):
        if self._current_room != value:
            self._current_room = value
            if Operators.current_room_changed_callback and self.refresh_order_room[0]:
                Operators.current_room_changed_callback(self)

    def is_high(self):
        return self.operator_type == 'high'

    def is_resting(self):
        return self.current_room.startswith("dorm")

    def is_working(self):
        return self.current_room in base_room_list and not self.is_resting()

    def need_to_refresh(self, h=2, r=""):
        # 是否需要读取心情
        if self.time_stamp is None or (
                self.time_stamp is not None and self.time_stamp + timedelta(hours=h) < datetime.now()) or (
                r.startswith("dorm") and not self.room.startswith("dorm")):
            return True

    def not_valid(self):
        if self.room == "train":
            return False
        if self.workaholic:
            return self.current_room != self.room or self.index != self.current_index
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
        return f"Operator(name='{self.name}', room='{self.room}', index={self.index}, group='{self.group}', replacement={self.replacement}, resting_priority='{self.resting_priority}', current_room='{self.current_room}',exhaust_require={self.exhaust_require},mood={self.mood}, upper_limit={self.upper_limit}, rest_in_full={self.rest_in_full}, current_index={self.current_index}, lower_limit={self.lower_limit}, operator_type='{self.operator_type}',depletion_rate={self.depletion_rate},time_stamp='{self.time_stamp}',refresh_order_room = {self.refresh_order_room})"
