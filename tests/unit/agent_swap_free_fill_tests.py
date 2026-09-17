"""AgentSwapService 自由位补位回归测试。

历史缺陷（本次修复）：
  A. free 分支用 `name not in self._agent_list` 过滤，而 `_agent_list` 是全部
     415 名干员表，该判断恒为真 —— 等于完全没有过滤，会把"已经在房内"的干员
     反复点选（实测 dormitory_2 连点 3 次「流明」）。
  B. free 补位命中后既不写入 `_selected`，也不占用 `_agents` 里的 Free 名额，
     导致 `_do_sort` 重建时 `click_order` 只含定向干员，补位结果被
     `INFRA_CLEAR_ALL` 清空后不再补回。

对齐 legacy 语义的参照实现：
  solvers/base_schedule.py:2939  selected.extend(selected_name)
  solvers/base_schedule.py:2942  agents[agents.index("Free")] = selected_name[0]
  solvers/base_schedule.py:2956  exists.extend(selected)

测试全部使用 mock 设备，不接触游戏。
"""

import unittest

from arknights_mower.scheduler.constants import (
    AGENT_SELECT_POSITIONS,
    INFRA_CLEAR_ALL,
)
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer

# 面板真实读数，来自 tests/live/probe_select_panel.py 实机探测（dormitory_2）
PANEL = [
    ("流明", ((631, 488), (820, 520))),
    ("琴柳", ((631, 909), (820, 941))),
    ("Lancet-2", ((847, 488), (1037, 520))),
    ("承曦格雷伊", ((847, 909), (1037, 941))),
    ("温蒂", ((1063, 488), (1252, 520))),
    ("清流", ((1063, 909), (1252, 941))),
    ("令", ((1280, 488), (1468, 520))),
    ("森蚺", ((1280, 909), (1468, 941))),
]

DORM_PLAN = ["流明", "琴柳", "Free", "Free", "Free"]
DORM_CURRENT = ["流明", "琴柳", "", "", ""]


def tap_name(x, y):
    """把归一化坐标反查成人类可读的动作名。"""
    if abs(x - INFRA_CLEAR_ALL[0]) < 0.01 and abs(y - INFRA_CLEAR_ALL[1]) < 0.01:
        return "CLEAR_ALL"
    for idx, pos in enumerate(AGENT_SELECT_POSITIONS):
        if abs(x - pos[0]) < 0.01 and abs(y - pos[1]) < 0.01:
            return f"SLOT{idx}"
    for name, box in PANEL:
        cx = (box[0][0] + box[1][0]) / 2 / 1920
        cy = (box[0][1] + box[1][1]) / 2 / 1080
        if abs(x - cx) < 0.005 and abs(y - cy) < 0.005:
            return name
    return f"({x},{y})"


def build_service(device, panel=None):
    """构造已隔离 UI 依赖的 AgentSwapService。"""
    svc = AgentSwapService(
        device,
        MockRecognizer(scenes=[Scene.INFRA_ARRANGE_ORDER]),
        lambda: Scene.INFRA_ARRANGE_ORDER,
        ThreadPauseController(),
        lambda **kwargs: None,
    )
    svc._operator_list_fn = lambda img, full_scan=False: (
        PANEL if panel is None else panel
    )
    svc._detect_arrange = lambda room: ("心情", True)
    svc._tap_sort = lambda *a, **k: None
    svc._open_filter = lambda *a, **k: None
    svc._switch_filter_other = lambda *a, **k: None
    return svc


class TestAgentSwapFreeFill(unittest.TestCase):
    def test_free_fill_skips_seated_operators(self):
        """缺陷 A：补位必须跳过已在房内的干员。"""
        device = MockDevicePort()
        svc = build_service(device)
        svc.run("dormitory_2", list(DORM_PLAN), current_operators=list(DORM_CURRENT))

        picked = [tap_name(x, y) for x, y in device.taps]
        picked = [n for n in picked if n in dict(PANEL)]
        for seated in ("流明", "琴柳"):
            self.assertNotIn(seated, picked, f"{seated} 已在房内，不应被补位点选")

    def test_free_fill_picks_distinct_operators(self):
        """补位 3 个名额应点中 3 个互不相同的干员。"""
        device = MockDevicePort()
        svc = build_service(device)
        svc.run("dormitory_2", list(DORM_PLAN), current_operators=list(DORM_CURRENT))

        picked = [tap_name(x, y) for x, y in device.taps]
        picked = [n for n in picked if n in dict(PANEL)]
        self.assertEqual(len(picked), 3, f"应补位 3 次，实际 {picked}")
        self.assertEqual(len(set(picked)), 3, f"补位点到了重复干员：{picked}")

    def test_free_fill_survives_sort_rebuild(self):
        """缺陷 B：补位结果必须被 _do_sort 重建时保留（不清空后丢失）。"""
        device = MockDevicePort()
        svc = build_service(device)
        svc.run("dormitory_2", list(DORM_PLAN), current_operators=list(DORM_CURRENT))

        names = [tap_name(x, y) for x, y in device.taps]
        picked = [n for n in names if n in dict(PANEL)]
        # 清空全部之后被重新点击的槽位数，应等于计划里的全部 5 个名额
        self.assertIn("CLEAR_ALL", names, "应执行清空全部")
        slot_taps = [n for n in names if n.startswith("SLOT")]
        self.assertEqual(
            len(slot_taps),
            len(DORM_PLAN),
            f"清空后应重建全部 {len(DORM_PLAN)} 个槽位，实际 {slot_taps}",
        )
        for name in picked:
            self.assertIn(name, svc._selected, f"补位干员 {name} 未记入 _selected")

    def test_free_count_consumed_by_fill(self):
        """补位后 Free 名额应被真实干员名替换，不再残留 Free。"""
        device = MockDevicePort()
        svc = build_service(device)
        svc.run("dormitory_2", list(DORM_PLAN), current_operators=list(DORM_CURRENT))

        self.assertEqual(
            svc._agents.count("Free"), 0, f"仍有未占用的 Free：{svc._agents}"
        )
        self.assertEqual(len(svc._agents), len(DORM_PLAN))


if __name__ == "__main__":
    unittest.main()
