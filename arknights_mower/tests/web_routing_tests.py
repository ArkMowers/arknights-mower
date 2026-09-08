import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import abort

import server
from arknights_mower.utils import resource_pkg as rp


class WebRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.shell = b"<html>mower fixture</html>"
        (self.root / "index.html").write_bytes(self.shell)
        manifest = Path(server.__file__).parent / "ui/public/frontend-routes.json"
        (self.root / manifest.name).write_bytes(manifest.read_bytes())
        self.pages = json.loads(manifest.read_text("utf-8"))
        for mock in (
            patch.object(server.app, "_static_folder", str(self.root)),
            patch.object(rp, "resource_ui_path", return_value=None),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        self.client = server.app.test_client()

    def get(self, path, **kwargs):
        response = self.client.get(path, **kwargs)
        self.addCleanup(response.close)
        return response

    def test_frontend_pages_refresh_with_query_trailing_slash_and_case(self):
        # /mastery-recommendation 已有同名 API，由原接口处理，不经过页面 404 兜底。
        for page in self.pages:
            if page == "/mastery-recommendation":
                continue
            for path in {page, page.upper(), page.rstrip("/") + "/?token=fixture"}:
                with self.subTest(path=path):
                    response = self.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, self.shell)
        with self.client.head("/record/depot") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"")

    def test_unknown_apis_and_missing_assets_remain_404_even_for_browser_navigation(
        self,
    ):
        for path in (
            "/report/nonexistent-api",
            "/record/nonexistent-api",
            "/depot/nonexistent-api",
            "/assets/missing.js",
            "/avatar/missing.webp",
            "/building_skill/missing.webp",
            "/missing.css",
        ):
            for accept in ("application/json, text/plain, */*", "text/html", "*/*"):
                with self.subTest(path=path, accept=accept):
                    response = self.get(path, headers={"Accept": accept})
                    self.assertEqual(response.status_code, 404)
                    self.assertNotEqual(response.data, self.shell)

    def test_existing_api_not_found_is_not_replaced_by_spa(self):
        def missing():
            abort(404)

        with patch.dict(server.app.view_functions, {"load_config": missing}):
            for method in ("get", "post"):
                with getattr(self.client, method)(
                    "/conf", headers={"Accept": "text/html"}
                ) as response:
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.get_json(), {"error": "Not Found"})

    def test_unknown_frontend_navigation_retains_vue_not_found_page(self):
        response = self.get(
            "/unknown-page",
            headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.shell)
        for headers in (
            {},
            {"Accept": "*/*"},
            {"Accept": "application/json"},
            {"Accept": "text/html;q=0,*/*"},
            {"Accept": "text/html", "Sec-Fetch-Dest": "image"},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(
                    self.get("/unknown-page", headers=headers).status_code, 404
                )

    def test_docs_directory_index_and_static_files_are_preserved(self):
        (self.root / "docs/guide").mkdir(parents=True)
        (self.root / "docs/guide/index.html").write_bytes(b"guide")
        (self.root / "docs/manual.html").write_bytes(b"manual")
        (self.root / "app.js").write_bytes(b"app")
        for path, body in (
            ("/docs/guide", b"guide"),
            ("/docs/guide/", b"guide"),
            ("/docs/manual.html", b"manual"),
            ("/app.js", b"app"),
        ):
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, body)
        self.assertEqual(self.get("/docs/missing").status_code, 404)

    def test_source_checkout_with_older_frontend_uses_source_route_manifest(self):
        (self.root / "frontend-routes.json").unlink()
        self.assertEqual(self.get("/record/depot").data, self.shell)

    def test_builtin_images_remain_available_without_external_package(self):
        (self.root / "avatar").mkdir()
        (self.root / "avatar/operator.webp").write_bytes(b"builtin avatar")
        response = self.get("/avatar/operator.webp")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"builtin avatar")

    def test_missing_external_image_does_not_mix_in_builtin_version(self):
        (self.root / "avatar").mkdir()
        (self.root / "avatar/operator.webp").write_bytes(b"builtin avatar")
        with patch.object(rp, "resource_ui_path", return_value=self.root / "package"):
            response = self.get("/avatar/operator.webp")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"builtin avatar", response.data)


if __name__ == "__main__":
    unittest.main()
