"""Hermetic OTA generation, installation, download and fallback regressions."""

import hashlib
import io
import json
import os
from unittest.mock import MagicMock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from arknights_mower.tests.resource_pkg_tests import ResourcePkgTestBase, resource_zip
from arknights_mower.utils import manual_update
from arknights_mower.utils import resource_pkg as rp
from arknights_mower.utils.res_version import RES_PACKAGE_DIRS, is_package_file
from arknights_mower.utils.resource_ota import OTA_MARKER, build_ota
from arknights_mower.utils.resource_update_job import ResourceUpdateJob

BASE = "v2026.08.23-aaaaaaa"
TARGET = "v2026.08.24-bbbbbbb"


def rewrite(data, transform):
    with ZipFile(io.BytesIO(data)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    transform(files)
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def change_manifest(data, transform):
    def change(files):
        manifest = json.loads(files[OTA_MARKER])
        transform(manifest)
        files[OTA_MARKER] = json.dumps(manifest).encode()

    return rewrite(data, change)


class TestResourceOTA(ResourcePkgTestBase):
    def setUp(self):
        super().setUp()
        self.old = resource_zip(BASE)
        # Real incompressible unchanged files make a file-level OTA smaller.
        self.old = rewrite(
            self.old,
            lambda files: files.update(
                {RES_PACKAGE_DIRS[0] + "/large.webp": os.urandom(16000)}
            ),
        )
        self.new = rewrite(
            self.old,
            lambda files: files.update(
                {
                    rp._RESOURCE_MARKER: json.dumps({"res_version": TARGET}).encode(),
                    "ui/public/avatar/new.webp": b"new image",
                }
            ),
        )
        self.old_path, self.new_path, self.ota_path = (
            self.base / name for name in ("old.zip", "resource.zip", "delta.zip")
        )
        self.old_path.write_bytes(self.old)
        self.new_path.write_bytes(self.new)
        build_ota(self.old_path, self.new_path, self.ota_path, is_package_file)
        self.delta = self.ota_path.read_bytes()
        self.assertTrue(rp.install_resource_pkg(self.old))
        self.fetch_index = patch.object(
            rp, "_fetch_resource_update_index", return_value=None
        )
        self.fetch_index.start()
        self.addCleanup(self.fetch_index.stop)

    def assert_target(self):
        self.assertEqual(self.installed_version(), TARGET)
        with ZipFile(io.BytesIO(self.new)) as archive:
            for name in archive.namelist():
                self.assertEqual(
                    rp.resource_pkg_path(name).read_bytes(), archive.read(name)
                )

    def index(self):
        def descriptor(name, data):
            return {
                "name": name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }

        return {
            "format": 1,
            "version": TARGET,
            "full": descriptor("resource.zip", self.new),
            "ota": [
                {
                    "from": BASE,
                    **descriptor(f"resource-ota_{BASE}_to_{TARGET}.zip", self.delta),
                }
            ],
        }

    def response(self, data):
        response = MagicMock(headers={"Content-Length": str(len(data))})
        response.__enter__.return_value = response
        response.iter_content.return_value = iter([data[:17], data[17:]])
        return response

    def test_reconstructs_complete_generation_and_omits_deleted_files(self):
        removed = RES_PACKAGE_DIRS[0] + "/large.webp"
        extra = RES_PACKAGE_DIRS[0] + "/y.webp"
        self.new = rewrite(
            self.new,
            lambda files: (files.pop(removed), files.update({extra: b"replacement"})),
        )
        self.new_path.write_bytes(self.new)
        build_ota(self.old_path, self.new_path, self.ota_path, is_package_file)
        with ZipFile(self.ota_path) as archive:
            self.assertNotIn(
                "payload/" + RES_PACKAGE_DIRS[1] + "/x.webp", archive.namelist()
            )
        previous = rp.resource_pkg_path(rp._RESOURCE_MARKER).parent.parent.parent
        self.assertTrue(rp.install_resource_pkg(self.ota_path.read_bytes()))
        self.assert_target()
        self.assertFalse(rp.resource_pkg_path(removed).exists())
        self.assertTrue((previous / removed).exists())

    def test_reuses_bundled_resource_and_bundled_dist_images(self):
        from arknights_mower.utils.resource_ota import VERSION_MARKER

        # Model a portable installation's Python data and UI dist layout.
        with ZipFile(io.BytesIO(self.old)) as archive:
            for name in archive.namelist():
                if name.startswith("arknights_mower/"):
                    target = self.builtin / name.removeprefix("arknights_mower/")
                elif name.startswith("ui/public/"):
                    target = (
                        self.builtin.parent
                        / "ui/dist"
                        / name.removeprefix("ui/public/")
                    )
                else:
                    target = self.builtin.parent / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        rp._write_index([])
        rp._active_resource = None
        self.assertEqual(
            json.loads(rp.resource_pkg_path(VERSION_MARKER).read_bytes())[
                "res_version"
            ],
            BASE,
        )
        self.assertTrue(rp.install_resource_pkg(self.delta))
        self.assert_target()

    def test_unchanged_corrupt_base_file_keeps_index_and_previous_generation(self):
        source = rp.resource_pkg_path("ui/public/avatar/x.webp")
        source.write_bytes(b"FAIL")
        before = (self.overlay / "index.json").read_bytes()
        self.assertFalse(rp.install_resource_pkg(self.delta))
        self.assertEqual((self.overlay / "index.json").read_bytes(), before)
        self.assertEqual(self.installed_version(), BASE)
        self.assertFalse(rp._STAGING.exists())

    def test_unmatched_starting_version_keeps_current_generation(self):
        invalid = change_manifest(
            self.delta,
            lambda manifest: manifest.update({"from": "v2026.08.21-eeeeeee"}),
        )
        self.assertFalse(rp.install_resource_pkg(invalid))
        self.assertEqual(self.installed_version(), BASE)

    def test_target_manifest_version_mismatch_is_rejected(self):
        invalid = change_manifest(
            self.delta, lambda manifest: manifest.update({"to": "v2026.08.25-ccccccc"})
        )
        self.assertFalse(rp.install_resource_pkg(invalid))
        self.assertEqual(self.installed_version(), BASE)

    def test_invalid_paths_payload_and_target_limits_are_rejected(self):
        invalids = [
            change_manifest(
                self.delta,
                lambda m: m["files"].update(
                    {"../outside": {"size": 0, "sha256": "0" * 64}}
                ),
            ),
            change_manifest(
                self.delta,
                lambda m: m["files"].update(
                    {
                        "arknights_mower/utils/runtime.py": {
                            "size": 0,
                            "sha256": "0" * 64,
                        }
                    }
                ),
            ),
            rewrite(self.delta, lambda files: files.update({"unexpected": b"x"})),
            change_manifest(
                self.delta,
                lambda m: m["files"][rp._RESOURCE_MARKER].update(
                    {"size": 513 * 1024**2}
                ),
            ),
            rewrite(
                self.delta,
                lambda files: files.update(
                    {"payload/ui/public/avatar/new.webp": b"bad image"}
                ),
            ),
        ]
        for invalid in invalids:
            with self.subTest(invalid=hashlib.sha256(invalid).hexdigest()):
                self.assertFalse(rp.install_resource_pkg(invalid))
                self.assertEqual(self.installed_version(), BASE)
                self.assertFalse(rp._STAGING.exists())

    def test_ota_installed_in_background_waits_for_task_boundary(self):
        from threading import Thread

        results = []
        with rp.resource_task_session():
            thread = Thread(
                target=lambda: results.append(rp.install_resource_pkg(self.delta))
            )
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results, [True])
            self.assertEqual(self.installed_version(), BASE)
            self.assertTrue(rp.reload_resource_caches_if_changed())
            self.assert_target()

    def test_case_colliding_target_paths_are_rejected(self):
        def collide(manifest):
            original = "ui/public/avatar/x.webp"
            manifest["files"]["ui/public/avatar/X.webp"] = manifest["files"][original]

        invalid = change_manifest(self.delta, collide)
        self.assertFalse(rp.install_resource_pkg(invalid))
        self.assertEqual(self.installed_version(), BASE)

    def test_declared_download_size_and_deadline_are_bounded(self):
        response = self.response(self.new)
        response.headers["Content-Length"] = str(513 * 1024**2)
        with patch.object(rp, "request_download", return_value=(response, "unused")):
            self.assertIsNone(rp.download_resource_pkg())
        response = self.response(self.new)
        with (
            patch.object(rp, "request_download", return_value=(response, "unused")),
            patch.object(rp.time, "monotonic", side_effect=[0, 301]),
        ):
            self.assertIsNone(rp.download_resource_pkg())
        self.assertEqual(self.installed_version(), BASE)

    def test_smaller_compatible_ota_download_uses_fixed_release_url_and_reports_bytes(
        self,
    ):
        index = self.index()
        events = []
        with (
            patch.object(rp, "_fetch_resource_update_index", return_value=index),
            patch.object(
                rp,
                "request_download",
                return_value=(self.response(self.delta), "unused"),
            ) as download,
        ):
            self.assertEqual(
                rp.download_resource_pkg(
                    callback=lambda **values: events.append(values)
                ),
                self.delta,
            )
        url = download.call_args.args[2]
        self.assertEqual(
            url,
            f"https://github.com/ArkMowers/MowerResource/releases/download/{TARGET}/resource-ota_{BASE}_to_{TARGET}.zip",
        )
        self.assertEqual(events[-1]["current"], len(self.delta))
        self.assertIn("OTA", events[-1]["message"])

    def test_no_matching_base_or_larger_ota_selects_target_full_package(self):
        for unmatched in (True, False):
            index = self.index()
            if unmatched:
                index["ota"][0]["from"] = "v2026.08.22-0000000"
            else:
                index["ota"][0]["size"] = len(self.new) + 1
            with (
                patch.object(rp, "_fetch_resource_update_index", return_value=index),
                patch.object(
                    rp,
                    "request_download",
                    return_value=(self.response(self.new), "unused"),
                ) as download,
            ):
                self.assertEqual(rp.download_resource_pkg(), self.new)
            self.assertEqual(
                download.call_args.args[2],
                f"https://github.com/ArkMowers/MowerResource/releases/download/{TARGET}/resource.zip",
            )

    def test_bad_ota_download_falls_back_once_to_same_target_full(self):
        responses = [
            (self.response(b"broken"), "unused"),
            (self.response(self.new), "unused"),
        ]
        with (
            patch.object(rp, "_fetch_resource_update_index", return_value=self.index()),
            patch.object(rp, "request_download", side_effect=responses) as download,
        ):
            self.assertEqual(rp.download_resource_pkg(), self.new)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(
            download.call_args.args[2],
            f"https://github.com/ArkMowers/MowerResource/releases/download/{TARGET}/resource.zip",
        )

    def test_bad_full_download_fails_without_partial_install(self):
        with (
            patch.object(rp, "_fetch_resource_update_index", return_value=self.index()),
            patch.object(
                rp,
                "request_download",
                side_effect=[
                    (self.response(b"broken"), "unused"),
                    (self.response(b"broken"), "unused"),
                ],
            ) as download,
        ):
            self.assertIsNone(rp.download_resource_pkg())
        self.assertEqual(download.call_count, 2)
        self.assertEqual(self.installed_version(), BASE)

    def test_job_ota_reconstruction_failure_downloads_same_target_full(self):
        rp.resource_pkg_path("ui/public/avatar/x.webp").write_bytes(b"FAIL")
        job = ResourceUpdateJob()
        with patch.object(
            rp, "download_resource_pkg", side_effect=[self.delta, self.new]
        ) as download:
            job.run(None)
        self.assertEqual(job.snapshot()["status"], "success")
        self.assertEqual(download.call_count, 2)
        self.assertFalse(download.call_args.kwargs["prefer_ota"])
        self.assertIn(
            f"/{TARGET}/resource.zip", download.call_args.kwargs["asset"]["url"]
        )
        self.assert_target()

    def test_manual_ota_is_offline_and_wrong_base_never_downloads(self):
        with patch.object(
            rp,
            "request_download",
            side_effect=AssertionError("manual OTA must remain offline"),
        ):
            invalid = change_manifest(
                self.delta, lambda m: m.update({"from": "v2026.08.21-eeeeeee"})
            )
            self.assertFalse(manual_update.apply_manual_update(invalid)["ok"])
            result = manual_update.apply_manual_update(self.delta)
        self.assertTrue(result["ok"])
        self.assertFalse(result["restart_required"])
        self.assert_target()

    def test_failed_resource_cache_reload_rolls_back_index_after_ota(self):
        before = (self.overlay / "index.json").read_bytes()
        with patch.object(
            rp,
            "reload_resource_caches",
            side_effect=[RuntimeError("broken cache"), None],
        ):
            self.assertFalse(rp.install_resource_pkg(self.delta))
        self.assertEqual((self.overlay / "index.json").read_bytes(), before)
        self.assertEqual(self.installed_version(), BASE)

    def test_no_metadata_keeps_legacy_download_url(self):
        with patch.object(
            rp, "request_download", return_value=(self.response(self.new), "unused")
        ) as download:
            self.assertEqual(rp.download_resource_pkg(), self.new)
        self.assertEqual(download.call_args.args[2], rp.RESOURCE_ZIP_URL)


def test_metadata_reader_is_bounded_and_bad_format_is_ignored():
    for data in (b"x" * (65536 + 1), b"{}", b"not-json"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [data]
        with patch.object(rp, "request_download", return_value=(response, "unused")):
            assert rp._fetch_resource_update_index() is None


def test_metadata_reader_accepts_valid_index_and_ignores_expired_stream():
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b'{"format": 1, "ota": []}']
    with patch.object(rp, "request_download", return_value=(response, "unused")):
        assert rp._fetch_resource_update_index() == {"format": 1, "ota": []}
    response.iter_content.return_value = [b'{"format": 1, "ota": []}']
    with (
        patch.object(rp, "request_download", return_value=(response, "unused")),
        patch.object(rp.time, "monotonic", side_effect=[0, 31]),
    ):
        assert rp._fetch_resource_update_index() is None
