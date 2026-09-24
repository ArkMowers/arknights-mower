import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import ui_state


class UiStateTests(unittest.TestCase):
    def test_log_layout_round_trip_and_clamp(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(
                ui_state, "state_path", return_value=Path(folder) / "ui-state.json"
            ),
        ):
            self.assertEqual(
                ui_state.get_log_layout(),
                {"screenshot_height": None, "task_height": None},
            )
            saved = ui_state.save_log_layout(
                {"screenshot_height": 260.4, "task_height": 999}
            )
            self.assertEqual(saved, {"screenshot_height": 260, "task_height": 600})
            self.assertEqual(ui_state.get_log_layout(), saved)

    def test_log_layout_rejects_non_numeric_value(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(
                ui_state, "state_path", return_value=Path(folder) / "ui-state.json"
            ),
        ):
            with self.assertRaises(ValueError):
                ui_state.save_log_layout({"task_height": "320"})


if __name__ == "__main__":
    unittest.main()
