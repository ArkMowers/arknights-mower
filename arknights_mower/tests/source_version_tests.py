"""Source version selection and environment-independent preflight."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from flask import Flask

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker
from arknights_mower.views.software_update import software_update_bp


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        for context in (
            patch.object(runtime, "state_dir", return_value=self.state),
            patch.object(
                update, "source_repository", return_value=("b" * 40, "alpha", "")
            ),
            patch.dict(update._checks, {}, clear=True),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.target = {
            "sha": "a" * 40,
            "commit": {
                "message": "旧版本\n说明",
                "author": {"name": "Mower", "date": "2026-09-05T00:00:00Z"},
            },
        }

    def github(self, path, proxy):
        if path.startswith("/branches?"):
            return [{"name": "alpha"}, {"name": "feature/中文"}]
        if path.startswith("/branches/"):
            return {"name": "alpha"}
        if path.startswith("/commits?"):
            return [self.target]
        if path.startswith("/contents/"):
            return {"type": "file"}
        return self.target

    def test_branch_history_encodes_branch_and_lists_current_commit(self):
        with patch.object(update, "github", side_effect=self.github) as github:
            result = update.source_history("feature/中文")
        self.assertEqual(result["branches"], ["alpha", "feature/中文"])
        self.assertEqual(result["current_commit"], "b" * 40)
        self.assertEqual(result["commits"][0]["sha"], "a" * 40)
        self.assertIn("sha=feature%2F%E4%B8%AD%E6%96%87", github.call_args.args[0])

    def test_branch_tag_and_short_sha_are_pinned_to_full_commit(self):
        with patch.object(update, "github", side_effect=self.github):
            for reference in ("alpha", "v4.1.6-alpha.4", "aaaaaaa", "feature/中文"):
                with self.subTest(reference=reference):
                    result = update.check_source_version(reference, "alpha")
                    plan = update._checks[result["check_id"]]
                    self.assertEqual(plan["operation"], "source-version")
                    self.assertEqual(plan["ref"], "a" * 40)
                    self.assertTrue(plan["available"])
                    self.assertTrue(plan["force_available"])
            self.assertEqual(len(update._checks), 4)

    def test_manual_selection_can_apply_older_or_current_commit(self):
        with (
            patch.object(update, "github", side_effect=self.github),
            patch.object(update, "start_job") as start,
        ):
            result = update.check_source_version("a" * 40)
            update.submit(result["check_id"])
            self.assertEqual(start.call_args.args[0]["commit"], "a" * 40)
            self.target["sha"] = "b" * 40
            result = update.check_source_version("b" * 40)
            update.submit(result["check_id"], force=True)
            self.assertTrue(start.call_args.kwargs["force"])

    def test_unsupported_target_is_rejected_without_creating_install_plan(self):
        def github(path, proxy):
            if path.startswith("/contents/"):
                response = requests.Response()
                response.status_code = 404
                raise requests.HTTPError(response=response)
            return self.github(path, proxy)

        with patch.object(update, "github", side_effect=github):
            with self.assertRaisesRegex(ValueError, "早于软件更新"):
                update.check_source_version("v4.1.6-alpha.3")
        self.assertFalse(update._checks)

    def test_invalid_input_never_reaches_network(self):
        with patch.object(update, "github") as github:
            for reference in (
                None,
                {},
                "",
                "--upload-pack=x",
                "HEAD~1",
                "a..b",
                "https://github.com/a",
                "a\nalpha",
                "a b",
                "@{1}",
            ):
                with self.subTest(reference=reference), self.assertRaises(ValueError):
                    update.check_source_version(reference)
            github.assert_not_called()

    def test_dev_checks_follow_remembered_branch(self):
        runtime.write_json(
            self.state / "settings.json", {"source_branch": "feature/中文"}
        )
        with (
            patch.object(update, "github", side_effect=self.github) as github,
            patch.object(runtime, "frozen", return_value=False),
            patch.object(subprocess, "check_output", return_value="b" * 40),
            patch.object(update.network_settings, "apply_http_proxy"),
        ):
            result = update.check("dev", proxy="")
        self.assertIn("/commits/feature%2F", github.call_args.args[0])
        self.assertEqual(
            update._checks[result["check_id"]]["ref"], "refs/heads/feature/中文"
        )

    def test_read_and_check_routes_require_existing_authorization(self):
        app = Flask(__name__)
        app.token = "fixture"
        app.register_blueprint(software_update_bp)
        client = app.test_client()
        self.assertEqual(client.get("/software-update/source/history").status_code, 403)
        self.assertEqual(
            client.post(
                "/software-update/source/check",
                json={"reference": "alpha"},
                headers={"token": "fixture"},
            ).status_code,
            403,
        )
        with patch.object(update, "github", side_effect=self.github):
            response = client.post(
                "/software-update/source/check",
                json={"reference": "alpha", "branch": "alpha"},
                headers={"token": "fixture", "X-Mower-Update": "1"},
            )
        self.assertTrue(response.json["ok"])

    def test_submitted_version_remembers_branch_and_disables_auto_update(self):
        runtime.write_json(
            self.state / "settings.json",
            {"auto_check": True, "auto_update": True, "source_branch": "alpha"},
        )
        plan = {
            "deployment": "source",
            "operation": "source-version",
            "channel": "dev",
            "source_branch": "feature/中文",
            "version": "commit@aaaaaaa",
        }
        with (
            patch.object(runtime, "installation_root", return_value=self.state),
            patch.object(update, "info", return_value={"blockers": []}),
            patch.object(
                update,
                "source_tools",
                return_value={
                    "git": "git",
                    "python": sys.executable,
                    "base_python": sys.executable,
                },
            ),
            patch.object(update, "require_clean_source"),
            patch.object(update.network_settings, "apply_http_proxy"),
            patch.object(
                update.network_settings,
                "get_effective_settings",
                return_value={"http_proxy": ""},
            ),
            patch.object(update.github_download, "get_proxy", return_value=""),
            patch.object(subprocess, "Popen", return_value=Mock(pid=os.getpid())),
        ):
            result = update.start_job(plan, background=True)
        self.assertTrue(result["ok"])
        saved = update.get_settings()
        self.assertFalse(saved["auto_update"])
        self.assertTrue(saved["auto_check"])
        self.assertEqual(saved["source_branch"], "feature/中文")
        self.assertEqual(saved["channel"], "dev")


class SourceEnvironmentTests(unittest.TestCase):
    def test_no_pip_does_not_imply_uv_and_bootstrap_keeps_current_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            for uv in (None, "/tools/uv"):
                with (
                    self.subTest(uv=uv),
                    patch.object(update.importlib.util, "find_spec", return_value=None),
                    patch.object(
                        update.shutil,
                        "which",
                        side_effect=lambda name, path: uv if name == "uv" else name,
                    ),
                    patch.object(
                        subprocess,
                        "check_output",
                        return_value="https://github.com/ArkMowers/arknights-mower.git",
                    ),
                ):
                    result = update.source_tools(root)
                self.assertEqual(result["uv"], uv)
                self.assertFalse(result["pip_available"])
                self.assertTrue(result["in_place_environment"])
                self.assertEqual(result["python"], sys.executable)

    def test_environment_names_and_locations_do_not_block_any_source_platform(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "install"
            root.mkdir()
            (root / ".git").write_text("gitdir: ../worktree-git")
            local = root / "python environments/custom name"
            local.mkdir(parents=True)
            (local / "pyvenv.cfg").write_text("include-system-site-packages = true\n")
            conda = root / "my-conda"
            (conda / "conda-meta").mkdir(parents=True)
            for platform in ("win32", "linux", "darwin"):
                for prefix, in_place in (
                    (local, False),
                    (Path(temporary) / "external env", True),
                    (Path(sys.base_prefix), True),
                    (conda, True),
                ):
                    with (
                        self.subTest(platform=platform, prefix=prefix),
                        patch.object(sys, "platform", platform),
                        patch.object(sys, "prefix", str(prefix)),
                        patch.object(
                            update.shutil, "which", side_effect=lambda name, path: name
                        ),
                        patch.object(
                            subprocess,
                            "check_output",
                            return_value="https://github.com/ArkMowers/arknights-mower.git",
                        ),
                    ):
                        result = update.source_tools(root)
                        self.assertEqual(result["python"], sys.executable)
                        self.assertEqual(result["in_place_environment"], in_place)
                        if not in_place:
                            self.assertEqual(
                                result["venv_dir"], "python environments/custom name"
                            )
                            self.assertTrue(result["system_site_packages"])

    def test_source_detection_does_not_depend_on_exe_extension_or_os(self):
        for platform in ("win32", "linux", "darwin"):
            with (
                self.subTest(platform=platform),
                patch.object(sys, "platform", platform),
                patch.object(sys, "executable", "C:/Python/python.exe"),
                patch.object(sys, "frozen", False, create=True),
            ):
                self.assertFalse(runtime.frozen())
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", "/bundle", create=True),
            ):
                with self.assertRaisesRegex(ValueError, "仅支持源码"):
                    update.source_repository()

    def test_cache_reset_only_removes_saved_state_for_each_instance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            work = root / "work"
            runtime.write_json(
                work / "job.json",
                {
                    "id": "cache",
                    "root": str(root),
                    "state_dir": str(root / "state"),
                    "deployment": "source",
                    "operation": "source-version",
                    "version": "old",
                },
            )
            records = [
                {"kind": "instance", "space": "one"},
                {
                    "kind": "instance",
                    "space": "two",
                    "data_dir": str(root / "external"),
                },
                {
                    "kind": "instance",
                    "space": "three",
                    "data_dir": "relative",
                    "cwd": str(root / "launch"),
                },
                {"kind": "instance", "space": str(root / "absolute")},
            ]
            paths = [
                root / "one",
                root / "external/two",
                root / "launch/relative/three",
                root / "absolute",
            ]
            for path in paths:
                (path / "tmp").mkdir(parents=True)
                with sqlite3.connect(path / "tmp/data.db") as db:
                    for table in (
                        "saved_state",
                        "mastery_plan",
                        "inventory",
                        "history",
                    ):
                        db.execute(f"CREATE TABLE {table} (value TEXT)")
                        db.execute(f"INSERT INTO {table} VALUES ('keep')")
            Worker(work / "job.json").clear_source_runtime_snapshots(
                records
                + records
                + [{"kind": "manager"}, {"kind": "instance", "space": "missing"}]
            )
            for path in paths:
                with sqlite3.connect(path / "tmp/data.db") as db:
                    self.assertEqual(
                        db.execute("SELECT COUNT(*) FROM saved_state").fetchone()[0], 0
                    )
                    for table in ("mastery_plan", "inventory", "history"):
                        self.assertEqual(
                            db.execute(f"SELECT value FROM {table}").fetchall(),
                            [("keep",)],
                        )
            self.assertFalse((root / "missing").exists())


if __name__ == "__main__":
    unittest.main()
