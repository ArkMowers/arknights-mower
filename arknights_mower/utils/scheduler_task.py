from datetime import datetime, timedelta
import copy
from enum import Enum
from ..utils.log import logger

from arknights_mower.utils.datetime import the_same_time
from arknights_mower.utils import config


class TaskTypes(Enum):
    RUN_ORDER = ("run_order", "跑单", 1)
    FIAMMETTA = ("菲亚梅塔", "肥鸭", 2)
    SHIFT_OFF = ("shifit_off", "下班", 2)
    SHIFT_ON = ("shifit_on", "上班", 2)
    SELF_CORRECTION = ("self_correction", "纠错", 2)
    CLUE_PARTY = ("Impart", "趴体", 2)
    MAA_MALL = ("maa_Mall", "MAA信用购物", 2)
    NOT_SPECIFIC = ("", "空任务", 2)
    RECRUIT = ("recruit", "公招", 2)
    SKLAND = ("skland", "森空岛签到", 2)
    RE_ORDER = ("宿舍排序", "宿舍排序", 2)
    DEPOT=("仓库扫描","仓库扫描",2) #但是我不会写剩下的

    def __new__(cls, value, display_value, priority):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display_value = display_value
        obj.priority = priority
        return obj


def find_next_task(tasks, compare_time=None, task_type='', compare_type='<', meta_data=''):
    if compare_type == '=':
        return next((e for e in tasks if the_same_time(e.time, compare_time) and (
            True if task_type == '' else task_type == e.type) and (
                         True if meta_data == '' else meta_data in e.meta_data)), None)
    elif compare_type == '>':
        return next((e for e in tasks if (True if compare_time is None else e.time > compare_time) and (
            True if task_type == '' else task_type == e.type) and (
                         True if meta_data == '' else meta_data in e.meta_data)), None)
    else:
        return next((e for e in tasks if (True if compare_time is None else e.time < compare_time) and (
            True if task_type == '' else task_type == e.type) and (
                         True if meta_data == '' else meta_data in e.meta_data)), None)


def scheduling(tasks, run_order_delay=5, execution_time=0.75, time_now=None):
    # execution_time per room
    if time_now is None:
        time_now = datetime.now()
    if len(tasks) > 0:
        tasks.sort(key=lambda x: x.time)

        # 任务间隔最小时间（5分钟）
        min_time_interval = timedelta(minutes=run_order_delay)

        # 初始化变量以跟踪上一个优先级0任务和计划执行时间总和
        last_priority_0_task = None
        total_execution_time = 0

        # 遍历任务列表
        for i, task in enumerate(tasks):
            current_time = time_now
            # 判定任务堆积，如果第一个任务已经超时，则认为任务堆积
            if task.type.priority == 1 and current_time > task.time:
                total_execution_time += (current_time - task.time).total_seconds() / 60

            if task.type.priority == 1:
                if last_priority_0_task is not None:
                    time_difference = task.time - last_priority_0_task.time
                    if config.grandet_mode and time_difference < min_time_interval and time_now < last_priority_0_task.time:
                        logger.info("检测到跑单任务过于接近，准备修正跑单时间")
                        return last_priority_0_task
                # 更新上一个优先级0任务和总执行时间
                last_priority_0_task = task
                total_execution_time = 0
            else:
                # 找到下一个优先级0任务的位置
                next_priority_0_index = -1
                for j in range(i + 1, len(tasks)):
                    if tasks[j].type.priority == 1:
                        next_priority_0_index = j
                        break
                # 如果其他任务的总执行时间超过了下一个优先级0任务的执行时间，调整它们的时间
                if next_priority_0_index > -1:
                    for j in range(i, next_priority_0_index):
                        # 菲亚充能/派对内置3分钟，线索购物内置1分钟
                        task_time = 0 if len(tasks[j].plan) > 0 and tasks[j].type not in [TaskTypes.FIAMMETTA,
                                                                                          TaskTypes.CLUE_PARTY] else (
                            3 if tasks[j].type in [TaskTypes.FIAMMETTA, TaskTypes.CLUE_PARTY] else 1)
                        # 其他任务按照 每个房间*预设执行时间算 默认 45秒
                        estimate_time = len(tasks[j].plan) * execution_time if task_time == 0 else task_time
                        if timedelta(minutes=total_execution_time + estimate_time) + time_now < \
                                tasks[
                                    j].time:
                            total_execution_time = 0
                        else:
                            total_execution_time += estimate_time
                    if timedelta(minutes=total_execution_time) + time_now > tasks[next_priority_0_index].time:
                        logger.info("检测到任务可能影响到下次跑单修改任务至跑单之后")
                        logger.debug('||'.join([str(t) for t in tasks]))
                        next_priority_0_time = tasks[next_priority_0_index].time
                        for j in range(i, next_priority_0_index):
                            tasks[j].time = next_priority_0_time + timedelta(seconds=1)
                            next_priority_0_time = tasks[j].time
                        logger.debug('||'.join([str(t) for t in tasks]))
                        break
        tasks.sort(key=lambda x: x.time)


