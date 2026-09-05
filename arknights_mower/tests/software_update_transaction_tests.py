"""Local end-to-end source transactions with Git, venv, pip and npm.

No dependencies are downloaded: the fixture contains only a stdlib launcher and
an empty requirements.in. Git's origin is another temporary local directory.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker


@unittest.skipUnless(
    shutil.which("git") and shutil.which("npm"), "requires Git and npm"
)
class SourceTransactionTests(unittest.TestCase):
    def transaction(self, fail_build=False):
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
            (root / "requirements.in").write_text("# No third party dependencies\n")
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
                "registration.record.update(ready=True, fixture_version=Path('version.txt').read_text())\nregistration.publish()\n"
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
            command(git, "add", ".")
            command(git, "commit", "-m", "old version")
            old_commit = command(git, "rev-parse", "HEAD")
            (root / "version.txt").write_text("new")
            if fail_build:
                (ui / "build.cjs").write_text("process.exit(2)")
            command(git, "add", ".")
            command(git, "commit", "-m", "new version")
            new_commit = command(git, "rev-parse", "HEAD")
            command(git, "init", "--bare", str(directory / "origin.git"))
            command(git, "remote", "add", "origin", str(directory / "origin.git"))
            command(git, "push", "origin", "HEAD:refs/heads/alpha")
            command(git, "switch", "-c", "original", old_commit)
            command(base_python, "-m", "venv", "--without-pip", str(root / ".venv"))
            python = root / (
                ".venv/Scripts/python.exe"
                if sys.platform == "win32"
                else ".venv/bin/python"
            )
            (root / ".venv/old-marker").write_text("original environment")
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
                    "version": "alpha@" + new_commit[:7],
                    "background": True,
                    "git": git,
                    "npm": shutil.which("npm"),
                    "python": str(python),
                    "base_python": base_python,
                    "commit": new_commit,
                    "ref": "refs/heads/alpha",
                }
                runtime.write_json(work / "job.json", job)
                worker = Worker(work / "job.json")
                run_command = worker.run_command

                def run_without_lfs(args, **kwargs):
                    self.assertNotIn(
                        "lfs", args, "ordinary source updates must not require Git LFS"
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
                    self.assertEqual(command(git, "rev-parse", "HEAD"), old_commit)
                    self.assertEqual(
                        command(git, "branch", "--show-current"), "original"
                    )
                    self.assertEqual((ui / "dist/index.html").read_text(), "old")
                    self.assertTrue((root / ".venv/old-marker").exists())
                    self.assertTrue(
                        all(row["fixture_version"] == "old" for row in records)
                    )
                else:
                    self.assertEqual(status["status"], "succeeded")
                    self.assertEqual(command(git, "rev-parse", "HEAD"), new_commit)
                    self.assertEqual((ui / "dist/index.html").read_text(), "new")
                    self.assertTrue(
                        all(row["fixture_version"] == "new" for row in records)
                    )
                self.assertFalse((state / "active").exists())
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


if __name__ == "__main__":
    unittest.main()
