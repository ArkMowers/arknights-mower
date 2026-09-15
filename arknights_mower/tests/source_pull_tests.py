"""API-only PR checks and an isolated local merge sharing existing Git objects."""

import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker
from arknights_mower.views.software_update import software_update_bp


class SourcePullTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mower-单 PR 中文 ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.remote = self.home / "github"
        self.remote.mkdir()
        self.repo = self.home / "installation"
        self.git = shutil.which("git")
        self.assertIsNotNone(self.git, "Git is required")
        self.command("init", "--template=", "-b", "alpha")
        self.command("config", "user.name", "Fixture")
        self.command("config", "user.email", "fixture@example.invalid")
        self.command("config", "commit.gpgsign", "false")
        self.command("config", "core.hooksPath", str(self.home / "hooks"))
        (self.remote / "shared.txt").write_text("original\n")
        self.command("add", ".")
        self.command("commit", "-m", "original")
        self.original = self.command("rev-parse", "HEAD")
        self.command("clone", "--template=", str(self.remote), str(self.repo))
        self.command("switch", "-c", "feature")
        (self.remote / "feature.txt").write_text("PR content\n")
        (self.remote / "shared.txt").write_text("PR content\n")
        self.command("add", ".")
        self.command("commit", "-m", "PR")
        self.head = self.command("rev-parse", "HEAD")
        self.command("switch", "alpha")
        (self.remote / "upstream.txt").write_text("latest base\n")
        (self.remote / "arknights_mower/utils").mkdir(parents=True)
        (self.remote / "arknights_mower/utils/update_runtime.py").write_text(
            "# fixture\n"
        )
        self.command("add", ".")
        self.command("commit", "-m", "target advances")
        self.base = self.command("rev-parse", "HEAD")
        self.command("update-ref", "refs/pull/7/head", self.head)
        # GitHub can report clean while its generated merge still uses an old base.
        self.command("update-ref", "refs/pull/7/merge", self.original)
        self.pull = {
            "number": 7,
            "title": "Feature",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "mergeable_state": "blocked",  # CI/review not required.
            "merge_commit_sha": self.original,
            "head": {"sha": self.head},
            "base": {"ref": "alpha", "sha": self.original},  # Stale snapshot.
        }
        for context in (
            patch.object(
                update, "source_repository", return_value=(self.original, "alpha", "")
            ),
            patch.object(
                update,
                "resolve_source_remote",
                return_value={
                    "source_repo": "personal/mower",
                    "source_url": self.remote.as_uri(),
                },
            ),
            patch.object(update, "github", side_effect=self.github),
            patch.dict(update._checks, {}, clear=True),
        ):
            context.start()
            self.addCleanup(context.stop)

    def command(self, *args, cwd=None):
        return subprocess.check_output(
            [self.git, *args],
            cwd=cwd or self.remote,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        ).strip()

    def github(self, path, proxy, *, repo):
        self.assertEqual(repo, "personal/mower")
        if path == "/pulls/7":
            return self.pull
        if path == "/branches/alpha":
            return {"commit": {"sha": self.base}}
        self.fail(f"Unexpected GitHub call: {path}")

    def check(self):
        return update.check_source_pull(7, "personal/mower")

    def worker(self):
        checked = self.check()
        path = self.home / "work/job.json"
        runtime.write_json(
            path,
            {
                **update._checks[checked["check_id"]],
                "id": "single-pr",
                "root": str(self.repo),
                "state_dir": str(self.home / "state"),
                "git": self.git,
            },
        )
        worker = Worker(path)
        self.addCleanup(
            lambda: (
                worker.cleanup_preparation() if worker.source_stage.exists() else None
            )
        )
        return worker

    def test_preview_uses_only_api_and_pins_latest_base_plus_head(self):
        with patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("No Git downloads during preview"),
        ):
            checked = self.check()
        plan = update._checks[checked["check_id"]]
        self.assertEqual(plan["source_pr"], 7)
        self.assertEqual(plan["ref"], "refs/pull/7/head")
        self.assertEqual(plan["base_commit"], self.base)
        self.assertEqual(plan["head_commit"], self.head)
        self.assertEqual(checked["sha"], self.head)
        self.assertNotIn("source_prs", plan)
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )

    def test_stale_or_missing_github_merge_does_not_block_selection(self):
        for value in (self.original, None, "obsolete-value"):
            with patch.dict(self.pull, {"merge_commit_sha": value}):
                checked = self.check()
                self.assertEqual(checked["base_commit"], self.base)
                self.assertEqual(checked["sha"], self.head)

    def test_admission_rechecks_closed_conflicting_moved_or_retargeted_pr(self):
        checked = self.check()
        plan = update._checks[checked["check_id"]]
        with patch.object(update, "info", side_effect=RuntimeError("admitted")):
            with self.assertRaisesRegex(RuntimeError, "admitted"):
                update._start_job(plan)
        for change in (
            {"state": "closed"},
            {"draft": True},
            {"mergeable": False},
            {"head": {"sha": self.original}},
            {"base": {"ref": "alpha", "repo": {"full_name": "another/mower"}}},
        ):
            with (
                self.subTest(change=change),
                patch.dict(self.pull, change),
                patch.object(update, "info") as info,
            ):
                with self.assertRaises(ValueError):
                    update._start_job(plan)
                info.assert_not_called()
        # A target branch advance still needs confirmation.
        with (
            patch.object(self, "base", self.original),
            patch.object(update, "info") as info,
        ):
            with self.assertRaisesRegex(ValueError, "已改变"):
                update._start_job(plan)
            info.assert_not_called()

    def test_worker_merges_latest_base_and_head_without_touching_running_checkout(self):
        worker = self.worker()
        # A user need not have configured Git identity, signing or update hooks.
        self.command("config", "user.useConfigOnly", "true", cwd=self.repo)
        self.command("config", "commit.gpgsign", "true", cwd=self.repo)
        with patch.object(worker, "run_command", wraps=worker.run_command) as run:
            worker.prepare_source()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            [args for args in commands if args[1] == "fetch"],
            [
                [
                    self.git,
                    "fetch",
                    "--no-tags",
                    self.remote.as_uri(),
                    "refs/heads/alpha",
                ],
                [
                    self.git,
                    "fetch",
                    "--no-tags",
                    self.remote.as_uri(),
                    "refs/pull/7/head",
                ],
            ],
        )
        self.assertFalse(any("clone" in args or "init" in args for args in commands))
        merged = worker.job["commit"]
        self.assertEqual(
            self.command("show", "-s", "--format=%P", merged, cwd=self.repo).split(),
            [self.base, self.head],
        )
        self.assertEqual(
            self.command("show", f"{merged}:upstream.txt", cwd=self.repo), "latest base"
        )
        self.assertEqual(
            self.command("show", f"{merged}:feature.txt", cwd=self.repo), "PR content"
        )
        self.assertEqual(runtime.read_json(worker.job_path)["commit"], merged)
        self.assertEqual(
            (worker.source_stage / "shared.txt").read_text(), "PR content\n"
        )
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )
        self.assertEqual(self.command("status", "--porcelain", cwd=self.repo), "")
        self.assertFalse(worker.stopped)

    def test_worker_rejects_branch_or_pr_drift_before_merging(self):
        worker = self.worker()
        for ref, expected in (
            ("refs/heads/alpha", self.base),
            ("refs/pull/7/head", self.head),
        ):
            self.command("update-ref", ref, self.original)
            with self.assertRaisesRegex(ValueError, "远端版本已改变"):
                worker.prepare_source()
            self.command("update-ref", ref, expected)
            self.assertFalse(worker.source_stage.exists())
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )
        self.assertFalse(worker.stopped)

    def test_actual_conflict_is_reported_and_cleaned_without_shutdown(self):
        (self.remote / "shared.txt").write_text("new upstream conflict\n")
        self.command("add", ".")
        self.command("commit", "-m", "base diverges after GitHub mergeability check")
        self.base = self.command("rev-parse", "HEAD")
        worker = self.worker()
        with patch.object(worker, "stop_instances") as stop:
            worker.execute()
        stop.assert_not_called()
        status = runtime.read_json(worker.state / "status.json")
        self.assertEqual(status["status"], "failed")
        self.assertIn("PR #7", status["message"])
        self.assertIn("合并冲突", status["message"])
        self.assertIn("shared.txt", status["message"])
        self.assertFalse(worker.source_stage.exists())
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )
        self.assertEqual(self.command("status", "--porcelain", cwd=self.repo), "")
        self.assertNotIn(
            str(worker.source_stage),
            self.command("worktree", "list", "--porcelain", cwd=self.repo),
        )

    def test_cancel_after_stage_creation_cleans_up_without_shutdown(self):
        worker = self.worker()
        run = worker.run_command

        def cancel_before_merge(args, **kwargs):
            if "merge" in args:
                runtime.write_json(worker.state / "active/cancel.json", {})
            return run(args, **kwargs)

        with (
            patch.object(worker, "run_command", side_effect=cancel_before_merge),
            patch.object(worker, "stop_instances") as stop,
        ):
            worker.execute()
        stop.assert_not_called()
        self.assertEqual(
            runtime.read_json(worker.state / "status.json")["status"], "cancelled"
        )
        self.assertFalse(worker.source_stage.exists())
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )

    def test_final_merge_must_contain_recovery_module(self):
        self.command("switch", "-C", "feature", self.base)
        self.command("rm", "arknights_mower/utils/update_runtime.py")
        self.command("commit", "-m", "PR removes recovery module")
        self.head = self.command("rev-parse", "HEAD")
        self.pull["head"]["sha"] = self.head
        self.command("update-ref", "refs/pull/7/head", self.head)
        worker = self.worker()
        with self.assertRaisesRegex(ValueError, "实例恢复功能"):
            worker.prepare_source()
        self.assertFalse(worker.stopped)

    def test_lfs_is_downloaded_for_remote_commits_then_checked_out_in_stage(self):
        # An unavailable global LFS filter must not run while creating the
        # merge worktree. Actual LFS downloads and checkout are tested below.
        (self.remote / ".gitattributes").write_text("*.model filter=lfs -text\n")
        (self.remote / "fixture.model").write_text(
            "version https://git-lfs.github.com/spec/v1\noid sha256:"
            + "a" * 64
            + "\nsize 5\n"
        )
        self.command(
            "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false", "add", "."
        )
        self.command("commit", "-m", "base adds LFS resource")
        self.base = self.command("rev-parse", "HEAD")
        self.command(
            "config", "filter.lfs.process", "missing-lfs-filter", cwd=self.repo
        )
        self.command("config", "filter.lfs.required", "true", cwd=self.repo)
        worker = self.worker()
        run = worker.run_command
        commands = []

        def without_lfs(args, **kwargs):
            if args[1:2] == ["lfs"]:
                commands.append((args, kwargs.get("cwd")))
            else:
                return run(args, **kwargs)

        with (
            patch.object(worker, "target_uses_lfs", return_value=True),
            patch.object(worker, "run_command", side_effect=without_lfs),
        ):
            worker.prepare_source()
        self.assertEqual(
            commands,
            [
                ([self.git, "lfs", "version"], None),
                (
                    [
                        self.git,
                        "lfs",
                        "fetch",
                        self.remote.as_uri(),
                        self.base,
                        self.head,
                    ],
                    None,
                ),
                ([self.git, "lfs", "checkout"], worker.source_stage),
            ],
        )

    def test_multi_selection_rejected_before_network_and_old_single_request_works(self):
        app = Flask(__name__)
        app.token = "fixture"
        app.register_blueprint(software_update_bp)
        client = app.test_client()
        headers = {"token": "fixture", "X-Mower-Update": "1"}
        with patch.object(update, "source_repository") as source:
            for numbers in ([], [7, 8], [7, 7], [True], ["7"], 7, None):
                response = client.post(
                    "/software-update/source/pr/check",
                    json={"numbers": numbers},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json["ok"])
            source.assert_not_called()
        for selection in ({"number": 7}, {"numbers": [7]}):
            response = client.post(
                "/software-update/source/pr/check", json=selection, headers=headers
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["source_pr"], 7)
        plan = copy.deepcopy(update._checks[response.json["check_id"]])
        plan["source_prs"] = [{"number": 7}, {"number": 8}]
        with patch.object(update, "info") as info:
            with self.assertRaisesRegex(ValueError, "已取消多 PR"):
                update._start_job(plan)
            info.assert_not_called()
