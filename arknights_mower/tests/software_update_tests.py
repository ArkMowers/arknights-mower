"""Software updates are exercised only in temporary installations."""

import hashlib
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import zipfile
from itertools import product
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from werkzeug.datastructures import FileStorage

from arknights_mower.tests.software_package_tests import make_release_package
from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker, extract_archive
from arknights_mower.views.software_update import software_update_bp


def release(
    version,
    prerelease=False,
    draft=False,
    system="macos",
    arch="arm64",
    published_at="2026-09-01T00:00:00Z",
):
    extension = {"windows": "zip", "linux": "tar.gz", "macos": "dmg"}[system]
    name = f"arknights-mower_{version.lstrip('v')}_{system}_{arch}.{extension}"
    return {
        "tag_name": version,
        "prerelease": prerelease,
        "draft": draft,
        "published_at": published_at,
        "html_url": update.RELEASES_URL,
        "body": "Release notes",
        "assets": [
            {
                "name": name,
                "size": 12,
                "digest": "sha256:" + "a" * 64,
                "browser_download_url": f"https://github.com/{update.REPO}/releases/download/{version}/{name}",
            }
        ],
    }


class ReleaseDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = patch.object(runtime, "state_dir", return_value=Path(temporary.name))
        state.start()
        self.addCleanup(state.stop)

    def test_channels_are_separate_and_drafts_are_excluded(self):
        data = [
            release("v4.1.6-alpha.3", True),
            release("v4.1.5"),
            release("v4.1.7", draft=True),
            release("v4.1.6-alpha.12", True),
        ]
        self.assertEqual(update.choose_release(data, "stable")["tag_name"], "v4.1.5")
        self.assertEqual(
            update.choose_release(data, "beta")["tag_name"], "v4.1.6-alpha.12"
        )

    def test_prerelease_order_and_local_commit_suffix(self):
        versions = [
            "4.1.6-alpha.3+abc",
            "v4.1.6-alpha.12",
            "4.1.6-beta.1",
            "4.1.6-rc.1",
            "4.1.6",
            "4.2.0-alpha.1",
        ]
        self.assertEqual(sorted(versions, key=update.version_key), versions)

    def test_published_time_beats_legacy_version_numbers_and_creation_time(self):
        legacy = release("2025.2.1", published_at="2025-02-13T08:03:09Z")
        stable = release("v4.1.5", published_at="2026-04-08T15:38:59Z")
        legacy["created_at"] = "2027-01-01T00:00:00Z"
        stable["created_at"] = "2024-01-01T00:00:00Z"
        for data in ([legacy, stable], [stable, legacy]):
            with self.subTest(first=data[0]["tag_name"]):
                self.assertIs(update.choose_release(data, "stable"), stable)

    def test_stable_channel_uses_github_latest_without_scanning_old_releases(self):
        latest = release("v4.1.5")
        latest["assets"] = []
        with (
            patch.object(update, "__version__", "4.1.5"),
            patch.object(runtime, "frozen", return_value=True),
            patch.object(update, "github", return_value=latest) as api,
        ):
            result = update.check("stable")
        self.assertEqual(result["version"], "v4.1.5")
        self.assertFalse(result["available"])
        api.assert_called_once()
        self.assertEqual(api.call_args.args[0], "/releases/latest")

    def test_missing_latest_is_reported_without_falling_back_to_an_old_release(self):
        response = update.requests.Response()
        response.status_code = 404
        error = update.requests.HTTPError(response=response)
        with (
            patch.object(runtime, "frozen", return_value=True),
            patch.object(update, "github", side_effect=error) as api,
        ):
            with self.assertRaisesRegex(ValueError, "暂无已发布的 Latest"):
                update.check("stable")
        api.assert_called_once()

    def test_publication_timestamps_use_timezone_and_ignore_invalid_dates(self):
        older = release("v4.2.0", published_at="2026-09-09T08:00:00+08:00")
        latest = release("v4.1.6", published_at="2026-09-09T01:00:00Z")
        invalid = [
            release("v5.0.0", published_at=value)
            for value in (None, "", "invalid", "2026-09-10T00:00:00", 123)
        ]
        for item in invalid:
            item["created_at"] = "2027-01-01T00:00:00Z"
        self.assertIs(
            update.choose_release([older, latest, *invalid], "stable"), latest
        )
        with self.assertRaisesRegex(ValueError, "有效发布时间"):
            update.choose_release(invalid, "stable")

    def test_checks_do_not_reinstall_the_same_version_or_require_its_assets(self):
        for (system, arch), (channel, version) in product(
            [("windows", "x64"), ("macos", "arm64"), ("linux", "x64")],
            [("stable", "v4.1.5"), ("beta", "v4.1.6-alpha.4")],
        ):
            data = release(version, prerelease=channel == "beta")
            data["assets"] = []
            with (
                self.subTest(system=system, channel=channel),
                patch.object(update, "__version__", version.lstrip("v") + "+abcdef"),
                patch.object(runtime, "frozen", return_value=True),
                patch.object(update, "platform_asset", return_value=(system, arch)),
                patch.object(
                    update,
                    "github",
                    return_value=data if channel == "stable" else [data],
                ),
                patch.object(update, "choose_asset") as asset,
            ):
                result = update.check(channel)
                self.assertTrue(result["ok"])
                self.assertFalse(result["available"])
                self.assertEqual(result["version"], version)
                self.assertEqual(result["check_id"], "")
                self.assertEqual(
                    runtime.read_json(runtime.state_dir() / "last-check.json")[
                        "version"
                    ],
                    version,
                )
                asset.assert_not_called()

    def test_channel_targets_can_upgrade_or_downgrade_on_each_platform(self):
        for (system, arch), (channel, current, version) in product(
            [("windows", "x64"), ("macos", "arm64"), ("linux", "x64")],
            [
                ("beta", "4.1.6-alpha.4", "v4.1.6-alpha.5"),
                ("stable", "4.1.6-alpha.4", "v4.1.6"),
                ("stable", "4.1.6-alpha.4", "v4.1.5"),
                ("stable", "4.1.6", "v4.1.5"),
                ("beta", "4.1.6-alpha.5", "v4.1.6-alpha.4"),
            ],
        ):
            target = release(
                version,
                prerelease=channel == "beta",
                system=system,
                arch=arch,
                published_at="2026-09-10T00:00:00Z",
            )
            legacy = release("2025.2.1", published_at="2025-02-13T08:03:09Z")
            with (
                self.subTest(system=system, channel=channel, target=version),
                patch.object(update, "__version__", current),
                patch.object(runtime, "frozen", return_value=True),
                patch.object(update, "platform_asset", return_value=(system, arch)),
                patch.object(
                    update,
                    "github",
                    return_value=target if channel == "stable" else [legacy, target],
                ),
            ):
                result = update.check(channel)
                self.assertTrue(result["available"])
                self.assertEqual(result["version"], version)
                self.assertEqual(
                    result["downgrade"],
                    update.version_key(version) < update.version_key(current),
                )
                self.assertEqual(
                    update._checks[result["check_id"]]["asset"]["name"],
                    target["assets"][0]["name"],
                )

    def test_source_release_can_follow_an_older_latest_commit(self):
        target = release("v4.1.5")
        with (
            patch.object(update, "__version__", "4.1.6-alpha.4"),
            patch.object(runtime, "frozen", return_value=False),
            patch.object(update, "github", side_effect=[target, {"sha": "a" * 40}]),
            patch.object(subprocess, "check_output", return_value="b" * 40),
        ):
            result = update.check("stable")
        self.assertTrue(result["available"])
        self.assertEqual(update._checks[result["check_id"]]["commit"], "a" * 40)

    def test_auto_update_waits_for_rollback_confirmation_without_reinstall_loop(self):
        for channel, current, version in [
            ("stable", "4.1.6-alpha.4", "v4.1.5"),
            ("beta", "4.1.6-alpha.5", "v4.1.6-alpha.4"),
        ]:
            target = release(version, prerelease=channel == "beta")
            update.save_settings(
                {"channel": channel, "auto_update": True, "background": True}
            )
            marker = runtime.state_dir() / "auto-check.json"
            marker.unlink(missing_ok=True)
            with (
                self.subTest(channel=channel),
                patch.dict(os.environ, {"MOWER_RESTART_JOB": ""}),
                patch.object(runtime, "frozen", return_value=True),
                patch.object(update, "platform_asset", return_value=("macos", "arm64")),
                patch.object(
                    update,
                    "github",
                    return_value=target if channel == "stable" else [target],
                ) as api,
                patch.object(update, "start_job", return_value={"ok": True}) as start,
            ):
                with patch.object(update, "__version__", current):
                    self.assertTrue(update.check_on_launch())
                    start.assert_not_called()
                    cached = runtime.read_json(runtime.state_dir() / "last-check.json")
                    self.assertTrue(cached["available"])
                    self.assertTrue(cached["downgrade"])
                    self.assertIn("确认后安装", cached["message"])
                    # The clicked install action refreshes the display-only cache.
                    result = update.check(channel)
                    with self.assertRaisesRegex(ValueError, "二次确认"):
                        update.submit(result["check_id"], True)
                    start.assert_not_called()
                    update.submit(result["check_id"], True, confirm_downgrade=True)
                    start.assert_called_once_with(
                        update._checks[result["check_id"]],
                        True,
                        force=False,
                        confirm_downgrade=True,
                    )

                # Simulate the installed target, and bypass the one-minute
                # throttle so the second check really exercises version equality.
                marker.unlink()
                with patch.object(update, "__version__", version.lstrip("v")):
                    self.assertTrue(update.check_on_launch())
                self.assertEqual(api.call_count, 3)
                start.assert_called_once()
                self.assertFalse(
                    runtime.read_json(runtime.state_dir() / "last-check.json")[
                        "available"
                    ]
                )

    def test_later_pages_are_checked_even_when_first_page_has_a_candidate(self):
        first_page = [release("v4.1.6-alpha.4", prerelease=True)] * 100
        target = release(
            "v4.1.6-alpha.5", prerelease=True, published_at="2026-09-10T00:00:00Z"
        )
        with (
            patch.object(update, "__version__", "4.1.6-alpha.4"),
            patch.object(runtime, "frozen", return_value=True),
            patch.object(update, "platform_asset", return_value=("macos", "arm64")),
            patch.object(update, "github", side_effect=[first_page, [target]]) as api,
        ):
            result = update.check("beta")
        self.assertTrue(result["available"])
        self.assertEqual(result["version"], "v4.1.6-alpha.5")
        self.assertEqual(
            [call.args[0] for call in api.call_args_list],
            ["/releases?per_page=100&page=1", "/releases?per_page=100&page=2"],
        )

    def test_each_platform_selects_its_exact_asset(self):
        for system, arch in [
            ("macos", "arm64"),
            ("macos", "x64"),
            ("linux", "arm64"),
            ("linux", "x64"),
            ("windows", "x64"),
        ]:
            with (
                self.subTest(system=system, arch=arch),
                patch.object(update, "platform_asset", return_value=(system, arch)),
            ):
                data = release("v4.2.0", system=system, arch=arch)
                self.assertEqual(
                    update.choose_asset(data)["name"], data["assets"][0]["name"]
                )

    def test_missing_platform_or_hash_is_not_installable(self):
        with patch.object(update, "platform_asset", return_value=("windows", "x64")):
            with self.assertRaises(ValueError) as missing:
                update.choose_asset(release("v4.2.0"))
            self.assertNotIn("macOS", str(missing.exception))
            data = release("v4.2.0", system="windows", arch="x64")
            data["assets"][0]["digest"] = None
            with self.assertRaises(ValueError):
                update.choose_asset(data)

    def test_dev_is_rejected_for_frozen_deployments_without_network(self):
        with (
            patch.object(runtime, "frozen", return_value=True),
            patch.object(update, "github") as network,
        ):
            with self.assertRaisesRegex(ValueError, "仅支持源码"):
                update.check("dev")
            network.assert_not_called()

    def test_prerelease_check_does_not_use_latest_endpoint(self):
        with (
            patch.object(runtime, "frozen", return_value=True),
            patch.object(update, "platform_asset", return_value=("macos", "arm64")),
            patch.object(
                update, "github", return_value=[release("v4.2.0-alpha.1", True)]
            ) as network,
        ):
            result = update.check("beta")
            self.assertTrue(result["available"])
            self.assertTrue(result["check_id"])
            self.assertIn("/releases?", network.call_args.args[0])

    def test_source_release_resolves_tag_not_default_branch(self):
        with (
            patch.object(runtime, "frozen", return_value=False),
            patch.object(
                update,
                "github",
                side_effect=[[release("v4.2.0-alpha.1", True)], {"sha": "a" * 40}],
            ) as network,
            patch.object(subprocess, "check_output", return_value="b" * 40),
        ):
            result = update.check("beta")
            plan = update._checks[result["check_id"]]
            self.assertEqual(plan["ref"], "refs/tags/v4.2.0-alpha.1")
            self.assertEqual(plan["commit"], "a" * 40)
            self.assertEqual(network.call_args.args[0], "/commits/v4.2.0-alpha.1")

    def test_proxy_is_optional_and_cannot_contain_credentials_or_commands(self):
        self.assertEqual(
            update.validate_proxy("http://127.0.0.1:7897"), "http://127.0.0.1:7897"
        )
        self.assertEqual(update.validate_proxy(""), "")
        for proxy in [
            "file:///tmp/a",
            "http://name:secret@proxy:80",
            "http://proxy:bad",
            "http://proxy/a",
        ]:
            with self.subTest(proxy=proxy), self.assertRaises(ValueError):
                update.validate_proxy(proxy)


class ManualPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name).resolve()
        for target, name, value in (
            (runtime, "frozen", True),
            (runtime, "state_dir", self.state),
            (update, "platform_asset", ("windows", "x64")),
        ):
            mocked = patch.object(target, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        version = patch.object(update, "__version__", "4.1.6-alpha.4")
        version.start()
        self.addCleanup(version.stop)
        checks = patch.dict(update._checks, {}, clear=True)
        checks.start()
        self.addCleanup(checks.stop)
        for target in (
            "requests.sessions.Session.request",
            "arknights_mower.utils.software_update.github",
        ):
            network = patch(
                target, side_effect=AssertionError("manual install must stay offline")
            )
            network.start()
            self.addCleanup(network.stop)

    def upload(self, version="4.2.0", name="任意改名 (1).bin"):
        return FileStorage(
            stream=io.BytesIO(make_release_package(version)), filename=name
        )

    def test_preview_uses_package_version_and_does_not_start_worker(self):
        with patch.object(subprocess, "Popen") as process:
            result = update.inspect_upload(
                self.upload("4.1.5", "arknights-mower_99.0.0.zip")
            )
        self.assertEqual(result["version"], "v4.1.5")
        self.assertTrue(result["downgrade"])
        plan = update._checks[result["check_id"]]
        self.assertEqual(plan["asset"]["name"], "package.zip")
        staged = Path(plan["_upload"])
        self.assertTrue(staged.is_file())
        self.assertEqual(
            hashlib.sha256(staged.read_bytes()).hexdigest(), plan["asset"]["sha256"]
        )
        process.assert_not_called()

    def test_confirmation_and_discard_are_bound_to_the_preview(self):
        result = update.inspect_upload(self.upload("4.1.5"))
        plan = update._checks[result["check_id"]]
        staged = Path(plan["_upload"])
        with patch.object(update, "start_job", return_value={"ok": True}) as start:
            with self.assertRaisesRegex(ValueError, "二次确认"):
                update.submit(result["check_id"])
            start.assert_not_called()
            update.submit(result["check_id"], True, confirm_downgrade=True)
            start.assert_called_once_with(
                plan, True, uploaded=staged, force=False, confirm_downgrade=True
            )
        update.discard_upload(result["check_id"])
        self.assertFalse(staged.exists())
        with self.assertRaisesRegex(ValueError, "过期"):
            update.submit(result["check_id"], confirm_downgrade=True)

    def test_same_version_and_confirmed_older_uploads_work_offline(self):
        for version in ("4.1.5", "4.1.6-alpha.4"):
            with patch.object(update, "start_job", return_value={"ok": True}) as start:
                result = update.upload_package(
                    self.upload(version), confirm_downgrade=version == "4.1.5"
                )
                self.assertTrue(result["ok"])
                self.assertEqual(start.call_args.args[0]["version"], "v" + version)
        self.assertEqual(list((self.state / "uploads").iterdir()), [])

    def test_invalid_or_oversized_uploads_leave_no_preview_or_worker(self):
        with patch.object(update, "start_job") as start:
            with self.assertRaises(ValueError):
                update.inspect_upload(
                    FileStorage(stream=io.BytesIO(b"broken"), filename="mower.zip")
                )
            with (
                patch.object(update, "MAX_PACKAGE_BYTES", 8),
                self.assertRaisesRegex(ValueError, "2 GiB"),
            ):
                update.inspect_upload(self.upload())
            self.assertEqual(list((self.state / "uploads").iterdir()), [])
            start.assert_not_called()

    def test_source_cannot_apply_binary_over_git_checkout(self):
        with (
            patch.object(runtime, "frozen", return_value=False),
            self.assertRaisesRegex(ValueError, "源码部署"),
        ):
            update.inspect_upload(self.upload())

    def test_offline_upload_stages_integrity_hash_and_restart_option(self):
        root = self.state / "install"
        (root / "_internal").mkdir(parents=True)
        (root / "mower").write_text("fixture executable")
        with (
            patch.object(runtime, "installation_root", return_value=root),
            patch.object(sys, "executable", str(root / "mower")),
            patch.object(update, "info", return_value={"blockers": []}),
            patch.object(subprocess, "Popen", return_value=Mock(pid=12345)) as process,
        ):
            result = update.upload_package(self.upload(), background=True)
        self.assertTrue(result["ok"])
        job_path = Path(process.call_args.args[0][-1])
        job = runtime.read_json(job_path)
        self.assertTrue(job["background"])
        self.assertTrue(job["manual"])
        self.assertNotIn("_upload", job)
        staged = job_path.parent / job["asset"]["name"]
        self.assertEqual(
            hashlib.sha256(staged.read_bytes()).hexdigest(), job["asset"]["sha256"]
        )
        self.assertTrue(runtime.read_json(self.state / "settings.json")["background"])
        self.assertEqual(list((self.state / "uploads").iterdir()), [])


class AdmissionAndRoutesTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(software_update_bp)
        self.client = self.app.test_client()

    def test_manual_preview_route_reads_contents_before_confirmation(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(runtime, "frozen", return_value=True),
            patch.object(runtime, "state_dir", return_value=Path(temporary)),
            patch.object(update, "platform_asset", return_value=("windows", "x64")),
            patch.object(update, "__version__", "4.1.6-alpha.4"),
            patch(
                "requests.sessions.Session.request",
                side_effect=AssertionError("offline"),
            ),
            patch.object(update, "start_job", return_value={"ok": True}) as start,
        ):
            headers = {"X-Mower-Update": "1"}
            result = self.client.post(
                "/software-update/manual/inspect",
                data={
                    "file": (io.BytesIO(make_release_package("4.1.5")), "arbitrary.bin")
                },
                headers=headers,
            )
            self.assertEqual(result.status_code, 200)
            preview = result.get_json()
            self.assertEqual(preview["version"], "v4.1.5")
            start.assert_not_called()
            data = {"check_id": preview["check_id"]}
            self.assertEqual(
                self.client.post(
                    "/software-update/start", json=data, headers=headers
                ).status_code,
                400,
            )
            data["confirm_downgrade"] = True
            self.assertEqual(
                self.client.post(
                    "/software-update/start", json=data, headers=headers
                ).status_code,
                200,
            )
            start.assert_called_once()
            self.client.post(
                "/software-update/manual/discard", json=data, headers=headers
            )
            self.assertEqual(list((Path(temporary) / "uploads").iterdir()), [])

    def test_force_route_requires_explicit_boolean_and_forwards_it(self):
        with patch.object(update, "submit", return_value={"ok": True}) as submit:
            for value in ("false", "true", 1, None):
                response = self.client.post(
                    "/software-update/start",
                    json={"check_id": "fixture", "force": value},
                    headers={"X-Mower-Update": "1"},
                )
                self.assertEqual(response.status_code, 400)
            submit.assert_not_called()
            for value in (False, True):
                response = self.client.post(
                    "/software-update/start",
                    json={"check_id": "fixture", "background": True, "force": value},
                    headers={"X-Mower-Update": "1"},
                )
                self.assertEqual(response.status_code, 200)
                submit.assert_called_with(
                    "fixture", True, force=value, confirm_downgrade=False
                )

    def test_online_rollback_confirmation_is_enforced_and_cannot_be_forced(self):
        plan = {
            "created_at": time.time(),
            "downgrade": True,
            "available": True,
            "deployment": "source",
        }
        with (
            patch.dict(update._checks, {"rollback": plan}, clear=True),
            patch.object(update, "start_job", return_value={"ok": True}) as start,
        ):
            for force, value in product((False, True), (False, "true", 1, None)):
                response = self.client.post(
                    "/software-update/start",
                    json={
                        "check_id": "rollback",
                        "force": force,
                        "confirm_downgrade": value,
                    },
                    headers={"X-Mower-Update": "1"},
                )
                self.assertEqual(response.status_code, 400)
            start.assert_not_called()
            response = self.client.post(
                "/software-update/start",
                json={"check_id": "rollback", "confirm_downgrade": True},
                headers={"X-Mower-Update": "1"},
            )
            self.assertEqual(response.status_code, 200)
            start.assert_called_once_with(
                plan, False, force=False, confirm_downgrade=True
            )

    def test_job_admission_requires_boolean_rollback_confirmation(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(runtime, "state_dir", return_value=Path(temporary)),
            patch.object(update, "_start_job", return_value={"ok": True}) as start,
        ):
            plan = {"downgrade": True}
            for force, value in product((False, True), (False, "true", 1, None)):
                with (
                    self.subTest(force=force, value=value),
                    self.assertRaises(ValueError),
                ):
                    update.start_job(plan, force=force, confirm_downgrade=value)
            start.assert_not_called()
            self.assertTrue(update.start_job(plan, confirm_downgrade=True)["ok"])
            start.assert_called_once()

    def test_manual_route_requires_explicit_rollback_confirmation(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(runtime, "frozen", return_value=True),
            patch.object(runtime, "state_dir", return_value=Path(temporary)),
            patch.object(update, "__version__", "4.1.6-alpha.4"),
            patch.object(update, "platform_asset", return_value=("windows", "x64")),
            patch.object(update, "start_job", return_value={"ok": True}) as start,
        ):
            for value in (None, "false", "1", "True", "", "true"):
                data = {
                    "file": (
                        io.BytesIO(make_release_package("4.1.5")),
                        "renamed (1).bin",
                    )
                }
                if value is not None:
                    data["confirm_downgrade"] = value
                response = self.client.post(
                    "/software-update/manual",
                    data=data,
                    headers={"X-Mower-Update": "1"},
                )
                self.assertEqual(response.status_code, 200 if value == "true" else 400)
                if value != "true":
                    start.assert_not_called()
            start.assert_called_once()
            self.assertTrue(start.call_args.kwargs["confirm_downgrade"])

    def test_force_cannot_bypass_tools_or_apply_to_release(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(runtime, "state_dir", return_value=Path(folder)),
            patch.object(
                update,
                "info",
                return_value={"blockers": ["missing npm"], "force_supported": False},
            ),
            patch.object(subprocess, "Popen") as process,
        ):
            with self.assertRaisesRegex(ValueError, "missing npm"):
                update.start_job({"deployment": "source"}, force=True)
            with self.assertRaisesRegex(ValueError, "仅支持源码"):
                update.start_job({"deployment": "release"}, force=True)
            process.assert_not_called()

    def test_manual_route_accepts_one_package_offline(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(runtime, "frozen", return_value=True),
            patch.object(runtime, "state_dir", return_value=Path(temporary)),
            patch.object(update, "platform_asset", return_value=("windows", "x64")),
            patch.object(update, "github") as network,
            patch.object(update, "start_job", return_value={"ok": True}) as start,
        ):
            response = self.client.post(
                "/software-update/manual",
                data={
                    "file": (
                        io.BytesIO(make_release_package()),
                        "renamed (1).bin",
                    ),
                },
                headers={"X-Mower-Update": "1"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["ok"])
            self.assertTrue(start.call_args.args[0]["manual"])
            self.assertFalse(start.call_args.args[1])
            network.assert_not_called()

    def test_token_is_required_for_read_and_write(self):
        self.app.token = "test-token"
        self.assertEqual(self.client.get("/software-update/info").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/software-update/check",
                json={"channel": "beta"},
                headers={"X-Mower-Update": "1"},
            ).status_code,
            403,
        )

    def test_cross_origin_and_simple_form_posts_are_blocked(self):
        with patch.object(update, "check") as check:
            self.assertEqual(
                self.client.post(
                    "/software-update/check", json={"channel": "beta"}
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    "/software-update/check",
                    json={"channel": "beta"},
                    headers={
                        "X-Mower-Update": "1",
                        "Origin": "https://example.invalid",
                    },
                ).status_code,
                403,
            )
            check.assert_not_called()

    def test_successful_check_and_error_are_json(self):
        headers = {"X-Mower-Update": "1", "Origin": "http://localhost"}
        with patch.object(
            update, "check", return_value={"ok": True, "available": True}
        ):
            self.assertTrue(
                self.client.post(
                    "/software-update/check", json={"channel": "beta"}, headers=headers
                ).get_json()["available"]
            )
        with patch.object(
            update, "check", side_effect=ValueError("network unavailable")
        ):
            result = self.client.post(
                "/software-update/check", json={"channel": "beta"}, headers=headers
            )
            self.assertEqual(result.status_code, 400)
            self.assertFalse(result.get_json()["ok"])

    def test_stale_check_cannot_start_a_job(self):
        with (
            patch.dict(update._checks, {"expired": {"created_at": 0}}, clear=True),
            patch.object(update, "start_job") as start,
        ):
            with self.assertRaises(ValueError):
                update.submit("expired")
            start.assert_not_called()

    def test_submission_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as temporary:
            with runtime.submission_lock(temporary):
                with self.assertRaises(ValueError):
                    with runtime.submission_lock(temporary):
                        pass
            with runtime.submission_lock(temporary):
                pass

    def test_dirty_checkout_prevents_worker_spawn(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(runtime, "state_dir", return_value=Path(temporary)),
            patch.object(update, "info", return_value={"blockers": []}),
            patch.object(update, "source_tools", return_value={"git": "git"}),
            patch.object(subprocess, "check_output", return_value=b" M manager.py"),
            patch.object(subprocess, "Popen") as process,
        ):
            with self.assertRaisesRegex(ValueError, "未提交"):
                update.start_job({"deployment": "source"})
            process.assert_not_called()


class WorkerTests(unittest.TestCase):
    def setUp(self):
        clean_source = patch(
            "arknights_mower.utils.software_update_worker.require_clean_source"
        )
        clean_source.start()
        self.addCleanup(clean_source.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / "install"
        self.work = base / "jobs/one"
        self.state = base / "state"
        self.root.mkdir()
        self.work.mkdir(parents=True)
        self.job = {
            "id": "test-job",
            "root": str(self.root),
            "state_dir": str(self.state),
            "deployment": "source",
            "version": "v4.2.0",
            "background": True,
            "git": "git",
            "python": sys.executable,
            "base_python": sys.executable,
            "npm": "npm",
            "commit": "new",
            "ref": "refs/heads/alpha",
        }

    def worker(self):
        runtime.write_json(self.work / "job.json", self.job)
        return Worker(self.work / "job.json")

    def test_release_transaction_allows_background_restart(self):
        self.job.update(deployment="release")
        worker = self.worker()
        worker.prepare_package = Mock()
        worker.stop_instances = Mock()
        worker.install_package = Mock()
        worker.restart = Mock()
        worker.execute()
        worker.install_package.assert_called_once()
        worker.restart.assert_called_once_with(worker.original)
        self.assertEqual(
            runtime.read_json(self.state / "status.json")["status"], "succeeded"
        )

    def test_cleanup_failure_after_verified_restart_never_rolls_back(self):
        self.job.update(deployment="release")
        worker = self.worker()
        worker.prepare_package = Mock()
        worker.stop_instances = Mock()
        worker.install_package = Mock()
        worker.restart = Mock()
        worker.verified_restart = True
        worker.cleanup_verified_backups = Mock(side_effect=PermissionError("locked"))
        worker.rollback = Mock()
        worker.execute()
        worker.rollback.assert_not_called()
        self.assertEqual(
            runtime.read_json(self.state / "status.json")["status"], "succeeded"
        )

    def test_failed_restart_never_discards_rollback_files(self):
        self.job.update(deployment="release")
        worker = self.worker()
        worker.prepare_package = Mock()
        worker.stop_instances = Mock()
        worker.install_package = Mock(
            side_effect=lambda: setattr(worker, "switched", True)
        )
        worker.restart = Mock(side_effect=[RuntimeError("not ready"), None])
        worker.cleanup_verified_backups = Mock()
        worker.rollback = Mock()
        worker.execute()
        worker.rollback.assert_called_once()
        worker.cleanup_verified_backups.assert_not_called()
        self.assertEqual(
            runtime.read_json(self.state / "status.json")["status"], "failed"
        )

    def test_release_restart_option_controls_instances_and_manager(self):
        records = [
            {
                "kind": "instance",
                "space": f"space{i}",
                "name": f"实例{i}",
                "port": 58100 + i,
                "running": i != 1,
            }
            for i in range(3)
        ] + [{"kind": "manager"}]
        for background in (True, False):
            with (
                self.subTest(background=background),
                patch.object(subprocess, "Popen") as process,
            ):
                self.job.update(deployment="release", background=background)
                worker = self.worker()
                worker.restart(records, verify=False)
                self.assertEqual(process.call_count, 3 if background else 4)
                for call, record in zip(process.call_args_list, records):
                    env = call.kwargs["env"]
                    self.assertEqual(
                        env["MOWER_BACKGROUND"], "1" if background else "0"
                    )
                    self.assertEqual(
                        env["MOWER_RESUME_RUN"], "1" if record.get("running") else "0"
                    )
                    self.assertEqual(
                        env["MOWER_RESTART_PORT"], str(record.get("port") or "")
                    )
                    self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_silent_restart_restores_unified_tray_and_managed_instances(self):
        records = [
            {"kind": "manager", "unified_tray": True},
            {
                "kind": "instance",
                "managed": True,
                "space": "test",
                "name": "test",
                "port": 58100,
                "running": True,
            },
        ]
        with patch.object(subprocess, "Popen") as process:
            self.job.update(deployment="release", background=True)
            self.worker().restart(records, verify=False)
        self.assertEqual(process.call_count, 2)
        manager_env, instance_env = [c.kwargs["env"] for c in process.call_args_list]
        self.assertEqual(manager_env["MOWER_BACKGROUND"], "1")
        self.assertEqual(instance_env["MOWER_BACKGROUND"], "1")
        self.assertEqual(instance_env["MOWER_MANAGED"], "1")
        self.assertEqual(instance_env["MOWER_RESUME_RUN"], "1")
        self.assertEqual(instance_env["MOWER_RESTART_PORT"], "58100")

        with patch.object(subprocess, "Popen") as process:
            self.worker().restart(records[1:], verify=False)
        self.assertEqual(process.call_args.kwargs["env"]["MOWER_MANAGED"], "1")
        with (
            patch.dict(os.environ, process.call_args.kwargs["env"]),
            patch.object(runtime, "state_dir", return_value=self.state),
        ):
            restarted = runtime.RuntimeRegistration("instance", name="test")
            try:
                self.assertEqual(runtime.managed_instances(), [restarted.record])
            finally:
                restarted.close()

    def test_dependency_failure_restores_old_virtualenv_and_frontend(self):
        worker = self.worker()
        worker.old_commit = "old"
        for relative in (".venv", "ui/node_modules", "ui/dist"):
            folder = self.root / relative
            folder.mkdir(parents=True)
            (folder / "old").write_text(relative)
        worker.git_output = lambda *args: "old" if args[0] == "rev-parse" else ""

        def command(args, **kwargs):
            if "venv" in args:
                (self.root / ".venv").mkdir()
                (self.root / ".venv/new").write_text("new dependencies")
            if "pip" in args:
                raise RuntimeError("pip failed")

        worker.run_command = command
        with self.assertRaisesRegex(RuntimeError, "pip failed"):
            worker.install_source()
        worker.rollback()
        for relative in (".venv", "ui/node_modules", "ui/dist"):
            self.assertEqual((self.root / relative / "old").read_text(), relative)
        self.assertFalse((self.root / ".venv/new").exists())

    def test_portable_update_preserves_user_data_and_removes_obsolete_runtime(self):
        self.job.update(deployment="release", background=False)
        worker = self.worker()
        worker.prepared = self.work / "prepared"
        (worker.prepared / "_internal").mkdir(parents=True)
        (worker.prepared / "_internal/new-code").write_text("new")
        (worker.prepared / "mower.exe").write_text("new executable")
        (self.root / "_internal").mkdir()
        (self.root / "_internal/obsolete").write_text("old")
        (self.root / "mower.exe").write_text("old executable")
        (self.root / "instances.json").write_text("my instances")
        (self.root / "config").mkdir()
        (self.root / "config/conf.yml").write_text("maa_path: '@app/MAA'")
        (self.root / "MAA").mkdir()
        (self.root / "MAA/user-data").write_text("keep MAA")
        (self.root / "resources/packages").mkdir(parents=True)
        (self.root / "resources/packages/persistent").write_text("shared resource")
        worker.install_package()
        self.assertFalse((self.root / "_internal/obsolete").exists())
        self.assertEqual((self.root / "mower.exe").read_text(), "new executable")
        self.assertEqual(
            (self.root / "config/conf.yml").read_text(), "maa_path: '@app/MAA'"
        )
        self.assertEqual((self.root / "MAA/user-data").read_text(), "keep MAA")
        self.assertEqual(
            (self.root / "resources/packages/persistent").read_text(), "shared resource"
        )
        worker.rollback()
        self.assertEqual((self.root / "_internal/obsolete").read_text(), "old")
        self.assertEqual((self.root / "mower.exe").read_text(), "old executable")
        self.assertEqual((self.root / "instances.json").read_text(), "my instances")
        self.assertEqual((self.root / "MAA/user-data").read_text(), "keep MAA")

    def test_checksum_failure_happens_before_shutdown(self):
        for manual in (False, True):
            with (
                self.subTest(manual=manual),
                patch(
                    "requests.sessions.Session.request",
                    side_effect=AssertionError("offline"),
                ),
            ):
                self.job.update(
                    deployment="release",
                    background=False,
                    manual=manual,
                    asset={"name": "package.zip", "sha256": "a" * 64},
                )
                (self.work / "package.zip").write_bytes(b"changed after inspection")
                worker = self.worker()
                worker.stop_instances = Mock()
                worker.execute()
                worker.stop_instances.assert_not_called()
                result = runtime.read_json(self.state / "status.json")
                self.assertEqual(result["status"], "failed")
                self.assertIn("SHA-256", result["message"])
                self.assertFalse((self.state / "active").exists())

    def test_missing_manual_package_fails_without_network_or_shutdown(self):
        self.job.update(
            deployment="release",
            background=False,
            manual=True,
            asset={"name": "missing.zip"},
        )
        worker = self.worker()
        worker.stop_instances = Mock()
        with patch("requests.get") as network:
            worker.execute()
            network.assert_not_called()
        worker.stop_instances.assert_not_called()
        self.assertIn(
            "重新上传", runtime.read_json(self.state / "status.json")["message"]
        )

    def test_manual_and_online_packages_prepare(self):
        package = self.work / "package.zip"
        executable = "mower.exe" if sys.platform == "win32" else "mower"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(f"mower/{executable}", "fixture executable")
            archive.writestr(
                "mower/_internal/arknights_mower/utils/update_runtime.py", "# fixture"
            )
        for manual in (True, False):
            with self.subTest(manual=manual):
                asset = {"name": package.name}
                if not manual:
                    asset["sha256"] = hashlib.sha256(package.read_bytes()).hexdigest()
                self.job.update(
                    deployment="release", background=False, manual=manual, asset=asset
                )
                worker = self.worker()
                with patch("requests.get") as network:
                    worker.prepare_package()
                    network.assert_not_called()
                self.assertEqual(
                    (worker.prepared / executable).read_text(), "fixture executable"
                )
                shutil.rmtree(worker.prepared)
                shutil.rmtree(self.work / "payload")

    def test_macos_bundle_failure_restores_original(self):
        self.job.update(
            deployment="release", background=False, root=str(self.root / "mower.app")
        )
        root = Path(self.job["root"])
        root.mkdir()
        (root / "old").write_text("original")
        worker = self.worker()
        worker.prepared = self.work / "missing-payload"
        with self.assertRaises(OSError):
            worker.install_package()
        self.assertEqual((root / "old").read_text(), "original")

    def test_branch_change_during_prepare_is_not_overwritten(self):
        worker = self.worker()
        worker.old_commit = "old"
        worker.git_output = lambda *args: (
            "another-commit" if args[0] == "rev-parse" else ""
        )
        worker.run_command = Mock()
        with self.assertRaises(ValueError):
            worker.install_source()
        worker.run_command.assert_not_called()

    def test_target_without_update_protocol_is_rejected_before_shutdown(self):
        worker = self.worker()
        worker.git_output = Mock(
            side_effect=[
                "old",
                "main",
                "new",
                subprocess.CalledProcessError(1, ["git", "cat-file"]),
            ]
        )
        worker.run_command = Mock()
        worker.stop_instances = Mock()
        worker.execute()
        worker.stop_instances.assert_not_called()
        self.assertIn(
            "尚未包含", runtime.read_json(self.state / "status.json")["message"]
        )

    @unittest.skipUnless(sys.platform == "darwin", "DMG is macOS-only")
    def test_real_dmg_mount_copy_replace_and_rollback(self):
        content = self.work / "dmg-content/mower.app"
        (content / "Contents/MacOS").mkdir(parents=True)
        resources = content / "Contents/Resources/arknights_mower/utils"
        resources.mkdir(parents=True)
        (resources / "update_runtime.py").write_text("# fixture protocol")
        shutil.copyfile("/usr/bin/true", content / "Contents/MacOS/mower")
        (content / "Contents/MacOS/mower").chmod(0o755)
        (content / "Contents/MacOS/_internal").symlink_to("../Resources")
        with (content / "Contents/Info.plist").open("wb") as stream:
            plistlib.dump(
                {
                    "CFBundleIdentifier": "test.mower.updater",
                    "CFBundleExecutable": "mower",
                    "CFBundlePackageType": "APPL",
                },
                stream,
            )
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(content)],
            check=True,
            capture_output=True,
        )
        package = self.work / "fixture.dmg"
        subprocess.run(
            [
                "/usr/bin/hdiutil",
                "create",
                "-srcfolder",
                str(content.parent),
                "-format",
                "UDZO",
                str(package),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=60,
        )
        root = self.root / "mower.app"
        root.mkdir()
        (root / "old-version").write_text("original")
        self.job.update(
            root=str(root),
            deployment="release",
            background=False,
            manual=True,
            asset={"name": package.name},
        )
        worker = self.worker()
        worker.prepare_package()
        worker.install_package()
        self.assertTrue((root / "Contents/MacOS/_internal").is_symlink())
        self.assertFalse((root / "old-version").exists())
        worker.verify_macos_signature(root)
        (
            root / "Contents/Resources/arknights_mower/utils/update_runtime.py"
        ).write_text("changed after signing")
        with self.assertRaisesRegex(ValueError, "签名完整性检查失败"):
            worker.verify_macos_signature(root)
        worker.rollback()
        self.assertEqual((root / "old-version").read_text(), "original")

    def test_invalid_macos_signature_aborts_before_instance_shutdown(self):
        self.job.update(deployment="release", root=str(self.root / "mower.app"))
        worker = self.worker()
        worker.prepare_package = lambda: worker.verify_macos_signature(self.root)
        worker.stop_instances = Mock()
        worker.install_package = Mock()
        worker.run_command = Mock(
            side_effect=subprocess.CalledProcessError(1, ["codesign"])
        )
        worker.execute()
        worker.stop_instances.assert_not_called()
        worker.install_package.assert_not_called()
        self.assertIn(
            "签名完整性检查失败",
            runtime.read_json(self.state / "status.json")["message"],
        )


class ArchiveAndLauncherTests(unittest.TestCase):
    def test_zip_and_tar_layouts_extract(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with zipfile.ZipFile(directory / "package.zip", "w") as archive:
                archive.writestr("mower/_internal/module.py", "module")
            extract_archive(directory / "package.zip", directory / "zip")
            with tarfile.open(directory / "package.tar.gz", "w:gz") as archive:
                info = tarfile.TarInfo("mower/mower")
                info.size = 3
                info.mode = 0o755
                archive.addfile(info, io.BytesIO(b"app"))
            extract_archive(directory / "package.tar.gz", directory / "tar")
            self.assertTrue((directory / "zip/mower/_internal/module.py").is_file())
            self.assertEqual((directory / "tar/mower/mower").read_bytes(), b"app")

    def test_registration_cleanup_and_installation_scoping(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(runtime, "state_dir", return_value=Path(temporary)),
        ):
            registration = runtime.RuntimeRegistration(
                "instance", name="test", running=lambda: True
            )
            self.assertTrue(runtime.instances()[0]["running"])
            registration.close()
            self.assertEqual(runtime.instances(), [])

    def test_background_env_controls_source_and_release_startup(self):
        from webview_ui import background_requested

        for frozen in (False, True):
            for value in ("1", "0", ""):
                with (
                    self.subTest(frozen=frozen, value=value),
                    patch.dict(os.environ, {"MOWER_BACKGROUND": value}),
                    patch.object(runtime, "frozen", return_value=frozen),
                ):
                    self.assertEqual(background_requested(), value == "1")

    def test_desktop_background_preserves_trays_and_current_restart_behavior(self):
        import webview_ui
        from arknights_mower import utils
        from arknights_mower.utils import network, path

        for system, background, tray_enabled, restart, managed in product(
            ("darwin", "linux", "win32"), *[(True, False)] * 4
        ):
            config = Mock()
            config.conf.webview.tray = tray_enabled
            config.conf.webview.token = ""
            config.conf.start_automatically = False
            server = Mock(app=Flask(__name__))
            server._job_running.return_value = False
            server.resource_update.running.side_effect = [True, False]
            server.stop.return_value = "true"
            registration = Mock(record={})
            registration.shutdown_requested.return_value = True
            with (
                self.subTest(
                    system=system,
                    background=background,
                    tray=tray_enabled,
                    restart=restart,
                ),
                patch.object(sys, "platform", system),
                patch.dict(
                    os.environ,
                    {
                        "MOWER_BACKGROUND": "1" if background else "0",
                        "MOWER_RESTART_JOB": "fixture" if restart else "",
                        "MOWER_RESUME_RUN": "1",
                        "MOWER_RESTART_PORT": "58100",
                        "MOWER_MANAGED": "1" if managed else "0",
                    },
                ),
                patch.dict(sys.modules, {"server": server}),
                patch.object(sys, "argv", ["mower"]),
                patch.object(utils, "config", config, create=True),
                patch.object(path, "global_space", ""),
                patch.object(runtime, "read_json", return_value={}),
                patch.object(runtime, "active_job", return_value=False),
                patch.object(runtime, "frozen", return_value=True),
                patch.object(runtime, "RuntimeRegistration", return_value=registration),
                patch.object(runtime, "hide_macos_dock_icon") as hide_dock,
                patch.object(network, "is_port_in_use", side_effect=[False, True]),
                patch.multiple(
                    webview_ui,
                    exit_if_webview_backend_missing=Mock(),
                    close_child=Mock(),
                ),
                patch.object(update, "request_auto_check") as auto_check,
                patch.object(webview_ui.mp, "Queue") as queue,
                patch.object(
                    webview_ui, "start_desktop_child", return_value=(Mock(), Mock())
                ) as process,
                patch(
                    "arknights_mower.utils.desktop_process.log_channel",
                    return_value=Mock(),
                ),
                patch.multiple(
                    "arknights_mower.utils.log",
                    init_file_logging=Mock(),
                    start_mp_listener=Mock(),
                    mp_listener=Mock(),
                ),
                patch("threading.Thread") as threads,
            ):
                webview_ui.run_desktop()
                auto_check.assert_called_once()
                self.assertEqual(server.resource_update.running.call_count, 2)
                targets = [call.args[0] for call in process.call_args_list]
                expected = [] if background else ["splash"]
                if (tray_enabled or background) and not managed:
                    expected.append("tray")
                if not background:
                    expected.append("window")
                self.assertEqual(targets, expected)
                if system == "darwin":
                    queue.assert_not_called()
                hide_dock.assert_not_called()
                registration.close.assert_called_once()
                resumes = [
                    call.kwargs["target"]
                    for call in threads.call_args_list
                    if call.kwargs["target"].__name__ == "resume_after_update"
                ]
                self.assertEqual(len(resumes), int(restart))
                if resumes:
                    registration.shutdown_requested.return_value = False
                    resumes[0]()
                    server.start.assert_called_once_with("2")

    def test_tray_always_hides_its_dock_icon(self):
        from webview_ui import start_tray

        for frozen, background in (
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ):
            with (
                self.subTest(frozen=frozen, background=background),
                patch.dict(
                    os.environ, {"MOWER_BACKGROUND": "1" if background else "0"}
                ),
                patch.dict(sys.modules, {"pystray": Mock()}),
                patch.object(runtime, "frozen", return_value=frozen),
                patch.object(runtime, "hide_macos_dock_icon") as hide_dock,
                patch("PIL.Image.open"),
            ):
                start_tray(Mock(), "test", 58100, "http://127.0.0.1:58100")
                hide_dock.assert_called_once()

    def test_dock_helper_sets_accessory_policy(self):
        appkit = Mock()
        appkit.NSApplicationActivationPolicyAccessory = 1
        with (
            patch.object(sys, "platform", "darwin"),
            patch.dict(sys.modules, {"AppKit": appkit}),
        ):
            runtime.hide_macos_dock_icon()
        appkit.NSApplication.sharedApplication().setActivationPolicy_.assert_called_once_with(
            1
        )

    def test_closed_child_is_joined_without_forced_termination(self):
        from webview_ui import close_child

        process = Mock()
        process.is_alive.side_effect = [True, False, False]
        connection = Mock()
        close_child(process, connection)
        connection.send.assert_called_once_with("exit")
        process.terminate.assert_not_called()
        self.assertEqual(process.join.call_count, 2)


class ThreeInstanceIntegrationTests(unittest.TestCase):
    """Actual subprocess shutdown/restart; no emulator, GitHub or real config."""

    def test_three_instances_restore_names_ports_and_run_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "install"
            state = directory / "state"
            root.mkdir()
            helper = root / "update_runtime.py"
            shutil.copy2(runtime.__file__, helper)
            launcher = root / "webview_ui.py"
            launcher.write_text(
                "import os, sys, time\n"
                "from pathlib import Path\n"
                "import update_runtime as r\n"
                f"r.state_dir = lambda: Path({str(state)!r})\n"
                f"r.installation_root = lambda: Path({str(root)!r})\n"
                "registration = r.RuntimeRegistration('instance', space=sys.argv[1], name=sys.argv[2], port=int(os.environ['MOWER_RESTART_PORT']), running=lambda: os.environ['MOWER_RESUME_RUN']=='1')\n"
                "registration.record['ready'] = True\n"
                "registration.publish()\n"
                "while not registration.shutdown_requested(): time.sleep(.05)\n"
                "registration.close()\n",
                encoding="utf-8",
            )
            original = []
            replacement = []
            try:
                for index in range(3):
                    env = runtime.launch_environment(
                        {"port": 58100 + index, "running": index != 1}
                    )
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            str(launcher),
                            f"space{index}",
                            f"实例{index}",
                        ],
                        cwd=root,
                        env=env,
                    )
                    original.append(process)
                    threading.Thread(target=process.wait, daemon=True).start()
                deadline = time.monotonic() + 10
                while (
                    len(runtime.instances(state)) != 3 and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                self.assertEqual(len(runtime.instances(state)), 3)
                job = {
                    "id": "integration",
                    "state_dir": str(state),
                    "root": str(root),
                    "version": "v4.2.0",
                    "deployment": "source",
                    "background": True,
                    "python": sys.executable,
                }
                runtime.write_json(directory / "job.json", job)
                worker = Worker(directory / "job.json")
                worker.prepare_source = Mock()
                worker.prepare_source_payload = Mock()
                worker.install_source = Mock()
                worker.execute()
                replacement = worker.new_processes
                self.assertEqual(
                    runtime.read_json(state / "status.json")["status"], "succeeded"
                )
                records = sorted(runtime.instances(state), key=lambda row: row["name"])
                self.assertEqual(
                    [row["name"] for row in records], ["实例0", "实例1", "实例2"]
                )
                self.assertEqual(
                    [row["port"] for row in records], [58100, 58101, 58102]
                )
                self.assertEqual(
                    [row["running"] for row in records], [True, False, True]
                )
                self.assertTrue(all(process.poll() is not None for process in original))
                self.assertFalse((state / "active").exists())
            finally:
                for record in runtime.instances(state):
                    runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
                for process in original + replacement:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
