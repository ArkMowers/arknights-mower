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


if __name__ == "__main__":
    unittest.main()
