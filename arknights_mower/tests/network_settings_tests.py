"""Proxy integration uses only temporary settings and loopback HTTP servers."""

import hashlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from flask import Flask

from arknights_mower.utils import github_download as github
from arknights_mower.utils import (
    hot_update,
    resource_pkg,
    resource_version,
    software_update,
)
from arknights_mower.utils import network_settings as network
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.maa_resource_update import (
    GITHUB_RESOURCE_ARCHIVE_URL,
    GITHUB_RESOURCE_VERSION_URL,
    download_resource_archive,
    get_github_resource_release,
)
from arknights_mower.utils.maa_update import (
    HTTPRangeReader,
    ReleaseAsset,
    download_asset,
)
from arknights_mower.utils.software_update_worker import Worker
from arknights_mower.views.network import network_bp


class ProxySettingsBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        for target, name, value in (
            (network, "settings_path", lambda: self.folder / "network.json"),
            (network, "_base_environment", None),
            (network, "_effective_settings", None),
            (urllib.request, "_opener", None),
        ):
            replacement = patch.object(target, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for key in (
            *network._ENV_KEYS,
            network._BASE_ENV_KEY,
            "ALL_PROXY",
            "all_proxy",
        ):
            os.environ.pop(key, None)

    def save(self, http="", github_proxy=""):
        settings = network.save_settings(
            {"http_proxy": http, "github_proxy": github_proxy}
        )
        return settings

    def restart(self):
        network._effective_settings = None
        network.apply_http_proxy()


class ProxySettingsTests(ProxySettingsBase):
    def test_settings_round_trip_and_clear(self):
        self.assertEqual(network.get_settings(), {"http_proxy": "", "github_proxy": ""})
        self.save(" http://127.0.0.1:7897/ ", " https://ghfast.top ")
        self.assertEqual(
            network.get_settings(),
            {
                "http_proxy": "http://127.0.0.1:7897",
                "github_proxy": "https://ghfast.top/",
            },
        )
        self.assertEqual(github.get_proxy(), "https://ghfast.top/")
        self.save()
        self.assertEqual(github.get_proxy(), "")

    def test_invalid_settings_do_not_replace_previous_values(self):
        self.save(github_proxy="https://ghfast.top")
        for value in (
            None,
            123,
            "file:///tmp/proxy",
            "https://user:pass@example.test/",
            "https://example.test/?url=",
            "https://example.test/#x",
            "https://example.test:bad",
            "https://example.test/https://github.com/a/b",
            "https://example.test/a b",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save(github_proxy=value)
            self.assertEqual(github.get_proxy(), "https://ghfast.top/")
        for value in (
            None,
            "socks4://localhost:1080",
            "socks5h://localhost",
            "http://localhost/path",
            "http://localhost:0",
            "http://localhost:65536",
            "socks5://localhost:0",
            "socks5h://user:password@localhost:1080",
        ):
            with self.subTest(http=value), self.assertRaises(ValueError):
                self.save(http=value)

    def test_settings_shared_between_named_instances(self):
        from arknights_mower.utils import path

        with (
            patch.object(path, "_data_dir", self.folder),
            patch.object(path, "global_space", "one"),
        ):
            first = network.get_path("@app/config/network.json", space="")
            with patch.object(path, "global_space", "two"):
                second = network.get_path("@app/config/network.json", space="")
        self.assertEqual(first, second)
        self.assertEqual(first, self.folder / "config/network.json")

    def test_file_urls_rewritten_once_and_other_urls_unchanged(self):
        self.save(github_proxy="https://proxy.example.test/download/")
        for url in (
            resource_pkg.RESOURCE_ZIP_URL,
            resource_version.RESOURCE_VERSION_URL,
            "https://github.com/ArkMowers/arknights-mower/archive/refs/heads/alpha.zip",
            "https://codeload.github.com/ArkMowers/MowerResource/zip/main",
            GITHUB_RESOURCE_ARCHIVE_URL,
            GITHUB_RESOURCE_VERSION_URL,
            "https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v1/maa.zip",
        ):
            with self.subTest(url=url):
                rewritten = github.download_url(url)
                self.assertEqual(
                    rewritten, "https://proxy.example.test/download/" + url
                )
                self.assertEqual(github.download_url(rewritten), rewritten)
        for url in (
            "https://api.github.com/repos/ArkMowers/arknights-mower/releases",
            "https://example.test/github.com/file.zip",
            "http://127.0.0.1:8000/screenshot",
            "https://github.com.example.test/a/b",
            "https://user:secret@github.com/a/b",
        ):
            with self.subTest(url=url):
                self.assertEqual(github.download_url(url), url)

    def test_http_proxy_is_inherited_by_sessions_and_children_and_bypasses_local(self):
        os.environ["no_proxy"] = "existing.example.test"
        session = requests.Session()  # MAA creates long-lived sessions too.
        self.addCleanup(session.close)
        self.save("http://127.0.0.1:7897", "https://ghfast.top")
        proxies = session.merge_environment_settings(
            "https://api.maa.plus/version", {}, False, True, None
        )["proxies"]
        self.assertEqual(proxies["https"], "http://127.0.0.1:7897")
        for url in (
            "http://127.0.0.1:54768/status",
            "http://localhost/test",
            "http://[::1]/test",
        ):
            self.assertEqual(requests.utils.get_environ_proxies(url), {})
        self.assertEqual(
            requests.utils.get_environ_proxies("https://existing.example.test/test")[
                "https"
            ],
            "http://127.0.0.1:7897",
        )
        inherited = subprocess.check_output(
            [sys.executable, "-c", "import os; print(os.environ['https_proxy'])"],
            text=True,
        ).strip()
        self.assertEqual(inherited, "http://127.0.0.1:7897")

    def test_global_setting_replaces_all_startup_proxy_variables(self):
        for key in network._PROXY_ENV_KEYS:
            os.environ[key] = "http://old.example.invalid:9999"
        os.environ["NO_PROXY"] = "*"
        self.save("http://127.0.0.1:7897")
        for key in network._PROXY_ENV_KEYS:
            self.assertEqual(os.environ[key], "http://127.0.0.1:7897")
        self.assertNotIn("*", os.environ["NO_PROXY"])
        self.assertEqual(
            requests.utils.get_environ_proxies("https://api.deepseek.com")["https"],
            "http://127.0.0.1:7897",
        )

    def test_clear_restores_launch_environment_even_after_restart(self):
        os.environ["https_proxy"] = "http://original.example.test:8080"
        self.save("http://127.0.0.1:7897")
        # Simulate a restarted child that inherited the active proxy and baseline.
        network._base_environment = network._effective_settings = None
        network.apply_http_proxy()
        self.save()
        self.assertEqual(os.environ["https_proxy"], "http://original.example.test:8080")
        self.assertNotIn("http_proxy", os.environ)

    def test_saving_new_proxies_updates_subsequent_connections(self):
        self.save("http://127.0.0.1:7897", "https://old.example.test/")
        network.save_settings(
            {
                "http_proxy": "http://localhost:8888",
                "github_proxy": "https://new.example.test/",
            }
        )
        network.apply_http_proxy()
        self.assertEqual(os.environ["https_proxy"], "http://localhost:8888")
        self.assertEqual(github.get_proxy(), "https://new.example.test/")

    def test_disabled_setting_preserves_system_proxy_discovery(self):
        self.save()
        self.assertNotIn("no_proxy", os.environ)
        self.assertNotIn("NO_PROXY", os.environ)

    def test_existing_process_syncs_settings_from_another_instance(self):
        self.save("http://127.0.0.1:7897")
        initialization = (
            "import os\nfrom pathlib import Path\n"
            "from arknights_mower.utils import network_settings as n\n"
            f"n.settings_path=lambda:Path({str(network.settings_path())!r})\n"
            "n.start_proxy_sync()\n"
        )
        script = (
            initialization
            + "print(os.environ['https_proxy'],flush=True)\ninput()\n"
            + "import time\ndeadline=time.monotonic()+5\n"
            + "while os.environ['https_proxy'] != 'http://localhost:8888' and time.monotonic()<deadline: time.sleep(0.05)\n"
            + "print(os.environ['https_proxy'])\nn._sync_stop.set()\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "http://127.0.0.1:7897")
            network.save_settings(
                {"http_proxy": "http://localhost:8888", "github_proxy": ""}
            )
            output, error = process.communicate("continue\n", timeout=5)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(output.strip(), "http://localhost:8888")
            fresh = subprocess.check_output(
                [
                    sys.executable,
                    "-c",
                    initialization + "print(os.environ['https_proxy'])",
                ],
                text=True,
            )
            self.assertEqual(fresh.strip(), "http://localhost:8888")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_routes_save_validate_and_authenticate(self):
        app = Flask(__name__)
        app.token = "local-test-token"
        app.register_blueprint(network_bp)
        client = app.test_client()
        headers = {"token": app.token, "X-Mower-Settings": "1"}
        self.assertEqual(client.get("/network/settings").status_code, 403)
        data = {"http_proxy": "", "github_proxy": "https://ghfast.top"}
        self.assertEqual(
            client.post(
                "/network/settings", json=data, headers={"token": app.token}
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/network/settings",
                json=data,
                headers={**headers, "Origin": "https://example.test"},
            ).status_code,
            403,
        )
        response = client.post("/network/settings", json=data, headers=headers)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(
            client.get("/network/settings", headers=headers).get_json()["github_proxy"],
            "https://ghfast.top/",
        )
        for bad in (
            [],
            {"http_proxy": ""},
            {"http_proxy": "http://localhost/path", "github_proxy": ""},
        ):
            self.assertEqual(
                client.post("/network/settings", json=bad, headers=headers).status_code,
                400,
            )
        self.assertEqual(network.get_settings()["github_proxy"], "https://ghfast.top/")

    def test_copilot_download_uses_fixed_backend_endpoint_without_forwarding_token(
        self,
    ):
        app = Flask(__name__)
        app.token = "local-test-token"
        app.register_blueprint(network_bp)
        client = app.test_client()
        self.assertEqual(client.get("/network/maa-copilot/123").status_code, 403)
        self.save("http://127.0.0.1:7897", "https://unused.example.test/")
        payload = {"data": {"content": '{"title":"fixture"}'}}
        with patch("arknights_mower.views.network.requests.get") as get:
            get.return_value.json.return_value = payload
            response = client.get(
                "/network/maa-copilot/123", headers={"token": app.token}
            )
            self.assertEqual(response.get_json(), payload)
            get.assert_called_once_with(
                "https://prts.maa.plus/copilot/get/123", timeout=30
            )
        with patch(
            "arknights_mower.views.network.requests.get", side_effect=requests.Timeout
        ):
            self.assertEqual(
                client.get(
                    "/network/maa-copilot/123", headers={"token": app.token}
                ).status_code,
                502,
            )


class LocalProxyIntegrationTests(ProxySettingsBase):
    def start_server(self, body, headers_seen=None, methods_seen=None, redirects=None):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.do_GET()

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.do_GET()

            def do_GET(self):
                seen.append(self.path)
                if methods_seen is not None:
                    methods_seen.append(self.command)
                if redirects and self.path in redirects:
                    self.send_response(302)
                    self.send_header("Location", redirects[self.path])
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if headers_seen is not None:
                    headers_seen.append(dict(self.headers))
                payload = body(self.path)
                range_header = self.headers.get("Range")
                if range_header:
                    start, end = map(
                        int, range_header.removeprefix("bytes=").split("-")
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

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}", seen

    def test_maa_program_resource_and_range_downloads_use_github_station(self):
        def body(path):
            if path.endswith("version.json"):
                return b'{"last_updated":"2026-09-05 10:00:00.000","activity":{"name":"fixture"}}'
            return b"fixture"

        proxy, seen = self.start_server(body)
        self.save(github_proxy=proxy)
        release = get_github_resource_release()
        download_resource_archive(release, self.folder / "resource.zip")
        url = "https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v1/maa.zip"
        asset = ReleaseAsset(name="maa.zip", url=url, size=7)
        download_asset(asset, self.folder / "maa.zip")
        with HTTPRangeReader(url) as reader:
            self.assertEqual(reader.read(3), b"fix")
        self.assertEqual(
            seen,
            [
                "/" + GITHUB_RESOURCE_VERSION_URL,
                "/" + GITHUB_RESOURCE_ARCHIVE_URL,
                "/" + url,
                "/" + url,
                "/" + url,
            ],
        )

    def test_connection_test_checks_download_route_without_forwarding_credentials(self):
        from arknights_mower.views import network as view

        headers_seen, methods_seen = [], []
        proxy, seen = self.start_server(
            lambda path: b"download fixture", headers_seen, methods_seen
        )
        self.save(http=proxy, github_proxy="http://download.example.invalid/")
        app = Flask(__name__)
        app.token = "private-local-token"
        app.register_blueprint(network_bp)
        client = app.test_client()
        self.assertEqual(client.post("/network/test").status_code, 403)
        headers = {"token": app.token, "X-Mower-Settings": "1"}
        self.assertEqual(
            client.post(
                "/network/test", headers={**headers, "Origin": "https://other.test"}
            ).status_code,
            403,
        )
        result = client.post("/network/test", headers=headers).get_json()
        self.assertTrue(result["ok"])
        self.assertEqual([item["ok"] for item in result["results"]], [True])
        self.assertCountEqual(
            seen,
            [
                "http://download.example.invalid/" + view.FILE_TEST_URL,
            ],
        )
        self.assertEqual(methods_seen, ["HEAD"])
        self.assertEqual(view.FILE_TEST_URL, resource_pkg.RESOURCE_ZIP_URL)
        for item in result["results"]:
            self.assertGreaterEqual(item["elapsed_ms"], 0)
        self.assertEqual(result["settings"], network.get_settings())
        for sent in headers_seen:
            self.assertNotIn("token", {key.lower() for key in sent})
            self.assertNotIn("authorization", {key.lower() for key in sent})
        with patch("requests.Session.head", side_effect=requests.Timeout):
            result = client.post("/network/test", headers=headers).get_json()
        self.assertTrue(all(not item["ok"] for item in result["results"]))
        self.assertTrue(all("超时" in item["message"] for item in result["results"]))

    def test_connection_test_follows_redirects_without_requesting_body(self):
        from arknights_mower.views.network import _probe_connection

        methods = []
        url, paths = self.start_server(
            lambda path: b"<html>No JSON validation for connectivity</html>",
            methods_seen=methods,
            redirects={"/download": "/asset"},
        )
        result = _probe_connection("fixture", url + "/download", None)
        self.assertTrue(result["ok"])
        self.assertEqual(paths, ["/download", "/asset"])
        self.assertEqual(methods, ["HEAD", "HEAD"])

    def test_connection_test_reports_http_errors(self):
        from arknights_mower.views.network import _probe_connection

        with patch("requests.Session.head", side_effect=requests.HTTPError("404")):
            result = _probe_connection("fixture", "https://github.com/", None)
        self.assertFalse(result["ok"])
        self.assertIn("连接失败", result["message"])

    def test_resource_hot_update_and_raw_version_downloads_use_site(self):
        proxy, seen = self.start_server(
            lambda path: b'{"res_version":"v2026.09.05-test"}'
        )
        self.save(github_proxy=proxy)
        self.assertIsNotNone(resource_pkg.download_resource_pkg())
        self.assertIsNotNone(resource_version._fetch_remote_version_json())
        with patch.object(hot_update, "_extract_zip", return_value=True):
            self.assertTrue(hot_update._download_and_extract())
        self.assertEqual(
            seen,
            [
                "/" + resource_pkg.RESOURCE_ZIP_URL,
                "/" + resource_version.RESOURCE_VERSION_URL,
                f"/https://github.com/{hot_update.HOT_UPDATE_REPO}/releases/latest/download/hot_update.zip",
            ],
        )

    def test_github_site_can_be_reached_through_global_http_proxy(self):
        proxy, seen = self.start_server(lambda path: b"fixture resource")
        self.save(http=proxy, github_proxy="http://download.example.invalid/")
        self.assertEqual(resource_pkg.download_resource_pkg(), b"fixture resource")
        self.assertEqual(
            seen, ["http://download.example.invalid/" + resource_pkg.RESOURCE_ZIP_URL]
        )

    def test_global_proxy_reaches_maa_and_urllib_on_non_github_hosts(self):
        proxy, seen = self.start_server(
            lambda path: (
                b'{"last_updated":"2026-09-05 10:00:00.000000","activity":{"name":"test"}}'
            )
        )
        session = requests.Session()
        self.addCleanup(session.close)
        self.save(http=proxy, github_proxy="https://unused.example.test/")
        # HTTP fixture avoids external TLS while exercising the real MAA session.
        with patch(
            "arknights_mower.utils.maa_resource_update.GITHUB_RESOURCE_VERSION_URL",
            "http://maa.example.invalid/version.json",
        ):
            result = get_github_resource_release(session)
        self.assertEqual(result.url, GITHUB_RESOURCE_ARCHIVE_URL)
        with urllib.request.urlopen(
            "http://mower.example.invalid/check", timeout=3
        ) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(
            seen,
            [
                "http://maa.example.invalid/version.json",
                "http://mower.example.invalid/check",
            ],
        )

    def test_detached_release_worker_downloads_through_site_and_checks_digest(self):
        buf = io.BytesIO()
        executable = "mower.exe" if sys.platform == "win32" else "mower"
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr(f"mower/{executable}", "fixture")
            archive.writestr(
                "mower/_internal/arknights_mower/utils/update_runtime.py", "# fixture"
            )
        data = buf.getvalue()
        proxy, seen = self.start_server(lambda path: data)
        package_url = "https://github.com/ArkMowers/arknights-mower/releases/download/v4.2.0/package.zip"
        job = {
            "id": "proxy-test",
            "root": str(self.folder / "install"),
            "state_dir": str(self.folder / "state"),
            "version": "v4.2.0",
            "deployment": "release",
            "background": False,
            "proxy": "",
            "github_proxy": proxy,
            "asset": {
                "name": "package.zip",
                "url": package_url,
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        }
        job_path = self.folder / "job/job.json"
        runtime.write_json(job_path, job)
        worker = Worker(job_path)
        worker.prepare_package()
        self.assertEqual((worker.prepared / executable).read_text(), "fixture")
        self.assertEqual(seen, ["/" + package_url])
        worker.job["asset"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            worker.prepare_package()

    def test_source_updater_copies_proxy_helper_and_global_settings(self):
        root = self.folder / "source"
        root.mkdir()
        state = self.folder / "state"
        self.save("http://127.0.0.1:7897", "https://ghfast.top/")
        plan = {
            "deployment": "source",
            "channel": "dev",
            "version": "alpha@test",
            "proxy": "http://old.example.test:80",
        }
        with (
            patch.object(runtime, "installation_root", return_value=root),
            patch.object(runtime, "state_dir", return_value=state),
            patch.object(software_update, "info", return_value={"blockers": []}),
            patch.object(
                software_update,
                "source_tools",
                return_value={"git": "git", "base_python": sys.executable},
            ),
            patch.object(subprocess, "check_output", return_value=b""),
            patch.object(subprocess, "Popen", return_value=Mock(pid=os.getpid())),
        ):
            result = software_update.start_job(plan)
        work = state / "jobs" / result["id"]
        job = runtime.read_json(work / "job.json")
        self.assertEqual(job["proxy"], "http://127.0.0.1:7897")
        self.assertEqual(job["github_proxy"], "https://ghfast.top/")
        self.assertTrue((work / "github_download.py").is_file())
        # Copied worker must import without access to the application package.
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                f"import sys; sys.path.insert(0, {str(work)!r}); import software_update_worker",
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
