"""Installed update channels admit newer releases with stronger stability."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.tests.software_update_tests import release, release_index
from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime


class ChannelPromotionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = patch.object(runtime, "state_dir", return_value=Path(temporary.name))
        state.start()
        self.addCleanup(state.stop)

    def index(self, version, current, *, valid=True):
        record = release_index(
            release(version, "-" in version, system="windows", arch="x64")
        )
        record["full_assets"][0]["size"] = 100
        if not valid:
            record["full_assets"][0]["digest"] = ""
        name = f"arknights-mower-ota_{current}_to_{version[1:]}_windows_x64_v2.zip"
        record["ota_assets"] = [
            {
                "name": name,
                "size": 9,
                "digest": "sha256:" + "b" * 64,
                "url": f"https://github.com/{update.OTA_REPO}/releases/download/{version}/{name}",
            }
        ]
        return record

    def check(self, channel, current, indexes):
        def read(name):
            if name not in indexes:
                raise ValueError("Channel unavailable")
            return indexes[name]

        with (
            patch.object(runtime, "frozen", return_value=True),
            patch.object(update, "platform_asset", return_value=("windows", "x64")),
            patch.object(update, "__version__", current),
            patch.object(update, "release_index", side_effect=read) as network,
            patch.object(update, "github") as github,
            patch.object(update.network_settings, "apply_http_proxy"),
            patch.object(
                update.network_settings,
                "get_effective_settings",
                return_value={"http_proxy": ""},
            ),
        ):
            update.save_settings({"channel": channel})
            result = update.check(channel)
            self.assertEqual(update.get_settings()["channel"], channel)
        github.assert_not_called()
        return result, network

    def test_newer_beta_and_stable_use_direct_ota_without_switching_channel(self):
        current = "4.1.6-alpha.10.g85e916f7"
        for channel, promoted, target in (
            ("dev", "beta", "v4.1.6-alpha.11"),
            ("dev", "stable", "v4.1.6"),
            ("beta", "stable", "v4.1.6"),
        ):
            with self.subTest(channel=channel, target=target):
                own = "v" + current if channel == "dev" else "v4.1.6-alpha.11"
                result, _ = self.check(
                    channel,
                    current,
                    {
                        channel: self.index(own, current),
                        promoted: self.index(target, current),
                    },
                )
                plan = update._checks[result["check_id"]]
                self.assertEqual(result["channel"], channel)
                self.assertEqual(result["version"], target)
                self.assertTrue(result["available"])
                self.assertFalse(result["downgrade"])
                self.assertEqual(plan["channel"], channel)
                self.assertIn(f"_to_{target[1:]}_", plan["ota_asset"]["name"])
                self.assertIn(f"/{target}/", plan["asset"]["url"])

    def test_newest_eligible_version_wins_and_current_stable_is_not_reinstalled(self):
        current = "4.1.6"
        indexes = {
            "dev": self.index("v4.1.6-alpha.10.g85e916f7", current),
            "beta": self.index("v4.1.6-alpha.11", current),
            "stable": self.index("v4.1.6", current),
        }
        result, _ = self.check("dev", current, indexes)
        self.assertEqual(result["version"], "v4.1.6")
        self.assertFalse(result["available"])

        indexes["dev"] = self.index("v4.1.7-alpha.1.g12345678", current)
        result, _ = self.check("dev", current, indexes)
        self.assertEqual(result["version"], indexes["dev"]["version"])

    def test_optional_missing_or_unverifiable_release_preserves_own_channel(self):
        current = "4.1.6-alpha.10.g85e916f7"
        own = self.index("v4.1.6-alpha.11.g12345678", current)
        incompatible = self.index("v4.1.6", current)
        incompatible["full_assets"] = []
        for other in (
            {},
            {"stable": self.index("v4.1.6", current, valid=False)},
            {"stable": incompatible},
        ):
            with self.subTest(other=bool(other)):
                result, _ = self.check("dev", current, {"dev": own, **other})
                self.assertEqual(result["version"], own["version"])

    def test_public_target_without_exact_source_ota_uses_its_full_package(self):
        current = "4.1.6-alpha.10.g85e916f7"
        target = self.index("v4.1.6-alpha.11", "4.1.6-alpha.10")
        result, _ = self.check(
            "dev", current, {"dev": self.index("v" + current, current), "beta": target}
        )
        plan = update._checks[result["check_id"]]
        self.assertEqual(result["version"], target["version"])
        self.assertNotIn("ota_asset", plan)
        self.assertIn("/v4.1.6-alpha.11/", plan["asset"]["url"])

    def test_optional_malformed_asset_metadata_preserves_primary_release(self):
        current = "4.1.6-alpha.10.g85e916f7"
        for field, value in (
            ("size", None),
            ("size", -1),
            ("digest", 123),
            ("url", 123),
        ):
            with self.subTest(field=field, value=value):
                candidate = self.index("v4.1.6", current)
                candidate["full_assets"][0][field] = value
                result, _ = self.check(
                    "dev",
                    current,
                    {"dev": self.index("v" + current, current), "stable": candidate},
                )
                self.assertFalse(result["available"])

    def test_stable_channel_excludes_beta_and_nightly(self):
        current = "4.1.5"
        result, network = self.check(
            "stable",
            current,
            {
                "stable": self.index("v4.1.6", current),
                "beta": self.index("v4.1.7-alpha.11", current),
                "dev": self.index("v4.1.7-alpha.11.g12345678", current),
            },
        )
        self.assertEqual(result["version"], "v4.1.6")
        network.assert_called_once_with("stable")
