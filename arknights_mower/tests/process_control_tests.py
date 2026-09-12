import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from flask import Flask

from arknights_mower.utils import process_control as control
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.views.process_control import process_control_bp


class ProcessControlTests(unittest.TestCase):
    def test_reset_start_skips_incompatible_saved_state(self):
        import server

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(server, "active_job", return_value=False),
            patch.object(server, "_job_running", return_value=False),
            patch.object(server, "mower_thread", None),
            patch.object(server, "log_stream"),
            patch.object(server, "get_path", return_value=Path(folder)),
            patch.object(server.config, "stop_mower"),
            patch.object(server.config.conf, "refresh_backup_plan_after_mood", True),
            patch.object(
                server, "load_state", side_effect=ValueError("incompatible snapshot")
            ) as load,
            patch.object(server, "Thread") as thread,
            patch.object(server, "set_mower_thread"),
        ):
            headers = {"token": getattr(server.app, "token", "")}
            response = server.app.test_client().get("/start/2", headers=headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            load.assert_not_called()
            self.assertEqual(thread.call_args.kwargs["args"], ({}, True))

    def test_normal_start_still_loads_saved_state(self):
        import server

        saved_state = {"tasks": ["saved-task"]}
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(server, "active_job", return_value=False),
            patch.object(server, "_job_running", return_value=False),
            patch.object(server, "mower_thread", None),
            patch.object(server, "log_stream"),
            patch.object(server, "get_path", return_value=Path(folder)),
            patch.object(server.config, "stop_mower"),
            patch.object(server, "load_state", return_value=saved_state) as load,
            patch.object(server, "Thread") as thread,
            patch.object(server, "set_mower_thread"),
        ):
            headers = {"token": getattr(server.app, "token", "")}
            response = server.app.test_client().get("/start/0", headers=headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            load.assert_called_once_with()
            self.assertEqual(thread.call_args.kwargs["args"], (saved_state, False))

    def test_route_requires_token_and_intent_header(self):
        app = Flask(__name__)
        app.token = "private-fixture"
        app.register_blueprint(process_control_bp)
        client = app.test_client()
        with patch.object(
            control, "request_action", return_value={"ok": True}
        ) as action:
            for headers in (
                {},
                {"token": app.token},
                {
                    "token": app.token,
                    "X-Mower-Control": "1",
                    "Origin": "https://other.invalid",
                },
            ):
                self.assertEqual(
                    client.post(
                        "/process-control/action",
                        json={"action": "stop"},
                        headers=headers,
                    ).status_code,
                    403,
                )
            action.assert_not_called()
            response = client.post(
                "/process-control/action",
                json={"action": "restart"},
                headers={"token": app.token, "X-Mower-Control": "1"},
            )
            self.assertTrue(response.get_json()["ok"])
            action.assert_called_once_with("restart")

    def test_status_id_cannot_escape_job_directory(self):
        for value in ("../status", "../../job", "", None):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                control.job_folder(value)

    def test_restart_command_keeps_source_and_frozen_arguments(self):
        record = {
            "executable": "/app/python",
            "argv": ["webview_ui.py", "/data/space with spaces", "实例", "extra"],
        }
        self.assertEqual(
            control.restart_command(record, False),
            [record["executable"], *record["argv"]],
        )
        self.assertEqual(
            control.restart_command(record, True),
            [record["executable"], *record["argv"][1:]],
        )

    def test_only_current_instance_is_selected(self):
        records = [
            {"pid": os.getpid() + 1, "kind": "instance"},
            {"pid": os.getpid(), "kind": "instance", "name": "chosen"},
        ]
        with patch.object(runtime, "instances", return_value=records):
            self.assertEqual(control.current_instance()["name"], "chosen")

    def test_active_update_blocks_process_control(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(runtime, "state_dir", return_value=Path(folder)),
            patch.object(runtime, "active_job", return_value=True),
            patch.object(subprocess, "Popen") as launch,
        ):
            with self.assertRaisesRegex(ValueError, "正在进行"):
                control.request_action("restart")
            launch.assert_not_called()


class ProcessControlIntegrationTests(unittest.TestCase):
    def test_current_instance_restart_and_stop_preserve_manager_and_other_instances(
        self,
    ):
        with tempfile.TemporaryDirectory(prefix="mower-control-") as folder:
            root = Path(folder)
            state = root / "state"
            launcher = root / "launcher.py"
            runtime_copy = root / "update_runtime.py"
            runtime_copy.write_text(
                Path(runtime.__file__).read_text(encoding="utf-8"), encoding="utf-8"
            )
            launcher.write_text(
                "import os,sys,time\nfrom pathlib import Path\nimport update_runtime as r\n"
                f"r.state_dir=lambda:Path({str(state)!r})\n"
                "kind='manager' if sys.argv[1]=='manager' else 'instance'\n"
                "record=r.RuntimeRegistration(kind,space=sys.argv[1],name=sys.argv[2],port=int(os.environ['MOWER_RESTART_PORT']),running=lambda:os.environ.get('MOWER_RESUME_RUN')=='1')\n"
                "record.record.update(ready=True);record.publish()\n"
                "while not record.shutdown_requested():time.sleep(.02)\nrecord.close()\n",
                encoding="utf-8",
            )
            processes = []
            real_popen = subprocess.Popen

            def launch(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                processes.append(process)
                threading.Thread(target=process.wait, daemon=True).start()
                return process

            def wait_for_records(count):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    records = runtime.instances(state)
                    if len(records) == count and all(
                        record.get("ready") for record in records
                    ):
                        return records
                    time.sleep(0.05)
                self.fail("fixture processes did not become ready")

            try:
                for index, name in enumerate(
                    ("当前实例", "其他一", "其他二", "manager")
                ):
                    space = (
                        "manager" if name == "manager" else str(root / f"data {index}")
                    )
                    env = runtime.launch_environment(
                        {
                            "port": 58800 + index,
                            "running": index == 0,
                            "data_dir": str(root / "shared data"),
                        }
                    )
                    launch(
                        [
                            sys.executable,
                            str(launcher),
                            space,
                            name,
                            "keep-extra-argument",
                        ],
                        cwd=root,
                        env=env,
                    )
                originals = wait_for_records(4)
                target = next(
                    record for record in originals if record["name"] == "当前实例"
                )
                untouched = {
                    record["pid"]
                    for record in originals
                    if record["pid"] != target["pid"]
                }
                job_id = uuid4().hex
                job_path = root / "restart/job.json"
                runtime.write_json(
                    job_path,
                    {
                        "id": job_id,
                        "action": "restart",
                        "record": target,
                        "state_dir": str(state),
                        "frozen": False,
                    },
                )
                runtime.write_json(
                    state / "active/owner.json", {"id": job_id, "pid": os.getpid()}
                )
                with patch.object(control.subprocess, "Popen", side_effect=launch):
                    control.execute(job_path)
                result = runtime.read_json(job_path.parent / "status.json")
                self.assertEqual(result["status"], "succeeded", result)
                records = wait_for_records(4)
                restarted = next(
                    record for record in records if record["name"] == "当前实例"
                )
                self.assertNotEqual(restarted["pid"], target["pid"])
                for key in (
                    "space",
                    "name",
                    "port",
                    "running",
                    "data_dir",
                    "argv",
                    "cwd",
                    "background",
                ):
                    self.assertEqual(restarted[key], target[key], key)
                self.assertEqual(
                    {
                        record["pid"]
                        for record in records
                        if record["pid"] != restarted["pid"]
                    },
                    untouched,
                )
                job = runtime.read_json(job_path)
                job.update(action="stop", record=restarted)
                runtime.write_json(job_path, job)
                control.execute(job_path)
                self.assertEqual(
                    {record["pid"] for record in wait_for_records(3)}, untouched
                )
                self.assertFalse((state / "active").exists())
            finally:
                for record in runtime.instances(state):
                    runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
                for process in processes:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)


class ProcessRestartPersistenceTests(unittest.TestCase):
    def test_repeated_process_restart_keeps_restored_config_plan_and_update_ack(self):
        """Run the restart worker with real config loading in isolated child processes."""
        import json

        from arknights_mower.utils.config.plan import PlanModel

        tmp_path = Path(self.enterContext(tempfile.TemporaryDirectory()))
        state = tmp_path / "runtime"
        data = tmp_path / "data"
        config_dir = data / "instance" / "config"
        config_dir.mkdir(parents=True)
        plan = PlanModel(
            plan1={"central": {"plans": [{"agent": "阿米娅"}]}}
        ).model_dump(exclude_none=True)
        (config_dir / "conf.yml").write_text("account: original\n", encoding="utf-8")
        # Imported originals may include a BOM; actual startup must accept it too.
        (config_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8-sig")
        original_plan_bytes = (config_dir / "plan.json").read_bytes()
        launcher = tmp_path / "launcher.py"
        launcher.write_text(
            "import sys,time\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})\n"
            "from arknights_mower.utils import path\npath.global_space=sys.argv[1]\n"
            "from arknights_mower.utils import config,update_runtime as runtime\n"
            "from arknights_mower.utils.update_notice import UpdateNoticeManager\n"
            f"runtime.state_dir=lambda:Path({str(state)!r})\n"
            "notice=UpdateNoticeManager()\nshown=notice.get_notice()['should_show']\n"
            "notice.acknowledge(notice.current_version)\n"
            "record=runtime.RuntimeRegistration('instance',space=sys.argv[1])\n"
            "record.record.update(ready=True,account=config.conf.account,plan=config.plan.model_dump(exclude_none=True),notice=shown)\n"
            "record.publish()\n"
            "while not record.shutdown_requested():time.sleep(.02)\nrecord.close()\n",
            encoding="utf-8",
        )
        processes = []
        real_popen = subprocess.Popen

        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            threading.Thread(target=process.wait, daemon=True).start()
            return process

        def ready():
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                records = runtime.instances(state, timeout=0)
                if len(records) == 1 and records[0].get("ready"):
                    return records[0]
                time.sleep(0.05)
            raise AssertionError("isolated config launcher did not become ready")

        try:
            launch(
                [sys.executable, str(launcher), "instance"],
                cwd=tmp_path,
                env=runtime.launch_environment({"data_dir": str(data)}),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            record = ready()
            assert record["account"] == "original"
            assert record["notice"] is True
            acknowledged = (config_dir / "state.json").read_bytes()
            self.enterContext(
                patch.object(control.subprocess, "Popen", side_effect=launch)
            )
            for index in range(2):
                account = f"manually-restored-{index}"
                (config_dir / "conf.yml").write_text(
                    f"account: {account}\n", encoding="utf-8"
                )
                job_id = uuid4().hex
                job_path = tmp_path / job_id / "job.json"
                runtime.write_json(
                    job_path,
                    {
                        "id": job_id,
                        "action": "restart",
                        "record": record,
                        "state_dir": str(state),
                        "frozen": False,
                    },
                )
                control.execute(job_path)
                assert (
                    runtime.read_json(job_path.parent / "status.json")["status"]
                    == "succeeded"
                )
                record = ready()
                assert record["account"] == account
                assert record["plan"] == plan
                assert (config_dir / "plan.json").read_bytes() == original_plan_bytes
                assert record["notice"] is False
                assert (config_dir / "state.json").read_bytes() == acknowledged
        finally:
            for record in runtime.instances(state):
                runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
