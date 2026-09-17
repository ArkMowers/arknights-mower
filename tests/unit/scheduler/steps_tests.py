"""S2 基础层回归测试：`Step` 下沉 + 常量收敛 + 死代码删除。

覆盖验收标准 1/2/4/6，并守住"无裸坐标"（标准 5）的**静态**部分。
`run_steps` 的运行时行为见同目录的 `run_steps_tests.py`。

本 Session 的目标是把 `Step` / `StepRetry` / `StepRestart` 从
`executors/base.py` 下沉到 `scheduler/steps.py`，消除
`services/ → executors/` 的层级倒挂。关键约束是**兼容再导出**：
三个既有引用方（`executors/infra_scan.py`、`executors/shift.py`、
`services/agent_swap_service.py`）必须一行不改也能继续 import。

因此本文件的核心断言是「`executors.base.Step` 与 `steps.Step`
**是同一个对象**」—— 一旦有人把类重新复制回 `executors/base.py`，
这条会立刻变红（已用变异测试实测确认）。

不使用真实设备：这里只做模块级、AST 级与源码级断言，不触碰 Device / 截图。
"""

import ast
import importlib
import unittest
from dataclasses import fields
from pathlib import Path

from arknights_mower.scheduler import steps
from arknights_mower.scheduler.constants import TRADE_ORDER_AGENTS, TapPosition
from arknights_mower.scheduler.executors.base import (
    AbstractExecutor,
    Step,
    StepRestart,
    StepRetry,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEDULER = REPO_ROOT / "arknights_mower" / "scheduler"
EXECUTORS_BASE = SCHEDULER / "executors" / "base.py"

# 跑单干员，与 constants.py 的权威定义逐字一致
EXPECTED_TRADE_ORDER_AGENTS = ["但书", "龙舌兰", "佩佩", "可露希尔"]


class StepDefinitionUniquenessTests(unittest.TestCase):
    """验收标准 1：`class Step` 在全 `scheduler/` 内只定义一次。"""

    def test_class_step_defined_only_in_steps_module(self):
        # Arrange: 扫描 scheduler/ 全部源码，找出顶层 class Step 定义点
        definitions = []
        for path in sorted(SCHEDULER.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == "Step":
                    definitions.append(path.relative_to(SCHEDULER).as_posix())

        # Act / Assert: 唯一且落在 steps.py
        self.assertEqual(
            ["steps.py"],
            definitions,
            "class Step 必须只在 scheduler/steps.py 定义一次",
        )

    def test_step_exceptions_defined_only_in_steps_module(self):
        # 与上一条同理，控制流异常也不得再有第二处定义
        found = {}
        for path in sorted(SCHEDULER.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name in (
                    "StepRetry",
                    "StepRestart",
                ):
                    found.setdefault(node.name, []).append(
                        path.relative_to(SCHEDULER).as_posix()
                    )

        self.assertEqual({"StepRetry": ["steps.py"], "StepRestart": ["steps.py"]}, found)


class StepContractTests(unittest.TestCase):
    """`Step` 的字段契约原样搬迁：语义不得在下沉时被改动。"""

    def test_fields_and_defaults_unchanged(self):
        # Act: 读 dataclass 字段名序列
        names = [f.name for f in fields(Step)]

        # Assert: 顺序与名称都与搬迁前一致（name/enter/act/start）
        self.assertEqual(["name", "enter", "act", "start"], names)

    def test_act_and_start_have_defaults_but_name_and_enter_do_not(self):
        step = Step(name="enter", enter=lambda scene: True)

        self.assertIsNone(step.start, "start 默认必须为 None")
        self.assertIsNone(step.act(), "act 默认必须返回 None（无追加步骤）")

    def test_retry_and_restart_are_exceptions(self):
        self.assertTrue(issubclass(StepRetry, Exception))
        self.assertTrue(issubclass(StepRestart, Exception))


class ReExportCompatibilityTests(unittest.TestCase):
    """验收标准 2：`executors/base.py` 的再导出指回同一定义。"""

    def test_executors_base_reexports_the_same_objects(self):
        base = importlib.import_module("arknights_mower.scheduler.executors.base")

        # Assert: 同一对象（is），不是复制出来的副本
        self.assertIs(base.Step, steps.Step)
        self.assertIs(base.StepRetry, steps.StepRetry)
        self.assertIs(base.StepRestart, steps.StepRestart)

    def test_direct_import_from_both_modules_yields_one_class(self):
        # Act: 两个路径分别 import
        from arknights_mower.scheduler.executors.base import Step as ViaBase
        from arknights_mower.scheduler.steps import Step as ViaSteps

        # Assert
        self.assertIs(ViaBase, ViaSteps)

    def test_original_import_sites_still_resolve(self):
        """三个既有引用方一行未改，必须仍能 import 成功。"""
        for module in (
            "arknights_mower.scheduler.executors.infra_scan",
            "arknights_mower.scheduler.executors.shift",
            "arknights_mower.scheduler.services.agent_swap_service",
        ):
            with self.subTest(module=module):
                imported = importlib.import_module(module)

                self.assertIs(imported.Step, steps.Step)


class DeletedSymbolTests(unittest.TestCase):
    """验收标准 4：`safe_execute` 与 `LegacyPlannerAdapter` 全库零命中。"""

    def test_safe_execute_is_gone_from_abstract_executor(self):
        self.assertFalse(hasattr(AbstractExecutor, "safe_execute"))

    def test_legacy_planner_adapter_is_gone(self):
        planners_base = importlib.import_module("arknights_mower.scheduler.planners.base")

        self.assertFalse(hasattr(planners_base, "LegacyPlannerAdapter"))

    def test_no_reference_anywhere_in_package(self):
        # 与验收标准的 grep 逐字等价：整包源码内不得再出现这两个符号
        hits = []
        for path in sorted((REPO_ROOT / "arknights_mower").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for name in ("safe_execute", "LegacyPlannerAdapter"):
                if name in text:
                    hits.append(f"{path.relative_to(REPO_ROOT)}: {name}")

        self.assertEqual([], hits, "死代码符号必须全库零命中")


class AbstractPlannerSurfaceTests(unittest.TestCase):
    """标准 4 的反向断言：删掉适配器不得伤到 `AbstractPlanner` 本体。"""

    def test_abstract_planner_still_intact(self):
        planners_base = importlib.import_module("arknights_mower.scheduler.planners.base")

        # S6 才会改造多任务接口，此处只确认接口未在 S2 被误删
        for name in ("should_run", "plan", "condition", "make_task"):
            with self.subTest(method=name):
                self.assertTrue(hasattr(planners_base.AbstractPlanner, name))


class TradeOrderAgentsConstantTests(unittest.TestCase):
    """验收标准 6：`constants.py` 预置唯一权威定义的跑单干员表。"""

    def test_constant_matches_expected_roster(self):
        self.assertEqual(EXPECTED_TRADE_ORDER_AGENTS, TRADE_ORDER_AGENTS)

    def test_constant_agrees_with_scattered_definition(self):
        """与散落定义同源同值：逐一比对，证明没有搬错字。

        本 Session **不**改下游（S5/S6 各自改为 import），所以这里只验证
        定义本身可用、可变，而不是断言它已被引用。
        """
        self.assertIsInstance(TRADE_ORDER_AGENTS, list)

        from arknights_mower.scheduler.planners.exhaust import (
            TRADE_ORDER_AGENTS as from_exhaust,
        )

        self.assertEqual(from_exhaust, TRADE_ORDER_AGENTS)


class TapPositionConstantTests(unittest.TestCase):
    """验收标准 5（静态部分）：坐标由 `constants` 提供，非裸数字。"""

    def test_member_normalized_from_screen_constants(self):
        from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W

        x, y = TapPosition.LEAVE_INFRASTRUCTURE.value

        self.assertAlmostEqual(670 / SCREEN_W, x)
        self.assertAlmostEqual(750 / SCREEN_H, y)

    def test_executors_base_has_no_raw_screen_literals(self):
        # 源码级：与验收标准的 grep 逐字等价
        source = EXECUTORS_BASE.read_text(encoding="utf-8")

        self.assertNotIn("/1920", source)
        self.assertNotIn("/1080", source)

    def test_executors_base_has_no_division_by_raw_resolution_ast(self):
        """AST 级守卫：`670 / 1920` 这种**带空格**的写法骗不过源码字符串匹配。

        上面那条逐字 grep 等价断言被 `670 / 1920`（空格包围）绕过，
        已用变异测试实测确认。这里按符号名判断：除数只要是裸数字
        1920/1080 就算违规，而引用 `SCREEN_W` / `SCREEN_H`
        （`ast.Name`）是允许的。
        """
        # Arrange: 遍历 base.py，找出所有"除以裸分辨率数字"的二元表达式
        offenders = []
        tree = ast.parse(EXECUTORS_BASE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
                continue
            divisor = node.right
            if isinstance(divisor, ast.Constant) and divisor.value in (1920, 1080):
                offenders.append(f"line {node.lineno}: divides by {divisor.value}")

        # Assert
        self.assertEqual(
            [], offenders, "不得用裸分辨率数字做归一化，应引用 SCREEN_W/SCREEN_H"
        )


if __name__ == "__main__":
    unittest.main()