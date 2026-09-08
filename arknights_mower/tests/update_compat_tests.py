"""Failure-path integration for update admission, restart and resource indexes."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

from arknights_mower.utils import process_control as control
from arknights_mower.utils import resource_pkg as resources
from arknights_mower.utils import software_update_worker as installer
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.views.process_control import process_control_bp
from arknights_mower.views.software_update import software_update_bp


class UpdateCompatibilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="mower 更新 ")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.state = self.root / "state"
        self.job_path = self.root / "job/job.json"
        self.job = {
            "id": "compat",
            "root": str(self.root),
            "state_dir": str(self.state),
            "deployment": "source",
            "version": "fixture",
            "background": True,
            "python": sys.executable,
        }
        runtime.write_json(self.job_path, self.job)
        self.record = {
            "id": "fixture",
            "pid": os.getpid(),
            "kind": "instance",
            "space": "中文 空间",
            "name": "实例",
            "port": 1234,
            "executable": sys.executable,
            "argv": ["webview_ui.py", "中文 空间", "实例"],
            "cwd": str(self.root),
            "ready": True,
            "restart_job": "compat",
        }

    def test_windows_worktree_cleanup_retries_released_directory_handle(self):
        worker = installer.Worker(self.job_path)
        worker.job["git"] = "git"
        worker.source_stage.mkdir()
        (worker.source_stage / "fixture").write_text("temporary")
        worker.run_command = Mock(side_effect=subprocess.CalledProcessError(255, "git"))
        remove_tree = installer.shutil.rmtree
        locked = PermissionError("directory handle still open")
        locked.winerror = 32
        attempts = 0

        def remove(path):
            nonlocal attempts
            self.assertEqual(path, worker.source_stage)
            attempts += 1
            if attempts == 1:
                raise locked
            remove_tree(path)

        with (
            patch.object(installer.sys, "platform", "win32"),
            patch.object(installer.shutil, "rmtree", side_effect=remove),
            patch.object(installer.time, "sleep") as sleep,
        ):
            worker.cleanup_preparation()
        self.assertEqual(attempts, 2)
        self.assertFalse(worker.source_stage.exists())
        self.assertTrue(self.root.exists())
        worker.run_command.assert_called_once()
        sleep.assert_called_once_with(0.1)

    def test_windows_worktree_cleanup_is_bounded_and_reports_permanent_lock(self):
        worker = installer.Worker(self.job_path)
        worker.job["git"] = "git"
        worker.source_stage.mkdir()
        worker.run_command = Mock(side_effect=subprocess.CalledProcessError(255, "git"))
        locked = PermissionError("directory stays open")
        locked.winerror = 32
        with (
            patch.object(installer.sys, "platform", "win32"),
            patch.object(installer.shutil, "rmtree", side_effect=locked) as remove,
            patch.object(installer.time, "monotonic", side_effect=[0, 6]),
            patch.object(installer.time, "sleep") as sleep,
            patch.object(installer.traceback, "print_exc") as report,
        ):
            worker.cleanup_preparation()
        remove.assert_called_once_with(worker.source_stage)
        sleep.assert_not_called()
        report.assert_called_once()
        self.assertTrue(worker.source_stage.exists())

    def test_settings_apis_report_unreadable_registration_without_server_error(self):
        app = Flask(__name__)
        app.register_blueprint(software_update_bp)
        app.register_blueprint(process_control_bp)
        with (
            patch.object(
                runtime,
                "instances",
                side_effect=runtime.InstanceScanError("登记文件被占用"),
            ),
            patch.object(runtime, "state_dir", return_value=self.state),
            patch.object(runtime, "installation_root", return_value=self.root),
            patch.object(runtime, "frozen", return_value=True),
        ):
            response = app.test_client().get("/software-update/info")
            self.assertEqual(response.status_code, 200)
            self.assertIn("登记文件被占用", response.json["blockers"])
            response = app.test_client().get("/process-control/info")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["supported"])
            self.assertEqual(response.json["message"], "登记文件被占用")

    def test_incomplete_snapshot_aborts_before_shutdown_or_installation(self):
        worker = installer.Worker(self.job_path)
        registration = self.state / "instances/fixture.json"
        runtime.write_json(registration, self.record)
        with (
            patch.object(worker, "prepare_source"),
            patch.object(worker, "prepare_source_payload"),
            patch.object(worker, "cleanup_preparation"),
            patch.object(
                installer,
                "instances",
                side_effect=runtime.InstanceScanError("登记文件被占用"),
            ),
            patch.object(worker, "install_source") as install,
            patch.object(worker, "restart") as restart,
            patch.object(worker, "rollback") as rollback,
        ):
            worker.execute()
        self.assertEqual(worker.status["status"], "failed")
        self.assertIn("登记文件被占用", worker.status["message"])
        self.assertFalse((self.state / "shutdown").exists())
        self.assertEqual(runtime.read_json(registration), self.record)
        install.assert_not_called()
        restart.assert_not_called()
        rollback.assert_not_called()

    def test_software_restart_retries_scan_and_keeps_original_identity(self):
        worker = installer.Worker(self.job_path)
        with (
            patch.object(
                installer.subprocess,
                "Popen",
                return_value=Mock(poll=Mock(return_value=None)),
            ) as spawn,
            patch.object(
                installer,
                "instances",
                side_effect=[runtime.InstanceScanError("locked"), [self.record]],
            ) as scan,
            patch.object(installer.time, "sleep"),
        ):
            worker.restart([self.record])
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(spawn.call_args.kwargs["env"]["MOWER_RESTART_PORT"], "1234")
        self.assertEqual(spawn.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")

    def test_current_instance_restart_retries_scan(self):
        self.job.update(action="restart", record=self.record, frozen=False)
        runtime.write_json(self.job_path, self.job)
        with (
            patch.object(
                control.subprocess,
                "Popen",
                return_value=Mock(poll=Mock(return_value=None)),
            ),
            patch.object(runtime, "process_alive", return_value=False),
            patch.object(
                runtime,
                "instances",
                side_effect=[runtime.InstanceScanError("locked"), [self.record]],
            ) as scan,
            patch.object(control.time, "sleep"),
        ):
            control.execute(self.job_path)
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(
            runtime.read_json(self.job_path.parent / "status.json")["status"],
            "succeeded",
        )

    def test_both_windowed_worker_entrypoints_open_utf8_logs(self):
        for entry, target, filename in (
            (installer.main, "installer", "update.log"),
            (control.worker_main, "control", "process.log"),
        ):
            with self.subTest(entry=entry):
                execute = (
                    patch.object(
                        installer.Worker,
                        "execute",
                        side_effect=lambda: print("更新 🧪"),
                    )
                    if target == "installer"
                    else patch.object(
                        control, "execute", side_effect=lambda _: print("重启 🧪")
                    )
                )
                with (
                    execute,
                    patch.object(sys, "stdout", None),
                    patch.object(sys, "stderr", None),
                ):
                    entry(self.job_path)
                self.assertIn(
                    "🧪", (self.job_path.parent / filename).read_text(encoding="utf-8")
                )

    def test_real_worker_entry_reconfigures_redirected_legacy_stdout(self):
        code = (
            "import sys\n"
            "from unittest.mock import patch\n"
            "from arknights_mower.utils.software_update_worker import Worker, main\n"
            "with patch.object(Worker, 'execute', side_effect=lambda: print('正在更新 🧪', flush=True)):\n"
            "    main(sys.argv[1])\n"
        )
        for encoding in ("gbk", "cp1252"):
            with self.subTest(encoding=encoding):
                output = subprocess.check_output(
                    [sys.executable, "-c", code, str(self.job_path)],
                    env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": encoding},
                    stderr=subprocess.STDOUT,
                    timeout=30,
                )
                self.assertEqual(output.decode("utf-8").strip(), "正在更新 🧪")

    def test_resource_index_retries_windows_sharing_error_and_keeps_old_on_failure(
        self,
    ):
        index = self.root / "resources/index.json"
        with patch.object(resources, "RESOURCE_OVERLAY", index.parent):
            resources._write_index(["old"])
            replace = os.replace
            attempts = []

            def replace_once(source, destination):
                attempts.append(destination)
                if len(attempts) == 1:
                    error = PermissionError("sharing violation")
                    error.winerror = 32
                    raise error
                return replace(source, destination)

            with (
                patch.object(runtime.sys, "platform", "win32"),
                patch.object(runtime.os, "replace", side_effect=replace_once),
            ):
                resources._write_index(["new"])
            self.assertEqual(len(attempts), 2)
            self.assertEqual(runtime.read_json(index), {"packages": ["new"]})
            with patch.object(runtime.os, "replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    resources._write_index(["failed"])
            self.assertEqual(runtime.read_json(index), {"packages": ["new"]})
            self.assertEqual(list(index.parent.iterdir()), [index])


if __name__ == "__main__":
    unittest.main()
