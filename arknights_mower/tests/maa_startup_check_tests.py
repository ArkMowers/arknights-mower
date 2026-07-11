import unittest
from unittest.mock import MagicMock, patch

import arknights_mower.__main__ as mower_main


class TestMaaStartupCheck(unittest.TestCase):
    def test_check_runs_after_initialization_with_connected_device(self):
        calls = []
        scheduler = MagicMock()
        scheduler.device.client.device_id = "connected-device"

        def initialize(_tasks):
            calls.append("initialize")
            return scheduler

        def run_maa_connectivity_check(*, adb):
            calls.append(("maa_check", adb))
            return {"status": "failed", "message": "failed"}

        with (
            patch.object(mower_main, "initialize", side_effect=initialize),
            patch.object(
                mower_main,
                "run_maa_connectivity_check",
                side_effect=run_maa_connectivity_check,
            ),
        ):
            mower_main.simulate(None, startup_maa_check=True)

        self.assertEqual(calls, ["initialize", ("maa_check", "connected-device")])
        scheduler.initialize_operators.assert_not_called()


if __name__ == "__main__":
    unittest.main()