def check_dorm_ordering(tasks, op_data):
    # 仅当下班的时候才触发宿舍排序任务
    plan = op_data.plan
    if len(tasks) == 0:
        return
    if tasks[0].type == TaskTypes.SHIFT_OFF and tasks[0].meta_data == "":
        extra_plan = {}
        other_plan = {}
        for room, v in tasks[0].plan.items():
            # 非宿舍则不需要清空
            if room.startswith('dorm'):
                # 是否检查过vip位置
                pass_first_free = False
                for idx, agent in enumerate(v):
                    # 如果当前位置非宿管 且无人员变动（有变动则是下班干员）
                    if "Free" == plan[room][idx].agent and agent == "Current":
                        # 如果高优先不变，则跳过逻辑判定
                        if not pass_first_free:
                            break
                        current = next((obj for obj in op_data.operators.values() if
                                        obj.current_room == room and obj.current_index == idx), None)
                        if current:
                            if current.resting_priority != "high":
                                # 替换成高优先的实际名字
                                if current.is_high():
                                    v[idx] = current.name
                                if room not in extra_plan:
                                    extra_plan[room] = copy.deepcopy(v)
                                # 新生成移除任务 --> 换成任意干员
                                extra_plan[room][idx] = "Free"
                    if "Free" == plan[room][idx].agent and not pass_first_free:
                        pass_first_free = True
            else:
                other_plan[room] = v
        tasks[0].meta_data = "宿舍排序完成"
        if extra_plan:
            for k, v in other_plan.items():
                del tasks[0].plan[k]
                extra_plan[k] = v
            tasks.insert(0, SchedulerTask(task_plan=extra_plan, time=tasks[0].time - timedelta(seconds=1),
                                          task_type=TaskTypes.RE_ORDER))


class SchedulerTask:
    time = None
    type = ''
    plan = {}
    meta_data = ''

    def __init__(self, time=None, task_plan={}, task_type='', meta_data=""):
        if time is None:
            self.time = datetime.now()
        else:
            self.time = time
        self.plan = task_plan
        if task_type == "":
            self.type = TaskTypes.NOT_SPECIFIC
        else:
            self.type = task_type
        self.meta_data = meta_data

    def format(self, time_offset=0):
        res = copy.deepcopy(self)
        res.time += timedelta(hours=time_offset)
        res.type = res.type.display_value
        if res.type == "空任务" and res.meta_data:
            res.type = res.meta_data
        return res

    def __str__(self):
        return f"SchedulerTask(time='{self.time}',task_plan={self.plan},task_type={self.type},meta_data='{self.meta_data}')"

    def __eq__(self, other):
        if isinstance(other, SchedulerTask):
            return self.type == other.type and self.plan == other.plan and the_same_time(self.time,
                                                                                         other.time)
        return False
