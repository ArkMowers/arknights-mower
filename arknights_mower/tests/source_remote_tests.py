"""Fork selection stays consistent across API previews, fetch and future checks."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker
from arknights_mower.views.software_update import software_update_bp


class SourceRemoteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mower-remote-中文 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git = shutil.which("git")
        self.assertIsNotNone(self.git, "Git is required for source remote tests")
        self.command("init", "-b", "alpha")
        self.command("config", "core.hooksPath", str(self.root / "no-hooks"))
        self.command(
            "remote",
            "add",
            "origin",
            "https://github.com/ArkMowers/arknights-mower.git",
        )
        self.command("remote", "add", "personal", "git@github.com:personal/mower.git")
        self.command("remote", "add", "local-only", str(self.root / "local"))
        for context in (
            patch.object(runtime, "state_dir", return_value=self.root / "state"),
            patch.object(runtime, "installation_root", return_value=self.root),
            patch.object(runtime, "frozen", return_value=False),
            patch.object(
                update, "source_repository", return_value=("b" * 40, "alpha", "")
            ),
            patch.dict(update._checks, {}, clear=True),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.target = {
            "sha": "a" * 40,
            "commit": {"message": "fork change", "author": {}},
        }
        self.pull = {
            "number": 7,
            "title": "Fork feature",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "merge_commit_sha": "d" * 40,
            "head": {"sha": "a" * 40},
            "base": {"ref": "main", "sha": "b" * 40},
        }

    def command(self, *args, cwd=None):
        return subprocess.check_output(
            [self.git, *args],
            cwd=cwd or self.root,
            text=True,
            encoding="utf-8",
            stderr=subprocess.STDOUT,
        ).strip()

    def github(self, path, proxy, *, repo=update.REPO):
        self.assertEqual(repo, "personal/mower")
        if path.startswith("/pulls?"):
            return [self.pull, {**self.pull, "number": 8, "draft": True}]
        if path.startswith("/pulls/"):
            return self.pull
        if not path:
            return {"default_branch": "main"}
        if path.startswith("/branches?"):
            return [{"name": "main"}, {"name": "feature/fork"}]
        if path.startswith("/branches/"):
            return {"commit": {"sha": "b" * 40, "commit": {}}}
        if path.startswith("/commits?"):
            return [self.target]
        if path.startswith("/contents/"):
            return {"type": "file"}
        return self.target

    def test_url_formats_and_local_remote_choices(self):
        for value in (
            "personal/mower",
            "https://github.com/personal/mower.git/",
            "https://github.com/personal/mower",
        ):
            self.assertEqual(
                update.resolve_source_remote(value)["source_url"],
                "https://github.com/personal/mower.git",
            )
        for value in (
            "personal",
            "git@github.com:personal/mower.git",
            "ssh://git@github.com/personal/mower.git",
        ):
            self.assertEqual(
                update.resolve_source_remote(value)["source_url"],
                "git@github.com:personal/mower.git",
            )
        self.assertEqual([r["value"] for r in update.source_remotes()], ["origin"])
        with self.assertRaisesRegex(ValueError, "不存在"):
            update.resolve_source_remote("missing")

    def test_invalid_addresses_are_rejected_before_network(self):
        with patch.object(update.requests, "get") as request:
            for value in (
                None,
                {},
                "",
                "--upload-pack=command",
                "file:///tmp/repo",
                "https://other.site/a/b",
                "https://github.com.evil/a/b",
                "https://token@github.com/a/b",
                "https://github.com/a/b?token=x",
                "https://github.com/a/b/tree/main",
                "a/b\ncommand",
                "ext::command",
            ):
                if value is None:
                    continue  # None intentionally selects the saved default remote.
                with self.subTest(value=value), self.assertRaises(ValueError):
                    update.resolve_source_remote(value)
            request.assert_not_called()

    def test_frozen_installations_cannot_select_remotes(self):
        with patch.object(runtime, "frozen", return_value=True):
            with self.assertRaisesRegex(ValueError, "仅支持源码"):
                update.resolve_source_remote("personal/mower")

    def test_fork_history_uses_default_branch_and_links_to_fork(self):
        with patch.object(update, "github", side_effect=self.github):
            history = update.source_history("", "personal")
        self.assertEqual(history["branch"], "main")
        self.assertEqual(history["source_repo"], "personal/mower")
        self.assertIn("github.com/personal/mower/commit/", history["commits"][0]["url"])

    def test_check_pins_url_even_when_local_remote_is_retargeted(self):
        with patch.object(update, "github", side_effect=self.github):
            checked = update.check_source_version("aaaaaaa", "main", "personal")
        self.command(
            "remote", "set-url", "personal", "https://github.com/another/mower.git"
        )
        with patch.object(update, "start_job") as start:
            update.submit(checked["check_id"])
        plan = start.call_args.args[0]
        self.assertEqual(plan["source_url"], "git@github.com:personal/mower.git")
        self.assertEqual(plan["source_repo"], "personal/mower")
        self.assertEqual(plan["ref"], self.target["sha"])
        self.assertEqual(plan["commit"], self.target["sha"])

    def test_api_route_forwards_selected_remote(self):
        app = Flask(__name__)
        app.token = "fixture"
        app.register_blueprint(software_update_bp)
        client = app.test_client()
        with patch.object(update, "github", side_effect=self.github):
            history = client.get(
                "/software-update/source/history",
                query_string={"remote": "personal", "branch": ""},
                headers={"token": "fixture"},
            )
            checked = client.post(
                "/software-update/source/check",
                json={"remote": "personal", "branch": "main", "reference": "aaaaaaa"},
                headers={"token": "fixture", "X-Mower-Update": "1"},
            )
        self.assertTrue(history.json["ok"])
        self.assertEqual(history.json["source_repo"], "personal/mower")
        self.assertTrue(checked.json["ok"])
        self.assertEqual(checked.json["source_repo"], "personal/mower")

    def test_automatic_checks_use_saved_fork_and_remote_is_part_of_cache_key(self):
        settings = update.get_settings()
        settings.update(source_remote="personal/mower", source_branch="main")
        self.assertNotEqual(
            update.automatic_check_key(settings),
            update.automatic_check_key(update.get_settings()),
        )
        runtime.write_json(self.root / "state/settings.json", settings)
        with (
            patch.object(update, "github", side_effect=self.github),
            patch.object(subprocess, "check_output", return_value="b" * 40),
        ):
            checked = update.check("dev", proxy="")
        plan = update._checks[checked["check_id"]]
        self.assertEqual(plan["source_url"], "https://github.com/personal/mower.git")
        self.assertEqual(plan["ref"], "a" * 40)

    def test_release_api_stays_official_and_source_api_uses_selected_repo(self):
        response = Mock(status_code=200)
        response.json.return_value = {}
        with patch.object(update.requests, "get", return_value=response) as get:
            update.github("/releases/latest")
            self.assertEqual(get.call_args.args[0], update.API + "/releases/latest")
            update.github("/commits/main", repo="personal/mower")
            self.assertEqual(
                get.call_args.args[0],
                "https://api.github.com/repos/personal/mower/commits/main",
            )

    def test_worker_fetches_selected_url_without_modifying_origin(self):
        # Map a GitHub URL to a local fixture: exercise real Git without network.
        (self.root / "arknights_mower/utils").mkdir(parents=True)
        (self.root / "arknights_mower/utils/update_runtime.py").write_text(
            "# fixture\n"
        )
        (self.root / ".gitignore").write_text("state/\nwork/\nfork/\n")
        self.command("config", "user.name", "Local fixture")
        self.command("config", "user.email", "fixture@example.invalid")
        self.command("add", ".")
        self.command("commit", "-m", "original")
        old = self.command("rev-parse", "HEAD")
        fork = self.root / "fork"
        self.command(
            "-c",
            f"core.hooksPath={self.root / 'no-hooks'}",
            "clone",
            str(self.root),
            str(fork),
        )
        self.command("config", "core.hooksPath", str(self.root / "no-hooks"), cwd=fork)
        self.command("config", "user.name", "Local fixture", cwd=fork)
        self.command("config", "user.email", "fixture@example.invalid", cwd=fork)
        (fork / "fork.txt").write_text("personal branch")
        self.command("add", ".", cwd=fork)
        self.command("commit", "-m", "fork", cwd=fork)
        target = self.command("rev-parse", "HEAD", cwd=fork)
        url = "https://github.com/personal/mower.git"
        self.command("config", f"url.{fork.as_uri()}.insteadOf", url)
        job_path = self.root / "work/job.json"
        runtime.write_json(
            job_path,
            {
                "id": "fork",
                "root": str(self.root),
                "state_dir": str(self.root / "state"),
                "deployment": "source",
                "version": "fork",
                "git": self.git,
                "source_url": url,
                "ref": target,
                "commit": target,
            },
        )
        worker = Worker(job_path)
        worker.prepare_source()
        self.assertEqual(self.command("rev-parse", "FETCH_HEAD"), target)
        self.assertEqual(self.command("rev-parse", "HEAD"), old)
        self.assertEqual(
            self.command("remote", "get-url", "origin"),
            "https://github.com/ArkMowers/arknights-mower.git",
        )
        self.assertFalse(worker.stopped)
        # LFS must receive the same pinned source, too.
        with (
            patch.object(worker, "target_uses_lfs", return_value=True),
            patch.object(worker, "run_command") as run,
        ):
            worker.prepare_source()
        self.assertIn(
            [self.git, "lfs", "fetch", url, target],
            [call.args[0] for call in run.call_args_list],
        )
        # Exercise GitHub's PR ref form and a subsequent head change locally.
        self.command("update-ref", "refs/pull/7/head", target, cwd=fork)
        worker.job["ref"] = "refs/pull/7/head"
        worker.prepare_source()
        self.assertEqual(self.command("rev-parse", "FETCH_HEAD"), target)
        self.command("update-ref", "refs/pull/7/head", old, cwd=fork)
        with self.assertRaisesRegex(ValueError, "远端版本已改变"):
            worker.prepare_source()
        self.assertEqual(self.command("rev-parse", "HEAD"), old)
        self.assertFalse(worker.stopped)

    def test_open_pr_selection_pins_head_and_preserves_default_source(self):
        previous = update.get_settings()
        with patch.object(update, "github", side_effect=self.github):
            listed = update.source_pulls("personal")
            checked = update.check_source_pull(7, "personal")
        self.assertEqual([p["number"] for p in listed["pulls"]], [7])
        plan = update._checks[checked["check_id"]]
        self.assertEqual(plan["head_commit"], "a" * 40)
        self.assertEqual(plan["base_commit"], "b" * 40)
        self.assertEqual(plan["commit"], "a" * 40)
        self.assertEqual(plan["ref"], "refs/pull/7/head")
        self.assertEqual(plan["source_url"], "git@github.com:personal/mower.git")
        self.assertEqual(plan["operation"], "source-pr")
        self.assertEqual(update.get_settings(), previous)
        self.assertEqual(checked["source_pr"], 7)

    def test_prs_that_are_closed_draft_or_conflicting_cannot_be_selected(self):
        for change in (
            {"state": "closed"},
            {"draft": True},
            {"mergeable": False},
        ):
            with (
                self.subTest(change=change),
                patch.dict(self.pull, change),
                patch.object(update, "github", side_effect=self.github),
            ):
                with self.assertRaises(ValueError):
                    update.check_source_pull(7, "personal")
                self.assertFalse(update._checks)

    def test_branch_head_uses_branch_endpoint_and_validates_sha(self):
        with patch.object(
            update, "github", return_value={"commit": {"sha": "b" * 40, "commit": {}}}
        ) as github:
            self.assertEqual(
                update.source_branch_head("feature/test", "personal/mower", ""),
                "b" * 40,
            )
            github.assert_called_once_with(
                "/branches/feature%2Ftest", "", repo="personal/mower"
            )
            github.return_value = {"commit": {"sha": "invalid", "commit": {}}}
            with self.assertRaisesRegex(ValueError, "SHA 无效"):
                update.source_branch_head("alpha", "personal/mower", "")

    def test_unknown_mergeability_retries_then_reports_pending(self):
        with (
            patch.dict(self.pull, {"mergeable": None}),
            patch.object(update, "github", side_effect=self.github) as github,
            patch.object(update.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "正在计算.*稍后重新检查"):
                update.mergeable_source_pull(7, "personal/mower", "")
        self.assertFalse(update._checks)
        self.assertEqual(
            sum(call.args[0] == "/pulls/7" for call in github.call_args_list), 3
        )
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0])

    def test_unknown_mergeability_can_finish_or_close_during_retry(self):
        for result in (
            {**self.pull, "head": {"sha": "c" * 40}},
            {**self.pull, "state": "closed"},
        ):
            with (
                patch.object(
                    update,
                    "github",
                    side_effect=[{**self.pull, "mergeable": None}, result],
                ) as github,
                patch.object(update.time, "sleep"),
            ):
                if result["state"] == "closed":
                    with self.assertRaisesRegex(ValueError, "PR #7.*已关闭"):
                        update.mergeable_source_pull(7, "personal/mower", "")
                else:
                    self.assertEqual(
                        update.mergeable_source_pull(7, "personal/mower", "")["head"][
                            "sha"
                        ],
                        "c" * 40,
                    )
                self.assertEqual(github.call_count, 2)

    def test_pr_status_and_head_are_rechecked_before_instance_scan(self):
        with patch.object(update, "github", side_effect=self.github):
            checked = update.check_source_pull(7, "personal")
            for change in (
                {"state": "closed"},
                {"mergeable": False},
                {"head": {"sha": "c" * 40}},
            ):
                with (
                    self.subTest(change=change),
                    patch.dict(self.pull, change),
                    patch.object(update, "info") as info,
                ):
                    with self.assertRaises(ValueError):
                        update.submit(checked["check_id"])
                    info.assert_not_called()

    def test_pr_install_keeps_original_channel_remote_branch_and_disables_auto_install(
        self,
    ):
        original = {
            **update.get_settings(),
            "channel": "beta",
            "source_branch": "alpha",
            "source_remote": "https://github.com/ArkMowers/arknights-mower.git",
            "auto_check": True,
            "auto_update": True,
        }
        runtime.write_json(self.root / "state/settings.json", original)
        with (
            patch.object(update, "github", side_effect=self.github),
            patch.object(update, "info", return_value={"blockers": []}),
            patch.object(
                update,
                "source_tools",
                return_value={
                    "git": self.git,
                    "python": sys.executable,
                    "base_python": sys.executable,
                },
            ),
            patch.object(update, "require_clean_source"),
            patch.object(subprocess, "Popen", return_value=Mock(pid=os.getpid())),
        ):
            checked = update.check_source_pull(7, "personal/mower")
            started = update.submit(checked["check_id"])
        self.assertTrue(started["ok"])
        saved = update.get_settings()
        for key in ("channel", "source_remote", "source_branch", "auto_check"):
            self.assertEqual(saved[key], original[key])
        self.assertFalse(saved["auto_update"])

    def test_only_user_entered_remotes_are_remembered_per_installation(self):
        self.assertEqual(
            update.source_remotes(), [{"value": "origin", "label": "默认仓库"}]
        )
        before = update.get_settings()
        update.remember_source_remote("personal/mower")
        result = update.remember_source_remote("https://github.com/personal/mower.git")
        self.assertEqual(
            [r["value"] for r in result["remotes"]],
            ["origin", "https://github.com/personal/mower.git"],
        )
        for key in (
            "source_remote",
            "source_branch",
            "channel",
            "auto_check",
            "auto_update",
        ):
            self.assertEqual(update.get_settings()[key], before[key])
        with patch.object(
            runtime, "state_dir", return_value=self.root / "other-installation"
        ):
            self.assertEqual(
                update.source_remotes(), [{"value": "origin", "label": "默认仓库"}]
            )
        for index in range(12):
            update.remember_source_remote(f"personal/repo-{index}")
        self.assertEqual(len(update.get_settings()["source_remote_history"]), 10)

    def test_invalid_or_unauthorized_remote_input_is_not_saved(self):
        for value in (
            "fork",
            "--upload-pack=x",
            "https://token@github.com/personal/mower",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                update.remember_source_remote(value)
        app = Flask(__name__)
        app.token = "fixture"
        app.register_blueprint(software_update_bp)
        client = app.test_client()
        response = client.post(
            "/software-update/source/remote", json={"remote": "personal/mower"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(update.get_settings()["source_remote_history"], [])
        response = client.post(
            "/software-update/source/remote",
            json={"remote": "personal/mower"},
            headers={"token": "fixture", "X-Mower-Update": "1"},
        )
        self.assertTrue(response.json["ok"])
        self.assertEqual(
            response.json["source_url"], "https://github.com/personal/mower.git"
        )
