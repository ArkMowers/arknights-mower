from .utils.adb import ADBConnector
from .utils.recognize import Recognizer
from .solvers import *


class Solver():

    def __init__(self, adb=None, recog=None):
        self.adb = adb if adb is not None else ADBConnector()
        self.recog = recog if recog is not None else Recognizer(self.adb)

    def base(self):
        BaseConstructSolver(self.adb, self.recog).run()

    def credit(self):
        CreditSolver(self.adb, self.recog).run()

    def mission(self):
        MissionSolver(self.adb, self.recog).run()

    def recruit(self, priority=None):
        RecruitSolver(self.adb, self.recog).run(priority)

    def ope(self, times=-1, potion=0, originite=0, level=None, eliminate=False):
        OpeSolver(self.adb, self.recog).run(times, potion, originite, level, eliminate)

    def shop(self, priority=None):
        ShopSolver(self.adb, self.recog).run(priority)
