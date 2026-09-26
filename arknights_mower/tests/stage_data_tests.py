"""Stage data follows the installed resource package without legacy overlays."""

import unittest
from unittest.mock import patch

from arknights_mower import data as data_module


class StageDataTests(unittest.TestCase):
    def test_builtin_data_is_available(self):
        self.assertIsInstance(data_module._stage_data_base, list)
        self.assertTrue(data_module._stage_data_base)

    def test_resource_reload_is_visible_to_existing_view(self):
        base = [{"id": "0-1"}]
        with patch.object(data_module, "_stage_data_base", base):
            view = data_module.stage_data_full
            self.assertEqual(list(view), [{"id": "0-1"}])
            base[:] = [{"id": "AP-5"}]
            self.assertEqual(list(view), [{"id": "AP-5"}])


if __name__ == "__main__":
    unittest.main()
