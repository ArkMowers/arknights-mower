"""API-only PR checks and incremental installation of GitHub's test merge."""

import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from flask import Flask

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import UpdateCancelled, Worker
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
        (self.remote / "arknights_mower/utils").mkdir(parents=True)
        (self.remote / "arknights_mower/utils/update_runtime.py").write_text(
            "# fixture\n"
        )
        self.command("add", ".")
        self.command("commit", "-m", "original")
        self.original = self.command("rev-parse", "HEAD")
        self.command("clone", "--template=", str(self.remote), str(self.repo))
        self.command("switch", "-c", "feature")
        (self.remote / "feature.txt").write_text("PR content\n")
        self.command("add", ".")
        self.command("commit", "-m", "PR")
        self.head = self.command("rev-parse", "HEAD")
        self.command("switch", "alpha")
        (self.remote / "upstream.txt").write_text("latest base\n")
        self.command("add", ".")
        self.command("commit", "-m", "target advances")
        self.base = self.command("rev-parse", "HEAD")
        # Only the simulated server creates a merge. Mower must just fetch it.
        self.command("switch", "--detach")
        self.command("merge", "--no-ff", "--no-edit", self.head)
        self.merge = self.command("rev-parse", "HEAD")
        self.command("update-ref", "refs/pull/7/merge", self.merge)
        self.pull = {
            "number": 7,
            "title": "Feature",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "mergeable_state": "blocked",  # CI/review not required.
            "merge_commit_sha": self.merge,
            "head": {"sha": self.head},
            "base": {"ref": "alpha", "sha": self.original},  # Stale snapshot.
        }
        self.commit = {
            "sha": self.merge,
            "message": "GitHub test merge",
            "parents": [{"sha": self.base}, {"sha": self.head}],
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
        if path == "/git/commits/" + self.merge:
            return self.commit
        if (
            path
            == "/contents/arknights_mower/utils/update_runtime.py?ref=" + self.merge
        ):
            return {"type": "file"}
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
        return Worker(path)

    def test_preview_uses_only_api_and_pins_latest_base_plus_head(self):
        with patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("No Git downloads during preview"),
        ):
            checked = self.check()
        plan = update._checks[checked["check_id"]]
        self.assertEqual(plan["source_pr"], 7)
        self.assertEqual(plan["ref"], "refs/pull/7/merge")
        self.assertEqual(plan["base_commit"], self.base)
        self.assertEqual(plan["head_commit"], self.head)
        self.assertEqual(checked["sha"], self.merge)
        self.assertNotIn("source_prs", plan)
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )

    def test_stale_or_missing_merge_is_pending_not_a_conflict(self):
        for parents in (
            [],
            [{"sha": self.original}, {"sha": self.head}],
            [{"sha": self.base}, {"sha": self.original}],
        ):
            with patch.dict(self.commit, {"parents": parents}):
                with self.assertRaisesRegex(ValueError, "正在准备.*稍后重新检查"):
                    self.check()
        with patch.dict(self.pull, {"merge_commit_sha": None}):
            with self.assertRaisesRegex(ValueError, "正在准备"):
                self.check()
        self.assertFalse(update._checks)
        # No stale result is cached; the next check succeeds when GitHub is ready.
        self.assertEqual(self.check()["sha"], self.merge)

    def test_missing_merge_object_and_missing_runtime_have_clear_errors(self):
        real_api = self.github
        for endpoint, message in (
            ("/git/commits/", "正在准备"),
            ("/contents/", "实例恢复模块"),
        ):

            def api(path, *args, **kwargs):
                if path.startswith(endpoint):
                    response = requests.Response()
                    response.status_code = 404
                    raise requests.HTTPError(response=response)
                return real_api(path, *args, **kwargs)

            with patch.object(update, "github", side_effect=api):
                with self.assertRaisesRegex(ValueError, message):
                    self.check()
            self.assertFalse(update._checks)

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
        # A new valid merge after the target branch advances still needs confirmation.
        with (
            patch.object(self, "base", self.original),
            patch.dict(
                self.commit,
                {
                    "parents": [{"sha": self.original}, {"sha": self.head}],
                },
            ),
            patch.object(update, "info") as info,
        ):
            with self.assertRaisesRegex(ValueError, "已改变"):
                update._start_job(plan)
            info.assert_not_called()

    def test_worker_fetches_merge_into_existing_repo_without_merging_or_shutdown(self):
        worker = self.worker()
        with patch.object(worker, "run_command", wraps=worker.run_command) as run:
            worker.prepare_source()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            commands,
            [
                [
                    self.git,
                    "fetch",
                    "--no-tags",
                    self.remote.as_uri(),
                    "refs/pull/7/merge",
                ]
            ],
        )
        self.assertEqual(
            self.command("rev-parse", "FETCH_HEAD", cwd=self.repo), self.merge
        )
        self.assertEqual(
            self.command("show", f"{self.merge}:upstream.txt", cwd=self.repo),
            "latest base",
        )
        self.assertEqual(
            self.command("show", f"{self.merge}:feature.txt", cwd=self.repo),
            "PR content",
        )
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )
        self.assertFalse(worker.stopped)
        runtime.write_json(self.home / "state/active/cancel.json", {})
        with self.assertRaises(UpdateCancelled):
            worker.prepare_source()
        self.assertFalse(worker.stopped)

    def test_worker_rejects_ref_drift_or_wrong_parents_before_stopping(self):
        worker = self.worker()
        self.command("update-ref", "refs/pull/7/merge", self.head)
        with self.assertRaisesRegex(ValueError, "远端版本已改变"):
            worker.prepare_source()
        self.command("update-ref", "refs/pull/7/merge", self.merge)
        worker.job["head_commit"] = self.original
        with self.assertRaisesRegex(ValueError, "合并结果已改变"):
            worker.prepare_source()
        self.assertEqual(
            self.command("rev-parse", "HEAD", cwd=self.repo), self.original
        )
        self.assertFalse(worker.stopped)

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
