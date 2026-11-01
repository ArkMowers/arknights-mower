"""The same authenticated update routes support a host Release installer."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


class AndroidDistributionTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Mock()
        source = Path(__file__).parents[1] / "views/software_update.py"
        spec = importlib.util.spec_from_file_location(
            "android_distribution_routes", source
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch("arknights_mower.utils.software_update", self.desktop, create=True):
            spec.loader.exec_module(self.module)
        self.app = Flask(__name__)
        self.app.token = "test-token"
        self.app.register_blueprint(self.module.software_update_bp)
        self.client = self.app.test_client()
        self.headers = {"token": "test-token", "X-Mower-Update": "1"}

    def test_release_provider_uses_same_info_route_without_git_probe(self):
        provider = Mock()
        provider.info.return_value = {
            "ok": True,
            "deployment": "release",
            "platform": "android",
        }
        self.app.extensions["software_update_provider"] = provider
        response = self.client.get("/software-update/info", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deployment"], "release")
        self.desktop.info.assert_not_called()

    def test_release_provider_settings_preserve_policy_errors(self):
        provider = Mock()
        provider.save_settings.side_effect = ValueError("Release does not support dev")
        self.app.extensions["software_update_provider"] = provider
        response = self.client.post(
            "/software-update/settings", json={"channel": "dev"}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.desktop.save_settings.assert_not_called()

    def test_provider_cannot_bypass_authentication_or_same_origin(self):
        provider = Mock()
        self.app.extensions["software_update_provider"] = provider
        self.assertEqual(self.client.get("/software-update/info").status_code, 403)
        response = self.client.post(
            "/software-update/check",
            json={"channel": "beta"},
            headers={**self.headers, "Origin": "https://example.invalid"},
        )
        self.assertEqual(response.status_code, 403)
        provider.info.assert_not_called()
        provider.check.assert_not_called()

    def test_desktop_keeps_original_update_route(self):
        self.desktop.info.return_value = {"ok": True, "deployment": "source"}
        response = self.client.get("/software-update/info", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["deployment"], "source")
        self.desktop.info.assert_called_once_with()
