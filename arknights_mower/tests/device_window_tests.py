import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.session_io import ProductionSimulator
from arknights_mower.utils.device.window import (
    parse_hotkey_keys,
    trigger_simulator_boss_key,
)


class FakeAdapter:
    """The manager step of one bound preset; only the launch result matters here."""

    def __init__(self, started):
        self.started = started

    def act(self, start):
        self.start_calls = getattr(self, "start_calls", []) + [start]
        return self.started


class DeviceWindowTests(unittest.TestCase):
    def simulator(self, started=True):
        simulator = ProductionSimulator(run=MagicMock(), spawn=MagicMock())
        adapter = FakeAdapter(started)
        simulator._adapter = lambda profile, timeout: adapter
        return simulator, adapter

    def profile(self, **overrides):
        return DeviceProfile(
            preset_id="windows.mumu12",
            installation_path="C:/MuMuPlayer",
            manager_path="C:/MuMuPlayer/nx_main/MuMuManager.exe",
            instance_id="0",
            **overrides,
        )

    def test_parse_hotkey_keys(self):
        self.assertEqual(parse_hotkey_keys(""), [])
        self.assertEqual(parse_hotkey_keys("   "), [])
        self.assertEqual(parse_hotkey_keys("alt+q"), ["alt", "q"])
        self.assertEqual(parse_hotkey_keys("Ctrl+Alt+H"), ["ctrl", "alt", "h"])
        self.assertEqual(parse_hotkey_keys("control+shift+z"), ["ctrl", "shift", "z"])
        self.assertEqual(parse_hotkey_keys("ctrl;alt;f1"), ["ctrl", "alt", "f1"])

    def test_trigger_boss_key_empty(self):
        result = trigger_simulator_boss_key("")
        self.assertFalse(result["ok"])
        self.assertIn("未配置", result["message"])

    def test_trigger_boss_key_immediate(self):
        mock_pyautogui = MagicMock()
        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            with self.assertLogs("arknights_mower.utils.log", level="INFO") as logs:
                result = trigger_simulator_boss_key("ctrl+alt+w")
            self.assertTrue(result["ok"])
            mock_pyautogui.hotkey.assert_called_once_with("ctrl", "alt", "w")
        # The line reports the keystroke that was actually sent, in one sentence.
        self.assertIn("已触发模拟器老板键（ctrl+alt+w）", "\n".join(logs.output))

    def test_trigger_boss_key_handles_exception(self):
        mock_pyautogui = MagicMock()
        mock_pyautogui.hotkey.side_effect = RuntimeError("Display unavailable")
        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            result = trigger_simulator_boss_key("alt+q")
            self.assertFalse(result["ok"])
            self.assertIn("失败", result["message"])

    def test_a_successful_instance_start_triggers_the_configured_boss_key(self):
        simulator, adapter = self.simulator()
        with patch(
            "arknights_mower.utils.device.window.trigger_simulator_boss_key"
        ) as trigger:
            started = simulator.start(
                self.profile(simulator_hotkey="alt+q", simulator_hotkey_delay=4.0), 30.0
            )
        self.assertTrue(started)
        self.assertEqual(adapter.start_calls, [True])
        trigger.assert_called_once_with("alt+q", delay=4.0)

    def test_a_failed_start_and_an_empty_boss_key_stay_silent(self):
        simulator, _ = self.simulator(started=False)
        with patch(
            "arknights_mower.utils.device.window.trigger_simulator_boss_key"
        ) as trigger:
            self.assertFalse(
                simulator.start(self.profile(simulator_hotkey="alt+q"), 30.0)
            )
            simulator, _ = self.simulator()
            self.assertTrue(simulator.start(self.profile(simulator_hotkey=""), 30.0))
        trigger.assert_not_called()


if __name__ == "__main__":
    unittest.main()
