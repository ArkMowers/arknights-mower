"""Exercise authenticated progress handoff and cancellation on local sockets."""

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
from arknights_mower.utils.software_update_worker import UpdateCancelled, Worker
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

    def test_installation_transition_refuses_late_cancel(self):
        worker = Worker(self.work / "job.json")
        worker.begin_install()
        with self.assertRaisesRegex(ValueError, "已开始替换"):
            cancel_update(self.state, self.job["id"])
        self.assertFalse(read_status(self.state)["cancellable"])
        worker.check_cancelled()

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

        self.assertIn(
            "Mower 更新进度", get("/software-update/progress").read().decode()
        )
        with self.assertRaises(HTTPError) as error:
            get("/software-update/status")
        self.assertEqual(error.exception.code, 403)
        headers = {
            "token": token,
            "X-Mower-Update": "1",
            "Content-Type": "application/json",
        }
        self.assertEqual(
            json.load(get("/software-update/status", headers=headers))["log"],
            "安装日志",
        )
        for path, origin in (
            ("/software-update/cancel", "http://elsewhere.invalid"),
            ("/unexpected", url),
        ):
            with self.assertRaises(HTTPError):
                get(path, headers={**headers, "Origin": origin}, data=b"{}")
        data = json.dumps({"id": self.job["id"]}).encode()
        self.assertTrue(
            json.load(get("/software-update/cancel", headers=headers, data=data))["ok"]
        )
        servers.close()
        # A replacement HTTP server can bind the exact original port immediately.
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        with ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler):
            pass

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
            },
        ):
            worker = Worker(self.work / "job.json")
        with patch.object(subprocess, "Popen") as process:
            process.return_value.wait.return_value = 0
            worker.run_command([sys.executable, "-c", "pass"])
        env = process.call_args.kwargs["env"]
        self.assertEqual(env["http_proxy"], "http://127.0.0.1:7897")
        self.assertEqual(env["https_proxy"], env["http_proxy"])
