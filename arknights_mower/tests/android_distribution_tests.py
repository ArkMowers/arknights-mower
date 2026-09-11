"""Android distribution requests must never enter the desktop Git updater."""

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


class AndroidDistributionTests(unittest.TestCase):
    def setUp(self):
        self.updater = Mock()
        source = Path(__file__).parents[1] / "views/software_update.py"
        spec = importlib.util.spec_from_file_location(
            "android_distribution_routes", source
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch("arknights_mower.utils.software_update", self.updater, create=True):
            spec.loader.exec_module(self.module)
        app = Flask(__name__)
        app.token = "test-token"
        app.register_blueprint(self.module.software_update_bp)
        self.client = app.test_client()

    @patch.dict(os.environ, {"MOWER_ANDROID": "1"})
    def test_android_info_does_not_probe_git_environment(self):
        response = self.client.get(
            "/software-update/info", headers={"token": "test-token"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("Android", response.json["message"])
        self.updater.info.assert_not_called()

    @patch.dict(os.environ, {"MOWER_ANDROID": "1"})
    def test_android_development_channel_cannot_reach_desktop_updater(self):
        response = self.client.post(
            "/software-update/settings",
            json={"channel": "dev"},
            headers={"token": "test-token", "X-Mower-Update": "1"},
        )
        self.assertEqual(response.status_code, 409)
        self.updater.save_settings.assert_not_called()

    @patch.dict(os.environ, {"MOWER_ANDROID": "1"})
    def test_android_guard_preserves_authentication(self):
        self.assertEqual(self.client.get("/software-update/info").status_code, 403)

    @patch.dict(os.environ, {"MOWER_ANDROID": "0"})
    def test_desktop_keeps_original_update_route(self):
        self.updater.info.return_value = {"ok": True, "deployment": "source"}
        response = self.client.get(
            "/software-update/info", headers={"token": "test-token"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deployment"], "source")
        self.updater.info.assert_called_once_with()
