"""BUG-2 / BUG-3 回归测试：换班失败必须**可上报**，且**不得死循环**。

修复前行为（主控实测，见 `重构流程.md` §10.4）
--------------------------------------------
`_do_select` 里原本是**一条** `if` 同时承担两件事，重构时被删：

    cur_names = [c[0] for c in self._cache]
    if cur_names == self._last_names:          # ← BUG-3：比较被删
        logger.error("... reached end of list ...")
        return []                              # ← BUG-2：静默返回

* **BUG-2**：`return []` 让 `_run_steps` 判定"正常完成"并返回 `True`，
  `ShiftExecutor._do_swap` 因此不报错，`dispatch` 判定成功，`state.error` 永远为 `False`
  —— **失败被上报为成功**。
* **BUG-3**：`_last_names` 变成只写变量（3 处赋值、0 处比较），根本没有"翻到底"的判据，
  只能一路翻到 `MAX_PAGE`。

两个缺陷共用同一条语句，必须一并修。此处断言的是**行为**（抛什么 / 调用了什么），
不是源码里有没有 `raise` 字样。测试全部离线，使用 mock 设备。
"""

import ast
import pathlib
import unittest

from arknights_mower.scheduler.constants import MAX_PAGE
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.scene import Scene
from arknights_mower.scheduler.services.agent_swap_errors import AgentSwapError
from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
from arknights_mower.scheduler.steps import StepRestart, StepRetry
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer

BOX_A = ((631, 488), (820, 520))
BOX_B = ((847, 488), (1037, 520))
BOX_C = ((1063, 488), (1252, 520))

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCAN_MODULE = (
    REPO_ROOT / "arknights_mower/scheduler/services/agent_swap_scan.py"
)


def build_service(device, panel):
    """构造已隔离 UI 依赖的 AgentSwapService。"""
    svc = AgentSwapService(
        device,
        MockRecognizer(scenes=[Scene.INFRA_ARRANGE_ORDER]),
        lambda: Scene.INFRA_ARRANGE_ORDER,
        ThreadPauseController(),
        lambda **kwargs: None,
    )
    svc._operator_list_fn = panel
    svc._detect_arrange = lambda room: ("技能", False)
    svc._tap_sort = lambda *a, **k: None
    svc._open_filter = lambda *a, **k: None
    svc._switch_filter_other = lambda *a, **k: None
    return svc


class EndOfListTests(unittest.TestCase):
    """BUG-3：连续两页相同 → 立即判定"翻到底"并抛 `AgentSwapError`。"""

    def test_repeated_page_raises_agent_swap_error(self):
        """`_cache` 与上一页逐字相同 → 抛 `AgentSwapError`（修复前是 `return []`）。"""
        device = MockDevicePort()
        panel = [("温蒂", BOX_A), ("清流", BOX_B)]
        svc = build_service(device, lambda img, full_scan=False: list(panel))

        # Arrange：模拟"刚扫完第 0 页"
        svc._cache = list(panel)
        svc._last_names = ["温蒂", "清流"]
        svc._pending = ["不存在的人"]
        svc._free_count = 0
        svc._selected = []

        # Act + Assert
        with self.assertRaises(AgentSwapError):
            svc._check_end_of_list()

    def test_end_of_list_stops_immediately_without_paging_to_max(self):
        """翻到底必须**立即**停：只滑 1 次，而不是撑到 MAX_PAGE=50。

        Arrange 用一个**不在干员表里**的名字，使自由人补位永远无候选 ——
        这样队列只能靠"翻到底"或 `MAX_PAGE` 终止，而修复后的正确终止点是前者。
        """
        device = MockDevicePort()
        # "无名者" 不在 agent_list → 不可能成为自由人候选
        panel = [("无名者", BOX_A)]
        svc = build_service(device, lambda img, full_scan=False: list(panel))

        # Act：走完整队列（异常在 _run_steps 内被转为 False）
        result = svc.run("dormitory_2", ["Free"], current_operators=None)

        # Assert：立即停（1 次滑动），且**报告为失败**
        self.assertEqual(len(device.swipes), 1, "翻到底应只滑动一次即停")
        self.assertLess(svc._page_count, MAX_PAGE, "不应撑到 MAX_PAGE")
        self.assertFalse(result, "翻到底后 run() 必须返回 False（可上报），不得 True")

    def test_last_names_is_compared_not_merely_assigned(self):
        """AST 级守卫：`_last_names` 必须出现在**比较**位置（防退化为只写变量）。

        S2 的教训：逐字 grep 等价可被空格写法绕过，故这里按 AST 节点判断。
        """
        tree = ast.parse(SCAN_MODULE.read_text(encoding="utf-8"))

        # Act：收集所有比较节点中出现的 self._last_names
        compared = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for operand in [node.left, *node.comparators]:
                if isinstance(operand, ast.Attribute) and operand.attr == "_last_names":
                    compared.append((node.lineno, ast.unparse(node)))

        # Assert
        self.assertTrue(
            compared,
            "agent_swap_scan.py 内没有任何对 self._last_names 的比较 —— BUG-3 回退",
        )


