from datetime import datetime, timedelta


class SchedulerTask(object):
    time = datetime.now()
    type = ''
    plan = {}

    def __init__(self, time, plan={}, task_type=''):
        self.config = time
        self.plan = plan
        self.type = task_type
