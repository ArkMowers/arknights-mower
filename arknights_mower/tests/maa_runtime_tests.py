import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.utils import maa_runtime as runtime


class MaaRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name)
        self.library = self.target / "MaaCore.dll"
        self.library.write_bytes(b"first core")

        class FakeAsst:
            load = Mock(return_value=True)

        self.asst_type = FakeAsst
        self.instance = Mock()
        self.instance.get_version.return_value = "v6.19.0-beta.1"
        self.verified = self.enterContext(
            patch.object(runtime, "VerifiedAsst", return_value=self.instance)
        )
        self.probe = self.enterContext(
            patch.object(
                runtime, "read_installed_version", return_value="v6.19.0-beta.1"
            )
        )
        self.enterContext(patch.object(runtime, "maa_in_use", return_value=False))
        self.clear = self.enterContext(
            patch.object(
                runtime,
                "clear_loaded_maa_cache",
                side_effect=runtime.MaaUpdateError("unsafe reload"),
            )
        )
        self.enterContext(patch.object(runtime.sys, "path", list(runtime.sys.path)))
        self.callback = Mock()

    def load(self):
        return runtime.load_verified_maa(self.asst_type, self.target, self.callback)

    def test_first_load_verifies_actual_core_before_connection(self):
        self.assertIs(self.load(), self.instance)
        self.asst_type.load.assert_called_once_with(
            path=self.target, incremental_path=self.target / "cache"
        )
        self.probe.assert_called_once_with(self.target, fresh=True)
        self.instance.connect.assert_not_called()

    def test_unchanged_core_reuses_probe_but_reloads_resources(self):
        self.load()
        self.load()
        self.assertEqual(self.probe.call_count, 1)
        self.assertEqual(self.asst_type.load.call_count, 2)

    def test_already_loaded_old_core_is_rejected(self):
        self.instance.get_version.return_value = "v6.18.0"
        with self.assertRaises(runtime.MaaCoreRestartRequired) as caught:
            self.load()
        self.assertEqual(caught.exception.code, "maa_core_restart_required")
        self.assertIn("v6.18.0", str(caught.exception))
        self.assertIn("v6.19.0-beta.1", str(caught.exception))
        self.instance.stop.assert_called_once()
        self.instance.connect.assert_not_called()
        self.assertNotIn("_mower_core_generation", vars(self.asst_type))

    def test_external_same_version_replacement_fails_before_resource_loading(self):
        self.load()
        self.library.write_bytes(b"different build, same version")
        with self.assertRaises(runtime.MaaCoreRestartRequired):
            self.load()
        self.assertEqual(self.asst_type.load.call_count, 1)
        self.assertEqual(self.verified.call_count, 1)

    def test_symlink_target_replacement_fails_before_resource_loading(self):
        physical = self.target / "physical-core"
        self.library.rename(physical)
        try:
            self.library.symlink_to(physical.name)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.load()
        replacement = self.target / "replacement"
        replacement.write_bytes(b"different target build")
        replacement.replace(physical)
        with self.assertRaises(runtime.MaaCoreRestartRequired):
            self.load()
        self.assertEqual(self.asst_type.load.call_count, 1)
        self.assertEqual(self.probe.call_count, 1)
        self.assertEqual(self.verified.call_count, 1)

    def test_symlink_target_change_during_probe_is_rejected(self):
        physical = self.target / "physical-core"
        self.library.rename(physical)
        try:
            self.library.symlink_to(physical.name)
        except OSError:
            self.skipTest("symlinks unavailable")

        def probe(*args, **kwargs):
            replacement = self.target / "replacement"
            replacement.write_bytes(b"changed during probe")
            replacement.replace(physical)
            return "v6.19.0-beta.1"

        self.probe.side_effect = probe
        with self.assertRaises(runtime.MaaCoreRestartRequired):
            self.load()
        self.assertNotIn("_mower_core_generation", vars(self.asst_type))
        self.instance.stop.assert_called_once()

    def test_resource_and_cache_updates_do_not_require_restart(self):
        self.load()
        (self.target / "resource").mkdir()
        (self.target / "resource" / "version.json").write_text("new resources")
        (self.target / "cache").mkdir()
        (self.target / "cache" / "tasks.json").write_text("new navigation")
        self.assertIs(self.load(), self.instance)
        self.assertEqual(self.probe.call_count, 1)

    def test_resource_load_failure_creates_no_native_instance(self):
        self.asst_type.load.return_value = False
        with self.assertRaisesRegex(runtime.MaaCallError, "资源加载失败"):
            self.load()
        self.verified.assert_not_called()
        self.probe.assert_not_called()

    def test_failed_version_probe_retains_no_validated_generation(self):
        self.probe.return_value = ""
        with self.assertRaisesRegex(runtime.MaaUpdateError, "读取.*版本"):
            self.load()
        self.instance.stop.assert_called_once()
        self.assertNotIn("_mower_core_generation", vars(self.asst_type))

    def test_core_changed_during_probe_fails_closed(self):
        def probe(*args, **kwargs):
            self.library.write_bytes(b"changed while probing")
            return "v6.19.0-beta.1"

        self.probe.side_effect = probe
        with self.assertRaises(runtime.MaaCoreRestartRequired):
            self.load()
        self.instance.stop.assert_called_once()

    def test_other_installation_is_not_silently_adopted(self):
        self.load()
        other = self.target / "other"
        other.mkdir()
        (other / "MaaCore.dll").write_bytes(b"first core")
        with self.assertRaises(runtime.MaaCoreRestartRequired):
            runtime.load_verified_maa(self.asst_type, other, self.callback)
        self.assertEqual(self.asst_type.load.call_count, 1)

    def test_updater_reimported_sdk_validates_the_new_generation(self):
        self.load()
        self.library.write_bytes(b"updated core")

        class NewAsst:
            load = Mock(return_value=True)

        self.assertIs(
            runtime.load_verified_maa(NewAsst, self.target, self.callback),
            self.instance,
        )
        self.assertEqual(self.probe.call_count, 2)

    def test_busy_instance_is_not_unloaded_or_replaced(self):
        with patch.object(runtime, "maa_in_use", return_value=True):
            with self.assertRaisesRegex(runtime.MaaUpdateError, "正在使用"):
                self.load()
        self.asst_type.load.assert_not_called()
        self.verified.assert_not_called()

    def test_missing_core_does_not_use_system_library_fallback(self):
        self.library.unlink()
        with self.assertRaisesRegex(runtime.MaaUpdateError, "核心"):
            self.load()
        self.asst_type.load.assert_not_called()

    def test_failed_cleanup_does_not_mask_version_mismatch(self):
        self.instance.get_version.return_value = "v6.18.0"
        self.instance.stop.side_effect = RuntimeError("stop failed")
        with self.assertRaises(runtime.MaaCoreRestartRequired):
            self.load()

    def test_external_replacement_reimports_sdk_and_verifies_new_core(self):
        self.load()
        self.library.write_bytes(b"new core build")
        self.clear.side_effect = None
        new_type = type("NewAsst", (), {"load": Mock(return_value=True)})
        with patch.object(
            runtime.importlib,
            "import_module",
            return_value=SimpleNamespace(Asst=new_type),
        ) as reimport:
            self.assertIs(self.load(), self.instance)
        self.clear.assert_called_once_with(self.target)
        reimport.assert_called_once_with("asst.asst")
        new_type.load.assert_called_once()
        self.assertEqual(self.probe.call_count, 2)
        self.assertNotEqual(
            new_type._mower_core_generation[0], self.asst_type._mower_core_generation[0]
        )

    def test_reload_retries_only_once_and_keeps_restart_guidance(self):
        self.load()
        self.library.write_bytes(b"updated")
        self.clear.side_effect = None
        new_type = type("NewAsst", (), {"load": Mock(return_value=True)})
        self.instance.get_version.return_value = "old core still resident"
        with patch.object(
            runtime.importlib,
            "import_module",
            return_value=SimpleNamespace(Asst=new_type),
        ) as reimport:
            with self.assertRaises(runtime.MaaCoreRestartRequired) as caught:
                self.load()
        self.assertEqual(caught.exception.code, "maa_core_restart_required")
        self.clear.assert_called_once()
        reimport.assert_called_once()
        self.instance.connect.assert_not_called()

    def test_failed_reimport_keeps_restart_guidance(self):
        self.load()
        self.library.write_bytes(b"updated")
        self.clear.side_effect = None
        with patch.object(
            runtime.importlib, "import_module", side_effect=ImportError("SDK")
        ):
            with self.assertRaises(runtime.MaaCoreRestartRequired) as caught:
                self.load()
        self.assertIsInstance(caught.exception.__cause__, ImportError)
        self.assertEqual(self.verified.call_count, 1)


if __name__ == "__main__":
    unittest.main()
