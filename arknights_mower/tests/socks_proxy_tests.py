"""SOCKS integration against a loopback fixture that never connects upstream."""

import asyncio
import hashlib
import io
import os
import shutil
import socket
import subprocess
import sys
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import StreamRequestHandler, ThreadingTCPServer
from unittest.mock import Mock, patch

import httpx
import requests
import socks
from flask import Flask

from arknights_mower.tests.network_settings_tests import ProxySettingsBase
from arknights_mower.utils import network_settings as network
from arknights_mower.utils import resource_pkg, software_update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.maa_update import (
    HTTPRangeReader,
    ReleaseAsset,
    download_asset,
)
from arknights_mower.utils.software_update_worker import Worker
from arknights_mower.views.network import FILE_TEST_URL, network_bp


class SocksProxyTests(ProxySettingsBase):
    def start_socks(self, body=lambda path: b"fixture"):
        targets, requests_seen = [], []

        class HttpHandler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                requests_seen.append((self.command, self.path))
                payload = body(self.path)
                requested_range = self.headers.get("Range")
                if requested_range:
                    start, end = map(
                        int, requested_range.removeprefix("bytes=").split("-")
                    )
                    total = len(payload)
                    payload = payload[start : end + 1]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

            def log_message(self, *args):
                pass

        class SocksHandler(StreamRequestHandler):
            def handle(self):
                self.request.settimeout(5)
                version, count = self.rfile.read(2)
                if version != 5 or 0 not in self.rfile.read(count):
                    return
                self.wfile.write(b"\x05\x00")
                version, command, _, kind = self.rfile.read(4)
                if version != 5 or command != 1:
                    return
                if kind == 3:
                    host = self.rfile.read(self.rfile.read(1)[0]).decode("ascii")
                elif kind in (1, 4):
                    family = socket.AF_INET if kind == 1 else socket.AF_INET6
                    host = socket.inet_ntop(
                        family, self.rfile.read(4 if kind == 1 else 16)
                    )
                else:
                    return
                port = int.from_bytes(self.rfile.read(2), "big")
                targets.append((kind, host, port))
                self.wfile.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
                # Serve only fixture content on this connection; never relay.
                HttpHandler(self.request, self.client_address, self.server)

        server = ThreadingTCPServer(("127.0.0.1", 0), SocksHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"socks5h://127.0.0.1:{server.server_address[1]}", targets, requests_seen

    def test_socks_settings_round_trip_environment_and_child_inheritance(self):
        for scheme in ("socks5", "socks5h"):
            proxy = f"{scheme}://[::1]:1080"
            self.save(f" {proxy}/ ")
            self.assertEqual(network.get_settings()["http_proxy"], proxy)
            for key in network._PROXY_ENV_KEYS:
                self.assertEqual(os.environ[key], proxy)
            self.assertIsNone(network.proxy_for_url("http://127.0.0.1/status"))
            self.assertEqual(
                subprocess.check_output(
                    [sys.executable, "-c", "import os; print(os.environ['ALL_PROXY'])"],
                    text=True,
                ).strip(),
                proxy,
            )
        self.save()
        self.assertNotIn("ALL_PROXY", os.environ)

    def test_requests_uses_socks5_for_ip_target(self):
        proxy, targets, _ = self.start_socks()
        self.save(proxy.replace("socks5h:", "socks5:"))
        with requests.get("http://192.0.2.1/fixture", timeout=3) as response:
            self.assertEqual(response.content, b"fixture")
        self.assertEqual(targets, [(1, "192.0.2.1", 80)])

    def test_socks5h_download_test_and_maa_downloads_resolve_at_proxy(self):
        proxy, targets, seen = self.start_socks()
        self.save(proxy, "http://downloads.example.invalid/")
        app = Flask(__name__)
        app.token = "local-fixture"
        app.register_blueprint(network_bp)
        result = (
            app.test_client()
            .post(
                "/network/test",
                headers={"token": app.token, "X-Mower-Settings": "1"},
            )
            .get_json()
        )
        self.assertTrue(result["results"][0]["ok"], result)
        self.assertEqual(seen, [("HEAD", "/" + FILE_TEST_URL)])
        self.assertEqual(resource_pkg.download_resource_pkg(), b"fixture")
        url = "https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v1/maa.zip"
        download_asset(
            ReleaseAsset(name="maa.zip", url=url, size=7), self.folder / "maa.zip"
        )
        self.assertEqual((self.folder / "maa.zip").read_bytes(), b"fixture")
        with HTTPRangeReader(url) as reader:
            self.assertEqual(reader.read(3), b"fix")
        self.assertTrue(targets)
        self.assertTrue(
            all(item == (3, "downloads.example.invalid", 80) for item in targets)
        )

    def test_httpx_sync_and_async_use_environment_without_client_wrapping(self):
        proxy, targets, _ = self.start_socks()
        self.save(proxy)
        with httpx.Client() as client:
            self.assertEqual(
                client.get("http://api.example.invalid/sync").content, b"fixture"
            )

        async def request():
            async with httpx.AsyncClient() as client:
                return (await client.get("http://api.example.invalid/async")).content

        self.assertEqual(asyncio.run(request()), b"fixture")
        self.assertEqual(targets, [(3, "api.example.invalid", 80)] * 2)

    def test_release_worker_downloads_through_socks_and_verifies_digest(self):
        archive = io.BytesIO()
        executable = "mower.exe" if sys.platform == "win32" else "mower"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(f"mower/{executable}", "fixture")
            package.writestr(
                "mower/_internal/arknights_mower/utils/update_runtime.py", "# fixture"
            )
        content = archive.getvalue()
        proxy, targets, _ = self.start_socks(lambda path: content)
        self.save(proxy)
        job_path = self.folder / "job/job.json"
        runtime.write_json(
            job_path,
            {
                "id": "socks-release",
                "root": str(self.folder / "install"),
                "state_dir": str(self.folder / "state"),
                "version": "v4.2.0",
                "proxy": proxy,
                "github_proxy": "http://downloads.example.invalid/",
                "asset": {
                    "name": "release.zip",
                    "url": "https://github.com/example/release.zip",
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
            },
        )
        worker = Worker(job_path)
        worker.prepare_package()
        self.assertEqual((worker.prepared / executable).read_text(), "fixture")
        self.assertEqual(targets, [(3, "downloads.example.invalid", 80)])
        worker.job["asset"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            worker.prepare_package()

    def test_source_job_stages_socks_before_old_venv_is_moved(self):
        self.save("socks5h://127.0.0.1:1080")
        root, state = self.folder / "source", self.folder / "state"
        root.mkdir()
        with (
            patch.object(runtime, "installation_root", return_value=root),
            patch.object(runtime, "state_dir", return_value=state),
            patch.object(software_update, "info", return_value={"blockers": []}),
            patch.object(
                software_update,
                "source_tools",
                return_value={"git": "git", "base_python": sys.executable},
            ),
            patch.object(subprocess, "check_output", return_value=""),
            patch.object(subprocess, "Popen", return_value=Mock(pid=os.getpid())),
        ):
            result = software_update.start_job(
                {"deployment": "source", "channel": "dev", "version": "alpha@fixture"}
            )
        staged = state / "jobs" / result["id"] / "socks.py"
        self.assertEqual(staged.read_bytes(), Path(socks.__file__).read_bytes())

    def test_fresh_venv_pip_can_download_using_staged_socks(self):
        wheel = io.BytesIO()
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "mower_socks_fixture-1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: mower-socks-fixture\nVersion: 1.0\n",
            )
            archive.writestr(
                "mower_socks_fixture-1.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            archive.writestr("mower_socks_fixture-1.0.dist-info/RECORD", "")
        filename = "mower_socks_fixture-1.0-py3-none-any.whl"
        proxy, targets, _ = self.start_socks(lambda path: wheel.getvalue())
        self.save(proxy)
        venv = self.folder / "new-venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True
        )
        python = venv / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        job_path = self.folder / "job/job.json"
        runtime.write_json(
            job_path,
            {
                "id": "bootstrap",
                "root": str(self.folder),
                "state_dir": str(self.folder / "state"),
                "version": "fixture",
                "proxy": proxy,
            },
        )
        shutil.copy2(socks.__file__, job_path.parent / "socks.py")
        worker = Worker(job_path)
        original_env = worker.env.copy()
        env = worker.pip_environment()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        result = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "download",
                "--no-deps",
                "--no-cache-dir",
                "--trusted-host",
                "packages.example.invalid",
                "--dest",
                str(self.folder / "downloads"),
                f"http://packages.example.invalid/{filename}",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.folder / "downloads" / filename).read_bytes(), wheel.getvalue()
        )
        self.assertEqual(targets, [(3, "packages.example.invalid", 80)])
        self.assertEqual(worker.env, original_env)


if __name__ == "__main__":
    unittest.main()
