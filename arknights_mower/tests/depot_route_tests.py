import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from arknights_mower.utils import depot
from arknights_mower.utils import resource_pkg as rp


class DepotRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.client = server.app.test_client()

    def test_depot_api_returns_inventory_with_active_resource_package(self):
        inventory = [
            {"A常用": {"龙门币": {"number": 123, "sort": 1, "icon": "龙门币"}}},
            '{"4001": 123}',
            "2026-09-08 12:00:00",
        ]
        with (
            patch.object(rp, "resource_ui_path", return_value=self.root),
            patch.object(depot, "读取仓库", return_value=inventory) as read_inventory,
            patch.object(server, "get_path", return_value=self.root / "cultivate.json"),
        ):
            response = self.client.get("/depot/readdepot")

        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(response.get_json()["depot"], inventory)
        self.assertFalse(response.get_json()["cultivate_ok"])
        read_inventory.assert_called_once_with()

    def test_resource_images_still_use_active_package(self):
        for directory in ("depot", "avatar", "building_skill"):
            with self.subTest(directory=directory):
                image = self.root / directory / "test.webp"
                image.parent.mkdir()
                image.write_bytes(b"resource image")
                with patch.object(rp, "resource_ui_path", return_value=self.root):
                    response = self.client.get(f"/{directory}/test.webp")
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, b"resource image")
                    self.assertEqual(response.mimetype, "image/webp")
                    self.assertEqual(response.headers["Cache-Control"], "no-cache")
                finally:
                    response.close()


if __name__ == "__main__":
    unittest.main()
