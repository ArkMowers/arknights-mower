import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import update_runtime as runtime
from manager import Api


class ManagerApiTests(unittest.TestCase):
    def test_instances_are_stored_at_explicit_writable_path(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            storage_path = Path(temporary_dir) / "nested" / "instances.json"
            api = Api(storage_path)

            api.add("default", "/tmp/mower-data")

            reloaded = Api(storage_path)
            self.assertEqual(
                reloaded.get_instances(),
                [{"name": "default", "path": "/tmp/mower-data"}],
            )

    def test_exited_instance_is_reaped_while_manager_stays_open(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            (root / "webview_ui.py").write_text("import sys\nsys.exit(0)\n")
            api = Api(root / "instances.json")
            api.add("reaping-fixture", str(root / "data"))
            children = []
            real_popen = subprocess.Popen

            def launch(*args, **kwargs):
                child = real_popen(*args, **kwargs)
                children.append(child)
                return child

            try:
                with (
                    patch.object(runtime, "active_job", return_value=False),
                    patch.object(runtime, "installation_root", return_value=root),
                    patch.object(subprocess, "Popen", side_effect=launch),
                ):
                    self.assertTrue(api.start(0)["ok"])
                child = children[0]
                deadline = time.monotonic() + 5
                # Do not poll/wait here: only the manager should reap the child.
                while child.returncode is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertEqual(child.returncode, 0)
                self.assertFalse(runtime.process_alive(child.pid))
                self.assertEqual(api.get_instances()[0]["name"], "reaping-fixture")
            finally:
                for child in children:
                    child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
