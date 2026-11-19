"""Independent desktop access settings retain the current session credential."""

import unittest
from unittest.mock import patch

import yaml

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.utils import config
from webview_ui import desktop_port


class StandaloneWebAccessTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.enterContext(
            patch("arknights_mower.utils.managed_device.enabled", return_value=False)
        )

    def test_saved_access_values_apply_to_next_launch_without_rotating_session(self):
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={"webview": {"port": 58123, "token": "synthetic-next-token"}},
        )
        self.assertEqual(response.status_code, 200, response.json)
        saved = yaml.safe_load(self.path.read_text())["webview"]
        self.assertEqual(saved["port"], 58123)
        self.assertEqual(saved["token"], "synthetic-next-token")
        self.assertEqual(desktop_port(config.conf.webview, False), 58123)
        self.assertEqual(self.server.app.token, "device-token")
        self.assertEqual(
            self.client.get("/conf", headers=self.headers).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                "/conf", headers={"token": "synthetic-next-token"}
            ).status_code,
            403,
        )

    def test_access_save_requires_current_session_token_before_parsing(self):
        from flask import Request

        before = self.path.read_bytes()
        with patch.object(Request, "get_json", side_effect=AssertionError("parsed")):
            for token in (None, "invalid-token"):
                headers = {} if token is None else {"token": token}
                response = self.client.patch(
                    "/conf", headers=headers, json={"webview": {"port": 58123}}
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.path.read_bytes(), before)

    def test_relay_restricts_machine_changes_only_for_this_request(self):
        remote = {"headers": self.headers, "environ_overrides": {"mower.relay": True}}
        exposed = self.client.get("/conf", **remote).json
        self.assertTrue(exposed["manager_owned_device"])
        self.assertFalse(exposed["extra_settings_visible"])
        before = self.path.read_bytes()
        for method in (self.client.post, self.client.patch):
            for changes in (
                {"webview": {"token": "different"}},
                {"webview": {"port": 58123}},
                {"webview": {"tray": not config.conf.webview.tray}},
                {"extra_settings_visible": True},
                {"screenshot_interval": config.conf.screenshot_interval + 1},
            ):
                response = method("/conf", json=changes, **remote)
                self.assertEqual(response.status_code, 403, response.json)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(
            self.client.post("/db-admin/delete", json={}, **remote).status_code, 403
        )
        local = self.client.get("/conf", headers=self.headers).json
        self.assertFalse(local["manager_owned_device"])
        self.assertEqual(
            self.client.patch(
                "/conf", json={"drone_count_limit": 117}, **remote
            ).status_code,
            200,
        )

    def test_local_maintenance_choice_applies_to_relay_and_can_be_revoked(self):
        remote = {"headers": self.headers, "environ_overrides": {"mower.relay": True}}
        maintenance = {"screenshot_archive_limit_mb": 1024}
        self.assertEqual(
            self.client.patch("/conf", json=maintenance, **remote).status_code, 403
        )
        self.assertEqual(
            self.client.get("/network/settings", **remote).status_code, 403
        )
        for allowed in (True, False):
            response = self.client.patch(
                "/conf", headers=self.headers, json={"extra_settings_visible": allowed}
            )
            self.assertEqual(response.status_code, 200, response.json)
            self.assertIs(
                yaml.safe_load(self.path.read_text())["extra_settings_visible"], allowed
            )
            for managed in (True, False):
                with patch(
                    "arknights_mower.utils.managed_device.enabled", return_value=managed
                ):
                    view = self.client.get("/conf", **remote).json
                    self.assertTrue(view["manager_owned_device"])
                    self.assertIs(view["extra_settings_visible"], allowed)
                    for method in (self.client.patch, self.client.post):
                        update = method(
                            "/conf",
                            json={"extra_settings_visible": not allowed},
                            **remote,
                        )
                        self.assertEqual(update.status_code, 403)
                        self.assertEqual(
                            method(
                                "/conf", json={"webview": {"port": 58111}}, **remote
                            ).status_code,
                            403,
                        )
                    self.assertEqual(
                        self.client.get("/network/settings", **remote).status_code,
                        200 if allowed else 403,
                    )
                    self.assertEqual(
                        self.client.post(
                            "/db-admin/delete", json={}, **remote
                        ).status_code,
                        400 if allowed else 403,
                    )
                    self.assertEqual(
                        self.client.patch(
                            "/conf", json=maintenance, **remote
                        ).status_code,
                        200 if allowed else 403,
                    )
            maintenance["screenshot_archive_limit_mb"] += 1
