import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from queue import Empty
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

from webview import FOLDER_DIALOG

from arknights_mower.utils import update_runtime as runtime
from manager import (
    Api,
    choose_instance_directory,
    manager_app,
    manager_window,
    run_manager,
)


class ManagerApiTests(unittest.TestCase):
    def test_instances_are_stored_at_explicit_writable_path(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            storage_path = Path(temporary_dir) / "nested" / "instances.json"
            api = Api(storage_path)

            api.add("default", "/tmp/mower-data")

            reloaded = Api(storage_path)
            self.assertEqual(
                reloaded.get_instances(),
                [{"name": "default", "path": "/tmp/mower-data"}],
            )

    def test_select_path_preserves_cancelled_selection_and_saves_new_directory(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            api = Api(Path(temporary_dir) / "instances.json")
            api.add("default", temporary_dir)
            with (
                mock.patch("manager.webview.active_window") as window,
                mock.patch("manager.choose_instance_directory") as choose,
            ):
                for cancelled in (None, (), []):
                    choose.return_value = cancelled
                    self.assertIsNone(api.select_path(0))
                    self.assertEqual(api.instances[0]["path"], temporary_dir)
                choose.return_value = (str(Path(temporary_dir) / "新建目录"),)
                selected = api.select_path(0)
                choose.assert_called_with(window.return_value, temporary_dir)
                self.assertEqual(Api(api.storage_path).instances[0]["path"], selected)

    def test_launched_instance_uses_manager_tray_even_if_parent_was_background(self):
        from arknights_mower.utils import update_runtime as runtime

        with tempfile.TemporaryDirectory() as temporary_dir:
            api = Api(Path(temporary_dir) / "instances.json")
            api.add("default", temporary_dir)
            with (
                mock.patch.object(runtime, "active_job", return_value=False),
                mock.patch.dict("os.environ", {"MOWER_BACKGROUND": "1"}),
                mock.patch("subprocess.Popen") as process,
            ):
                self.assertTrue(api.start(0)["ok"])
            env = process.call_args.kwargs["env"]
            self.assertEqual(env["MOWER_MANAGED"], "1")
            self.assertEqual(env["MOWER_BACKGROUND"], "0")

    def test_exited_instance_is_reaped_while_manager_stays_open(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            (root / "webview_ui.py").write_text("import sys\nsys.exit(0)\n")
            api = Api(root / "instances.json")
            api.add("reaping-fixture", str(root / "data"))
            children = []
            real_popen = subprocess.Popen

            def launch(*args, **kwargs):
                child = real_popen(*args, **kwargs)
                children.append(child)
                return child

            try:
                with (
                    patch.object(runtime, "active_job", return_value=False),
                    patch.object(runtime, "installation_root", return_value=root),
                    patch.object(subprocess, "Popen", side_effect=launch),
                ):
                    self.assertTrue(api.start(0)["ok"])
                child = children[0]
                deadline = time.monotonic() + 5
                # Do not poll/wait here: only the manager should reap the child.
                while child.returncode is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertEqual(child.returncode, 0)
                self.assertFalse(runtime.process_alive(child.pid))
                self.assertEqual(api.get_instances()[0]["name"], "reaping-fixture")
            finally:
                for child in children:
                    child.wait(timeout=5)


class ManagerAppTests(unittest.TestCase):
    def request(self, app, path):
        environ = {}
        setup_testing_defaults(environ)
        environ["PATH_INFO"] = path
        response = {}

        def start_response(status, headers, exc_info=None):
            response["status"] = status

        body = app(environ, start_response)
        try:
            return response["status"], b"".join(body)
        finally:
            if hasattr(body, "close"):
                body.close()

    def test_initial_page_is_manager_and_shared_assets_resolve_without_redirect(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir) / "ui/dist"
            (root / "manager").mkdir(parents=True)
            (root / "assets").mkdir()
            (root / "index.html").write_text("main UI")
            (root / "manager/index.html").write_text("manager UI")
            (root / "assets/manager.js").write_text("manager script")
            with mock.patch("manager.get_path", return_value=root):
                app = manager_app()
            self.assertEqual(self.request(app, "/"), ("200 OK", b"manager UI"))
            self.assertEqual(
                self.request(app, "/assets/manager.js"), ("200 OK", b"manager script")
            )
            self.assertTrue(
                self.request(app, "/assets/missing.js")[0].startswith("404")
            )

    def test_successful_retry_can_mark_ready_after_initial_loading_failed(self):
        from threading import Event

        ready = Event()
        with tempfile.TemporaryDirectory() as directory:
            api = Api(Path(directory) / "instances.json", ready=ready)
            # Reading data alone does not claim that the page rendered it.
            api.get_instances()
            self.assertFalse(ready.is_set())
            api.mark_ready()
            self.assertTrue(ready.is_set())
            api.mark_ready()
            self.assertTrue(ready.is_set())


class ManagerFolderDialogTests(unittest.TestCase):
    def test_other_platforms_keep_standard_folder_dialog(self):
        window = mock.Mock()
        with mock.patch("manager.sys.platform", "win32"):
            self.assertEqual(
                choose_instance_directory(window, "/data"),
                window.create_file_dialog.return_value,
            )
        window.create_file_dialog.assert_called_once_with(
            dialog_type=FOLDER_DIALOG, directory="/data"
        )

    def test_macos_allows_creating_folders_on_main_thread_and_handles_cancel(self):
        panel = mock.Mock()
        panel.runModal.side_effect = [1, 0]
        panel.URL.return_value.path.return_value = "/tmp/新建目录"
        call_after = mock.Mock(side_effect=lambda callback: callback())
        modules = {
            "AppKit": SimpleNamespace(
                NSModalResponseOK=1,
                NSOpenPanel=SimpleNamespace(openPanel=lambda: panel),
            ),
            "Foundation": SimpleNamespace(
                NSThread=SimpleNamespace(isMainThread=lambda: False), NSURL=mock.Mock()
            ),
            "PyObjCTools": SimpleNamespace(
                AppHelper=SimpleNamespace(callAfter=call_after)
            ),
        }
        with (
            mock.patch("manager.sys.platform", "darwin"),
            mock.patch.dict("sys.modules", modules),
            tempfile.TemporaryDirectory() as initial_directory,
        ):
            self.assertEqual(
                choose_instance_directory(mock.Mock(), initial_directory),
                "/tmp/新建目录",
            )
            call_after.assert_called_once()
            panel.setCanCreateDirectories_.assert_called_once_with(True)
            panel.setCanChooseFiles_.assert_called_once_with(False)
            panel.setCanChooseDirectories_.assert_called_once_with(True)
            panel.setAllowsMultipleSelection_.assert_called_once_with(False)
            panel.setDirectoryURL_.assert_called_once()
            self.assertIsNone(choose_instance_directory(mock.Mock()))

            panel.runModal.side_effect = RuntimeError("dialog failed")
            with self.assertRaisesRegex(RuntimeError, "dialog failed"):
                choose_instance_directory(mock.Mock())


class ManagerLifecycleTests(unittest.TestCase):
    def run_controller(self, messages, *, background=False, records=()):
        from arknights_mower.utils import update_runtime as runtime

        registration = mock.Mock(record={"ready": False})
        registration.shutdown_requested.side_effect = [False] * len(messages) + [True]
        registration.take_commands.return_value = []
        commands = mock.Mock()
        commands.get.side_effect = messages
        with (
            mock.patch.dict(
                "os.environ", {"MOWER_BACKGROUND": "1" if background else "0"}
            ),
            mock.patch.object(runtime, "active_job", return_value=False),
            mock.patch.object(runtime, "unified_managers", return_value=[]),
            mock.patch.object(runtime, "managed_instances", return_value=list(records)),
            mock.patch.object(
                runtime, "RuntimeRegistration", return_value=registration
            ),
            mock.patch.object(runtime, "send_instance_command") as send,
            mock.patch("webview_ui.exit_if_webview_backend_missing"),
            mock.patch("webview_ui.close_child") as close,
            mock.patch("manager.mp.Queue", return_value=commands),
            mock.patch("manager.mp.Event"),
            mock.patch("manager.mp.Pipe", return_value=(mock.Mock(), mock.Mock())),
            mock.patch("manager.mp.Process") as process,
        ):
            run_manager()
        return process, send, close, registration

    def test_silent_manager_has_one_tray_and_no_window(self):
        from arknights_mower.utils.manager_tray import start_manager_tray

        process, _, _, registration = self.run_controller([Empty()], background=True)
        self.assertEqual(
            [call.kwargs["target"] for call in process.call_args_list],
            [start_manager_tray],
        )
        self.assertTrue(registration.record["unified_tray"])
        self.assertTrue(registration.record["ready"])

    def test_normal_manager_has_one_tray_and_separate_panel(self):
        from arknights_mower.utils.manager_tray import start_manager_tray

        process, _, _, _ = self.run_controller([Empty()])
        self.assertEqual(
            [call.kwargs["target"] for call in process.call_args_list],
            [start_manager_tray, manager_window],
        )

    def test_manager_and_instance_closing_are_separate(self):
        records = [{"id": "one"}, {"id": "two"}]
        _, send, _, _ = self.run_controller([("close_manager",)], records=records)
        send.assert_not_called()
        _, send, _, _ = self.run_controller([("close_instances",)], records=records)
        self.assertEqual(
            send.call_args_list,
            [mock.call(record, "exit") for record in records],
        )

    def test_instance_actions_target_only_registered_managed_instances(self):
        record = {"id": "one"}
        _, send, _, _ = self.run_controller(
            [("instance", "one", "browser"), ("instance", "unmanaged", "exit")],
            records=[record],
        )
        send.assert_called_once_with(record, "browser")

    def test_reopening_manager_uses_existing_controller(self):
        from arknights_mower.utils import update_runtime as runtime

        record = {"id": "existing"}
        with (
            mock.patch.object(runtime, "active_job", return_value=False),
            mock.patch.object(runtime, "unified_managers", return_value=[record]),
            mock.patch.object(runtime, "send_instance_command") as send,
            mock.patch("webview_ui.exit_if_webview_backend_missing"),
            mock.patch("manager.mp.Process") as process,
        ):
            run_manager()
        send.assert_called_once_with(record, "show")
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
