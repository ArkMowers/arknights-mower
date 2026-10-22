import gzip
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
        pages_patch = patch.object(
            server, "frontend_pages", server._load_frontend_pages()
        )
        pages_patch.start()
        self.addCleanup(pages_patch.stop)
        self.client = server.app.test_client()

    def get(self, path, **kwargs):
        response = self.client.get(path, **kwargs)
        self.addCleanup(response.close)
        return response

    def static_file(self, path, body):
        target = self.root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return target

    def test_hashed_build_assets_are_public_and_immutable(self):
        for path, body in (
            ("/assets/main-Ab1_cd-2.js", b"console.log('mower');"),
            ("/assets/incomeWorker-BNIl5NnI.js", b"postMessage('mower');"),
            ("/assets/main-DJbKay_B.css", b"body { color: red; }"),
            ("/assets/logo-Ef5_gh-6.svg", b"<svg></svg>"),
            ("/assets/contact-Du2PVZeF.png", b"image fixture"),
        ):
            self.static_file(path, body)
            for method in ("get", "head"):
                for headers in ({}, {"token": "invalid"}):
                    with (
                        self.subTest(path=path, method=method, headers=headers),
                        patch.object(
                            server.app, "token", "fixture-secret", create=True
                        ),
                        getattr(self.client, method)(
                            path,
                            headers=headers,
                            environ_base={"REMOTE_ADDR": "192.0.2.1"},
                        ) as response,
                    ):
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            response.data, body if method == "get" else b""
                        )
                        self.assertEqual(
                            response.headers["Cache-Control"],
                            "public, max-age=31536000, immutable",
                        )

    def test_hashed_asset_gzip_and_identity_keep_separate_representations(self):
        path = "/assets/main-Ab1_cd-2.js"
        body = b"console.log('mower');"
        source = self.static_file(path, body)
        source.with_suffix(".js.gz").write_bytes(gzip.compress(body))
        for encoding in ("identity", "gzip", "gzip;q=0"):
            for method in ("get", "head"):
                with (
                    self.subTest(encoding=encoding, method=method),
                    getattr(self.client, method)(
                        path, headers={"Accept-Encoding": encoding}
                    ) as response,
                ):
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.cache_control.max_age, 31536000)
                    self.assertTrue(response.cache_control.immutable)
                    self.assertIn("Accept-Encoding", response.vary)
                    if encoding == "gzip":
                        self.assertEqual(response.headers["Content-Encoding"], "gzip")
                        self.assertNotIn("ETag", response.headers)
                        if method == "get":
                            self.assertEqual(gzip.decompress(response.data), body)
                    else:
                        self.assertNotIn("Content-Encoding", response.headers)
                        self.assertIn("ETag", response.headers)
                        if method == "get":
                            self.assertEqual(response.data, body)
                    if method == "head":
                        self.assertEqual(response.data, b"")

    def test_hashed_asset_not_modified_keeps_cache_and_encoding_variance(self):
        path = "/assets/main-Ab1_cd-2.js"
        body = b"console.log('mower');"
        source = self.static_file(path, body)
        source.with_suffix(".js.gz").write_bytes(gzip.compress(body))
        identity = self.get(path)
        for headers in (
            {"If-None-Match": identity.headers["ETag"]},
            {
                "Accept-Encoding": "gzip",
                "If-Modified-Since": identity.headers["Last-Modified"],
            },
            {"Accept-Encoding": "gzip", "If-None-Match": "*"},
        ):
            with self.subTest(headers=headers):
                response = self.get(path, headers=headers)
                self.assertEqual(response.status_code, 304)
                self.assertEqual(response.data, b"")
                self.assertEqual(response.cache_control.max_age, 31536000)
                self.assertTrue(response.cache_control.immutable)
                self.assertIn("Accept-Encoding", response.vary)
                if headers.get("Accept-Encoding") == "gzip":
                    self.assertNotIn("ETag", response.headers)

    def test_identity_etag_does_not_validate_gzip_bytes(self):
        path = "/assets/main-Ab1_cd-2.js"
        body = b"console.log('mower');"
        source = self.static_file(path, body)
        source.with_suffix(".js.gz").write_bytes(gzip.compress(body))
        identity = self.get(path)
        response = self.get(
            path,
            headers={
                "Accept-Encoding": "gzip",
                "If-None-Match": identity.headers["ETag"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(response.data), body)
        self.assertNotIn("ETag", response.headers)
        self.assertIn("Accept-Encoding", response.vary)

    def test_public_asset_variants_keep_the_same_token_boundary(self):
        path = "/assets/main-Ab1_cd-2.js"
        body = b"console.log('mower');"
        source = self.static_file(path, body)
        source.with_suffix(".js.gz").write_bytes(gzip.compress(body))
        identity = self.get(path)
        variants = (
            (path, {}, 200),
            (path, {"Accept-Encoding": "gzip"}, 200),
            (path, {"If-None-Match": identity.headers["ETag"]}, 304),
            (
                path,
                {
                    "Accept-Encoding": "gzip",
                    "If-Modified-Since": identity.headers["Last-Modified"],
                },
                304,
            ),
            ("/assets/missing-Ab1_cd-2.js", {"Accept-Encoding": "gzip"}, 404),
        )
        with patch.object(server.app, "token", "fixture-secret", create=True):
            for method in ("get", "head"):
                for token in (None, "invalid"):
                    for request_path, headers, status in variants:
                        if token is not None:
                            headers = {**headers, "token": token}
                        with (
                            self.subTest(method=method, token=token, headers=headers),
                            getattr(self.client, method)(
                                request_path,
                                headers=headers,
                                environ_base={"REMOTE_ADDR": "192.0.2.1"},
                            ) as response,
                        ):
                            self.assertEqual(response.status_code, status)
                            self.assertEqual(
                                response.cache_control.immutable, status != 404
                            )
                            if status != 404:
                                self.assertIn("Accept-Encoding", response.vary)

    def test_asset_caching_does_not_weaken_protected_api_requests(self):
        from arknights_mower.__main__ import device_control

        for method in ("get", "head"):
            for token in (None, "invalid", "fixture-secret"):
                headers = {"Accept-Encoding": "gzip", "If-None-Match": "*"}
                if token is not None:
                    headers["token"] = token
                with (
                    self.subTest(method=method, token=token),
                    patch.object(server.app, "token", "fixture-secret", create=True),
                    patch.object(
                        device_control,
                        "settings_status",
                        return_value={"active": False},
                    ) as read_status,
                    getattr(self.client, method)(
                        "/device/status",
                        headers=headers,
                        environ_base={"REMOTE_ADDR": "192.0.2.1"},
                    ) as response,
                ):
                    self.assertFalse(response.cache_control.immutable)
                    self.assertIsNone(response.cache_control.max_age)
                    if token == "fixture-secret":
                        self.assertEqual(response.status_code, 200)
                        read_status.assert_called_once_with()
                    else:
                        self.assertEqual(response.status_code, 403)
                        read_status.assert_not_called()

    def test_unversioned_files_and_html_keep_revalidation(self):
        paths = (
            "/assets/main.js",
            "/assets/main-dev.js",
            "/assets/main-Abcdefg.js",
            "/assets/main-Abcdefghi.js",
            "/assets/manual-Ab1_cd-2.html",
            "/other/main-Ab1_cd-2.js",
            "/bg.webp",
        )
        for path in paths:
            self.static_file(path, b"unversioned fixture")
        for path in (*paths, "/", "/index.html", "/plan-editor"):
            with self.subTest(path=path):
                response = self.get(path, headers={"Accept": "text/html"})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.cache_control.immutable)
                self.assertIsNone(response.cache_control.max_age)
                self.assertTrue(response.cache_control.no_cache)

    def test_resource_overlay_never_becomes_immutable(self):
        path = "/avatar/operator-Ab1_cd-2.webp"
        package = self.root / "package"
        (package / "avatar").mkdir(parents=True)
        (package / path.lstrip("/")).write_bytes(b"package avatar")
        with patch.object(rp, "resource_ui_path", return_value=package):
            response = self.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"package avatar")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")

    def test_missing_hashed_assets_and_error_responses_are_not_immutable(self):
        path = "/assets/main-Ab1_cd-2.js"
        missing = self.get(path, headers={"Accept-Encoding": "gzip"})
        self.assertEqual(missing.status_code, 404)
        self.assertFalse(missing.cache_control.immutable)
        self.assertIsNone(missing.cache_control.max_age)
        self.static_file(path, b"console.log('mower');")
        for status in (403, 500):
            with (
                self.subTest(status=status),
                patch.dict(
                    server.app.view_functions,
                    {"static": lambda **kwargs: ("asset error", status)},
                ),
            ):
                response = self.get(path)
                self.assertEqual(response.status_code, status)
                self.assertFalse(response.cache_control.immutable)
                self.assertIsNone(response.cache_control.max_age)

    def test_asset_like_html_and_non_file_responses_are_not_immutable(self):
        path = "/assets/main-Ab1_cd-2.js"
        source = self.static_file(path, b"console.log('mower');")
        for mimetype in ("text/html", "application/javascript"):
            if mimetype == "application/javascript":
                source.unlink()
            with (
                self.subTest(mimetype=mimetype),
                patch.dict(
                    server.app.view_functions,
                    {
                        "static": lambda mimetype=mimetype, **kwargs: (
                            server.app.response_class(self.shell, mimetype=mimetype)
                        )
                    },
                ),
            ):
                response = self.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.cache_control.immutable)
                self.assertIsNone(response.cache_control.max_age)

    def test_frontend_pages_refresh_with_query_trailing_slash_and_case(self):
        for page in self.pages:
            for path in {page, page.upper(), page.rstrip("/") + "/?token=fixture"}:
                with self.subTest(path=path):
                    response = self.get(
                        path,
                        headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, self.shell)
                    self.assertEqual(response.mimetype, "text/html")
                    with self.client.head(
                        path,
                        headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
                    ) as head:
                        self.assertEqual(head.status_code, 200)
                        self.assertEqual(head.data, b"")
                        self.assertEqual(head.mimetype, "text/html")

    def test_page_api_collision_preserves_api_dispatch_and_cache_variants(self):
        def api():
            return {"has_data": True}

        with patch.dict(server.app.view_functions, {"mastery_recommendation": api}):
            for headers in (
                {},
                {"Accept": "*/*"},
                {"Accept": "application/json, text/plain, */*"},
                {"Accept": "text/html;q=0,*/*"},
                {"Accept": "text/html", "Sec-Fetch-Dest": "empty"},
                {"Accept": "text/html", "Sec-Fetch-Dest": "image"},
            ):
                with self.subTest(headers=headers):
                    response = self.get("/mastery-recommendation", headers=headers)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json(), {"has_data": True})
                    self.assertTrue({"Accept", "Sec-Fetch-Dest"} <= set(response.vary))
            for destination in (None, "document", "iframe"):
                headers = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
                if destination is not None:
                    headers["Sec-Fetch-Dest"] = destination
                with self.subTest(destination=destination):
                    response = self.get("/mastery-recommendation", headers=headers)
                    self.assertEqual(response.data, self.shell)
                    self.assertTrue({"Accept", "Sec-Fetch-Dest"} <= set(response.vary))

    def test_navigation_does_not_intercept_non_read_methods(self):
        with self.client.post(
            "/mastery-recommendation",
            headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
        ) as response:
            self.assertEqual(response.status_code, 405)
            self.assertNotEqual(response.data, self.shell)

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
        pages = server._load_frontend_pages()
        self.assertEqual(pages, frozenset(page.lower() for page in self.pages))
        pages_patch = patch.object(server, "frontend_pages", pages)
        pages_patch.start()
        self.addCleanup(pages_patch.stop)
        self.assertEqual(self.get("/record/depot").data, self.shell)
        self.assertEqual(
            self.get(
                "/mastery-recommendation",
                headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
            ).data,
            self.shell,
        )

    def test_dispatch_does_not_read_manifest_during_requests(self):
        with (
            patch.dict(
                server.app.view_functions,
                {"mastery_recommendation": lambda: {"has_data": True}},
            ),
            patch.object(
                Path, "open", side_effect=AssertionError("request reads disk")
            ),
        ):
            for _ in range(2):
                response = self.get(
                    "/mastery-recommendation", headers={"Accept": "application/json"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"has_data": True})
            response = self.get(
                "/mastery-recommendation",
                headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, self.shell)

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
