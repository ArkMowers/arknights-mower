import unittest
from pathlib import Path

from arknights_mower.utils.path import _default_frozen_data_dir


class FrozenDataDirTests(unittest.TestCase):
    def test_macos_uses_application_support(self):
        result = _default_frozen_data_dir(
            Path("/Applications/mower.app/Contents/Frameworks"),
            platform_name="darwin",
            home_dir=Path("/Users/tester"),
        )

        self.assertEqual(
            result,
            Path("/Users/tester/Library/Application Support/arknights_mower"),
        )

    def test_other_platforms_keep_portable_bundle_layout(self):
        internal_dir = Path("/opt/mower/_internal")

        self.assertEqual(
            _default_frozen_data_dir(internal_dir, platform_name="linux"),
            Path("/opt/mower"),
        )


class PortableConfigPathTests(unittest.TestCase):
    def test_saved_defaults_follow_moved_bundle_and_global_data_directory(self):
        import json
        import tempfile
        from unittest.mock import patch

        from arknights_mower.utils import path
        from arknights_mower.utils.config.conf import Conf
        from arknights_mower.utils.maa_check import maa_check_params

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "DMG/mower"
            (before / "internal/platform-tools").mkdir(parents=True)
            (before / "internal/platform-tools/adb").write_text("bundled adb")
            (before / "MAA").mkdir()
            with (
                patch("sys.platform", "darwin"),
                patch.object(path, "_internal_dir", before / "internal"),
                patch.object(path, "_data_dir", before),
            ):
                serialized = Conf().model_dump_json()
            after = root / "Applications/mower"
            after.parent.mkdir()
            before.rename(after)
            with (
                patch.object(path, "_internal_dir", after / "internal"),
                patch.object(path, "_data_dir", after),
                patch.object(path, "global_space", str(root / "elsewhere/instance")),
            ):
                restored = Conf.model_validate_json(serialized)
                with patch("arknights_mower.utils.maa_check.config.conf", restored):
                    params = maa_check_params()
                self.assertEqual(params["maa_path"], str(after / "MAA"))
                self.assertEqual(
                    params["maa_adb_path"], str(after / "internal/platform-tools/adb")
                )
                self.assertTrue(Path(params["maa_adb_path"]).is_file())
                self.assertEqual(
                    json.loads(restored.model_dump_json()), json.loads(serialized)
                )

    def test_explicit_user_paths_and_empty_values_keep_their_meaning(self):
        from arknights_mower.utils.path import resolve_config_path

        for value in ("", "adb", "./custom/MAA", "/custom/maa", r"C:\MAA\adb.exe"):
            self.assertEqual(resolve_config_path(value), value)


if __name__ == "__main__":
    unittest.main()
