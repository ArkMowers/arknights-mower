from datetime import datetime, timedelta
import copy
from enum import Enum
from ..utils.log import logger

from arknights_mower.utils.datetime import the_same_time


class TaskTypes(Enum):
    RUN_ORDER = ("run_order", "跑单", 1)
    FIAMMETTA = ("菲亚梅塔", "肥鸭", 2)
    SHIFT_OFF = ("shifit_off", "下班", 2)
    SHIFT_ON = ("shifit_on", "上班", 2)
    SELF_CORRECTION = ("self_correction", "纠错", 2)
    CLUE_PARTY = ("Impart", "趴体", 2)
    MAA_MALL = ("maa_Mall", "MAA信用购物", 2)
    NOT_SPECIFIC = ("", "三无", 2)

    def __new__(cls, value, display_value, priority):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display_value = display_value
        obj.priority = priority
        return obj


def find_next_task(tasks, compare_time=None, task_type='', compare_type='<',meta_data =''):
    if compare_type == '=':
        return next((e for e in tasks if the_same_time(e.time, compare_time) and (
            True if task_type == '' else task_type == e.type) and (True if meta_data == '' else meta_data in e.meta_data)), None)
    elif compare_type == '>':
        return next((e for e in tasks if (True if compare_time is None else e.time > compare_time) and (
            True if task_type == '' else task_type == e.type) and (True if meta_data == '' else meta_data in e.meta_data)), None)
    else:
        return next((e for e in tasks if (True if compare_time is None else e.time < compare_time) and (
            True if task_type == '' else task_type == e.type) and (True if meta_data == '' else meta_data in e.meta_data)), None)


def scheduling(tasks, run_order_delay=5, execution_time=45):
    # execution_time per room
    if len(tasks) > 0:
        tasks.sort(key=lambda x: x.time, reverse=False)

        # 固定两单时间间隔
        min_time_difference_between_priority1 = timedelta(minutes=run_order_delay)

        # 队列时间逻辑
        for i in range(1, len(tasks)):
            time_difference = tasks[i].time - tasks[i - 1].time
            if tasks[i].type.priority == 1 and tasks[i - 1].type.priority == 1:
                if time_difference < min_time_difference_between_priority1:
                    # 如果跑单时间过于接近，则返回
                    logger.info("检测到跑单任务过于接近，准备修正跑单时间")
                    return tasks[i - 1]
            elif tasks[i].type.priority == 1:
                # 如果跑单前 时间超过预计执行之间，则延后执行
                sec_difference = len(tasks[i - 1].plan) * execution_time
                if time_difference < timedelta(seconds=sec_difference):
                    tasks[i - 1].time = tasks[i].time + timedelta(seconds=1)
                    logger.info("检测到换班任务与跑单过于接近，延后换班任务")
        tasks.sort(key=lambda x: x.time, reverse=False)


class SchedulerTask:
    time = None
    type = ''
    plan = {}
    meta_data = ''

    def __init__(self, time=None, task_plan={}, task_type='', meta_data = ""):
        if time is None:
            self.time = datetime.now()
        else:
            self.time = time
        self.plan = task_plan
        if task_type =="":
            self.type = TaskTypes.NOT_SPECIFIC
        else :
            self.type = task_type
        self.meta_data = meta_data

    def time_offset(self, h):
        after_offset = copy.deepcopy(self)
        after_offset.time += timedelta(hours=h)
        after_offset.type = after_offset.type.display_value
        return after_offset

    def format(self, time_offset):
        res = copy.deepcopy(self)
        res.time += timedelta(hours=time_offset)
        res.type = res.type.display_value
        return res

    def __str__(self):
        return f"SchedulerTask(time='{self.time}',task_plan={self.plan},task_type={self.type},meta_data='{self.meta_data}')"

    def __eq__(self, other):
        if isinstance(other, SchedulerTask):
            return self.type == other.type and self.plan == other.plan and the_same_time(self.time,
                                                                                         other.time)
        return False
