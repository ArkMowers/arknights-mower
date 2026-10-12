"""Exercise authenticated progress handoff and cancellation on local sockets."""

import ctypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from flask import Flask

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_progress import (
    ProgressServers,
    cancel_update,
    read_status,
)
from arknights_mower.utils.software_update_worker import (
    UpdateCancelled,
    WindowsCommandJob,
    Worker,
)
from arknights_mower.views.software_update import software_update_bp


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.state = self.directory / "state"
        self.work = self.directory / "job"
        self.job = {
            "id": "local-progress",
            "root": str(self.directory),
            "state_dir": str(self.state),
            "deployment": "source",
            "version": "test",
        }
        runtime.write_json(self.work / "job.json", self.job)
        runtime.write_json(
            self.state / "active/owner.json", {"pid": os.getpid(), "id": self.job["id"]}
        )
        runtime.write_json(
            self.state / "status.json",
            {
                "id": self.job["id"],
                "status": "running",
                "cancellable": True,
                "message": "本地测试",
                "log_path": str(self.work / "update.log"),
            },
        )
        (self.work / "update.log").write_text("安装日志", encoding="utf-8")

    def test_cancellation_is_bound_to_active_job(self):
        with self.assertRaises(ValueError):
            cancel_update(self.state, "stale-job")
        self.assertFalse((self.state / "active/cancel.json").exists())
        cancel_update(self.state, self.job["id"])
        with self.assertRaises(UpdateCancelled):
            Worker(self.work / "job.json").begin_install()
        self.assertFalse((self.state / "active/installing.json").exists())
        self.assertFalse(read_status(self.state)["cancellable"])
        self.assertIn("正在取消", read_status(self.state)["message"])

    def test_installation_transition_refuses_late_cancel(self):
        worker = Worker(self.work / "job.json")
        worker.begin_install()
        with self.assertRaisesRegex(ValueError, "已开始替换"):
            cancel_update(self.state, self.job["id"])
        self.assertFalse(read_status(self.state)["cancellable"])
        worker.check_cancelled()

    def test_download_progress_uses_actual_bytes_and_stays_within_bounds(self):
        for current, expected in ((0, 0), (1, 33.3), (3, 100), (4, 100)):
            with self.subTest(current=current):
                runtime.write_json(
                    self.state / "status.json",
                    {
                        "status": "running",
                        "phase": "downloading",
                        "current": current,
                        "total": 3,
                    },
                )
                self.assertEqual(read_status(self.state)["progress"], expected)

    def test_unmeasured_stages_do_not_reuse_completed_download_percentage(self):
        for phase in (
            "preparing",
            "dependencies",
            "building",
            "extracting",
            "stopping",
            "installing",
            "restarting",
            "rollback",
        ):
            with self.subTest(phase=phase):
                runtime.write_json(
                    self.state / "status.json",
                    {"status": "running", "phase": phase, "current": 100, "total": 100},
                )
                self.assertIsNone(read_status(self.state)["progress"])

    def test_source_or_unknown_size_download_has_no_invented_percentage(self):
        for sizes in ({}, {"current": 20, "total": 0}):
            with self.subTest(sizes=sizes):
                runtime.write_json(
                    self.state / "status.json",
                    {"status": "running", "phase": "downloading", **sizes},
                )
                self.assertIsNone(read_status(self.state)["progress"])

    def test_only_successful_terminal_job_has_a_completion_percentage(self):
        for status in ("succeeded", "failed", "cancelled"):
            with self.subTest(status=status):
                runtime.write_json(
                    self.state / "status.json",
                    {"status": status, "phase": "done", "current": 100, "total": 100},
                )
                self.assertEqual(
                    read_status(self.state)["progress"],
                    100 if status == "succeeded" else None,
                )

    def test_cancel_kills_only_the_update_command_tree(self):
        worker = Worker(self.work / "job.json")
        marker = self.work / "command-started"
        errors = []

        def run():
            try:
                worker.run_command(
                    [
                        sys.executable,
                        "-c",
                        "import pathlib, time; pathlib.Path("
                        + repr(str(marker))
                        + ").touch(); time.sleep(60)",
                    ]
                )
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=run)
        thread.start()
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(marker.exists())
        cancel_update(self.state, self.job["id"])
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], UpdateCancelled)
        self.assertTrue(runtime.process_alive(os.getpid()))

    def test_cleanup_commands_can_run_after_cancellation(self):
        worker = Worker(self.work / "job.json")
        cancel_update(self.state, self.job["id"])
        worker.run_command([sys.executable, "-c", "pass"], cancellable=False)

    def test_windows_command_is_contained_before_it_can_spawn(self):
        worker = Worker(self.work / "job.json")
        events = []
        process, job = Mock(), Mock()
        process.wait.return_value = 0
        job.start.side_effect = lambda value: events.append("start")
        job.close.side_effect = lambda: events.append("close")
        with (
            patch("sys.platform", "win32"),
            patch(
                "arknights_mower.utils.software_update_worker.detached_options",
                return_value={"creationflags": 0x08000000},
            ),
            patch(
                "arknights_mower.utils.software_update_worker.WindowsCommandJob",
                return_value=job,
            ),
            patch("subprocess.Popen", return_value=process) as spawn,
        ):
            worker.run_command(["npm.cmd", "run", "build"])
        self.assertEqual(spawn.call_args.kwargs["creationflags"], 0x08000004)
        job.start.assert_called_once_with(process)
        self.assertEqual(events, ["start", "close"])

    def test_windows_cancel_and_timeout_wait_for_the_owned_tree(self):
        worker = Worker(self.work / "job.json")
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                process, job = Mock(), Mock()
                events = []
                job.close.side_effect = lambda: events.append("tree-stopped")
                process.wait.side_effect = lambda **kwargs: events.append("root-waited")
                with (
                    patch("sys.platform", "win32"),
                    patch(
                        "arknights_mower.utils.software_update_worker.detached_options",
                        return_value={"creationflags": 0},
                    ),
                    patch(
                        "arknights_mower.utils.software_update_worker.WindowsCommandJob",
                        return_value=job,
                    ),
                    patch("subprocess.Popen", return_value=process),
                    patch.object(
                        worker,
                        "check_cancelled",
                        side_effect=[None, UpdateCancelled()] if cancelled else None,
                    ),
                ):
                    with self.assertRaises(
                        UpdateCancelled if cancelled else subprocess.TimeoutExpired
                    ):
                        worker.run_command(["npm.cmd", "run", "build"], timeout=0)
                self.assertEqual(events[:2], ["tree-stopped", "root-waited"])
                process.kill.assert_not_called()

    def test_windows_failed_containment_reaps_the_suspended_command(self):
        worker = Worker(self.work / "job.json")
        process, job = Mock(), Mock()
        job.start.side_effect = OSError("fixture assignment failure")
        with (
            patch("sys.platform", "win32"),
            patch(
                "arknights_mower.utils.software_update_worker.detached_options",
                return_value={"creationflags": 0},
            ),
            patch(
                "arknights_mower.utils.software_update_worker.WindowsCommandJob",
                return_value=job,
            ),
            patch("subprocess.Popen", return_value=process),
        ):
            with self.assertRaisesRegex(OSError, "assignment failure"):
                worker.run_command(["npm.cmd", "run", "build"])
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=15)
        job.close.assert_called_once()

    def test_windows_job_waits_for_all_descendants_and_closes_once(self):
        class Accounting(ctypes.Structure):
            _fields_ = [("ActiveProcesses", ctypes.c_uint32)]

        job = object.__new__(WindowsCommandJob)
        job.ctypes, job.Accounting, job.handle = ctypes, Accounting, 71
        job.kernel = Mock()
        counts = iter([2, 1, 0])

        def query(handle, info, value, size, returned):
            value._obj.ActiveProcesses = next(counts)
            return True

        job.kernel.QueryInformationJobObject.side_effect = query
        with patch("time.sleep"):
            job.close()
            job.close()
        self.assertEqual(job.kernel.QueryInformationJobObject.call_count, 3)
        job.kernel.TerminateJobObject.assert_called_once_with(71, 1)
        job.kernel.CloseHandle.assert_called_once_with(71)

    def test_windows_job_cleanup_is_bounded_and_closes_on_timeout(self):
        class Accounting(ctypes.Structure):
            _fields_ = [("ActiveProcesses", ctypes.c_uint32)]

        job = object.__new__(WindowsCommandJob)
        job.ctypes, job.Accounting, job.handle = ctypes, Accounting, 71
        job.kernel = Mock()

        def query(handle, info, value, size, returned):
            value._obj.ActiveProcesses = 1
            return True

        job.kernel.QueryInformationJobObject.side_effect = query
        with patch("time.monotonic", side_effect=[0, 16]):
            with self.assertRaisesRegex(TimeoutError, "15"):
                job.close()
        job.kernel.CloseHandle.assert_called_once_with(71)

    def test_download_cancel_removes_partial_package_without_stopping_instances(self):
        self.job.update(
            deployment="release",
            asset={
                "name": "test.zip",
                "url": "https://github.com/example/test.zip",
                "sha256": "unused",
            },
        )
        runtime.write_json(self.work / "job.json", self.job)
        worker = Worker(self.work / "job.json")
        worker.stop_instances = Mock()
        response = Mock()

        def chunks(size):
            yield b"partial package"
            cancel_update(self.state, self.job["id"])
            yield b"not written"

        response.iter_content.side_effect = chunks
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("requests.get", return_value=response):
            worker.execute()
        worker.stop_instances.assert_not_called()
        self.assertEqual(read_status(self.state)["status"], "cancelled")
        self.assertFalse((self.work / "test.zip").exists())

    def test_cancelled_stalled_download_is_reported_as_cancelled(self):
        self.job.update(
            deployment="release",
            asset={"name": "test.zip", "url": "https://github.com/example/test.zip"},
        )
        runtime.write_json(self.work / "job.json", self.job)
        worker = Worker(self.work / "job.json")
        worker.stop_instances = Mock()

        def timeout(*args, **kwargs):
            cancel_update(self.state, self.job["id"])
            raise TimeoutError("fixture network timeout")

        with patch("requests.get", side_effect=timeout):
            worker.execute()
        self.assertEqual(read_status(self.state)["status"], "cancelled")
        worker.stop_instances.assert_not_called()

    def test_progress_server_authentication_and_port_release(self):
        with socket.socket() as socket_:
            socket_.bind(("127.0.0.1", 0))
            port = socket_.getsockname()[1]
        token = "local-fixture-token"
        servers = ProgressServers(
            self.state,
            [
                {
                    "kind": "instance",
                    "port": port,
                    "listen_host": "127.0.0.1",
                    "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                }
            ],
        )
        self.addCleanup(servers.close)
        servers.start()
        self.assertEqual(len(servers.servers), 1)
        opener = build_opener(ProxyHandler({}))
        url = f"http://127.0.0.1:{port}"

        def get(path, **kwargs):
            return opener.open(Request(url + path, **kwargs), timeout=3)

        with get("/software-update/progress") as response:
            self.assertIn("Mower 更新进度", response.read().decode())
        with self.assertRaises(HTTPError) as error:
            get("/software-update/status")
        with error.exception:
            self.assertEqual(error.exception.code, 403)
        headers = {
            "token": token,
            "X-Mower-Update": "1",
            "Content-Type": "application/json",
        }
        with get("/software-update/status", headers=headers) as response:
            self.assertEqual(json.load(response)["log"], "安装日志")
        for path, origin, status in (
            ("/software-update/cancel", "http://elsewhere.invalid", 403),
            ("/unexpected", url, 404),
        ):
            with self.assertRaises(HTTPError) as error:
                get(path, headers={**headers, "Origin": origin}, data=b"{}")
            with error.exception:
                self.assertEqual(error.exception.code, status)
            self.assertFalse((self.state / "active/cancel.json").exists())
        data = json.dumps({"id": self.job["id"]}).encode()
        with get("/software-update/cancel", headers=headers, data=data) as response:
            self.assertTrue(json.load(response)["ok"])
        servers.close()
        # A replacement HTTP server can bind the exact original port immediately.
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        with ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler):
            pass

    def test_rejected_progress_posts_consume_bounded_body_before_reply(self):
        handler_type = ProgressServers(self.state, []).handler(
            hashlib.sha256(b"fixture").hexdigest()
        )
        headers = {"token": "fixture", "X-Mower-Update": "1", "Host": "localhost"}
        for changed, path, status in (
            ({"token": "wrong"}, "/software-update/cancel", 403),
            ({"X-Mower-Update": "0"}, "/software-update/cancel", 403),
            ({"Origin": "http://elsewhere.invalid"}, "/software-update/cancel", 403),
            ({}, "/unexpected", 404),
        ):
            with self.subTest(changed=changed, path=path):
                handler = object.__new__(handler_type)
                handler.headers = {**headers, **changed, "Content-Length": "8"}
                handler.path = path
                handler.connection = Mock()
                handler.rfile = BytesIO(b"not-json")

                def reply(code, body):
                    self.assertEqual(handler.rfile.tell(), 8)
                    self.assertEqual((code, body), (status, {"ok": False}))

                handler.reply = Mock(side_effect=reply)
                with patch(
                    "arknights_mower.utils.software_update_progress.cancel_update"
                ) as cancel:
                    handler.do_POST()
                cancel.assert_not_called()
                handler.reply.assert_called_once()
                handler.connection.settimeout.assert_called_once_with(5)

    def test_progress_post_read_limits_preserve_rejection_status(self):
        handler_type = ProgressServers(self.state, []).handler(
            hashlib.sha256(b"fixture").hexdigest()
        )
        for token, status in (("fixture", 400), ("wrong", 403)):
            for length in ("0", "-1", "1025", "invalid", "8"):
                with self.subTest(token=token, length=length):
                    handler = object.__new__(handler_type)
                    handler.headers = {
                        "token": token,
                        "X-Mower-Update": "1",
                        "Content-Length": length,
                    }
                    handler.path = "/software-update/cancel"
                    handler.connection = Mock()
                    handler.rfile = Mock()
                    handler.rfile.read.side_effect = TimeoutError("fixture timeout")
                    handler.reply = Mock()
                    with patch(
                        "arknights_mower.utils.software_update_progress.cancel_update"
                    ) as cancel:
                        handler.do_POST()
                    cancel.assert_not_called()
                    handler.reply.assert_called_once()
                    self.assertEqual(handler.reply.call_args.args[0], status)
                    if length == "8":
                        handler.rfile.read.assert_called_once_with(8)
                        handler.connection.settimeout.assert_called_once_with(5)
                    else:
                        handler.rfile.read.assert_not_called()
                        handler.connection.settimeout.assert_not_called()

    def test_older_records_do_not_create_unauthenticated_listeners(self):
        servers = ProgressServers(self.state, [{"kind": "instance", "port": 58000}])
        servers.start()
        self.assertFalse(servers.servers)

    def test_flask_progress_shell_is_public_but_cancel_requires_auth_and_origin(self):
        app = Flask(__name__)
        app.token = "fixture"
        app.register_blueprint(software_update_bp)
        client = app.test_client()
        self.assertEqual(client.get("/software-update/progress").status_code, 200)
        self.assertEqual(client.get("/software-update/status").status_code, 403)
        with patch(
            "arknights_mower.utils.software_update.runtime.state_dir",
            return_value=self.state,
        ):
            for headers in (
                {},
                {"token": "fixture"},
                {
                    "token": "fixture",
                    "X-Mower-Update": "1",
                    "Origin": "http://elsewhere.invalid",
                },
            ):
                self.assertEqual(
                    client.post(
                        "/software-update/cancel",
                        json={"id": self.job["id"]},
                        headers=headers,
                    ).status_code,
                    403,
                )
            result = client.post(
                "/software-update/cancel",
                json={"id": self.job["id"]},
                headers={"token": "fixture", "X-Mower-Update": "1"},
            )
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json["ok"])

    def test_update_commands_inherit_proxy_environment(self):
        with patch.dict(
            os.environ,
            {
                "http_proxy": "http://127.0.0.1:7897",
                "https_proxy": "http://127.0.0.1:7897",
                "HTTP_PROXY": "http://127.0.0.1:7897",
                "HTTPS_PROXY": "http://127.0.0.1:7897",
            },
        ):
            worker = Worker(self.work / "job.json")
        with (
            patch.object(subprocess, "Popen") as process,
            patch("arknights_mower.utils.software_update_worker.WindowsCommandJob"),
        ):
            process.return_value.wait.return_value = 0
            worker.run_command([sys.executable, "-c", "pass"])
        env = process.call_args.kwargs["env"]
        self.assertEqual(env["http_proxy"], "http://127.0.0.1:7897")
        self.assertEqual(env["https_proxy"], env["http_proxy"])
