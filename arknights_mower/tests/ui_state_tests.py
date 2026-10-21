import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from arknights_mower.utils import ui_state
from arknights_mower.utils.config import gui


class UiStateTests(unittest.TestCase):
    def test_log_layout_round_trip_and_clamp(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(gui, "gui_path", Path(folder) / "config/gui.yml"),
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
            patch.object(gui, "gui_path", Path(folder) / "config/gui.yml"),
        ):
            with self.assertRaises(ValueError):
                ui_state.save_log_layout({"task_height": "320"})


class MoodBoardStateTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(folder) / "config/gui.yml"
        self.enterContext(patch.object(gui, "gui_path", self.path))
        self.preferences = {
            "groupOrder": ["custom:focus-card", "一组"],
            "hiddenLines": {"一组": ["阿米娅"]},
            "hiddenGroups": ["一组"],
            "defaultOperators": {"一组": "银灰", "custom:focus-card": "煌"},
            "views": [{"id": "focus-card", "name": "重点", "operators": ["煌"]}],
        }

    def test_preferences_round_trip_and_partial_edits_preserve_log_layout(self):
        self.assertEqual(ui_state.get_mood_board(), {"preferences": None})
        ui_state.save_log_layout({"task_height": 320})
        ui_state.save_mood_board(self.preferences, initialize=True)
        self.assertEqual(ui_state.get_mood_board()["preferences"], self.preferences)

        ui_state.save_mood_board({"hiddenGroups": []})
        ui_state.save_log_layout({"screenshot_height": 200})
        expected = {**self.preferences, "hiddenGroups": []}
        self.assertEqual(ui_state.get_mood_board()["preferences"], expected)
        self.assertEqual(
            ui_state.get_log_layout(), {"task_height": 320, "screenshot_height": 200}
        )
        self.assertEqual(yaml.safe_load(self.path.read_text())["mood_board"], expected)

    def test_another_browser_cannot_replace_existing_preferences_during_migration(self):
        ui_state.save_mood_board(self.preferences, initialize=True)
        result = ui_state.save_mood_board({"groupOrder": ["旧编组"]}, initialize=True)
        self.assertEqual(result["preferences"], self.preferences)
        self.assertEqual(ui_state.get_mood_board()["preferences"], self.preferences)

    def test_invalid_payloads_do_not_change_saved_preferences(self):
        ui_state.save_mood_board(self.preferences)
        original = self.path.read_bytes()
        invalid = [
            None,
            [],
            {"unknown": []},
            {"groupOrder": "一组"},
            {"hiddenGroups": [None]},
            {"hiddenLines": {"一组": "阿米娅"}},
            {"defaultOperators": {"一组": ["阿米娅"]}},
            {"views": [{"id": "../bad", "name": "重点", "operators": []}]},
            {"views": self.preferences["views"] * 2},
            {"views": [{"id": "test-card", "name": "重点", "operators": ["a"] * 17}]},
            {"groupOrder": ["a"] * 513},
            {"groupOrder": ["x" * (129 * 1024)]},
        ]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:80]):
                with self.assertRaises(ValueError):
                    ui_state.save_mood_board(payload)
                self.assertEqual(self.path.read_bytes(), original)

    def test_routes_require_authentication_and_save_partial_fields(self):
        from flask import Flask

        from arknights_mower.views.ui_state import ui_state_bp

        app = Flask(__name__)
        app.token = "offline-ui-test"
        app.register_blueprint(ui_state_bp)
        client = app.test_client()
        url = "/ui-state/mood-board"
        for method in (client.get, client.post, client.patch):
            self.assertEqual(method(url).status_code, 403)
        headers = {"token": app.token}
        self.assertEqual(client.get(url, headers=headers).json, {"preferences": None})
        self.assertEqual(
            client.post(url, headers=headers, json=self.preferences).json[
                "preferences"
            ],
            self.preferences,
        )
        response = client.patch(url, headers=headers, json={"hiddenGroups": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["preferences"]["hiddenGroups"], [])
        self.assertEqual(
            response.json["preferences"]["views"], self.preferences["views"]
        )
        self.assertEqual(client.patch(url, headers=headers, json=[]).status_code, 400)


if __name__ == "__main__":
    unittest.main()
