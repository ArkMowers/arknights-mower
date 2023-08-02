from datetime import datetime, timedelta
import copy
from arknights_mower.utils.datetime import the_same_time


class SchedulerTask:
    time = None
    type = ''
    plan = {}
    meta_flag = False

    def __init__(self, time=None, task_plan={}, task_type='', meta_flag=False):
        if time is None:
            self.time = datetime.now()
        else:
            self.time = time
        self.plan = task_plan
        self.type = task_type
        self.meta_flag = meta_flag

    def time_offset(self, h):
        after_offset = copy.deepcopy(self)
        after_offset.time += timedelta(hours=h)
        return after_offset

    def __str__(self):
        return f"SchedulerTask(time='{self.time}',task_plan={self.plan},task_type='{self.type}',meta_flag={self.meta_flag})"

    def __eq__(self, other):
        if isinstance(other, SchedulerTask):
            return self.type == other.type and self.plan == other.plan and the_same_time(self.time,
                                                                                         other.time) and self.meta_flag == other.meta_flag
        return False
