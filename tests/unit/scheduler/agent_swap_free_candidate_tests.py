"""自由人（Free）补位候选的空闲判定 —— 裁定 14。

修复前行为
----------
free 分支写成 `if name not in self._agent_list or name in self._selected: continue`，
而 `_agent_list` 是**全体干员名集合** —— 该条件几乎恒为 `False`，**等于没有筛选**。
于是"已在别处工作"的干员也会被点选为自由人。

正确语义（对齐 legacy `solvers/base_schedule.py:2681` 的 `get_free_list`）
------------------------------------------------------------------------
`v.current_room == ""` 是**入选**条件 —— 空闲（不在任何房间）才算自由人。
⚠️ 方向不可反：要**排除**的是 `current_room != ""`（已在别处工作）的干员，
以及 `config.free_blacklist` 内的干员。

本文件用**真实的** `Operator` / `PlanConfig` domain 对象驱动判定，
但用一个最小 state 替身承载它们 —— 完整 `SchedulerState` 需要磁盘上的 plan.json
与全局 config（`_init_and_validate` 会 `config.save_conf()`），不适合离线单测。
替身只实现实现代码真正触碰的那两个成员：`operators` 与 `config`。
"""

import unittest

from arknights_mower.scheduler.domain.operators import Operator, OperatorType
from arknights_mower.scheduler.domain.plan import PlanConfig
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer

BOX_A = ((631, 488), (820, 520))
BOX_B = ((847, 488), (1037, 520))

# 三个都在 agent_list 里：保证"非干员名"这条旧筛除条件不会掩盖空闲判定
WORKING = "温蒂"
IDLE = "清流"
BLACKLISTED = "令"


class FakeState:
    """只提供换班服务真正读取的成员：`operators` 与 `config`。"""

    def __init__(self, operators, free_blacklist=None):
        self.operators = operators
        self.config = PlanConfig(free_blacklist=list(free_blacklist or []))


def operator(name, current_room):
    return Operator(
        name=name,
        room="",
        index=-1,
        operator_type=OperatorType.LOW,
        current_room=current_room,
        current_index=0 if current_room else -1,
    )


def build_service(device, panel, state=None):
    svc = AgentSwapService(
        device,
        MockRecognizer(scenes=[Scene.INFRA_ARRANGE_ORDER]),
        lambda: Scene.INFRA_ARRANGE_ORDER,
        ThreadPauseController(),
        lambda **kwargs: None,
        state=state,
    )
    svc._operator_list_fn = lambda img, full_scan=False: list(panel)
    svc._detect_arrange = lambda room: ("心情", True)
    svc._tap_sort = lambda *a, **k: None
    svc._open_filter = lambda *a, **k: None
    svc._switch_filter_other = lambda *a, **k: None
    return svc


def picked_names(device, panel):
    """把 tap 坐标反查成面板里的干员名。"""
    known = {}
    for name, box in panel:
        cx = (box[0][0] + box[1][0]) / 2 / 1920
        cy = (box[0][1] + box[1][1]) / 2 / 1080
        known[round(cx, 6), round(cy, 6)] = name
    return [known.get((round(x, 6), round(y, 6))) for x, y in device.taps]


class FreeCandidatePredicateTests(unittest.TestCase):
    """直接对入选判据断言，锁定方向（防止再次写反）。"""

    def test_idle_operator_is_a_candidate(self):
        """`current_room == ""`（空闲）**才是**合法候选。"""
        state = FakeState({IDLE: operator(IDLE, "")})
        svc = build_service(MockDevicePort(), [], state)

        # Act + Assert
        self.assertTrue(svc._is_free_candidate(IDLE))

    def test_working_operator_is_not_a_candidate(self):
        """`current_room != ""`（已在别处工作）必须被排除。"""
        state = FakeState({WORKING: operator(WORKING, "room_1_1")})
        svc = build_service(MockDevicePort(), [], state)

        # Act + Assert
        self.assertFalse(svc._is_free_candidate(WORKING))

    def test_blacklisted_operator_is_not_a_candidate(self):
        """`config.free_blacklist` 内的干员必须被排除。"""
        state = FakeState({BLACKLISTED: operator(BLACKLISTED, "")}, [BLACKLISTED])
        svc = build_service(MockDevicePort(), [], state)

        # Act + Assert
        self.assertFalse(svc._is_free_candidate(BLACKLISTED))

    def test_already_selected_operator_is_not_a_candidate(self):
        state = FakeState({IDLE: operator(IDLE, "")})
        svc = build_service(MockDevicePort(), [], state)
        svc._selected = [IDLE]

        # Act + Assert
        self.assertFalse(svc._is_free_candidate(IDLE))


class FreeFillSelectionTests(unittest.TestCase):
    """端到端：补位时只点真正空闲的干员。

    每个用例只留 **1 个** Free 名额：补满即结束（`result is True`），
    从而把断言集中在"点了谁"上，而不是被"名额不够导致翻页"干扰。
    """

    def test_working_operator_is_never_tapped_as_free(self):
        """面板同时有"工作中"和"空闲"的干员 → 只有空闲的那个被点。"""
        device = MockDevicePort()
        panel = [(WORKING, BOX_A), (IDLE, BOX_B)]
        state = FakeState(
            {
                WORKING: operator(WORKING, "room_1_1"),
                IDLE: operator(IDLE, ""),
            }
        )
        svc = build_service(device, panel, state)

        # Act
        result = svc.run("dormitory_2", ["Free"])

        # Assert
        self.assertTrue(result)
        picked = picked_names(device, panel)
        self.assertIn(IDLE, picked, "空闲干员应被补位")
        self.assertNotIn(WORKING, picked, "已在别处工作的干员不得被补位点选")

    def test_blacklisted_operator_is_never_tapped_as_free(self):
        """黑名单干员即使空闲也不得补位。"""
        device = MockDevicePort()
        panel = [(BLACKLISTED, BOX_A), (IDLE, BOX_B)]
        state = FakeState(
            {
                BLACKLISTED: operator(BLACKLISTED, ""),
                IDLE: operator(IDLE, ""),
            },
            [BLACKLISTED],
        )
        svc = build_service(device, panel, state)

        # Act
        result = svc.run("dormitory_2", ["Free"])

        # Assert
        self.assertTrue(result)
        picked = picked_names(device, panel)
        self.assertIn(IDLE, picked)
        self.assertNotIn(BLACKLISTED, picked, "黑名单干员不得被补位点选")

    def test_without_state_the_legacy_behaviour_is_kept(self):
        """未注入 state 时退化为拆分前的行为（不崩溃、照旧补位）。

        这是回归网 `agent_swap_free_fill_tests.py` 的兼容前提。
        """
        device = MockDevicePort()
        panel = [(IDLE, BOX_A)]
        svc = build_service(device, panel, state=None)

        # Act
        result = svc.run("dormitory_2", ["Free"])

        # Assert
        self.assertTrue(result)
        self.assertIn(IDLE, picked_names(device, panel))


if __name__ == "__main__":
    unittest.main()