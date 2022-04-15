from __future__ import annotations

from .solvers import *
from .utils.device import Device
from .utils.recognize import Recognizer
from .utils.solver import BaseSolver
from .utils import typealias as tp


class Solver(object):
    """ Integration solver """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        self.device = device if device is not None else Device()
        self.recog = recog if recog is not None else Recognizer(self.device)

    def base(self, arrange: tp.BasePlan = None, clue_collect: bool = False, drone_room: str = None) -> None:
        """
        :param arrange: dict(room_name: [agent,...]), 基建干员安排
        :param clue_collect: bool, 是否收取线索
        :param drone_room: str, 是否使用无人机加速（仅支持制造站）
        """
        BaseConstructSolver(self.device, self.recog).run(
            arrange, clue_collect, drone_room)

    def credit(self) -> None:
        CreditSolver(self.device, self.recog).run()

    def mission(self) -> None:
        MissionSolver(self.device, self.recog).run()

    def recruit(self, priority: list[str] = None) -> None:
        """
        :param priority: list[str], 优先考虑的公招干员，默认为高稀有度优先
        """
        RecruitSolver(self.device, self.recog).run(priority)

    def ope(self, level: str = None, times: int = -1, potion: int = 0, originite: int = 0, eliminate: bool = False, plan: list[tp.OpePlan] = None) -> list[tp.OpePlan]:
        """
        :param level: str, 指定关卡，默认为前往上一次关卡或当前界面关卡
        :param times: int, 作战的次数上限，-1 为无限制，默认为 -1
        :param potion: int, 使用药剂恢复体力的次数上限，-1 为无限制，默认为 0
        :param originite: int, 使用源石恢复体力的次数上限，-1 为无限制，默认为 0
        :param eliminate: bool, 是否优先处理未完成的每周剿灭，默认为 False
        :param plan: [[str, int]...], 指定多个关卡以及次数，优先级高于 level

        :return remain_plan: [[str, int]...], 未完成的计划
        """
        return OpeSolver(self.device, self.recog).run(level, times, potion, originite, eliminate, plan)

    def shop(self, priority: bool = None) -> None:
        """
        :param priority: list[str], 使用信用点购买东西的优先级, 若无指定则默认购买第一件可购买的物品
        """
        ShopSolver(self.device, self.recog).run(priority)

    def mail(self) -> None:
        MailSolver(self.device, self.recog).run()

    def index(self) -> None:
        BaseSolver(self.device, self.recog).back_to_index()
