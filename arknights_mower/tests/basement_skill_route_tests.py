import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class TestBasementSkillRoute(unittest.TestCase):
    """基建技能路由共享后端数据，缺失数据返回 404。"""

    def setUp(self):
        self.client = server.app.test_client()
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_returns_json_with_no_cache_when_resource_installed(self):
        (self.base / "skill.json").write_text('{"name": "sample"}', encoding="utf-8")
        with patch(
            "arknights_mower.utils.resource_pkg.resource_pkg_path",
            return_value=self.base / "skill.json",
        ):
            resp = self.client.get("/basement_skill/skill.json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), '{"name": "sample"}')
        self.assertEqual(resp.headers["Cache-Control"], "no-cache")

    def test_404_when_selected_skill_data_is_missing(self):
        with patch(
            "arknights_mower.utils.resource_pkg.resource_pkg_path",
            return_value=self.base / "missing.json",
        ):
            resp = self.client.get("/basement_skill/skill.json")
        self.assertEqual(resp.status_code, 404)

    def test_missing_file_does_not_fall_back_to_html_or_builtin(self):
        with patch(
            "arknights_mower.utils.resource_pkg.resource_pkg_path",
            return_value=self.base / "missing.json",
        ):
            self.assertEqual(
                self.client.get("/basement_skill/skill.json").status_code, 404
            )
            self.assertEqual(self.client.get("/depot/missing.webp").status_code, 404)

    def test_builtin_shared_data_keeps_the_existing_http_filename(self):
        data = self.base / "building_skill.json"
        data.write_text("[]")
        with patch(
            "arknights_mower.utils.resource_pkg.resource_pkg_path", return_value=data
        ):
            response = self.client.get("/basement_skill/skill.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])


if __name__ == "__main__":
    unittest.main()
