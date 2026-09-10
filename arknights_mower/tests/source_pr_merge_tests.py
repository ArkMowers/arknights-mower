"""Real Git coverage for combined PR previews and worker preparation."""

import copy
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import UpdateCancelled, Worker
from arknights_mower.utils.source_pr_merge import merge_source_pulls


class SourcePullMergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mower-组合 PR 中文 ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.repo = self.home / "repository"
        self.repo.mkdir()
        self.git = shutil.which("git")
        self.assertIsNotNone(self.git, "Git is required")
        self.command("init", "-b", "alpha")
        self.command("config", "user.name", "Fixture")
        self.command("config", "user.email", "fixture@example.invalid")
        self.command("config", "core.hooksPath", str(self.home / "hooks"))
        (self.repo / "arknights_mower/utils").mkdir(parents=True)
        (self.repo / "arknights_mower/utils/update_runtime.py").write_text(
            "# fixture\n"
        )
        (self.repo / "shared.txt").write_text("base\n")
        self.command("add", ".")
        self.command("commit", "-m", "base")
        self.base = self.command("rev-parse", "HEAD")
        self.pulls = []
        for number, filename, content in (
            (1, "shared.txt", "one\n"),
            (2, "second.txt", "two\n"),
            (3, "shared.txt", "conflict\n"),
        ):
            self.command("checkout", "--detach", self.base)
            (self.repo / filename).write_text(content)
            self.command("add", ".")
            self.command("commit", "-m", f"PR {number}")
            sha = self.command("rev-parse", "HEAD")
            self.command("update-ref", f"refs/pull/{number}/head", sha)
            self.pulls.append({"number": number, "sha": sha, "title": f"PR {number}"})
        self.command("checkout", "alpha")
        self.plan = {
            "source_branch": "alpha",
            "base_commit": self.base,
            "source_prs": self.pulls[:2],
            "merge_date": "@1700000000 +0000",
        }

    def command(self, *args, cwd=None):
        return subprocess.check_output(
            [self.git, *args],
            cwd=cwd or self.repo,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        ).strip()

    def merge(self, plan=None, name="preview", **kwargs):
        return merge_source_pulls(
            self.git,
            str(self.repo),
            plan or self.plan,
            self.home / name,
            os.environ,
            **kwargs,
        )

    def test_combination_is_reproducible_and_includes_both_changes(self):
        sha = self.merge()
        self.assertEqual(self.merge(name="worker"), sha)
        self.assertEqual(
            self.command("show", f"{sha}:shared.txt", cwd=self.home / "preview"), "one"
        )
        self.assertEqual(
            self.command("show", f"{sha}:second.txt", cwd=self.home / "preview"), "two"
        )
        self.assertEqual(self.command("rev-parse", "HEAD"), self.base)
        self.assertEqual(self.command("status", "--porcelain"), "")

    def test_conflicts_and_changed_heads_do_not_touch_running_checkout(self):
        plan = {**self.plan, "source_prs": [self.pulls[0], self.pulls[2]]}
        with self.assertRaisesRegex(ValueError, "PR #3.*合并冲突"):
            self.merge(plan)
        self.command("update-ref", "refs/pull/2/head", self.base)
        with self.assertRaisesRegex(ValueError, "已改变"):
            self.merge(name="moved")
        self.assertEqual(self.command("rev-parse", "HEAD"), self.base)
        self.assertEqual(self.command("status", "--porcelain"), "")

    def test_changed_base_is_rejected(self):
        self.command("update-ref", "refs/heads/alpha", self.pulls[0]["sha"])
        with self.assertRaisesRegex(ValueError, "已改变"):
            self.merge()

    def worker(self, commit):
        path = self.home / "work/job.json"
        runtime.write_json(
            path,
            {
                **self.plan,
                "id": "combined",
                "root": str(self.repo),
                "state_dir": str(self.home / "state"),
                "deployment": "source",
                "operation": "source-pr",
                "version": "combined",
                "git": self.git,
                "source_url": str(self.repo),
                "commit": commit,
            },
        )
        return Worker(path)

    def test_worker_recreates_checked_merge_before_shutdown_and_can_cancel(self):
        commit = self.merge()
        worker = self.worker(commit)
        worker.prepare_source()
        self.assertEqual(self.command("rev-parse", "FETCH_HEAD"), commit)
        self.assertEqual(self.command("rev-parse", "HEAD"), self.base)
        self.assertFalse(worker.stopped)
        runtime.write_json(self.home / "state/active/cancel.json", {})
        with self.assertRaises(UpdateCancelled):
            worker.prepare_source()
        self.assertEqual(self.command("rev-parse", "HEAD"), self.base)
        self.assertFalse(worker.stopped)

    def test_api_pins_combination_and_rechecks_each_pr_before_instance_scan(self):
        selected = {"source_repo": "personal/mower", "source_url": str(self.repo)}
        api_pulls = {
            pull["number"]: {
                "head": {"sha": pull["sha"]},
                "base": {"ref": "alpha", "sha": self.base},
                "title": pull["title"],
            }
            for pull in self.pulls
        }
        with (
            patch.object(
                update, "source_repository", return_value=(self.base, "alpha", "")
            ),
            patch.object(update, "resolve_source_remote", return_value=selected),
            patch.object(
                update,
                "mergeable_source_pull",
                side_effect=lambda number, *_: api_pulls[number],
            ),
            patch.dict(update._checks, {}, clear=True),
        ):
            result = update.check_source_pulls([1, 2], "personal/mower")
            plan = update._checks[result["check_id"]]
            self.assertEqual([p["number"] for p in plan["source_prs"]], [1, 2])
            self.assertEqual(result["sha"], plan["commit"])
            for number in (1, 2):
                original = copy.deepcopy(api_pulls[number])
                api_pulls[number]["head"]["sha"] = self.base
                with (
                    patch.object(update, "info") as info,
                    self.assertRaisesRegex(ValueError, "已改变"),
                ):
                    update._start_job(plan)
                info.assert_not_called()
                api_pulls[number] = original
            api_pulls[2]["base"]["ref"] = "other"
            with self.assertRaisesRegex(ValueError, "同一目标分支"):
                update.check_source_pulls([1, 2])

    def test_invalid_selection_does_not_start_network_or_git(self):
        with patch.object(update, "source_repository") as source:
            for numbers in ([], [1, 1], [True, 2], [1, "2"], list(range(1, 12))):
                with self.subTest(numbers=numbers), self.assertRaises(ValueError):
                    update.check_source_pulls(numbers)
            source.assert_not_called()
