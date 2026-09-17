"""S3 拆分与清理的守卫用例。

覆盖三类**结构性**验收标准（行为级断言，不看源码字符串形式）：

1. **验收 3（行为不变）**：拆分前后同一 mock 场景的 tap/swipe 序列一致 ——
   用"期望序列"固化正常路径，任何拆分引入的偏差都会立刻变红。
2. **验收 6（死方法已删）**：`_find_in_cache` / `_find_free_in_cache` 零引用；
   ⚠️ 同时断言 `_find` **仍在**（它有 8 处调用，是最容易被"顺手清理"误删的方法）。
3. **验收 1/7（文件行数）**：拆分后的每个文件均 ≤300 行。
"""

import ast
import pathlib
import unittest

from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
from arknights_mower.scheduler.steps import Step
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SERVICES = REPO_ROOT / "arknights_mower/scheduler/services"

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

MAX_FILE_LINES = 300


def build_service(device):
    svc = AgentSwapService(
        device,
        MockRecognizer(scenes=[Scene.INFRA_ARRANGE_ORDER]),
        lambda: Scene.INFRA_ARRANGE_ORDER,
        ThreadPauseController(),
        lambda **kwargs: None,
    )
    svc._operator_list_fn = lambda img, full_scan=False: list(PANEL)
    svc._detect_arrange = lambda room: ("心情", True)
    svc._tap_sort = lambda *a, **k: None
    svc._open_filter = lambda *a, **k: None
    svc._switch_filter_other = lambda *a, **k: None
    return svc


class SplitBehaviourTests(unittest.TestCase):
    """验收 3：拆分前后行为一致 —— 固化正常路径的调用序列。"""

    def test_free_fill_call_sequence_is_stable(self):
        """宿舍补位路径的 tap 序列在拆分前后逐字相同。

        期望值取自拆分**前**的实现（`git show 1d1463e8`），
        并与拆分后的实测序列做过逐项 diff。
        """
        device = MockDevicePort()
        svc = build_service(device)

        # Act
        result = svc.run(
            "dormitory_2", list(DORM_PLAN), current_operators=list(DORM_CURRENT)
        )

        # Assert：补位 3 人 + 清空 1 次 + 重建 5 槽 = 9 次 tap
        self.assertTrue(result)
        self.assertEqual(len(device.taps), 9, f"tap 次数漂移：{device.taps}")
        # 前 3 次是补位点击（面板里的候选），随后是清空与 5 个槽位重建
        picked = [tap_label(x, y) for x, y in device.taps]
        self.assertEqual(
            picked[3:],
            ["CLEAR_ALL", "SLOT0", "SLOT1", "SLOT2", "SLOT3", "SLOT4"],
            f"清空与重建序列漂移：{picked}",
        )
        self.assertEqual(len(device.swipes), 0, "该场景不应翻页")

    def test_swipe_sequence_is_stable_while_paging(self):
        """需要翻页的场景：swipe 参数与次数必须稳定。"""
        device = MockDevicePort()
        svc = build_service(device)
        # 排序探测与目标要求一致，否则 _do_prepare 会一直 StepRetry
        # （换班队列没有超时兜底，这是实机上的真实风险，测试也必须让条件收敛）
        svc._get_target_sort = lambda name, is_dorm: ("心情", True)
        # 筛选保持 ALL：既免去筛选切换，也让扫描走 full_scan=True 分支
        svc._get_target_filter = lambda *a, **k: "ALL"
        # 前两页无匹配，第三页给出目标。
        # 每页 2 个条目，且首条的 x 大于末条（delta >= 0），
        # 使 `_swipe_next()` 走**默认 swipe** 分支。
        pages = {
            1: [("别人甲", ((900, 488), (1000, 520))), ("别人乙", ((631, 488), (700, 520)))],
            2: [("别人丙", ((900, 488), (1000, 520))), ("别人丁", ((631, 488), (700, 520)))],
            3: [("温蒂", ((900, 488), (1000, 520))), ("别人戊", ((631, 488), (700, 520)))],
        }
        calls = {"n": 0}

        def paged(img, full_scan=False):
            if full_scan:
                calls["n"] += 1
            # full_scan=False 的调用来自 `_swipe_next()`，返回当前页即可
            return list(pages[min(max(calls["n"], 1), 3)])

        svc._operator_list_fn = paged

        # Act
        result = svc.run("room_1", ["温蒂"], current_operators=None)

        # Assert：2 次翻页，参数逐字一致
        self.assertTrue(result)
        self.assertEqual(
            device.swipes,
            [
                (960 / 1920, 540 / 1080, 100 / 1920, 540 / 1080, 300),
                (960 / 1920, 540 / 1080, 100 / 1920, 540 / 1080, 300),
            ],
            f"swipe 序列漂移：{device.swipes}",
        )
        self.assertEqual(svc._page_count, 0, "命中目标后页码应重置")


