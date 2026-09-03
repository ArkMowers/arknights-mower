import io
import json
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from arknights_mower import __rootdir__
from arknights_mower.utils import resource_pkg as rp


def _zip_bytes(entries=None, marker=True):
    buf = io.BytesIO()
    base = {
        "arknights_mower/data/version.json": json.dumps(
            {"res_version": "v2026.08.23-aaaaaaa"}
        ),
        "arknights_mower/data/key_mapping.json": '{"1": "固源岩"}',
        "ui/public/depot/x.webp": "WEBP",
    }
    if entries is not None:
        base.update(entries)
    if not marker:
        base.pop("arknights_mower/data/version.json", None)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in base.items():
            z.writestr(name, content)
    return buf.getvalue()


class ResourcePkgTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.overlay = self.base / "resource"
        self.staging = self.base / "resource_staging"
        self.old = self.base / "resource_old"
        self._patch = ExitStack()
        self._patch.enter_context(patch.object(rp, "RESOURCE_OVERLAY", self.overlay))
        self._patch.enter_context(patch.object(rp, "_STAGING", self.staging))
        self._patch.enter_context(patch.object(rp, "_OLD", self.old))
        self.addCleanup(self._patch.close)


class TestResourcePkgPath(ResourcePkgTestBase):
    def test_overlay_first_when_present(self):
        (self.overlay / "arknights_mower/data/key_mapping.json").parent.mkdir(
            parents=True, exist_ok=True
        )
        (self.overlay / "arknights_mower/data/key_mapping.json").write_text(
            "{}", encoding="utf-8"
        )
        got = rp.resource_pkg_path("arknights_mower/data/key_mapping.json")
        self.assertEqual(got, self.overlay / "arknights_mower/data/key_mapping.json")

    def test_fallback_to_builtin(self):
        got = rp.resource_pkg_path("arknights_mower/data/key_mapping.json")
        self.assertEqual(got, Path(__rootdir__) / "data/key_mapping.json")


class TestInstallResourcePkg(ResourcePkgTestBase):
    def test_missing_marker_rejected(self):
        self.assertFalse(rp.install_resource_pkg(_zip_bytes(marker=False)))
        self.assertFalse(self.overlay.exists())

    def test_zip_slip_rejected(self):
        data = _zip_bytes(entries={"../evil.txt": "x"})
        self.assertFalse(rp.install_resource_pkg(data))
        self.assertFalse(self.overlay.exists())

    def test_valid_install(self):
        self.assertTrue(rp.install_resource_pkg(_zip_bytes()))
        self.assertTrue((self.overlay / "arknights_mower/data/version.json").is_file())
        self.assertTrue((self.overlay / "ui/public/depot/x.webp").is_file())
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.old.exists())

    def test_replaces_previous_overlay(self):
        self.assertTrue(rp.install_resource_pkg(_zip_bytes()))
        new = _zip_bytes(
            entries={
                "arknights_mower/data/version.json": json.dumps(
                    {"res_version": "v2026.08.24-bbbbbbb"}
                )
            }
        )
        self.assertTrue(rp.install_resource_pkg(new))
        raw = (self.overlay / "arknights_mower/data/version.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("v2026.08.24-bbbbbbb", raw)

    def test_rollback_on_swap_failure(self):
        # 旧 overlay 先就位
        self.assertTrue(rp.install_resource_pkg(_zip_bytes()))
        old_marker = (self.overlay / "arknights_mower/data/version.json").read_text(
            encoding="utf-8"
        )

        real_replace = __import__("os").replace
        calls = []

        def fake_replace(src, dst):
            calls.append((Path(src).name, Path(dst).name))
            if len(calls) == 2:  # staging -> resource 这一步失败
                raise OSError("simulated swap failure")
            return real_replace(src, dst)

        with patch.object(rp.os, "replace", side_effect=fake_replace):
            ok = rp.install_resource_pkg(_zip_bytes())
        self.assertFalse(ok)
        # 旧 overlay 被回滚恢复
        self.assertTrue(self.overlay.exists())
        self.assertEqual(
            (self.overlay / "arknights_mower/data/version.json").read_text(
                encoding="utf-8"
            ),
            old_marker,
        )
        self.assertFalse(self.old.exists())


if __name__ == "__main__":
    unittest.main()
