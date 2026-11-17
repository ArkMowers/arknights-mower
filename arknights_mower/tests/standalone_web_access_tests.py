"""Independent desktop access settings retain the current session credential."""

import asyncio
import base64
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

import yaml

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.utils import config
from arknights_mower.utils.configuration_secrets import conf_secrets_path
from arknights_mower.utils.credential_store import read_credentials
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
        saved = yaml.safe_load(self.path.read_text(encoding="utf-8"))["webview"]
        self.assertEqual(saved["port"], 58123)
        self.assertNotIn("token", saved)
        self.assertEqual(
            read_credentials(conf_secrets_path(self.path))["MOWER_WEBVIEW_TOKEN"],
            "synthetic-next-token",
        )
        self.assertNotIn(
            b"synthetic-next-token", conf_secrets_path(self.path).read_bytes()
        )
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
        self.assertTrue(exposed["extra_settings_visible"])
        before = self.path.read_bytes()
        for method in (self.client.post, self.client.patch):
            for changes in (
                {"extra_settings_visible": False},
                {"screenshot_interval": config.conf.screenshot_interval + 1},
            ):
                response = method("/conf", json=changes, **remote)
                self.assertEqual(response.status_code, 403, response.json)
        self.assertEqual(self.path.read_bytes(), before)
        local = self.client.get("/conf", headers=self.headers).json
        self.assertFalse(local["manager_owned_device"])
        self.assertEqual(
            self.client.patch(
                "/conf", json={"drone_count_limit": 117}, **remote
            ).status_code,
            200,
        )

    def test_relay_maintenance_follows_actual_launch_mode(self):
        remote = {"headers": self.headers, "environ_overrides": {"mower.relay": True}}
        for managed in (False, True):
            for saved in (False, True):
                allowed = not managed or saved
                with (
                    self.subTest(managed=managed, saved=saved),
                    patch(
                        "arknights_mower.utils.managed_device.enabled",
                        return_value=managed,
                    ),
                    patch.object(config.conf, "extra_settings_visible", saved),
                ):
                    self.assertIs(
                        self.client.get("/conf", **remote).json[
                            "extra_settings_visible"
                        ],
                        allowed,
                    )
                    self.assertEqual(
                        self.client.get("/network/settings", **remote).status_code,
                        200 if allowed else 403,
                    )
                    # Empty categories exercise authorization without deleting records.
                    self.assertEqual(
                        self.client.post(
                            "/db-admin/delete", json={}, **remote
                        ).status_code,
                        400 if allowed else 403,
                    )
                    self.assertEqual(
                        self.client.patch(
                            "/conf",
                            json={
                                "screenshot_archive_limit_mb": config.conf.screenshot_archive_limit_mb
                                + 1
                            },
                            **remote,
                        ).status_code,
                        200 if allowed else 403,
                    )

    def test_standalone_relay_can_edit_access_after_authentication(self):
        from arknights_mower.utils.mower_relay.client import RelayClient
        from arknights_mower.utils.mower_relay.protocol import public_origin

        origin = public_origin("test-access")
        client = RelayClient(self.server.app)
        self.enterContext(patch.dict(self.server.app.extensions, mower_relay=client))
        events = []
        client.start = Mock(side_effect=lambda: events.append("reconnect"))

        async def receive(frame):
            events.append(frame["status"])

        ws = Mock(closed=False, send_json=AsyncMock(side_effect=receive))
        message = {
            "op": "request",
            "id": "save",
            "path": "/conf",
            "method": "PATCH",
            "headers": {"content-type": "application/json"},
            "body": base64.b64encode(
                json.dumps({"webview": {"port": 58111, "token": "new-local"}}).encode()
            ).decode(),
        }
        for token, managed, expected in (
            ("", False, 403),
            ("incorrect", False, 403),
            ("device-token", True, 403),
            ("device-token", False, 200),
        ):
            with patch(
                "arknights_mower.utils.managed_device.enabled", return_value=managed
            ):
                self.assertIs(
                    self.client.get(
                        "/conf",
                        headers=self.headers,
                        environ_overrides={"mower.relay": True},
                    ).json["web_access_editable"],
                    not managed,
                )
                events.clear()
                message["headers"]["token"] = token
                client._work_slots.acquire()
                asyncio.run(client._reply(ws, None, message, origin))
                self.assertEqual(
                    events, [200, "reconnect"] if expected == 200 else [403]
                )
        self.assertEqual(config.conf.webview.port, 58111)
        self.assertEqual(config.conf.webview.token, "new-local")
        self.assertFalse(client.token_ready)
        self.assertEqual(self.server.app.token, "device-token")

    def test_remote_container_cannot_clear_its_access_token(self):
        before = self.path.read_bytes()
        previous = config.conf.webview.token
        with patch.dict(os.environ, {"MOWER_REQUIRE_WEB_TOKEN": "1"}):
            for method in (self.client.post, self.client.patch):
                response = method(
                    "/conf", headers=self.headers, json={"webview": {"token": ""}}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json["message"], "此部署允许远程访问，访问令牌不能为空。"
                )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(config.conf.webview.token, previous)
