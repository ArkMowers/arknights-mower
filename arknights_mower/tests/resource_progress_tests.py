import unittest
from threading import Event
from unittest.mock import Mock, patch

import requests

import server
from arknights_mower.tests.resource_pkg_tests import ResourcePkgTestBase, resource_zip
from arknights_mower.utils import resource_pkg as rp
from arknights_mower.utils.resource_update_job import ResourceUpdateJob


class TestResourceProgress(ResourcePkgTestBase):
    def test_streamed_download_reports_bytes_with_or_without_content_length(self):
        for headers in ({"Content-Length": "6"}, {}):
            with self.subTest(headers=headers):
                response = Mock()
                response.headers = headers
                response.iter_content.return_value = iter([b"ab", b"", b"cdef"])
                events = []
                with patch.object(rp.requests, "get") as get:
                    get.return_value.__enter__.return_value = response
                    self.assertEqual(
                        rp.download_resource_pkg(
                            callback=lambda **data: events.append(data)
                        ),
                        b"abcdef",
                    )
                self.assertTrue(get.call_args.kwargs["stream"])
                self.assertEqual(events[-1]["current"], 6)
                self.assertEqual(events[-1]["progress"], 80 if headers else None)
                self.assertTrue(
                    all(event["phase"] == "downloading" for event in events)
                )

    def test_interrupted_download_does_not_return_partial_package(self):
        def chunks(_size):
            yield b"partial"
            raise requests.ConnectionError("disconnected")

        response = Mock(headers={"Content-Length": "100"})
        response.iter_content.side_effect = chunks
        with patch.object(rp.requests, "get") as get:
            get.return_value.__enter__.return_value = response
            self.assertIsNone(rp.download_resource_pkg())

    def test_progress_reaches_success_only_after_atomic_install(self):
        job = ResourceUpdateJob()
        events = []
        report = job.report

        def record(**data):
            if data.get("progress") == 100:
                self.assertEqual(self.installed_version(), "v2026.08.23-aaaaaaa")
            events.append(data)
            report(**data)

        with (
            patch.object(rp, "download_resource_pkg", return_value=resource_zip()),
            patch.object(job, "report", side_effect=record),
        ):
            job.start()
            job.thread.join(5)
        self.assertFalse(job.running())
        self.assertEqual(job.snapshot()["status"], "success")
        phases = [event.get("phase") for event in events]
        self.assertLess(phases.index("validating"), phases.index("extracting"))
        self.assertLess(phases.index("extracting"), phases.index("installing"))
        self.assertLess(phases.index("installing"), phases.index("done"))
        progress = [event["progress"] for event in events]
        self.assertEqual(progress, sorted(progress))

    def test_install_failure_keeps_old_resource_and_never_reports_success(self):
        job = ResourceUpdateJob()
        with patch.object(rp, "download_resource_pkg", return_value=b"broken zip"):
            job.start()
            job.thread.join(5)
        self.assertEqual(job.snapshot()["status"], "error")
        self.assertLess(job.snapshot()["progress"], 100)
        self.assertEqual(self.installed_version(), "v2026.08.22-0000000")

    def test_title_refresh_failure_does_not_change_installed_result(self):
        job = ResourceUpdateJob()
        with (
            patch.object(rp, "download_resource_pkg", return_value=resource_zip()),
            patch.object(rp, "install_resource_pkg", return_value=True),
        ):
            job.start(Mock(side_effect=RuntimeError("window closed")))
            job.thread.join(5)
        self.assertEqual(job.snapshot()["status"], "success")


class TestResourceProgressRoutes(unittest.TestCase):
    def setUp(self):
        self.job = ResourceUpdateJob()
        self.release = Event()
        self.entered = Event()
        self.client = server.app.test_client()
        for target, name, value in (
            (server, "resource_update", self.job),
            (server, "mower_thread", None),
            (server.app, "token", "resource-test-token"),
        ):
            mocked = patch.object(target, name, value, create=True)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.headers = {"token": "resource-test-token"}
        # Join before fixture paths and patches are removed, even on failure.
        self.addCleanup(self.finish_job)

    def finish_job(self):
        self.release.set()
        if self.job.thread:
            self.job.thread.join(5)

    def download(self, callback):
        callback(progress=25, phase="downloading", current=25, total=100)
        self.entered.set()
        if not self.release.wait(5):
            raise TimeoutError("test did not release download")
        return b"fixture"

    def test_background_request_returns_before_install_and_protects_running_job(self):
        with (
            patch.object(server, "active_job", return_value=None),
            patch.object(server, "_request_title_refresh"),
            patch.object(rp, "download_resource_pkg", side_effect=self.download),
            patch.object(rp, "install_resource_pkg", return_value=True) as install,
        ):
            try:
                response = self.client.post(
                    "/resource/install", json={"background": True}, headers=self.headers
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(self.entered.wait(2))
                install.assert_not_called()
                job_id = response.json["job"]["id"]
                status = self.client.get("/resource/status", headers=self.headers).json[
                    "job"
                ]
                self.assertEqual(status["id"], job_id)
                self.assertEqual(status["progress"], 25)
                duplicate = self.client.post(
                    "/resource/install", json={"background": True}, headers=self.headers
                )
                self.assertEqual(duplicate.status_code, 409)
                self.assertEqual(
                    self.client.get("/start/0", headers=self.headers).text, "false"
                )
            finally:
                self.finish_job()
            status = self.client.get("/resource/status", headers=self.headers).json[
                "job"
            ]
            self.assertEqual(status["id"], job_id)
            self.assertEqual(status["progress"], 100)
            self.assertEqual(status["status"], "success")

    def test_status_requires_existing_instance_token(self):
        self.assertEqual(self.client.get("/resource/status").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/resource/install", json={"background": True}
            ).status_code,
            403,
        )

    def test_software_operation_blocks_resource_submission(self):
        with patch.object(server, "active_job", return_value={"status": "running"}):
            response = self.client.post(
                "/resource/install", json={"background": True}, headers=self.headers
            )
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(self.job.thread)

    def test_old_client_waits_for_final_result(self):
        with (
            patch.object(server, "active_job", return_value=None),
            patch.object(server, "_request_title_refresh"),
            patch.object(rp, "download_resource_pkg", return_value=b"fixture"),
            patch.object(rp, "install_resource_pkg", return_value=True),
        ):
            response = self.client.post("/resource/install", headers=self.headers)
        self.assertTrue(response.json["ok"])
        self.assertEqual(response.json["job"]["status"], "success")
        self.assertFalse(response.json["restart_required"])
