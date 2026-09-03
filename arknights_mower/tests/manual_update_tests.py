import io
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from arknights_mower.utils import manual_update


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return buf.getvalue()


class TestApplyManualUpdate(unittest.TestCase):
    def test_applies_resource_package(self):
        data = _zip_bytes({"arknights_mower/data/version.json": '{"res_version":"v1"}'})
        with patch.object(manual_update, "install_resource_pkg", return_value=True):
            got = manual_update.apply_manual_update(data)
        self.assertEqual(got["kind"], "resource")
        self.assertTrue(got["ok"])

    def test_resource_package_honors_busy_response(self):
        data = _zip_bytes({"arknights_mower/data/version.json": '{"res_version":"v1"}'})

        def busy():
            return {"ok": False, "message": "busy"}

        with patch.object(
            manual_update,
            "install_resource_pkg",
            side_effect=AssertionError("busy 时不应安装"),
        ):
            got = manual_update.apply_manual_update(data, busy)
        self.assertEqual(got, {"ok": False, "message": "busy", "kind": "resource"})

    def test_applies_hot_update_package(self):
        data = _zip_bytes({"nav_steps.json": "{}"})
        with patch.object(
            manual_update.hot_update, "apply_manual_zip", return_value=True
        ):
            got = manual_update.apply_manual_update(data)
        self.assertEqual(
            got, {"ok": True, "kind": "hot_update", "message": "热更包已应用"}
        )

    def test_invalid_zip_is_rejected(self):
        got = manual_update.apply_manual_update(b"not a zip")
        self.assertFalse(got["ok"])
        self.assertEqual(got["kind"], "unknown")


if __name__ == "__main__":
    unittest.main()
