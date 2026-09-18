"""S4 等待原语 + 无裸尺寸 + 无 sleep（验收 1/2/4/5/6）。

共享夹具见 `navigator_scenarios.py`。全部断言零真实等待：
`wait_scene_stable` 的用例把 `max_duration` 调到极小或全静态帧。
"""

import ast
import inspect
import unittest

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W
from arknights_mower.scheduler.navigator import Navigator
from arknights_mower.scheduler.scene import Scene
from tests.harness.mock_recognizer import MockRecognizer
from tests.unit.scheduler.navigator_scenarios import (
    MAX_FILE_LINES,
    SCHEDULER,
    build,
    frame,
    navigator_sources,
)


class WaitSceneStableTests(unittest.TestCase):
    """验收 4：`wait_scene_stable` 仍可用（零真实等待）。"""

    def test_static_frames_return_true(self):
        """连续帧完全相同 -> 达到 `min_stable` 即返回 True。"""
        recog = MockRecognizer(scenes=[Scene.INDEX], frames=frame(128))
        nav, _device, _ = build(recognizer=recog)

        # Act
        result = nav.wait_scene_stable(max_duration=2.0, min_stable=3)

        # Assert
        self.assertTrue(result)
        # 首帧只做基准（stable 仍为 0），故需 1 + min_stable 次 update
        self.assertEqual(recog.update_count, 4)

    def test_changing_frames_return_false_on_budget(self):
        """帧持续变化 -> 永不稳定 -> 超时返回 False（`max_duration` 极小）。"""
        frames = [frame((i * 7) % 256) for i in range(400)]
        recog = MockRecognizer(scenes=[Scene.INDEX], frames=frames)
        nav, _device, _ = build(recognizer=recog)

        # Act
        result = nav.wait_scene_stable(max_duration=0.2, min_stable=3)

        # Assert
        self.assertFalse(result)
        self.assertGreater(recog.update_count, 0, "应真的取样过至少一帧")

    def test_crop_limits_compared_region(self):
        """`crop` 生效：只比较顶部 162 行时，下方变化不阻止稳定。"""
        base = frame(128)
        frames = []
        for i in range(10):
            f = base.copy()
            f[200:, :, :] = (i * 40) % 256  # 只在裁剪区之外变化
            frames.append(f)
        recog = MockRecognizer(scenes=[Scene.INDEX], frames=frames)
        nav, _device, _ = build(recognizer=recog)

        # Act
        cropped = nav.wait_scene_stable(
            max_duration=2.0, min_stable=2, crop=((0, 0), (SCREEN_W, 162))
        )
        # 对照：同样的帧序列不做裁剪时不稳定
        recog2 = MockRecognizer(scenes=[Scene.INDEX], frames=frames)
        nav2, _device2, _ = build(recognizer=recog2)
        uncropped = nav2.wait_scene_stable(max_duration=0.2, min_stable=2)

        # Assert
        self.assertTrue(cropped)
        self.assertFalse(uncropped)

    def test_threshold_argument_is_respected(self):
        """阈值放大到 1.0 时，任何差异都被判为稳定。"""
        frames = [frame((i * 20) % 256) for i in range(10)]
        recog = MockRecognizer(scenes=[Scene.INDEX], frames=frames)
        nav, _device, _ = build(recognizer=recog)

        # Act
        result = nav.wait_scene_stable(max_duration=2.0, min_stable=2, threshold=1.0)

        # Assert
        self.assertTrue(result)

    def test_wait_scene_returns_membership(self):
        """`wait_scene` 仍按集合成员判定。"""
        nav, _device, _ = build(scenes=[Scene.LOADING])

        # Assert
        self.assertTrue(nav.wait_scene({Scene.LOADING, Scene.INDEX}))
        self.assertFalse(nav.wait_scene({Scene.INDEX}))


class NoBareScreenSizeTests(unittest.TestCase):
    """验收 1/2：AST 级无裸尺寸 + 每个文件 ≤300 行。

    ⚠️ 刻意**不**用 grep 判断字面量 —— S2 的教训是 `670 / 1920`
    （空格包围）能绕过逐字 grep。这里直接看 AST 常量节点。

    判据通过 `SCREEN_W`/`SCREEN_H` 常量表达（而非重抄 1920/1080 字面量），
    这样本文件自身也不含裸尺寸。
    """

    def test_navigator_was_actually_split(self):
        """拆分必须真的产生多个文件，否则"≤300"可能是"什么都没拆"。"""
        self.assertGreaterEqual(len(navigator_sources()), 2)

    def test_screen_size_anchor(self):
        """锚点：用常量表达的判据必须与 1920×1080 等价（防静默失效）。

        没有这条，把 `SCREEN_W` 改成 1280 会让裸尺寸守卫**静默失效**。
        锚点取自**独立事实**而非重抄字面量：`constants.py:106` 定义
        `CENTER = (960 / SCREEN_W, 540 / SCREEN_H)`，屏幕中心必归一化为
        `(0.5, 0.5)` —— 这只有在 `SCREEN_W = 960 * 2` 时才成立。
        """
        from arknights_mower.scheduler.constants import TapPosition

        self.assertEqual(TapPosition.CENTER.value, (0.5, 0.5))
        self.assertEqual(SCREEN_W, 960 * 2)
        self.assertEqual(SCREEN_H, 540 * 2)

    def test_no_bare_screen_size_literals(self):
        for path in navigator_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            offenders = [
                (node.lineno, node.value)
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and node.value in (SCREEN_W, SCREEN_H)
            ]
            with self.subTest(file=path.name):
                self.assertEqual(offenders, [], f"{path.name} 仍有裸尺寸：{offenders}")

    def test_screen_size_constants_are_actually_used(self):
        """反向守卫：常量确实被引用（防止"删掉字面量但功能也没了"）。"""
        found = set()
        for path in navigator_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in ("SCREEN_W", "SCREEN_H"):
                    found.add(node.id)

        # Assert
        self.assertEqual(found, {"SCREEN_W", "SCREEN_H"})

    def test_all_navigator_files_within_line_limit(self):
        for path in navigator_sources():
            with self.subTest(file=path.name):
                lines = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(lines, MAX_FILE_LINES, f"{path.name} = {lines} 行")

    def test_navigator_preserves_public_construction_signature(self):
        """验收 5：构造签名不变（`bootstrap.py:39` / `__main__.py:48` 无需改动）。"""
        params = inspect.signature(Navigator.__init__).parameters
        self.assertEqual(
            list(params),
            ["self", "device", "graph", "get_scene", "pause_controller", "recognizer"],
        )
        self.assertIsNone(params["recognizer"].default)


class NoSleepTests(unittest.TestCase):
    """验收 6：未引入 sleep。

    显式许可 `import time as _time` + `_time.time()` 用于**超时预算**
    （见 §10.4「S4 缺陷 2」）；禁止的只是 `time.sleep(`。
    """

    def test_no_time_sleep_in_navigator(self):
        for path in navigator_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            offenders = [
                node.lineno
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep"
            ]
            with self.subTest(file=path.name):
                self.assertEqual(offenders, [])

    def test_timer_usage_is_budget_not_waiting(self):
        """`_time.time()` 只用于超时预算：断言它参与比较运算。"""
        tree = ast.parse((SCHEDULER / "navigator.py").read_text(encoding="utf-8"))

        compared = any(
            isinstance(node, ast.Compare)
            and any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "_time"
                for n in ast.walk(node)
            )
            for node in ast.walk(tree)
        )

        # Assert
        self.assertTrue(compared, "`_time.time()` 应出现在超时比较里（预算用途）")


if __name__ == "__main__":
    unittest.main()
