"""S4 导航层拆分用例的共享夹具。

**不参与 G1 收集**（文件名不是 `*_tests.py`），只被同目录的
`navigator_*_tests.py` import。

放在独立模块的理由：S4 的用例覆盖 5 条互不相同的验收标准，全部塞进一个文件
会超过 AGENTS.md 的 300 行上限；而夹具本身（场景驱动、构造辅助、常量）
在两个用例文件里都要用。
"""

from __future__ import annotations

import pathlib

import numpy as np

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W
from arknights_mower.scheduler.graph import build_default_graph
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.navigator import Navigator
from arknights_mower.scheduler.scene import Scene
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEDULER = REPO_ROOT / "arknights_mower/scheduler"
MAX_FILE_LINES = 300

# `MockRecognizer.find()` 的返回值按 `_tap_element` 的约定解析：
# 返回**元组**时取 `result[0]` 当 box，所以这里用两点列表让 `_center` 算中心。
MISSION_BOX = [[100, 200], [300, 400]]
DEPOT_BOX = [[1900, 200], [1950, 400]]
MISSION_CENTER = (200 / SCREEN_W, 300 / SCREEN_H)
DEPOT_CENTER = (1925 / SCREEN_W, 300 / SCREEN_H)

# 55 个动作里凡走 `_tap_element` 的资源名（AST 实测 20 个，另外
# `read_and_agree` 由 `_action_agreement` 经 `find()` 直接取）。
TAPPABLE_RESOURCES = [
    "confirm",
    "control_central",
    "control_central_assistants",
    "friend",
    "headhunting",
    "index",
    "login_awake",
    "login_captcha",
    "mail",
    "main_theme",
    "mission",
    "mission_daily",
    "mission_weekly",
    "nav_button",
    "recruit",
    "read_and_agree",
    "shop",
    "shop_credit_2",
    "skip",
    "terminal",
    "warehouse",
]


class BudgetExceeded(RuntimeError):
    """场景回放兜底：防止实现坏掉时用例无限循环。"""


class ScriptedDriver:
    """场景由**已发生的设备动作数**决定 —— 与实机同型（点击推进界面）。

    每次设备动作（tap/back/swipe）推进一格场景；`_WAITING_SCENES` 与
    `Scene.UNKNOWN` 由 `navigate` 自身轮询，不消耗动作。
    """

    def __init__(self, scenes, budget=200):
        self.scenes = list(scenes)
        self.queries = 0
        self.budget = budget

    def get_scene(self, action_count):
        self.queries += 1
        if self.queries > self.budget:
            raise BudgetExceeded(f"get_scene called {self.queries} times")
        return self.scenes[min(action_count, len(self.scenes) - 1)]


def build(finds=None, scenes=None, graph=None, recognizer=None, frames=None):
    """按脚本构造 `Navigator` + `MockDevicePort`。"""
    device = MockDevicePort()
    driver = ScriptedDriver(scenes or [Scene.INFRA_MAIN])
    recog = recognizer or MockRecognizer(scenes=scenes or [], frames=frames)
    recog.finds.update(finds or {})
    nav = Navigator(
        device,
        graph or build_default_graph(),
        lambda: driver.get_scene(len(device.calls)),
        ThreadPauseController(),
        recog,
    )
    return nav, device, driver


def graph_action_names():
    """`graph.py` 里全部 `SceneTransition.action` 名（实测 55 个）。"""
    actions = set()
    for _, _, data in build_default_graph()._graph.edges(data=True):
        actions.add(data["action"])
    return sorted(actions)


class CyclingRecognizer(MockRecognizer):
    """帧序列**无限循环**（不钳制）—— 相邻帧恒不相同，永不稳定。

    为什么需要它（§10.2 硬要求 5「禁止墙钟依赖」，主控 2026-09-18）：
    `MockRecognizer.advance_frame()` 钳制在最后一帧（`min(cursor+1, len-1)`），
    因此帧序列用尽后相邻帧**会变得相同**，稳定必然达成 —— 于是"能否在预算内
    跑完"成了竞态：同一用例在空载机器上凑够轮次就 `True`，负载高就 `False`。

    本类改写为 `(cursor + 1) % len(frames)`，只要**每一对相邻帧都真的不同**
    （含首尾相接那一对），无论循环跑 1 轮还是 10 万轮，结果恒为 `False` ——
    否定用例因此**结构性成立**，不再依赖墙钟。

    ️ 帧数必须 >= 2 且**首尾也要不同**：循环会让最后一帧接回第 0 帧，
    若这两帧恰好相同，稳定计数仍会增长。
    """

    def advance_frame(self) -> None:
        if self._frames:
            self._frame_cursor = (self._frame_cursor + 1) % len(self._frames)
            self._img = None
            self._gray = None


def navigator_sources():
    """`navigator*.py` 全部生产文件（拆分必须真的产生多个）。"""
    return sorted(SCHEDULER.glob("navigator*.py"))


def frame(value):
    return np.full((SCREEN_H, SCREEN_W, 3), value, dtype=np.uint8)
