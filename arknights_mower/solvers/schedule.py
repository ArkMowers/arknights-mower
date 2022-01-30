import time
import datetime

from functools import cmp_to_key
from collections.abc import Callable

from ..utils.device import Device
from ..utils.log import logger
from ..utils.solver import BaseSolver
from ..utils.priority_queue import PriorityQueue
from ..utils.datetime import the_same_day
from ..utils.operation import operation_times
from ..utils.recognize import Recognizer
from ..utils.operation import parse_operation_params
from .operation import OpeSolver

task_priority = {'base': 0, 'recruit': 1, 'mail': 2, 'credit': 3, 'shop': 4, 'mission': 5, 'operation': 6}


def operation_one(args: list[str] = [], device: Device = None) -> bool:
    """
    只为 schedule 模块使用的单次作战操作
    目前不支持使用源石和体力药

    返回值表示该次作战是否成功
    完成剿灭不算成功
    """
    level, _, _, _, eliminate = parse_operation_params(args)
    remain_plan = OpeSolver(device).run(level, 1, 0, 0, eliminate)
    for plan in remain_plan:
        if plan[1] != 0:
            return False
    return True


class Task(object):
    """
    单个任务
    """

    def __init__(self, tag: str = '', cmd: Callable = None, args: list[str] = [], device: Device = None):
        self.cmd = cmd
        self.cmd_args = args
        self.tag = tag
        self.last_run = None
        self.idx = None
        self.pending = False
        self.total = 1
        self.finish = 0
        self.device = device

        # per_hour 任务的第一次执行将在启动脚本后的一个小时之后
        if tag == 'per_hour':
            self.last_run = datetime.datetime.now()
        if cmd.__name__ == 'operation':
            self.total = operation_times(args)
            assert self.total != 0

    def __lt__(self, other):
        if task_priority[self.cmd.__name__] != task_priority[other.cmd.__name__]:
            return task_priority[self.cmd.__name__] < task_priority[other.cmd.__name__]
        return self.idx < other.idx

    def set_idx(self, idx: int = None):
        self.idx = idx

    def start_up(self) -> bool:
        return self.tag == 'start_up'

    def need_run(self, now: datetime.datetime = datetime.datetime.now()) -> bool:
        if self.pending:
            return False
        if self.start_up():
            if self.last_run is not None:
                return False
            self.pending = True
            self.last_run = now
            return True
        if self.tag[:4] == 'day_':
            # 同一天 and 跑过了
            if self.last_run is not None and the_same_day(now, self.last_run):
                return False
            # 还没到时间
            if now.strftime('%H:%M') < self.tag.replace('_', ':')[4:]:
                return False
            self.pending = True
            self.last_run = now
            return True
        if self.tag == 'per_hour':
            if self.last_run + datetime.timedelta(hours=1) <= now:
                self.pending = True
                self.last_run = now
                return True
            return False
        return False

    def run(self) -> bool:
        logger.info(f'task: {self.cmd.__name__} {self.cmd_args}')
        if self.cmd.__name__ == 'operation':
            if operation_one(self.cmd_args, self.device):
                self.finish += 1
                if self.finish == self.total:
                    self.finish = 0
                    self.pending = False
                    return True
            return False
        self.cmd(self.cmd_args, self.device)
        self.pending = False
        return True


def cmp_for_init(task_a: Task = None, task_b: Task = None) -> int:
    if task_a.start_up() and task_b.start_up():
        return 0

    if task_a.start_up():
        return -1

    if task_b.start_up():
        return 1
    return 0


class ScheduleSolver(BaseSolver):
    """
    按照计划定时、自动完成任务
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.tasks = []
        self.pending_list = PriorityQueue()
        self.device = device

    def add_task(self, tag: str = '', cmd: Callable = None, args: list[str] = []):
        task = Task(tag, cmd, args, self.device)
        self.tasks.append(task)

    def run(self):
        logger.info('Start: 计划')

        """
        这里是为了处理优先级相同的情况，对于优先级相同时，我们依次考虑：
        1. start_up 优先执行
        2. 按照配置文件的顺序决定先后顺序
        
        sort 是稳定排序，详见:
        https://docs.python.org/3/library/functions.html#sorted
        """
        self.tasks.sort(key=cmp_to_key(cmp_for_init))
        for idx, task in enumerate(self.tasks):
            task.set_idx(idx)

        super().run()

    def transition(self) -> None:
        while True:
            now = datetime.datetime.now()
            for task in self.tasks:
                if task.need_run(now):
                    self.pending_list.push(task)

            task = self.pending_list.pop()
            if task is not None:
                if task.run() is False:
                    self.pending_list.push(task)

            time.sleep(1)
