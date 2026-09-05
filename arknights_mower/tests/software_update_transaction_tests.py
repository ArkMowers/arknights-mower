"""Local end-to-end source transactions with Git, venv, pip and npm.

No dependencies are downloaded: the fixture contains a stdlib launcher and
two locally generated test wheels. Git's origin is a temporary local directory.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker


@unittest.skipUnless(
    shutil.which("git") and shutil.which("npm"), "requires Git and npm"
)
class SourceTransactionTests(unittest.TestCase):
    def transaction(
        self,
        fail_build=False,
        local_changes=None,
        downgrade=False,
        external=False,
        uv=None,
        no_pip=False,
    ):
        with tempfile.TemporaryDirectory(prefix="mower-transaction-") as temporary:
            directory = Path(temporary)
            root, state = directory / "install", directory / "state"
            root.mkdir()
            git = shutil.which("git")
            base_python = getattr(sys, "_base_executable", sys.executable)

            def command(*args, cwd=root):
                return subprocess.check_output(
                    list(map(str, args)), cwd=cwd, stderr=subprocess.STDOUT, text=True
                ).strip()

            command(git, "init", "-b", "main")
            command(git, "config", "user.name", "Local update test")
            command(git, "config", "user.email", "mower-test@example.invalid")
            command(git, "config", "core.hooksPath", str(directory / "no-hooks"))
            (root / ".gitignore").write_text(
                ".venv/\nui/node_modules/\nui/dist/\n__pycache__/\n"
            )
            wheels = {}
            for number, version in (("1.0", "old"), ("2.0", "new")):
                wheel = directory / f"mower_update_fixture-{number}-py3-none-any.whl"
                metadata = f"mower_update_fixture-{number}.dist-info"
                files = {
                    "mower_update_fixture.py": f"VERSION = {version!r}\n",
                    f"{metadata}/METADATA": f"Metadata-Version: 2.1\nName: mower-update-fixture\nVersion: {number}\n",
                    f"{metadata}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                }
                files[f"{metadata}/RECORD"] = "".join(
                    f"{name},,\n" for name in [*files, f"{metadata}/RECORD"]
                )
                with zipfile.ZipFile(wheel, "w") as archive:
                    for name, content in files.items():
                        archive.writestr(name, content)
                wheels[version] = wheel
            (root / "requirements.in").write_text(
                "--no-index\n" + wheels["old"].as_uri() + "\n"
            )
            shutil.copy2(runtime.__file__, root / "update_runtime.py")
            (root / "arknights_mower/utils").mkdir(parents=True)
            shutil.copy2(
                runtime.__file__, root / "arknights_mower/utils/update_runtime.py"
            )
            (root / "webview_ui.py").write_text(
                "import os, sys, time\nfrom pathlib import Path\nimport update_runtime as r\n"
                f"r.state_dir = lambda: Path({str(state)!r})\n"
                f"r.installation_root = lambda: Path({str(root)!r})\n"
                "registration = r.RuntimeRegistration('instance', space=sys.argv[1], name=sys.argv[2], port=int(os.environ['MOWER_RESTART_PORT']), running=lambda: os.environ['MOWER_RESUME_RUN']=='1')\n"
                "registration.record.update(ready=True, fixture_version=Path('version.txt').read_text(), fixture_prefix=sys.prefix, fixture_dependency=__import__('mower_update_fixture').VERSION)\nregistration.publish()\n"
                "while not registration.shutdown_requested(): time.sleep(.05)\nregistration.close()\n",
                encoding="utf-8",
            )
            (root / "version.txt").write_text("old")
            ui = root / "ui"
            ui.mkdir()
            (ui / "package.json").write_text(
                json.dumps(
                    {
                        "name": "mower-update-fixture",
                        "version": "1.0.0",
                        "private": True,
                        "scripts": {"build": "node build.cjs"},
                    }
                )
            )
            build_script = "const fs = require('fs'); fs.mkdirSync('dist', {recursive:true}); fs.writeFileSync('dist/index.html','new');"
            (ui / "build.cjs").write_text(build_script)
            lockfile = {
                "name": "mower-update-fixture",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "packages": {"": {"name": "mower-update-fixture", "version": "1.0.0"}},
            }
            (ui / "package-lock.json").write_text(json.dumps(lockfile))
            command(git, "add", ".")
            command(git, "commit", "-m", "old version")
            old_commit = command(git, "rev-parse", "HEAD")
            (root / "version.txt").write_text("new")
            (root / "requirements.in").write_text(
                "--no-index\n" + wheels["new"].as_uri() + "\n"
            )
            (root / "new-target.txt").write_text("upstream file")
            if fail_build:
                (ui / "build.cjs").write_text("process.exit(2)")
            command(git, "add", ".")
            command(git, "commit", "-m", "new version")
            new_commit = command(git, "rev-parse", "HEAD")
            command(git, "init", "--bare", str(directory / "origin.git"))
            command(git, "remote", "add", "origin", str(directory / "origin.git"))
            command(git, "push", "origin", "HEAD:refs/heads/alpha")
            target_commit, initial_commit = (
                (old_commit, new_commit) if downgrade else (new_commit, old_commit)
            )
            target_version, initial_version = (
                ("old", "new") if downgrade else ("new", "old")
            )
            command(git, "switch", "-c", "original", initial_commit)
            if local_changes == "metadata":
                lockfile["packages"][""]["peer"] = True
                (ui / "package-lock.json").write_text(json.dumps(lockfile, indent=2))
            elif local_changes == "force":
                (root / "version.txt").write_text("local modification")
                command(git, "add", "version.txt")
                (ui / "package-lock.json").write_text("invalid local lockfile")
                (root / "new-target.txt").write_text("conflicting untracked file")
                (root / "local-note.txt").write_text("unrelated untracked file")
            environment = directory / "external python" if external else root / ".venv"
            command(
                base_python,
                "-m",
                "venv",
                *([] if external and not uv and not no_pip else ["--without-pip"]),
                str(environment),
            )
            python = environment / (
                "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
            )
            (environment / "old-marker").write_text("original environment")
            packages = Path(
                command(
                    python,
                    "-c",
                    "import sysconfig; print(sysconfig.get_path('purelib'))",
                )
            )
            with zipfile.ZipFile(wheels[initial_version]) as archive:
                archive.extractall(packages)
            (ui / "dist").mkdir()
            (ui / "dist/index.html").write_text("old")
            original = []
            replacements = []
            try:
                for index in range(3):
                    env = runtime.launch_environment(
                        {"port": 58300 + index, "running": index != 1}
                    )
                    process = subprocess.Popen(
                        [
                            str(python),
                            str(root / "webview_ui.py"),
                            f"data{index}",
                            f"local{index}",
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
                work = directory / "job"
                job = {
                    "id": "transaction",
                    "root": str(root),
                    "state_dir": str(state),
                    "deployment": "source",
                    "version": "alpha@" + target_commit[:7],
                    "background": True,
                    "force": local_changes == "force",
                    "git": git,
                    "npm": shutil.which("npm"),
                    "python": str(python),
                    "base_python": base_python,
                    "original_python": str(python),
                    "in_place_environment": external,
                    "venv_dir": str(environment),
                    "uv": uv,
                    "pip_available": not no_pip and not uv,
                    "commit": target_commit,
                    "ref": target_commit if downgrade else "refs/heads/alpha",
                    "operation": "source-version" if downgrade else "update",
                }
                runtime.write_json(work / "job.json", job)
                worker = Worker(work / "job.json")
                run_command = worker.run_command

                def run_without_lfs(args, **kwargs):
                    self.assertNotIn(
                        "lfs", args, "ordinary source updates must not require Git LFS"
                    )
                    if "ensurepip" in args:
                        self.assertTrue(
                            all(process.poll() is None for process in original)
                        )
                    return run_command(args, **kwargs)

                worker.run_command = run_without_lfs
                worker.env.update(
                    PIP_DISABLE_PIP_VERSION_CHECK="1",
                    npm_config_offline="true",
                    npm_config_audit="false",
                    npm_config_fund="false",
                )
                worker.execute()
                replacements = worker.new_processes + worker.recovery_processes
                deadline = time.monotonic() + 10
                while (
                    len(runtime.instances(state)) != 3 and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                records = sorted(runtime.instances(state), key=lambda row: row["name"])
                self.assertEqual(len(records), 3)
                self.assertEqual(
                    [row["running"] for row in records], [True, False, True]
                )
                status = runtime.read_json(state / "status.json")
                if fail_build:
                    self.assertEqual(status["status"], "failed")
                    self.assertEqual(command(git, "rev-parse", "HEAD"), initial_commit)
                    self.assertEqual(
                        command(git, "branch", "--show-current"), "original"
                    )
                    self.assertEqual((ui / "dist/index.html").read_text(), "old")
                    self.assertTrue((environment / "old-marker").exists())
                    self.assertTrue(
                        all(
                            row["fixture_version"] == initial_version for row in records
                        )
                    )
                else:
                    self.assertEqual(status["status"], "succeeded")
                    self.assertEqual(command(git, "rev-parse", "HEAD"), target_commit)
                    self.assertEqual((ui / "dist/index.html").read_text(), "new")
                    self.assertTrue(
                        all(row["fixture_version"] == target_version for row in records)
                    )
                if external:
                    self.assertTrue((environment / "old-marker").exists())
                    self.assertTrue(
                        all(
                            Path(row["fixture_prefix"]).resolve()
                            == environment.resolve()
                            for row in records
                        )
                    )
                    self.assertFalse((work / "runtime-0.backup/old-marker").exists())
                self.assertTrue(
                    all(
                        row["fixture_dependency"]
                        == (initial_version if fail_build else target_version)
                        for row in records
                    )
                )
                self.assertFalse((state / "active").exists())
                if local_changes:
                    self.assertEqual(
                        (ui / "package-lock.json").read_bytes(),
                        subprocess.check_output(
                            [git, "show", "HEAD:ui/package-lock.json"], cwd=root
                        ),
                    )
                    self.assertFalse((work / "local-files").exists())
                    self.assertFalse(command(git, "stash", "list"))
                if local_changes == "force":
                    self.assertEqual(
                        (root / "local-note.txt").read_text(),
                        "unrelated untracked file",
                    )
                    if not fail_build:
                        self.assertEqual(
                            (root / "new-target.txt").read_text(), "upstream file"
                        )
            finally:
                for record in runtime.instances(state):
                    runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
                for process in original + replacements:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
                deadline = time.monotonic() + 5
                while runtime.instances(state) and time.monotonic() < deadline:
                    time.sleep(0.05)

    def test_full_source_update_restores_three_instances(self):
        self.transaction()

    def test_build_failure_rolls_back_code_environment_and_ui(self):
        self.transaction(fail_build=True)

    def test_npm_metadata_update_restores_all_instances_without_backup(self):
        self.transaction(local_changes="metadata")

    def test_force_update_discards_local_edits_and_conflicting_untracked_files(self):
        self.transaction(local_changes="force")

    def test_force_failure_restores_version_but_not_discarded_local_edits(self):
        self.transaction(fail_build=True, local_changes="force")

    def test_switch_to_older_commit_restores_three_instances(self):
        self.transaction(downgrade=True)

    def test_external_environment_is_updated_without_moving_or_recreating(self):
        self.transaction(external=True)

    def test_external_environment_failure_restores_original_code_and_instances(self):
        self.transaction(external=True, fail_build=True)

    def test_environment_without_pip_or_uv_bootstraps_pip_before_shutdown(self):
        self.transaction(external=True, no_pip=True)

    @unittest.skipUnless(shutil.which("uv"), "requires uv")
    def test_uv_environment_without_pip_updates_using_same_interpreter(self):
        self.transaction(external=True, uv=shutil.which("uv"), downgrade=True)


if __name__ == "__main__":
    unittest.main()
