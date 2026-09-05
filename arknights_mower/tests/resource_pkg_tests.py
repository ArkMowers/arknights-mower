import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from arknights_mower import __rootdir__
from arknights_mower.utils import path as mower_path
from arknights_mower.utils import resource_pkg as rp
from arknights_mower.utils.res_version import (
    RES_PACKAGE_DATA,
    RES_PACKAGE_DIRS,
    RES_PACKAGE_MODELS,
)
from arknights_mower.utils.resource_store import (
    compatibility_error,
    read_index,
    resource_newer,
)
from build_assets import _collect_arknights_mower_datas


def resource_zip(version="v2026.08.23-aaaaaaa", *, manifest=None, remove=None):
    files = {name: "{}" for name in (*RES_PACKAGE_DATA, *RES_PACKAGE_MODELS)}
    files.update({name + "/x.webp": "WEBP" for name in RES_PACKAGE_DIRS})
    files[rp._RESOURCE_MARKER] = json.dumps(
        {"res_version": version, **(manifest or {})}
    )
    if remove:
        files.pop(remove)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class ResourcePkgTestBase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.overlay = self.base / "resources"
        self.builtin = self.base / "builtin"
        (self.builtin / "data").mkdir(parents=True)
        (self.builtin / "data/version.json").write_text(
            '{"res_version":"v2026.08.22-0000000"}'
        )
        self.legacy = self.base / "instance/tmp/resource"
        self.shared_legacy = self.base / "tmp/resource"
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, value in {
            "RESOURCE_OVERLAY": self.overlay,
            "_STAGING": self.overlay / ".staging",
            "_INSTALL_LOCK_PATH": self.overlay / "install.lock",
            "_LEGACY_RESOURCE_OVERLAY": self.legacy,
            "_LEGACY_SHARED_RESOURCE_OVERLAY": self.shared_legacy,
            "__rootdir__": self.builtin,
            "__version__": "4.2.0",
            "_active_resource": None,
            "_task_owner": None,
            "_loaded_resource_signature": None,
            "_rejected_resource_signature": None,
        }.items():
            stack.enter_context(patch.object(rp, name, value))
        self.reload_caches = stack.enter_context(
            patch.object(rp, "reload_resource_caches")
        )

    def installed_version(self):
        return json.loads(rp.resource_pkg_path(rp._RESOURCE_MARKER).read_text())[
            "res_version"
        ]


class TestSharedResourceScope(unittest.TestCase):
    def test_overlay_is_persistent_and_shared(self):
        with patch.object(mower_path, "global_space", "instance-a"):
            shared = mower_path.get_path("@app/resources", space="")
            instance = mower_path.get_path("@app/resources")
        self.assertEqual(rp.RESOURCE_OVERLAY, shared)
        self.assertNotEqual(shared, instance)

    def test_pyinstaller_collects_builtin_version(self):
        collected = {
            Path(source).relative_to(Path(__rootdir__).parent).as_posix()
            for source, _ in _collect_arknights_mower_datas()
        }
        self.assertIn("arknights_mower/data/version.json", collected)


