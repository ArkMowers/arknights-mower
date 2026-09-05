"""Source update preflight with installed tools and ordinary Git checkouts."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker, require_clean_source


class SourceToolTests(unittest.TestCase):
    def test_desktop_path_finds_homebrew_tools_without_requiring_lfs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".git").mkdir()
            original_path = "/usr/bin:/bin"
            selected = {}

            def which(name, path):
                self.assertIn("/opt/homebrew/bin", path.split(os.pathsep))
                self.assertEqual(path.split(os.pathsep)[:2], ["/usr/bin", "/bin"])
                selected[name] = True
                return {
                    "git": "/usr/bin/git",
                    "node": "/opt/homebrew/bin/node",
                    "npm": "/opt/homebrew/bin/npm",
                }.get(name)

            with (
                patch.dict(os.environ, {"PATH": original_path}),
                patch.object(sys, "platform", "darwin"),
                patch.object(sys, "prefix", str(root / ".venv")),
                patch.object(shutil, "which", side_effect=which),
                patch.object(
                    subprocess,
                    "check_output",
                    return_value="https://github.com/ArkMowers/arknights-mower.git\n",
                ),
            ):
                tools = update.source_tools(root)
                self.assertEqual(os.environ["PATH"], original_path)
            self.assertEqual(set(selected), {"git", "npm", "node"})
            self.assertEqual(tools["npm"], "/opt/homebrew/bin/npm")
            self.assertIn("/opt/homebrew/bin", tools["tool_path"])

    def test_non_macos_path_is_preserved(self):
        with (
            patch.object(sys, "platform", "linux"),
            patch.dict(os.environ, {"PATH": "/custom/bin:/usr/bin"}),
        ):
            self.assertEqual(update.source_tool_path(), "/custom/bin:/usr/bin")


@unittest.skipUnless(shutil.which("git"), "requires Git")
class SourceCheckoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.root = self.folder / "repo"
        self.root.mkdir()
        self.git = shutil.which("git")
        self.command("init", "-b", "alpha")
        self.command("config", "user.name", "Local source test")
        self.command("config", "user.email", "source-test@example.invalid")
        self.command("config", "core.hooksPath", str(self.folder / "no-hooks"))
        (self.root / "arknights_mower/utils").mkdir(parents=True)
        (self.root / "arknights_mower/utils/update_runtime.py").write_text(
            "# protocol fixture\n"
        )

    def command(self, *args):
        return subprocess.check_output(
            [self.git, *args], cwd=self.root, text=True, stderr=subprocess.STDOUT
        ).strip()

    def worker(self, attributes=None):
        if attributes is not None:
            (self.root / "assets").mkdir()
            (self.root / "assets/.gitattributes").write_text(attributes)
        self.command("add", ".")
        self.command("commit", "-m", "source fixture")
        self.command("remote", "add", "origin", str(self.root))
        self.commit = self.command("rev-parse", "HEAD")
        job_path = self.folder / "work/job.json"
        runtime.write_json(
            job_path,
            {
                "id": "preflight",
                "root": str(self.root),
                "state_dir": str(self.folder / "state"),
                "deployment": "source",
                "version": "alpha",
                "git": self.git,
                "commit": self.commit,
                "ref": "refs/heads/alpha",
                "background": True,
                "tool_path": "/tool-fixture/bin"
                + os.pathsep
                + os.environ.get("PATH", os.defpath),
            },
        )
        return Worker(job_path)

    def test_regular_checkout_fetches_without_any_lfs_command(self):
        worker = self.worker("# *.bin filter=lfs\n*.txt text\n")
        run_command = worker.run_command

        def without_lfs(args, **kwargs):
            self.assertNotIn("lfs", args)
            return run_command(args, **kwargs)

        worker.run_command = without_lfs
        worker.prepare_source()
        self.assertFalse(worker.needs_lfs)
        self.assertEqual(self.command("rev-parse", "HEAD"), self.commit)
        self.assertTrue(worker.env["PATH"].startswith("/tool-fixture/bin"))

    def test_missing_install_tools_fails_before_stopping_current_instances(self):
        worker = self.worker()
        worker.job.update(
            in_place_environment=True,
            python=sys.executable,
            pip_available=False,
            uv=None,
        )
        run_command = worker.run_command

        def command(args, **kwargs):
            if "ensurepip" in args:
                raise subprocess.CalledProcessError(1, args)
            return run_command(args, **kwargs)

        worker.run_command = command
        worker.stop_instances = Mock()
        worker.execute()
        worker.stop_instances.assert_not_called()
        self.assertIn(
            "当前实例尚未停止",
            runtime.read_json(worker.state / "status.json")["message"],
        )

    def test_uv_installation_explicitly_targets_the_current_interpreter(self):
        worker = self.worker()
        worker.job.update(uv="/tools/uv", python="/custom/环境/python.exe")
        worker.run_command = Mock()
        worker.install_dependencies()
        self.assertEqual(
            worker.run_command.call_args.args[0],
            [
                "/tools/uv",
                "pip",
                "install",
                "--python",
                "/custom/环境/python.exe",
                "-r",
                "requirements.in",
            ],
        )

    def test_lfs_target_is_rejected_before_stopping_instances_when_lfs_missing(self):
        worker = self.worker("*.model filter=lfs diff=lfs merge=lfs -text\n")
        run_command = worker.run_command

        def missing_lfs(args, **kwargs):
            if args[1:3] == ["lfs", "version"]:
                raise subprocess.CalledProcessError(1, args)
            return run_command(args, **kwargs)

        worker.run_command = missing_lfs
        worker.stop_instances = Mock()
        worker.execute()
        worker.stop_instances.assert_not_called()
        status = runtime.read_json(worker.state / "status.json")
        self.assertEqual(status["status"], "failed")
        self.assertIn("目标版本使用 Git LFS", status["message"])
        self.assertEqual(self.command("rev-parse", "HEAD"), self.commit)

    def test_dirty_checkout_reports_files_and_leaves_them_untouched(self):
        self.worker()
        changed = self.root / "arknights_mower/utils/update_runtime.py"
        changed.write_text("# local edit\n")
        untracked = self.root / "user-note.txt"
        untracked.write_text("keep me")
        with self.assertRaises(ValueError) as caught:
            require_clean_source(self.git, self.root)
        self.assertIn("arknights_mower/utils/update_runtime.py", str(caught.exception))
        self.assertIn("user-note.txt", str(caught.exception))
        self.assertEqual(changed.read_text(), "# local edit\n")
        self.assertEqual(untracked.read_text(), "keep me")

    def test_custom_environment_files_do_not_block_but_tracked_edits_do(self):
        self.worker()
        environment = self.root / "python environments/custom name"
        environment.mkdir(parents=True)
        (environment / "pyvenv.cfg").write_text("# active runtime")
        (environment / "library.py").write_text("# generated dependency")
        require_clean_source(self.git, self.root, environment=str(environment))
        (environment.parent / "user-note.txt").write_text("keep me")
        with self.assertRaisesRegex(ValueError, "python environments"):
            require_clean_source(self.git, self.root, environment=str(environment))
        (environment.parent / "user-note.txt").unlink()
        self.command("add", ".")
        self.command("commit", "-m", "tracked fixture environment")
        (environment / "library.py").write_text("# tracked edit")
        with self.assertRaisesRegex(ValueError, "library.py"):
            require_clean_source(self.git, self.root, environment=str(environment))

    def test_gitignore_excludes_generated_files_but_not_tracked_source_edits(self):
        self.worker()
        (self.root / ".gitignore").write_text(
            "generated/\narknights_mower/utils/update_runtime.py\n"
        )
        self.command("add", ".gitignore")
        self.command("commit", "-m", "ignore generated output")
        (self.root / "generated").mkdir()
        (self.root / "generated/log.txt").write_text("generated output")
        require_clean_source(self.git, self.root)
        (self.root / "arknights_mower/utils/update_runtime.py").write_text(
            "# tracked local change"
        )
        with self.assertRaisesRegex(ValueError, "update_runtime.py"):
            require_clean_source(self.git, self.root)

    def test_restarted_instance_inherits_detected_tool_path(self):
        worker = self.worker()
        worker.command_for = Mock(return_value=[sys.executable, "launcher.py"])
        with patch.object(subprocess, "Popen") as start:
            worker.restart([{"kind": "instance", "name": "fixture"}], verify=False)
        self.assertEqual(start.call_args.kwargs["env"]["PATH"], worker.env["PATH"])

    def lockfile_fixture(self):
        (self.root / "ui").mkdir()
        self.lockfile = self.root / "ui/package-lock.json"
        self.lock_data = {
            "lockfileVersion": 2,
            "packages": {
                "": {"name": "fixture", "dependencies": {"peer": "1.0.0"}},
                "node_modules/peer": {
                    "version": "1.0.0",
                    "resolved": "https://registry.example.invalid/peer.tgz",
                    "integrity": "fixture-digest",
                    "dependencies": {"peer": "1.0.0"},
                },
            },
            "dependencies": {"peer": {"version": "1.0.0"}},
        }
        self.lockfile.write_text(json.dumps(self.lock_data))
        (self.root / "ui/package.json").write_text('{"name":"fixture"}')
        return self.worker()

    def test_npm_metadata_and_formatting_do_not_block_or_rewrite_on_check(self):
        worker = self.lockfile_fixture()
        self.lock_data["packages"]["node_modules/peer"].update(peer=True, license="MIT")
        self.lock_data["dependencies"]["peer"]["peer"] = True
        self.lockfile.write_text(json.dumps(self.lock_data, indent=2) + "\n")
        original = self.lockfile.read_bytes()
        generated = require_clean_source(self.git, self.root)
        self.assertEqual(generated["ui/package-lock.json"][0], original)
        worker.prepare_source()
        self.assertEqual(self.lockfile.read_bytes(), original)

    def test_real_dependency_changes_still_block_regular_update(self):
        self.lockfile_fixture()
        package = self.lock_data["packages"]["node_modules/peer"]
        for key, value in (
            ("version", "2.0.0"),
            ("resolved", "https://other.example.invalid/peer.tgz"),
            ("integrity", "changed-digest"),
            ("dependencies", {"peer": "2.0.0"}),
        ):
            with self.subTest(key=key):
                original = package[key]
                package[key] = value
                self.lockfile.write_text(json.dumps(self.lock_data))
                with self.assertRaisesRegex(ValueError, "package-lock.json"):
                    require_clean_source(self.git, self.root)
                require_clean_source(self.git, self.root, force=True)
                package[key] = original

    def test_staged_lock_changes_and_invalid_json_require_force(self):
        self.lockfile_fixture()
        self.lock_data["packages"]["node_modules/peer"]["peer"] = True
        self.lockfile.write_text(json.dumps(self.lock_data))
        self.command("add", "ui/package-lock.json")
        with self.assertRaisesRegex(ValueError, "package-lock.json"):
            require_clean_source(self.git, self.root)
        require_clean_source(self.git, self.root, force=True)
        self.command("reset", "HEAD", "--", "ui/package-lock.json")
        self.lockfile.write_text('{"invalid":')
        with self.assertRaisesRegex(ValueError, "package-lock.json"):
            require_clean_source(self.git, self.root)

    def test_force_only_bypasses_local_changes_not_git_errors(self):
        self.worker()
        (self.root / "local.txt").write_text("local file")
        require_clean_source(self.git, self.root, force=True)
        with self.assertRaises(subprocess.CalledProcessError):
            require_clean_source(self.git, self.folder, force=True)

    def test_info_only_allows_force_to_bypass_source_changes(self):
        self.worker()
        (self.root / "local.txt").write_text("local edit")
        with (
            patch.object(runtime, "installation_root", return_value=self.root),
            patch.object(runtime, "state_dir", return_value=self.folder / "state"),
            patch.object(runtime, "frozen", return_value=False),
            patch.object(
                runtime,
                "instances",
                return_value=[
                    {
                        "pid": os.getpid(),
                        "kind": "instance",
                        "name": "fixture",
                        "running": False,
                    }
                ],
            ) as instances,
            patch.object(
                update, "source_tools", return_value={"git": self.git}
            ) as tools,
        ):
            info = update.info()
            self.assertTrue(info["force_supported"])
            self.assertIn("local.txt", info["source_changes"])
            self.assertTrue(info["blockers"])
            instances.return_value = []
            self.assertFalse(update.info()["force_supported"])
            tools.side_effect = ValueError("missing npm")
            self.assertFalse(update.info()["force_supported"])

    def test_current_source_version_can_only_be_reinstalled_with_explicit_force(self):
        self.worker()
        with (
            patch.object(runtime, "installation_root", return_value=self.root),
            patch.object(runtime, "state_dir", return_value=self.folder / "state"),
            patch.object(runtime, "frozen", return_value=False),
            patch.object(
                update,
                "github",
                return_value={"sha": self.commit, "commit": {"message": "fixture"}},
            ),
            patch.object(update.network_settings, "apply_http_proxy"),
            patch.dict(update._checks, {}, clear=True),
            patch.object(update, "start_job") as start,
        ):
            result = update.check("dev", proxy="")
            self.assertFalse(result["available"])
            self.assertTrue(result["check_id"])
            with self.assertRaisesRegex(ValueError, "没有可用更新"):
                update.submit(result["check_id"])
            start.assert_not_called()
            update.submit(result["check_id"], force=True)
            self.assertTrue(start.call_args.kwargs["force"])