class MaxPageTests(unittest.TestCase):
    """BUG-2：翻到 `MAX_PAGE` 仍无候选 → 抛 `AgentSwapError`，不得静默返回。"""

    def test_max_page_raises_agent_swap_error(self):
        device = MockDevicePort()
        counter = {"n": 0}

        def varying(img, full_scan=False):
            counter["n"] += 1
            return [(f"干员{counter['n']}", BOX_A)]

        svc = build_service(device, varying)

        # Arrange：显式置于 MAX_PAGE 边界，直接命中该分支
        svc._page_count = MAX_PAGE
        svc._pending = ["温蒂"]
        svc._free_count = 0
        svc._selected = []
        svc._cache = [("别人", BOX_B)]
        svc._last_names = ["上页"]

        # Act + Assert
        with self.assertRaises(AgentSwapError):
            svc._advance_page()

    def test_max_page_is_reported_as_failure_end_to_end(self):
        """完整跑 50 页仍找不到目标：`run()` 必须返回 False（失败可上报）。"""
        device = MockDevicePort()
        counter = {"n": 0}

        def varying(img, full_scan=False):
            counter["n"] += 1
            return [(f"干员{counter['n']}", BOX_A)]

        svc = build_service(device, varying)

        # Act
        result = svc.run("room_1", ["温蒂"], current_operators=None)

        # Assert
        self.assertEqual(svc._page_count, MAX_PAGE, "应翻满 MAX_PAGE")
        self.assertFalse(result, "到 MAX_PAGE 仍无候选时必须报告失败")


class LoopSafetyTests(unittest.TestCase):
    """验收标准 11：为何**不能**用 `StepRetry` —— 它会在本队列里死循环。"""

    def test_agent_swap_error_is_not_a_control_flow_exception(self):
        """`AgentSwapError` 必须是普通异常，不能被 `_run_steps` 当成重试/重启。"""
        self.assertTrue(issubclass(AgentSwapError, Exception))
        self.assertFalse(issubclass(AgentSwapError, StepRetry))
        self.assertFalse(issubclass(AgentSwapError, StepRestart))

    def test_agent_swap_error_makes_run_steps_return_false(self):
        """普通异常经 `except Exception` → `return False`（而非原地重试）。"""
        device = MockDevicePort()
        svc = build_service(device, lambda img, full_scan=False: [("温蒂", BOX_A)])

        def boom():
            raise AgentSwapError("boom")

        # Act：单步队列，动作抛 AgentSwapError
        from arknights_mower.scheduler.steps import Step

        result = svc._run_steps(
            [Step("boom", svc._scene_check, boom)]
        )

        # Assert：被转为失败返回，未向上冒出（上层以 False 上报）
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
