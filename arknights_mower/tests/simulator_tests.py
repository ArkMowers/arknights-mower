import json
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from arknights_mower.utils import config, simulator
from arknights_mower.utils.device.adb_client import core as adb_core


class TestSimulatorReady(unittest.TestCase):
    def setUp(self):
        self.old_target = "127.0.0.1:16384"
        self.new_target = "127.0.0.1:16416"
        self.conf = SimpleNamespace(
            adb=self.old_target,
            fix_mumu12_adb_disconnect=False,
            simulator=SimpleNamespace(
                name="MuMu12", index="0", simulator_folder="", wait_time=2, hotkey=""
            ),
        )
        self.enterContext(patch.object(config, "conf", self.conf))
        self.discover = self.enterContext(
            patch.object(simulator, "query_mumu_adb_port", return_value=None)
        )
        self.session = self.enterContext(patch.object(simulator, "Session"))
        self.session.return_value.devices_list.return_value = []
        self.popen = self.enterContext(patch.object(simulator.subprocess, "Popen"))
        self.popen.return_value.poll.return_value = 0
        self.popen.return_value.returncode = 0
        self.sleep = self.enterContext(patch.object(simulator, "csleep"))

    def test_only_device_state_is_ready(self):
        for target in (self.old_target, ""):
            for state in ("offline", "unauthorized", "device"):
                with self.subTest(target=target, state=state):
                    self.conf.adb = target
                    self.session.return_value.devices_list.return_value = [
                        (self.old_target, state)
                    ]
                    self.assertEqual(simulator.adb_ready(), state == "device")

    def test_other_online_device_does_not_make_target_ready(self):
        self.session.return_value.devices_list.return_value = [
            (self.old_target, "offline"),
            (self.new_target, "device"),
        ]
        self.assertFalse(simulator.adb_ready())

    def test_empty_device_list_is_not_ready(self):
        self.conf.adb = ""
        self.assertFalse(simulator.adb_ready())

    def test_cold_start_discovers_new_port_without_extra_restart(self):
        # 启动前及首轮等待尚无端口，第二轮等待才发现新端口。
        self.discover.side_effect = [None, None, self.new_target]
        self.session.return_value.devices_list.side_effect = [
            [],
            [(self.new_target, "device")],
        ]
        self.assertTrue(simulator.restart_simulator(stop=False, start=True))
        self.assertEqual(self.conf.adb, self.new_target)
        self.session.return_value.connect.assert_called_with(
            self.new_target, throw_error=True
        )
        self.popen.assert_called_once()
        self.assertIn("launch_player", self.popen.call_args.args[0])

    def test_cold_start_hides_every_windows_port_discovery_process(self):
        # 使用真实端口查询：启动前和首轮探测未就绪，第二轮才发现新端口。
        # 设置 120 秒仍可在就绪后提前继续，隐藏窗口不改变等待/重发现规则。
        self.conf.simulator.wait_time = 120
        self.discover.side_effect = adb_core.query_mumu_adb_port
        self.session.return_value.devices_list.side_effect = [
            [],
            [(self.new_target, "device")],
        ]
        no_window = 0x08000000
        with (
            patch.object(adb_core, "__system__", "windows"),
            patch.object(simulator, "__system__", "windows"),
            patch.object(adb_core.os.path, "isfile", return_value=True),
            patch.object(
                adb_core.subprocess, "CREATE_NO_WINDOW", no_window, create=True
            ),
            patch.object(adb_core.subprocess, "run") as run,
        ):
            run.side_effect = [
                SimpleNamespace(stdout="{}"),
                SimpleNamespace(stdout="{}"),
                SimpleNamespace(stdout=json.dumps({"0": {"adb_port": 16416}})),
            ]
            self.assertTrue(simulator.restart_simulator(stop=False, start=True))
        self.assertEqual(run.call_count, 3)
        for invocation in run.call_args_list:
            self.assertEqual(
                invocation.args[0], ["MuMuManager.exe", "info", "-v", "all"]
            )
            self.assertEqual(invocation.kwargs["creationflags"], no_window)
            self.assertTrue(invocation.kwargs["capture_output"])
        self.popen.assert_called_once()
        self.assertEqual(self.popen.call_args.kwargs["creationflags"], no_window)
        self.assertEqual(self.conf.adb, self.new_target)
        self.sleep.assert_has_calls([call(3), call(1)])
        self.assertEqual(self.sleep.call_count, 2)

    def test_non_windows_port_discovery_does_not_use_windows_creation_flags(self):
        for platform in ("linux", "darwin"):
            with (
                self.subTest(platform=platform),
                patch.object(adb_core, "__system__", platform),
                patch.object(adb_core.os.path, "isfile", return_value=True),
                patch.object(adb_core.subprocess, "run") as run,
            ):
                run.return_value.stdout = json.dumps({"0": {"adb_port": 16416}})
                self.assertEqual(
                    adb_core.query_mumu_adb_port(self.conf.simulator), self.new_target
                )
                run.assert_called_once()
                self.assertEqual(run.call_args.kwargs["creationflags"], 0)

    def test_discovery_failure_keeps_configured_target(self):
        self.session.return_value.devices_list.return_value = [
            (self.old_target, "device")
        ]
        self.assertTrue(simulator.adb_ready())
        self.assertEqual(self.conf.adb, self.old_target)


if __name__ == "__main__":
    unittest.main()
