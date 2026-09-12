import os
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest import mock

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.manager_tray import manager_menu


class RuntimeCommandTests(unittest.TestCase):
    def test_commands_reach_only_the_selected_instance_once(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(runtime, "state_dir", return_value=Path(temporary)),
            mock.patch.dict(os.environ, {"MOWER_MANAGED": "1"}),
        ):
            first = runtime.RuntimeRegistration("instance", name="first")
            second = runtime.RuntimeRegistration("instance", name="second")
            try:
                runtime.send_instance_command(first.record, "browser")
                self.assertEqual(second.take_commands(), [])
                self.assertEqual(first.take_commands(), ["browser"])
                self.assertEqual(first.take_commands(), [])
                runtime.send_instance_command(second.record, "exit")
                self.assertFalse(first.shutdown_requested())
                self.assertTrue(second.shutdown_requested())
                with self.assertRaises(ValueError):
                    runtime.send_instance_command(first.record, "unsupported")
            finally:
                first.close()
                second.close()
            self.assertEqual(runtime.instances(), [])

    def test_shared_menu_excludes_standalone_and_other_data_roots(self):
        records = [
            {"id": "ours", "kind": "instance", "managed": True, "data_dir": "/ours"},
            {"id": "other", "kind": "instance", "managed": True, "data_dir": "/other"},
            {"id": "standalone", "kind": "instance", "managed": False},
            {
                "id": "manager",
                "kind": "manager",
                "unified_tray": True,
                "data_dir": "/ours",
            },
        ]
        with mock.patch.object(runtime, "instances", return_value=records):
            self.assertEqual(runtime.managed_instances(data_dir="/ours"), [records[0]])
            self.assertEqual(runtime.unified_managers(data_dir="/ours"), [records[3]])

    def test_launch_environment_does_not_leak_managed_state_to_standalone_instance(
        self,
    ):
        with mock.patch.dict(os.environ, {"MOWER_MANAGED": "1"}):
            self.assertEqual(runtime.launch_environment({})["MOWER_MANAGED"], "0")
            self.assertEqual(
                runtime.launch_environment({"managed": True})["MOWER_MANAGED"], "1"
            )


class Menu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items

    def __iter__(self):
        if len(self.items) == 1 and callable(self.items[0]):
            return iter(self.items[0]())
        return iter(self.items)


class MenuItem:
    def __init__(self, text, action, **kwargs):
        self.text = text
        self.action = action
        self.enabled = kwargs.get("enabled", True)


class ManagerTrayMenuTests(unittest.TestCase):
    def test_menu_refreshes_instances_and_dispatches_browser_and_separate_closing(self):
        commands = Queue()
        records = [{"id": "one", "name": "测试实例", "port": 58100}]
        with (
            mock.patch.dict(
                "sys.modules",
                {"pystray": SimpleNamespace(Menu=Menu, MenuItem=MenuItem)},
            ),
            mock.patch.object(
                runtime, "managed_instances", side_effect=lambda: records
            ),
        ):
            menu = manager_menu(commands)
            items = {item.text: item for item in menu if isinstance(item, MenuItem)}
            instance_items = {
                item.text: item
                for item in items["测试实例 @58100"].action
                if isinstance(item, MenuItem)
            }
            instance_items["在浏览器中打开网页面板"].action()
            self.assertEqual(commands.get_nowait(), ("instance", "one", "browser"))
            instance_items["打开/关闭窗口"].action()
            self.assertEqual(commands.get_nowait(), ("instance", "one", "toggle"))
            instance_items["关闭此实例"].action()
            self.assertEqual(commands.get_nowait(), ("instance", "one", "exit"))
            items["关闭所有实例"].action()
            self.assertEqual(commands.get_nowait(), ("close_instances",))
            items["关闭多开管理器"].action()
            self.assertEqual(commands.get_nowait(), ("close_manager",))
            records.clear()
            items = {item.text: item for item in menu if isinstance(item, MenuItem)}
            self.assertIn("暂无运行中的实例", items)
            self.assertFalse(items["关闭所有实例"].enabled)
