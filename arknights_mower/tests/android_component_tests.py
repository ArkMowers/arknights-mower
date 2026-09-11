import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from arknights_mower.utils.maa_update import (
    MaaUpdateError,
    extract_linux_package,
    parse_release,
)


class AndroidUpdateTests(unittest.TestCase):
    def payload(self, names):
        return {
            "tag_name": "v6.17.5",
            "assets": [
                {
                    "name": name,
                    "browser_download_url": "https://example.invalid/" + name,
                    "size": 10,
                    "digest": "sha256:" + "a" * 64,
                }
                for name in names
            ],
        }

    def test_only_official_android_component_selected(self):
        release = parse_release(
            self.payload(
                [
                    "MAA-v6.17.5-linux-aarch64.tar.gz",
                    "MAA-v6.17.5-win-arm64.zip",
                    "MAAComponent-v6.17.5-android-arm64.tar.gz",
                ]
            ),
            system="android",
            machine="aarch64",
        )
        self.assertEqual(
            release.runtime.name, "MAAComponent-v6.17.5-android-arm64.tar.gz"
        )
        self.assertIsNone(release.python_source)
        self.assertEqual(release.runtime.sha256, "a" * 64)

    def test_missing_android_asset_never_falls_back_to_linux(self):
        with self.assertRaises(MaaUpdateError):
            parse_release(
                self.payload(["MAA-v6.17.5-linux-aarch64.tar.gz"]),
                system="android",
                machine="arm64",
            )

    def test_android_archive_requires_android_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "wrong.tar.gz"
            dest = Path(directory) / "out"
            dest.mkdir()
            with tarfile.open(package, "w:gz") as tar:
                for name in ("libMaaCore.so", "resource/config.json", "Python/asst.py"):
                    info = tarfile.TarInfo(name)
                    info.size = 2
                    tar.addfile(info, io.BytesIO(b"{}"))
            with self.assertRaisesRegex(MaaUpdateError, "Android"):
                extract_linux_package(package, dest, android=True)

    def test_android_uses_same_channel_version_even_without_prerelease_flag(self):
        from unittest.mock import Mock

        from arknights_mower.utils.maa_update import (
            MAA_VERSION_API_URLS,
            get_latest_release,
        )

        for channel in ("stable", "beta"):
            with self.subTest(channel=channel):
                selected = self.payload(["MAAComponent-v6.17.5-android-arm64.tar.gz"])
                selected["prerelease"] = False
                client = Mock()
                channel_response, release_response = Mock(), Mock()
                channel_response.json.return_value = {
                    "version": "v6.17.5",
                    "details": {"tag_name": "v6.17.5", "assets": []},
                }
                release_response.json.return_value = selected
                client.get.side_effect = [channel_response, release_response]
                release = get_latest_release(
                    client, system="android", machine="arm64", channel=channel
                )
                self.assertEqual(release.tag, "v6.17.5")
                self.assertEqual(
                    client.get.call_args_list[0].args[0],
                    MAA_VERSION_API_URLS[0].format(channel=channel),
                )
                self.assertTrue(
                    client.get.call_args_list[1]
                    .args[0]
                    .endswith("/releases/tags/v6.17.5")
                )


class AndroidMirrorPolicyTests(unittest.TestCase):
    def test_core_resource_and_cdk_reject_mirror_before_network(self):
        from unittest.mock import Mock, patch

        from arknights_mower.utils.maa_resource_update import (
            get_mirrorchyan_resource_release,
        )
        from arknights_mower.utils.maa_update import (
            get_mirrorchyan_cdk_status,
            get_mirrorchyan_release,
        )

        client = Mock()
        with patch.dict("os.environ", {"MOWER_ANDROID": "1"}):
            for function in (
                get_mirrorchyan_release,
                get_mirrorchyan_resource_release,
                get_mirrorchyan_cdk_status,
            ):
                with self.subTest(function=function.__name__):
                    with self.assertRaisesRegex(
                        MaaUpdateError, "Android 暂不支持 Mirror酱"
                    ):
                        function("saved-token", session=client)
        client.get.assert_not_called()
