import unittest
from unittest.mock import Mock, patch

from arknights_mower.utils import update_runtime
from arknights_mower.utils.device.mumu12ipc import core as mumu_ipc


class WindowsConsoleTests(unittest.TestCase):
    def test_hidden_console_options_are_windows_only(self):
        with patch.object(update_runtime.sys, "platform", "win32"):
            self.assertEqual(
                update_runtime.hidden_console_options(),
                {"creationflags": 0x08000000},
            )
        with patch.object(update_runtime.sys, "platform", "linux"):
            self.assertEqual(update_runtime.hidden_console_options(), {})

    def test_mumu_queries_hide_the_windows_console(self):
        ipc = object.__new__(mumu_ipc.MuMu12IPC)
        ipc._manager = "MuMuManager.exe"
        ipc._index = 0
        ipc._setting_info = None
        responses = [
            '{"name": "MuMu"}',
            "4.1.21",
            "player index: 0\nstate: state=running\n",
        ]
        with (
            patch.object(
                mumu_ipc,
                "hidden_console_options",
                return_value={"creationflags": 0x08000000},
            ),
            patch.object(
                mumu_ipc.subprocess,
                "run",
                side_effect=[Mock(stdout=x) for x in responses],
            ) as run,
        ):
            self.assertEqual(ipc._manager_json("info"), {"name": "MuMu"})
            self.assertEqual(ipc.get_setting_core_version(), "4.1.21")
            self.assertEqual(ipc.get_emulator_info(), "running")

        self.assertEqual(run.call_count, 3)
        for invocation in run.call_args_list:
            self.assertEqual(invocation.kwargs["creationflags"], 0x08000000)


if __name__ == "__main__":
    unittest.main()
