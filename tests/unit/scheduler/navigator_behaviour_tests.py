"""S4 导航行为不变 + 55 动作可分派（验收 3 / 3b）。

期望序列取自拆分**前**实现（450 行 `navigator.py`）的实测快照
`_s4_before.json`，并与拆分后的 `_s4_after.json` 做过逐项 diff
（14 个场景全部 SAME）。共享夹具见 `navigator_scenarios.py`。
"""

import unittest

from arknights_mower.scheduler.graph import SceneGraph
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.navigator import Navigator
from arknights_mower.scheduler.navigator_actions import NavigatorActionsMixin
from arknights_mower.scheduler.scene import Scene
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer
from tests.unit.scheduler.navigator_scenarios import (
    DEPOT_BOX,
    DEPOT_CENTER,
    MISSION_BOX,
    MISSION_CENTER,
    TAPPABLE_RESOURCES,
    ScriptedDriver,
    build,
    graph_action_names,
)


class NavigationSequenceTests(unittest.TestCase):
    """验收 3：拆分前后 `navigate` 的调用序列逐字一致。"""

    def test_two_step_path_is_unchanged(self):
        """INDEX -> MISSION_WEEKLY：经由 MISSION_DAILY 两步，2 次 tap。"""
        nav, device, _ = build(
            {"mission": MISSION_BOX, "mission_weekly": MISSION_BOX},
            [Scene.INDEX, Scene.MISSION_DAILY, Scene.MISSION_WEEKLY],
        )

        # Act
        result = nav.navigate(Scene.MISSION_WEEKLY)

        # Assert
        self.assertTrue(result)
        self.assertEqual(device.call_names(), ["tap", "tap"])
        # 两次都是 `mission` 元素框中心 (200, 300) 的归一化坐标
        self.assertEqual(device.taps, [MISSION_CENTER, MISSION_CENTER])

    def test_back_path_is_unchanged(self):
        """BUSINESS_CARD -> INDEX：`back_to_index` 只回退一次。"""
        nav, device, _ = build({}, [Scene.BUSINESS_CARD, Scene.INDEX])

        # Act
        result = nav.navigate(Scene.INDEX)

        # Assert
        self.assertTrue(result)
        self.assertEqual(device.call_names(), ["back"])
        self.assertEqual(device.taps, [])

    def test_three_step_path_is_unchanged(self):
        """INFRA_MAIN -> DEPOT：NAVIGATION_BAR 中转，back + 两次 tap。"""
        nav, device, _ = build(
            {
                "nav_button": MISSION_BOX,
                "index": MISSION_BOX,
                "warehouse": DEPOT_BOX,
            },
            [Scene.INFRA_MAIN, Scene.NAVIGATION_BAR, Scene.INDEX, Scene.DEPOT],
        )

        # Act
        result = nav.navigate(Scene.DEPOT)

        # Assert
        self.assertTrue(result)
        self.assertEqual(device.call_names(), ["back", "tap", "tap"])
        self.assertEqual(device.taps, [MISSION_CENTER, DEPOT_CENTER])

    def test_no_path_aborts_without_device_action(self):
        """无路径场景（TRAIN_MAIN -> INDEX）：立即放弃，零设备动作。"""
        nav, device, _ = build({}, [Scene.TRAIN_MAIN])

        # Act
        result = nav.navigate(Scene.INDEX)

        # Assert
        self.assertFalse(result)
        self.assertEqual(device.call_names(), [])

    def test_unknown_scene_budget_is_unchanged(self):
        """UNKNOWN 持续：回退 3 次后放弃（`MAX_UNKNOWN = 6`）。"""
        nav, device, _ = build({}, [Scene.UNKNOWN])

        # Act
        result = nav.navigate(Scene.INDEX)

        # Assert
        self.assertFalse(result)
        self.assertEqual(device.call_names(), ["back", "back", "back"])

    def test_missing_handler_aborts_without_device_action(self):
        """graph 里的 action 无对应 `_action_*` -> 报 no handler 并放弃。"""
        device = MockDevicePort()
        driver = ScriptedDriver([Scene.INFRA_MAIN, Scene.INDEX])
        graph = SceneGraph()
        graph.add_transition(Scene.INFRA_MAIN, Scene.INDEX, "does_not_exist", 1)
        nav = Navigator(
            device,
            graph,
            lambda: driver.get_scene(len(device.calls)),
            ThreadPauseController(),
            MockRecognizer(),
        )

        # Act
        result = nav.navigate(Scene.INDEX)

        # Assert
        self.assertFalse(result)
        self.assertEqual(device.call_names(), [])

    def test_error_budget_is_unchanged(self):
        """handler 持续抛异常：`MAX_ERROR = 5` 后放弃（+1 容差 = 6 次）。"""
        device = MockDevicePort()
        driver = ScriptedDriver([Scene.INFRA_MAIN])
        graph = SceneGraph()
        graph.add_transition(Scene.INFRA_MAIN, Scene.INDEX, "boom", 1)
        nav = Navigator(
            device,
            graph,
            lambda: driver.get_scene(0),
            ThreadPauseController(),
            MockRecognizer(),
        )

        def boom():
            device.back()
            raise RuntimeError("boom")

        nav._action_boom = boom

        # Act
        result = nav.navigate(Scene.INDEX)

        # Assert
        self.assertFalse(result)
        self.assertEqual(device.call_names(), ["back"] * 6)


