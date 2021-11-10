from .utils.adb import ADBConnector
from .utils.recognize import Recognizer
from .solvers import *


class Solver():

    def __init__(self, adb=None, recog=None):
        self.adb = adb if adb is not None else ADBConnector()
        self.recog = recog if recog is not None else Recognizer(self.adb)

    def base(self, clue_collect=False, drone_room=None, arrange=None):
        """
        :param clue_collect: bool, 是否收取线索
        :param drone_room: str, 是否使用无人机加速（仅支持制造站）
        :param arrange: {room_name: [agent,...]}, 基建干员安排
        """
        BaseConstructSolver(self.adb, self.recog).run(clue_collect, drone_room, arrange)

    def credit(self):
        CreditSolver(self.adb, self.recog).run()

    def mission(self):
        MissionSolver(self.adb, self.recog).run()

    def recruit(self, priority=None):
        """
        :param priority: list[str], 优先考虑的公招干员，默认为火神和因陀罗
        """
        RecruitSolver(self.adb, self.recog).run(priority)

    def ope(self, times=-1, potion=0, originite=0, level=None, plan=None, eliminate=False):
        """
        :param times: int, 作战的次数上限，-1 为无限制，默认为 -1
        :param potion: int, 使用药剂恢复体力的次数上限，-1 为无限制，默认为 0
        :param originite: int, 使用源石恢复体力的次数上限，-1 为无限制，默认为 0
        :param level: str, 指定关卡，默认为前往上一次关卡或当前界面关卡
        :param plan: [[str, int]...], 指定多个关卡以及次数，优先级高于 level
        :param eliminate: bool, 是否优先处理未完成的每周剿灭，默认为 False

        :return remain_plan: [[str, int]...], 未完成的计划
        """
        return OpeSolver(self.adb, self.recog).run(times, potion, originite, level, plan, eliminate)

    def shop(self, priority=None):
        """
        :param priority: list[str], 使用信用点购买东西的优先级, 若无指定则默认购买第一件可购买的物品
        """
        ShopSolver(self.adb, self.recog).run(priority)

    def mail(self):
        MailSolver(self.adb, self.recog).run()
