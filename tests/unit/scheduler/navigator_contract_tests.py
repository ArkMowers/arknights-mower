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
    CyclingRecognizer,
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

    def test_always_changing_frames_return_false(self):
        """帧持续变化 -> 永不稳定 -> 返回 False。

        ⚠️ 修复前用 **400 帧**绕过 `MockRecognizer` 的钳制（帧用尽后相邻帧会相同）。
        方向对但代价大：400 × 5.93 MiB ≈ **2.32 GiB** 峰值内存，对 CI 是风险。
        按 §10.2 硬要求 5「新用例优先用循环帧而非海量帧」改为 `CyclingRecognizer`
        （**2 帧**，约 12 MiB，内存降 3 个数量级），语义不变：帧恒变 → 永不稳定。

        预算取 **2.0s**（宽裕）：让结果为 `False` 的是**结构**（相邻帧恒不同），
        不是"时间不够" —— 这正是硬要求 5 要求的形态。
        """
        first = frame(10)
        second = frame(200)
        recog = CyclingRecognizer(scenes=[Scene.INDEX], frames=[first, second])
        nav, _device, _ = build(recognizer=recog)

        # Act
        result = nav.wait_scene_stable(max_duration=2.0, min_stable=3)

        # Assert
        self.assertFalse(result)
        self.assertGreater(recog.update_count, 0, "应真的取样过至少一帧")

    def test_crop_limits_compared_region(self):
        """`crop` 生效：只比较顶部 162 行时，下方变化不阻止稳定。

        ⚠️ **本用例曾 flaky，修法见下**（§10.2 硬要求 5「禁止墙钟依赖」）。

        修复前行为：否定对照用 **10 帧 + `MockRecognizer` 钳制 + 0.2s 预算**。
        `advance_frame()` 钳制在最后一帧（`min(cursor+1, len-1)`），循环走到第 9 帧
        之后相邻帧**变得相同** → 稳定计数增长 → **第 11 轮**达成 `min_stable=2`。
        于是 `assertFalse(uncropped)` 的真假取决于"0.2 秒内 CPU 能跑 11 轮还是 10 轮"：
        单跑（空载）常凑够 11 轮 → 假红；全量跑（有争用）轮次不足 → 反而通过。
        主控实测 20 次单跑失败 1 次、全量 8 次失败 4 次。

        修复后：改用 `CyclingRecognizer`（帧**无限循环**，不钳制），两帧只在
        `y >= 200`（裁剪区之外）不同。这样**每一对相邻帧都真的不同**，无论循环跑
        1 轮还是 10 万轮结果恒为 `False` —— 否定用例**结构性成立**。
        因此否定对照也用**宽裕**预算（`max_duration=2.0`）：让结果为 `False` 的是
        结构而非"时间不够"。这同时是最强的回归守卫 —— 若有人改回"帧会钳制"的写法，
        宽裕预算下 `uncropped` 会变成 `True` → `assertFalse` 立刻变红。
        """
        # 两帧只在裁剪区（y >= 200）之外不同
        uncropped_a = frame(128)
        uncropped_b = uncropped_a.copy()
        uncropped_b[200:, :, :] = 40
        crop = ((0, 0), (SCREEN_W, 162))

        recog = CyclingRecognizer(
            scenes=[Scene.INDEX], frames=[uncropped_a, uncropped_b]
        )
        nav, _device, _ = build(recognizer=recog)

        # Act
        cropped = nav.wait_scene_stable(max_duration=2.0, min_stable=2, crop=crop)
        # 对照：同一组帧不做裁剪时，相邻帧恒不相同 -> 结构性不稳定
        recog2 = CyclingRecognizer(
            scenes=[Scene.INDEX], frames=[uncropped_a, uncropped_b]
        )
        nav2, _device2, _ = build(recognizer=recog2)
        uncropped = nav2.wait_scene_stable(max_duration=2.0, min_stable=2)

        # Assert：crop 的正反对照都必须有意义
        self.assertTrue(cropped, "裁剪区内静止，应判为稳定")
        self.assertFalse(uncropped, "相邻帧恒不同，应永远不稳定")

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
