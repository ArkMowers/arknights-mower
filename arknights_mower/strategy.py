from __future__ import annotations

import functools
import signal

from .solvers import *
from .utils import typealias as tp
from .utils.device import Device
from .utils.log import logger
from .utils.recognize import Recognizer
from .utils.solver import BaseSolver


class Solver(object):
    """ Integration solver """

    def __init__(self, device: Device = None, recog: Recognizer = None, timeout: int = 99) -> None:
        """
        :param timeout: int, 操作限时，单位为小时
        """
        self.device = device if device is not None else Device()
        self.recog = recog if recog is not None else Recognizer(self.device)
        self.timeout = timeout

    def timer(f):
        @functools.wraps(f)
        def inner(self: Solver, *args, **kwargs):
            def handler(signum, frame):
                logger.warning('Operation timed out')
                raise KeyboardInterrupt
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(self.timeout * 3600)
            ret = f(self, *args, **kwargs)
            signal.alarm(0)
            return ret
        return inner

    @timer
    def base(self, arrange: tp.BasePlan = None, clue_collect: bool = False, drone_room: str = None, fia_room: str = None) -> None:
        """
        :param arrange: dict(room_name: [agent,...]), 基建干员安排
        :param clue_collect: bool, 是否收取线索
        :param drone_room: str, 是否使用无人机加速
        :param fia_room: str, 是否使用菲亚梅塔恢复心情
        """
        BaseConstructSolver(self.device, self.recog).run(
            arrange, clue_collect, drone_room, fia_room)

    @timer
    def credit(self) -> None:
        CreditSolver(self.device, self.recog).run()

    @timer
    def mission(self) -> None:
        MissionSolver(self.device, self.recog).run()

    @timer
    def recruit(self, priority: list[str] = None) -> None:
        """
        :param priority: list[str], 优先考虑的公招干员，默认为高稀有度优先
        """
        RecruitSolver(self.device, self.recog).run(priority)

    @timer
    def ope(self, level: str = None, times: int = -1, potion: int = 0, originite: int = 0, eliminate: int = 0, plan: list[tp.OpePlan] = None) -> list[tp.OpePlan]:
        """
        :param level: str, 指定关卡，默认为前往上一次关卡或当前界面关卡
        :param times: int, 作战的次数上限，-1 为无限制，默认为 -1
        :param potion: int, 使用药剂恢复体力的次数上限，-1 为无限制，默认为 0
        :param originite: int, 使用源石恢复体力的次数上限，-1 为无限制，默认为 0
        :param eliminate: int, 是否优先处理未完成的每周剿灭，0 为忽略剿灭，1 为优先剿灭，2 为优先剿灭但只消耗代理卡，默认为 0
        :param plan: [[str, int]...], 指定多个关卡以及次数，优先级高于 level

        :return remain_plan: [[str, int]...], 未完成的计划
        """
        return OpeSolver(self.device, self.recog).run(level, times, potion, originite, eliminate, plan)

    @timer
    def shop(self, priority: bool = None) -> None:
        """
        :param priority: list[str], 使用信用点购买东西的优先级, 若无指定则默认购买第一件可购买的物品
        """
        ShopSolver(self.device, self.recog).run(priority)

    @timer
    def mail(self) -> None:
        MailSolver(self.device, self.recog).run()

    @timer
    def index(self) -> None:
        BaseSolver(self.device, self.recog).back_to_index()