class TestInstallResourcePkg(ResourcePkgTestBase):
    def test_valid_install_selects_complete_persistent_package(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        selected = rp.resource_pkg_path(rp._RESOURCE_MARKER)
        self.assertTrue(selected.is_relative_to(self.overlay / "packages"))
        self.assertEqual(self.installed_version(), "v2026.08.23-aaaaaaa")
        self.assertTrue(rp.resource_ui_path("depot/x.webp").is_file())
        self.assertTrue(
            rp.resource_ui_path(
                "pages/basement_skill/skill.json", source=True
            ).is_file()
        )
        self.assertFalse(rp._STAGING.exists())
        self.reload_caches.assert_called_once_with()

    def test_incomplete_invalid_and_incompatible_packages_are_rejected(self):
        for package in [
            resource_zip(remove=rp._RESOURCE_MARKER),
            resource_zip(remove=RES_PACKAGE_DATA[0]),
            resource_zip(manifest={"schema_version": 2}),
            resource_zip(manifest={"mower_version": ">=5"}),
        ]:
            with self.subTest(package_size=len(package)):
                self.assertFalse(rp.install_resource_pkg(package))
                self.assertEqual(read_index(self.overlay), [])
        self.reload_caches.assert_not_called()

    def test_bad_path_is_rejected(self):
        package = io.BytesIO(resource_zip())
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("../outside", "fixture")
        self.assertFalse(rp.install_resource_pkg(package.getvalue()))
        self.assertFalse((self.base / "outside").exists())

    def test_older_package_cannot_override_newer_builtin(self):
        self.assertFalse(rp.install_resource_pkg(resource_zip("v2026.08.21-aaaaaaa")))
        self.assertEqual(self.installed_version(), "v2026.08.22-0000000")

    def test_updates_retain_old_generation(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        previous = rp.resource_pkg_path(rp._RESOURCE_MARKER)
        self.assertTrue(rp.install_resource_pkg(resource_zip("v2026.08.24-bbbbbbb")))
        self.assertEqual(self.installed_version(), "v2026.08.24-bbbbbbb")
        self.assertIn("v2026.08.23-aaaaaaa", previous.read_text())
        self.assertEqual(len(read_index(self.overlay)), 2)

    def test_new_software_prefers_newer_builtin_as_a_whole(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        (self.builtin / "data/version.json").write_text(
            '{"res_version":"v2026.08.25-ccccccc"}'
        )
        self.assertTrue(rp.reload_resource_caches_if_changed())
        self.assertEqual(self.installed_version(), "v2026.08.25-ccccccc")
        self.assertEqual(
            rp.resource_pkg_path(RES_PACKAGE_MODELS[0]),
            self.builtin / "models/NORMAL.pkl",
        )
        self.assertIsNone(rp.resource_ui_path("depot/x.webp"))
        self.assertTrue(read_index(self.overlay))

    def test_missing_overlay_image_does_not_mix_in_builtin_image(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        missing = rp.resource_pkg_path("ui/public/depot/missing.webp")
        self.assertTrue(missing.is_relative_to(self.overlay / "packages"))
        self.assertFalse(missing.exists())

    def test_reload_failure_restores_index_and_previous_selection(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        before = (self.overlay / "index.json").read_bytes()
        self.reload_caches.reset_mock()
        self.reload_caches.side_effect = [RuntimeError("bad models"), None]
        self.assertFalse(rp.install_resource_pkg(resource_zip("v2026.08.24-bbbbbbb")))
        self.assertEqual((self.overlay / "index.json").read_bytes(), before)
        self.assertEqual(self.installed_version(), "v2026.08.23-aaaaaaa")
        self.assertEqual(self.reload_caches.call_count, 2)

    def test_pointer_write_failure_leaves_current_generation(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        with patch.object(rp, "_write_index", side_effect=OSError("disk full")):
            self.assertFalse(
                rp.install_resource_pkg(resource_zip("v2026.08.24-bbbbbbb"))
            )
        self.assertEqual(self.installed_version(), "v2026.08.23-aaaaaaa")

    def test_running_instance_pins_resource_until_task_boundary(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        previous = rp.resource_pkg_path(rp._RESOURCE_MARKER)
        self.reload_caches.reset_mock()
        with rp.resource_task_session():
            results = []

            def publish_from_web_thread():
                results.append(
                    rp.install_resource_pkg(resource_zip("v2026.08.24-bbbbbbb"))
                )
                results.append(rp.reload_resource_caches_if_changed())

            thread = threading.Thread(target=publish_from_web_thread)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results, [True, False])
            self.assertEqual(rp.resource_pkg_path(rp._RESOURCE_MARKER), previous)
            self.reload_caches.assert_not_called()
            self.assertTrue(rp.reload_resource_caches_if_changed())
            self.assertFalse(rp.reload_resource_caches_if_changed())
            self.assertEqual(self.installed_version(), "v2026.08.24-bbbbbbb")
        self.reload_caches.assert_called_once()
        self.assertTrue(previous.is_file())
        self.assertIsNone(rp._task_owner)

    def test_migration_copies_old_shared_and_keeps_original(self):
        with zipfile.ZipFile(io.BytesIO(resource_zip())) as archive:
            archive.extractall(self.shared_legacy)
        self.assertTrue(rp.migrate_legacy_resource_overlay())
        self.assertEqual(self.installed_version(), "v2026.08.23-aaaaaaa")
        self.assertTrue((self.shared_legacy / rp._RESOURCE_MARKER).is_file())
        self.assertFalse(rp.migrate_legacy_resource_overlay())

    def test_migration_can_use_legacy_instance_directory(self):
        with zipfile.ZipFile(io.BytesIO(resource_zip())) as archive:
            archive.extractall(self.legacy)
        self.assertTrue(rp.migrate_legacy_resource_overlay())
        self.assertEqual(self.installed_version(), "v2026.08.23-aaaaaaa")

    def test_file_lock_is_exclusive_and_released(self):
        with rp._resource_install_guard():
            with self.assertRaises(TimeoutError):
                with rp._resource_install_guard(timeout=0):
                    pass
        with rp._resource_install_guard(timeout=0):
            pass

    def test_three_processes_switch_independently_at_task_boundaries(self):
        self.assertTrue(rp.install_resource_pkg(resource_zip()))
        script = f"""
import json, sys
from pathlib import Path
from arknights_mower.utils import resource_pkg as rp
rp.RESOURCE_OVERLAY = Path({str(self.overlay)!r})
rp._STAGING = rp.RESOURCE_OVERLAY / '.staging'
rp._INSTALL_LOCK_PATH = rp.RESOURCE_OVERLAY / 'install.lock'
rp.__rootdir__ = Path({str(self.builtin)!r})
rp._active_resource = None
rp._loaded_resource_signature = None
def report():
    path = rp.resource_pkg_path(rp._RESOURCE_MARKER)
    print('RESOURCE_TEST ' + json.dumps({{'version': json.loads(path.read_text())['res_version'], 'path': str(path)}}), flush=True)
with rp.resource_task_session():
    report()
    for command in sys.stdin:
        if command.strip() == 'exit': break
        if command.strip() == 'boundary': rp.reload_resource_caches_if_changed()
        report()
"""
        children = []
        try:
            for i in range(3):
                (self.base / f"child{i}").mkdir()
                process = subprocess.Popen(
                    [sys.executable, "-c", script],
                    env=dict(os.environ, MOWER_DATA_DIR=str(self.base / f"child{i}")),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                replies = queue.Queue()
                logs = []

                def read_output(child=process, output=replies, lines=logs):
                    for line in child.stdout:
                        lines.append(line)
                        if line.startswith("RESOURCE_TEST "):
                            output.put(json.loads(line.removeprefix("RESOURCE_TEST ")))

                threading.Thread(target=read_output, daemon=True).start()
                children.append((process, replies))
                try:
                    first = replies.get(timeout=10)
                except queue.Empty:
                    self.fail("Resource child did not start: " + "".join(logs))
                self.assertEqual(first["version"], "v2026.08.23-aaaaaaa")
            self.assertTrue(
                rp.install_resource_pkg(resource_zip("v2026.08.24-bbbbbbb"))
            )
            for process, replies in children:
                process.stdin.write("read\n")
                process.stdin.flush()
                self.assertEqual(
                    replies.get(timeout=5)["version"], "v2026.08.23-aaaaaaa"
                )
            selected = []
            for process, replies in children:
                process.stdin.write("boundary\n")
                process.stdin.flush()
                result = replies.get(timeout=5)
                self.assertEqual(result["version"], "v2026.08.24-bbbbbbb")
                selected.append(result["path"])
            self.assertEqual(len(set(selected)), 1)
        finally:
            for process, _ in children:
                if process.poll() is None:
                    process.stdin.write("exit\n")
                    process.stdin.flush()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
                process.stdin.close()
                process.stdout.close()


class ResourceCompatibilityTests(unittest.TestCase):
    def test_same_day_hash_is_not_a_timestamp(self):
        older = {"res_version": "v2026.08.23-aaaaaaa"}
        newer = {"res_version": "v2026.08.23-bbbbbbb"}
        self.assertFalse(resource_newer(newer, older))
        older["last_updated"] = "2026-08-23 10:00:00"
        newer["last_updated"] = "2026-08-23 11:00:00"
        self.assertTrue(resource_newer(newer, older))

    def test_legacy_schema_and_explicit_mower_range(self):
        self.assertIsNone(compatibility_error({}, "4.1.6-alpha.1+abc"))
        self.assertIsNone(
            compatibility_error({"mower_version": ">=4.1.6a1,<5"}, "4.1.6-alpha.3")
        )
        self.assertIsNotNone(compatibility_error({"mower_version": ">=5"}, "4.2.0"))
        self.assertIsNotNone(compatibility_error({"mower_version": "bad"}, "4.2.0"))
        self.assertIsNotNone(compatibility_error({"schema_version": True}, "4.2.0"))


if __name__ == "__main__":
    unittest.main()
