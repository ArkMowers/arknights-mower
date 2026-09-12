import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from arknights_mower.utils.maa_resource_update import MaaResourceRelease
from arknights_mower.utils.maa_update import MaaRelease, ReleaseAsset


def _maa_release(version: str) -> MaaRelease:
    return MaaRelease(
        tag=version,
        runtime=ReleaseAsset(
            name=f"MAA-{version}-macos-runtime-universal.zip",
            url="https://example.test/maa.zip",
            size=1,
        ),
    )


class _FakeThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def is_alive(self):
        return False

    def start(self):
        self.started = True


class TestMaaUpdateRoutes(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.headers = {}
        if hasattr(server.app, "token"):
            self.headers["token"] = server.app.token
        self.temp = tempfile.TemporaryDirectory()
        self.target = str(Path(self.temp.name) / "MAA")
        server.maa_update_check.update(
            {
                "id": "",
                "target": "",
                "source": "",
                "channel": "",
                "installed_version": "",
                "latest_version": "",
            }
        )
        server.maa_resource_update_check.update(
            {
                "id": "",
                "target": "",
                "source": "",
                "current_version": "",
                "latest_version": "",
                "latest_release_note": "",
            }
        )
        server.maa_update_job.update({"thread": None, "status": "idle"})
        server.maa_resource_update_job.update({"thread": None, "status": "idle"})

    def tearDown(self):
        server.maa_update_job.update({"thread": None, "status": "idle"})
        server.maa_resource_update_job.update({"thread": None, "status": "idle"})
        self.temp.cleanup()

    def test_android_saved_mirror_config_uses_official_default_and_rejects_requests(
        self,
    ):
        with (
            patch.dict("os.environ", {"MOWER_ANDROID": "1"}),
            patch.object(server, "__system__", "linux"),
            patch.object(server.config.conf, "maa_mirrorchyan_token", "saved-token"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch.object(server, "active_job", return_value=False),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.5",
            ),
            patch("arknights_mower.utils.maa_update._request_mirrorchyan") as network,
        ):
            response = self.client.get(
                "/maa-update/info",
                query_string={"maa_path": self.target},
                headers=self.headers,
            )
            self.assertEqual(response.json["default_source"], "github")
            for route in (
                "/maa-update/check",
                "/maa-update/start",
                "/maa-resource-update/check",
                "/maa-resource-update/start",
                "/maa-update/mirrorchyan-status",
            ):
                with self.subTest(route=route):
                    response = self.client.post(
                        route,
                        json={
                            "maa_path": self.target,
                            "source": "mirrorchyan",
                            "channel": "beta",
                            "mirror_token": "saved-token",
                        },
                        headers=self.headers,
                    )
                    self.assertFalse(response.json["ok"])
                    self.assertIn("Android 暂不支持 Mirror酱", response.json["message"])
            network.assert_not_called()

    def test_portable_maa_path_is_resolved_consistently_by_all_update_routes(self):
        from arknights_mower.utils import path

        current = {"version": "2026-09-03 01:00:00.000", "release_note": ""}
        release = MaaResourceRelease(
            version="2026-09-04 01:07:54.000", source="github", available=True
        )
        with (
            patch.object(path, "_data_dir", Path(self.temp.name)),
            patch.object(path, "global_space", "other-instance"),
            patch.object(server.config.conf, "maa_path", "@app/MAA"),
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch.object(server, "mower_thread", None),
            patch.object(server, "active_job", return_value=False),
            patch.object(server, "Thread", side_effect=_FakeThread) as launch,
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=_maa_release("v6.18.0"),
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.get_maa_resource_release",
                return_value=release,
            ),
        ):
            for prefix in ("maa-update", "maa-resource-update"):
                info = self.client.get(
                    f"/{prefix}/info", headers=self.headers
                ).get_json()
                self.assertEqual(info["target"], self.target)
                payload = {
                    "maa_path": "@app/MAA",
                    "source": "github",
                    "channel": "stable",
                }
                checked = self.client.post(
                    f"/{prefix}/check", json=payload, headers=self.headers
                ).get_json()
                self.assertTrue(checked["ok"], checked)
                started = self.client.post(
                    f"/{prefix}/start",
                    json={**payload, "check_id": checked["check_id"]},
                    headers=self.headers,
                ).get_json()
                self.assertTrue(started["ok"], started)
                self.assertEqual(launch.call_args.kwargs["args"][0], self.target)
                server.maa_update_job.update({"thread": None, "status": "idle"})
                server.maa_resource_update_job.update(
                    {"thread": None, "status": "idle"}
                )
            resource = Path(self.target) / "resource"
            resource.mkdir(parents=True)
            (resource / "config.json").write_text(
                '{"connection":[{"configName":"CompatMac"}]}'
            )
            response = self.client.get("/maa-conn-preset", headers=self.headers)
            self.assertEqual(response.get_json(), ["CompatMac"])

    def test_maa_check_returns_check_id_only_for_new_version(self):
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ) as read_version,
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=_maa_release("v6.18.0"),
            ),
        ):
            response = self.client.post(
                "/maa-update/check",
                json={
                    "maa_path": self.target,
                    "source": "github",
                    "channel": "stable",
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["available"])
        self.assertTrue(data["check_id"])
        read_version.assert_called_once_with(self.target, fresh=True)

        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.18.0",
            ),
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=_maa_release("v6.18.0"),
            ),
        ):
            response = self.client.post(
                "/maa-update/check",
                json={
                    "maa_path": self.target,
                    "source": "github",
                    "channel": "stable",
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["available"])
        self.assertEqual(data["check_id"], "")

    def test_maa_info_returns_cached_latest_and_fresh_installed_version(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        server.maa_update_check.update(
            {
                "id": "",
                "target": target,
                "source": "github",
                "channel": channel,
                "installed_version": "v6.17.0",
                "latest_version": "v6.18.0",
            }
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.18.0",
            ) as read_version,
        ):
            response = self.client.get(
                "/maa-update/info",
                query_string={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertEqual(data["latest"]["tag"], "v6.18.0")
        self.assertEqual(data["installed_version"], "v6.18.0")
        read_version.assert_called_once_with(Path(target), fresh=True)

    def test_maa_update_start_requires_matching_successful_check(self):
        with (
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
        ):
            response = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": self.target,
                    "source": "github",
                    "channel": server.config.conf.maa_update_channel,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("先检查 MAA 更新", data["message"])

    def test_maa_update_start_accepts_matching_successful_check(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        check_id = server._record_update_check(
            server.maa_update_check,
            server.maa_update_check_lock,
            target=target,
            source="github",
            channel=channel,
            installed_version="v6.17.0",
            latest_version="v6.18.0",
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "Thread", _FakeThread),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
        ):
            response = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                    "check_id": check_id,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(server.maa_update_check["id"], "")

    def test_maa_update_start_rejects_equal_checked_version(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        check_id = server._record_update_check(
            server.maa_update_check,
            server.maa_update_check_lock,
            target=target,
            source="github",
            channel=channel,
            installed_version="v6.18.0",
            latest_version="v6.18.0",
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.18.0",
            ),
        ):
            response = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                    "check_id": check_id,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("发现新版本后再更新", data["message"])

    def test_resource_check_and_start_use_separate_check_result(self):
        current = {"version": "2026-09-03 01:00:00.000", "release_note": ""}
        release = MaaResourceRelease(
            version="2026-09-04 01:07:54.000",
            source="github",
            available=True,
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.get_maa_resource_release",
                return_value=release,
            ),
        ):
            checked = self.client.post(
                "/maa-resource-update/check",
                json={"maa_path": self.target, "source": "github"},
                headers=self.headers,
            ).get_json()

        self.assertTrue(checked["available"])
        self.assertTrue(checked["check_id"])

        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
        ):
            response = self.client.post(
                "/maa-resource-update/start",
                json={"maa_path": self.target, "source": "github"},
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("先检查 MAA 资源更新", data["message"])

    def test_resource_info_returns_cached_latest_version(self):
        target = str(Path(self.target).expanduser())
        latest = "2026-09-04 01:07:54.000"
        server.maa_resource_update_check.update(
            {
                "id": "",
                "target": target,
                "source": "github",
                "current_version": "2026-09-03 01:00:00.000",
                "latest_version": latest,
                "latest_release_note": "测试活动",
            }
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value={"version": latest, "release_note": "测试活动"},
            ),
        ):
            response = self.client.get(
                "/maa-resource-update/info",
                query_string={"maa_path": target, "source": "github"},
                headers=self.headers,
            )

        data = response.get_json()
        self.assertEqual(data["latest"]["version"], latest)
        self.assertEqual(data["latest"]["release_note"], "测试活动")

    def test_resource_update_start_rejects_equal_checked_version(self):
        target = str(Path(self.target).expanduser())
        version = "2026-09-04 01:07:54.000"
        check_id = server._record_update_check(
            server.maa_resource_update_check,
            server.maa_resource_update_check_lock,
            target=target,
            source="github",
            current_version=version,
            latest_version=version,
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value={"version": version, "release_note": ""},
            ),
        ):
            response = self.client.post(
                "/maa-resource-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "check_id": check_id,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("发现新版本后再更新", data["message"])


if __name__ == "__main__":
    unittest.main()