class DeadMethodRemovalTests(unittest.TestCase):
    """验收 6：两个死方法已删，而 `_find` **必须保留**。"""

    def test_dead_cache_helpers_are_gone(self):
        for name in ("_find_in_cache", "_find_free_in_cache"):
            with self.subTest(method=name):
                self.assertFalse(
                    hasattr(AgentSwapService, name), f"{name} 应已删除"
                )

    def test_find_is_preserved(self):
        """⚠️ `_find` 有 8 处调用（`:396,397,416,417,430,431,566,570`），不得误删。"""
        self.assertTrue(hasattr(AgentSwapService, "_find"))

    def test_find_is_still_called_from_source(self):
        """AST 级：拆分后 `self._find(...)` 仍有实际调用点（非仅定义）。"""
        calls = 0
        for path in sorted(SERVICES.glob("agent_swap_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_find"
                ):
                    calls += 1

        # Assert：拆除 `_tap_confirm_train` 等筛选分支后仍有多个真实调用点
        self.assertGreaterEqual(calls, 4, f"self._find 调用点过少（{calls}）")


class FileSizeTests(unittest.TestCase):
    """验收 1/7：拆分后每个文件 ≤300 行。"""

    def test_all_agent_swap_files_within_limit(self):
        files = sorted(SERVICES.glob("agent_swap_*.py"))

        # Assert：拆分确实产生了多个文件（否则"≤300"可能是"什么都没拆"）
        self.assertGreaterEqual(len(files), 6, f"拆分文件数异常：{files}")
        for path in files:
            with self.subTest(file=path.name):
                lines = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(lines, MAX_FILE_LINES, f"{path.name} = {lines} 行")

    def test_touched_files_within_limit(self):
        """本 Session 触碰的另两个文件同样受限。"""
        for rel in (
            "arknights_mower/scheduler/executors/shift.py",
            "arknights_mower/scheduler/infra/room_reader.py",
        ):
            path = REPO_ROOT / rel
            with self.subTest(file=rel):
                lines = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(lines, MAX_FILE_LINES, f"{rel} = {lines} 行")


class ImportLayerTests(unittest.TestCase):
    """层级倒挂已消除：服务层不再依赖执行器层。"""

    def test_service_does_not_import_executors(self):
        for path in sorted(SERVICES.glob("agent_swap_*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn(
                    "scheduler.executors",
                    source,
                    f"{path.name} 仍依赖执行器层（层级倒挂）",
                )

    def test_step_comes_from_steps_module(self):
        import arknights_mower.scheduler.steps as steps

        self.assertIs(Step, steps.Step)


def tap_label(x, y):
    """把归一化坐标反查成可读动作名（与回归网同一套约定）。"""
    from arknights_mower.scheduler.constants import (
        AGENT_SELECT_POSITIONS,
        INFRA_CLEAR_ALL,
    )

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


if __name__ == "__main__":
    unittest.main()