"""夹具自检：证明 MockDevicePort / MockRecognizer 可用，且协议漂移会立刻失败。

**不参与门禁 G1**（文件名不是 `*_tests.py`），改动 harness 后手跑：

    .venv\\Scripts\\python.exe -m unittest tests.harness.selftest

之所以刻意排在 G1 之外：G1 的计数基线是 35，夹具自身的元测试不该挤进业务用例数，
否则"夹具变了"和"业务行为变了"在 G1 数字上无法区分。
"""

from __future__ import annotations

import unittest

import numpy as np

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.scene import Scene
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer


class HarnessSmokeTests(unittest.TestCase):
    def test_mock_device_is_a_device_port(self):
        device = MockDevicePort()

        self.assertIsInstance(device, DevicePort)
        # 9 个抽象方法必须全部落地
        self.assertEqual(MockDevicePort.__abstractmethods__, frozenset())
        self.assertLessEqual(
            set(
                (
                    "tap",
                    "swipe",
                    "screencap",
                    "launch",
                    "exit",
                    "swipe_path",
                    "back",
                    "check_focus",
                    "reconnect",
                )
            ),
            set(dir(MockDevicePort)),
        )

    def test_protocol_drift_is_detected_immediately(self):
        """协议漂移必须立刻炸：给 DevicePort 加一个抽象方法，实现类就不能实例化。"""
        from abc import abstractmethod

        class DriftedDevicePort(DevicePort):
            @abstractmethod
            def brand_new_method(self) -> None: ...

        class DriftedMock(MockDevicePort, DriftedDevicePort):
            pass

        self.assertIn("brand_new_method", DriftedMock.__abstractmethods__)
        with self.assertRaises(TypeError):
            DriftedMock()

    def test_mock_device_records_call_sequence(self):
        device = MockDevicePort()

        device.launch()
        device.tap(0.5, 0.5)
        device.back()
        device.swipe(0.1, 0.2, 0.3, 0.4)
        device.exit()

        self.assertEqual(
            device.call_names(), ["launch", "tap", "back", "swipe", "exit"]
        )
        self.assertEqual(device.taps, [(0.5, 0.5)])
        self.assertEqual(device.swipes, [(0.1, 0.2, 0.3, 0.4, 100)])
        self.assertEqual(device.back_count, 1)

    def test_mock_device_default_screencap_is_1080p(self):
        device = MockDevicePort()

        frame = device.screencap()

        self.assertEqual(frame.shape, (SCREEN_H, SCREEN_W, 3))

    def test_mock_device_screencap_factory_is_used(self):
        marker = np.full((SCREEN_H, SCREEN_W, 3), 7, dtype=np.uint8)
        device = MockDevicePort(screencap_factory=lambda n: marker)

        self.assertIs(device.screencap(), marker)
        self.assertEqual(device.call_names(), ["screencap"])

    def test_mock_device_tap_names(self):
        device = MockDevicePort()

        device.tap_named("CLEAR_ALL", 0.1, 0.2)
        device.tap(0.3, 0.4)

        self.assertEqual(device.tap_names(), ["CLEAR_ALL", "@0.3000,0.4000"])
        self.assertEqual(
            device.tap_names(resolver=lambda x, y: "SLOT"), ["CLEAR_ALL", "SLOT"]
        )

    def test_mock_recognizer_replays_scene_sequence(self):
        recog = MockRecognizer(scenes=[Scene.INFRA_MAIN, Scene.INFRA_DETAILS])

        recog.update()
        self.assertEqual(recog.get_scene(), Scene.INFRA_MAIN)
        # get_scene 不推进
        self.assertEqual(recog.get_scene(), Scene.INFRA_MAIN)
        recog.update()
        self.assertEqual(recog.get_scene(), Scene.INFRA_DETAILS)
        # 序列耗尽后停在最后一个
        recog.update()
        self.assertEqual(recog.get_scene(), Scene.INFRA_DETAILS)

    def test_mock_recognizer_whitelist_masks_scene(self):
        recog = MockRecognizer(scenes=[Scene.INFRA_MAIN])
        recog.update()

        recog.set_scene_whitelist([Scene.INDEX])
        self.assertEqual(recog.get_scene(), Scene.UNKNOWN)
        recog.set_scene_whitelist(None)
        self.assertEqual(recog.get_scene(), Scene.INFRA_MAIN)

    def test_mock_recognizer_find_and_img(self):
        recog = MockRecognizer(finds={"arrange_check_in": ((1, 2), (3, 4))})

        self.assertEqual(recog.find("arrange_check_in"), ((1, 2), (3, 4)))
        self.assertIsNone(recog.find("nope"))
        self.assertEqual(recog.find_calls, ["arrange_check_in", "nope"])
        self.assertEqual(recog.img.shape, (SCREEN_H, SCREEN_W, 3))
        self.assertEqual(recog.gray.shape, (SCREEN_H, SCREEN_W))

    def test_mock_device_swipe_noinertia_goes_through_swipe_path(self):
        """DevicePort 的具体方法必须作用于本 mock 的记录面，而不是被绕过。"""
        device = MockDevicePort()

        device.swipe_noinertia((0.5, 0.5), (0, -300))

        self.assertEqual(device.call_names(), ["swipe_path"])
        self.assertEqual(len(device.swipe_paths), 1)


class DiscoveryContractTests(unittest.TestCase):
    """锁定 §10.2 的两个陷阱：漏收与重复加载。都不依赖外部进程。"""

    def test_every_tests_subdirectory_has_init(self):
        """任何 tests/ 子目录缺 __init__.py，其用例会被 discover 静默漏收。"""
        from tests._bootstrap import REPO_ROOT

        tests_dir = REPO_ROOT / "tests"
        missing = [
            str(p.relative_to(REPO_ROOT))
            for p in tests_dir.rglob("*")
            if p.is_dir()
            and p.name != "__pycache__"
            and not (p / "__init__.py").is_file()
        ]
        self.assertEqual(
            missing, [], f"以下目录缺 __init__.py，用例会被漏收：{missing}"
        )

    def test_test_modules_are_not_loaded_twice(self):
        """缺 `-t .` 时同一文件会以 unit.* 与 tests.* 两个模块名同时存在。"""
        import sys

        dupes = {}
        for name, mod in sys.modules.items():
            if not name.endswith("_tests"):
                continue
            path = getattr(mod, "__file__", None)
            if path is not None:
                dupes.setdefault(path, []).append(name)

        shadowed = {path: names for path, names in dupes.items() if len(names) > 1}
        self.assertEqual(
            shadowed,
            {},
            "同一测试文件被加载成多个模块（缺 `-t .`？）："
            f"{ {p: sorted(n) for p, n in shadowed.items()} }",
        )

    def test_bootstrap_exposes_repo_root(self):
        from tests._bootstrap import REPO_ROOT

        self.assertTrue((REPO_ROOT / "tests" / "_bootstrap.py").is_file())
        self.assertTrue((REPO_ROOT / "arknights_mower").is_dir())


if __name__ == "__main__":
    unittest.main()
