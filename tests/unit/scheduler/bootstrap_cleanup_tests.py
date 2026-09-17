"""S1 启动期清理的回归测试。

覆盖本 Session 的删除与接线清理，防止这些违规被重新引入：

1. `InfraKit` 不得再有 `agent_selector` 字段 —— 其唯一生产者
   `infra/agent_selection.py` 已删除（全库零调用），字段留着就是死接线，
   且会诱导后来者重新 `AgentSelection.create(...)`。
2. `bootstrap` 必须可导入，且启动路径上**不得**推送硬编码假任务
   （历史缺陷：无条件 `state.task_queue.push(SHIFT_ON, {"room_1_1": [...]})`）。
3. `infra.agent_selection` / `infra.registry` / `scheduler.hooks` 三个模块
   必须已删除且不再被引用；`errors.AgentSelectionError` 随之删除。

不使用真实设备：这里只做模块级与 AST 级断言，不触碰 Device / 截图。
"""

import ast
import importlib
import importlib.util
import unittest
from dataclasses import fields
from pathlib import Path

from arknights_mower.scheduler.infra import InfraKit

BOOTSTRAP = (
    Path(__file__).resolve().parents[3]
    / "arknights_mower"
    / "scheduler"
    / "bootstrap.py"
)


class InfraKitShapeTests(unittest.TestCase):
    """验收标准 9：断言 InfraKit 无 agent_selector 字段 + bootstrap 可导入。"""

    def test_infra_kit_has_no_agent_selector_field(self):
        names = {f.name for f in fields(InfraKit)}

        self.assertNotIn(
            "agent_selector",
            names,
            "InfraKit.agent_selector 已在 S1 移除，不得重新引入",
        )

    def test_infra_kit_keeps_device_pause_and_navigator(self):
        # 反向断言：确保上一条不是因为 InfraKit 被整体改坏才通过
        names = {f.name for f in fields(InfraKit)}

        self.assertEqual({"device", "pause", "state", "navigator"}, names)

    def test_bootstrap_importable(self):
        module = importlib.import_module("arknights_mower.scheduler.bootstrap")

        self.assertTrue(callable(module.run))


class DeletedModuleTests(unittest.TestCase):
    """验收标准 1：删除目标确实消失且不再可导入。"""

    def test_deleted_modules_are_gone(self):
        for name in (
            "arknights_mower.scheduler.infra.agent_selection",
            "arknights_mower.scheduler.infra.registry",
            "arknights_mower.scheduler.hooks",
        ):
            with self.subTest(module=name):
                self.assertFalse(
                    importlib.util.find_spec(name),
                    f"{name} 应在 S1 删除后不可再导入",
                )

    def test_agent_selection_error_is_gone(self):
        errors = importlib.import_module("arknights_mower.scheduler.errors")

        self.assertFalse(hasattr(errors, "AgentSelectionError"))

    def test_no_agent_selector_field_on_bootstrap_source(self):
        # 源码级断言：bootstrap 里不得再出现 agent_selector / AgentSelection
        source = BOOTSTRAP.read_text(encoding="utf-8")

        self.assertNotIn("agent_selector", source)
        self.assertNotIn("AgentSelection", source)

    def test_no_commented_out_planner_in_bootstrap(self):
        """不得留下注释掉的 planner 接线（S1 删的是注释死代码，不是 planner 本身）。

        注意本用例**只**断言"没有被注释掉的接线"，并**不**断言
        `InfraScanPlanner` 这个符号不存在 —— `planners/infra_scan.py` 是合规 planner
        （`condition` + `make_task`），**S6 会合法地把它注册进 `_build_planners`**。
        早期版本误写成 `assertNotIn("InfraScanPlanner", source)`，会在 S6 接线时
        造成误报，已修正。
        """
        source = BOOTSTRAP.read_text(encoding="utf-8")

        commented = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith("#") and "Planner" in line
        ]

        self.assertEqual([], commented, "不得残留注释掉的 planner 接线")

    def test_build_planners_has_no_commented_wiring_ast(self):
        # AST 级：_build_planners 内不得只有注释、没有有效 append
        tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
        build_fn = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_planners"
        )
        appends = [
            node
            for node in ast.walk(build_fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
        ]

        self.assertGreaterEqual(len(appends), 1, "_build_planners 必须至少注册一个 planner")


class NoFakeTaskTests(unittest.TestCase):
    """验收标准 8：启动路径不再推送硬编码假任务。"""

    def test_bootstrap_run_pushes_no_hardcoded_task(self):
        """修复前行为：`run()` 无条件 push SHIFT_ON room_1_1 假任务并打日志。"""
        source = BOOTSTRAP.read_text(encoding="utf-8")

        self.assertNotIn("room_1_1", source)
        self.assertNotIn("test: pushed", source)

    def test_bootstrap_run_has_no_task_queue_push_call(self):
        # AST 级断言，比字符串匹配更抗"换个换行/缩进就骗过"的改写
        tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
        run_fn = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        pushes = [
            node
            for node in ast.walk(run_fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "push"
        ]

        self.assertEqual([], pushes, "run() 不得再向 task_queue 推送任何硬编码任务")

    def test_bootstrap_imports_no_datetime(self):
        # 假任务删除后 datetime 只剩无用 import（ruff F401）
        tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                imported.update(alias.name for alias in node.names)

        self.assertEqual(set(), imported)


class NoSleepInSchedulerTests(unittest.TestCase):
    """验收标准 2/3：scheduler/ 内无 time.sleep 与 `import time`。"""

    def test_no_literal_time_sleep_and_no_toplevel_import_time(self):
        # 与验收标准 2/3 的 grep 逐字等价：`time.sleep(` 与行首 `import time`
        root = BOOTSTRAP.parent
        sleep_hits = []
        import_hits = []
        for path in sorted(root.rglob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "time.sleep(" in line:
                    sleep_hits.append(f"{path}:{lineno}: {line.strip()}")
                if line.startswith("import time"):
                    import_hits.append(f"{path}:{lineno}: {line.strip()}")

        self.assertEqual([], sleep_hits, "scheduler/ 内不得存在 time.sleep(")
        self.assertEqual([], import_hits, "scheduler/ 内不得存在行首 import time")

    def test_no_sleep_call_ast(self):
        # AST 级：即使写成 `from time import sleep` 也逃不过
        root = BOOTSTRAP.parent
        offenders = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "sleep":
                    offenders.append(f"{path}:{node.lineno}: .sleep()")
                elif isinstance(func, ast.Name) and func.id == "sleep":
                    offenders.append(f"{path}:{node.lineno}: sleep()")

        self.assertEqual([], offenders, "scheduler/ 内不得调用 sleep()")


class MainEntrypointTests(unittest.TestCase):
    """`__main__.py` 去掉 time.sleep 后仍须可导入且入口完整。"""

    def test_main_module_importable_and_sleep_free(self):
        module = importlib.import_module("arknights_mower.scheduler.__main__")

        self.assertTrue(callable(module.test_scene))

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("time.sleep", source)
        self.assertNotIn("import time", source)


if __name__ == "__main__":
    unittest.main()