class ActionDispatchTests(unittest.TestCase):
    """验收 3b：55 个动作仍绑定在 `Navigator` 实例上（防组合化回归）。

    ⚠️ 这是本 Session 最关键的守卫：Mixin 与组合在静态检查、import、
    方法存在性上都看不出差别，**只有 `getattr` 分派才暴露**。若把
    `_action_*` 挪进 `self._actions = ...` 组合对象，下面每一个
    subTest 都会变红。
    """

    def test_graph_has_exactly_55_actions(self):
        """基线锚点：`graph.py` 恰有 55 条不同 action（少一条说明图被改了）。"""
        self.assertEqual(len(graph_action_names()), 55)

    def test_all_graph_actions_resolve_on_instance(self):
        nav, _device, _ = build({}, [Scene.INFRA_MAIN])

        # Assert：每个 action 名都能取到可调用对象
        for name in graph_action_names():
            with self.subTest(action=name):
                handler = getattr(nav, f"_action_{name}", None)
                self.assertIsNotNone(handler, f"_action_{name} 取不到（组合化拆分？）")
                self.assertTrue(callable(handler))

    def test_actions_live_on_mixin_but_bind_to_navigator(self):
        """结构守卫：处理器定义在 Mixin，但绑定在 `Navigator` 实例上。"""
        nav, _device, _ = build({}, [Scene.INFRA_MAIN])

        # Mixin 自己持有全部 55 个处理器
        mixin_actions = {
            n for n in vars(NavigatorActionsMixin) if n.startswith("_action_")
        }
        self.assertEqual(len(mixin_actions), 55)
        self.assertIsInstance(nav, NavigatorActionsMixin)
        # 且实例上确实解析得到（Mixin 生效，不是被覆盖）
        for name in mixin_actions:
            with self.subTest(action=name):
                self.assertIsNotNone(getattr(nav, name, None))

    def test_every_action_produces_device_activity(self):
        """行为守卫：每个动作**调用后都有设备动作**。

        `_action_get_scene` 是刻意的空动作（图里 UNDEFINED -> INDEX 的占位），
        故单独排除；其余 54 个必须真的碰设备。

        `_action_announcement` 走 `check_announcement()`：MockRecognizer 返回
        `None` 时退化到 `TapPosition.CENTER`，同样是设备动作。
        """
        finds = {name: MISSION_BOX for name in TAPPABLE_RESOURCES}
        recog = MockRecognizer(scenes=[Scene.INDEX], finds=finds)
        nav, device, _ = build(scenes=[Scene.INDEX], recognizer=recog)
        nav._get_scene = lambda: Scene.INDEX

        inert = []
        for name in graph_action_names():
            device.reset()
            getattr(nav, f"_action_{name}")()
            if not device.calls:
                inert.append(f"_action_{name}")

        # Assert
        self.assertEqual(inert, ["_action_get_scene"], f"无设备动作的处理器：{inert}")


if __name__ == "__main__":
    unittest.main()
