"""运行日志背景图的访问、持久保存和恢复默认。"""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from PIL import Image

from arknights_mower.utils import log_background
from arknights_mower.utils.config import gui
from arknights_mower.views.gui import gui_bp


def image_bytes(format="PNG", color="red", size=(40, 24)):
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format=format)
    return stream.getvalue()


class LogBackgroundTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config" / "gui.yml"
        self.enterContext(patch.object(gui, "gui_path", self.path))
        self.app = Flask(__name__)
        self.app.token = "background-token"
        self.app.register_blueprint(gui_bp)
        self.client = self.app.test_client()
        self.headers = {"token": self.app.token}
        self.image_path = self.path.parent / "log-background.webp"

    def upload(self, content=None, **kwargs):
        return self.client.put(
            "/gui/log-background",
            data=image_bytes() if content is None else content,
            headers=self.headers,
            content_type="image/png",
            **kwargs,
        )

    def test_default_upload_replace_and_reset(self):
        self.assertEqual(
            self.client.get("/gui/log-background", headers=self.headers).status_code,
            204,
        )
        gui.save_window_mode("maximized")
        before_gui = self.path.read_bytes()
        for format, color in (("PNG", "red"), ("JPEG", "green"), ("WEBP", "blue")):
            with self.subTest(format=format):
                uploaded = self.upload(image_bytes(format, color))
                self.assertEqual(uploaded.status_code, 200)
                self.assertEqual(uploaded.content_type, "image/webp")
                self.assertEqual(uploaded.headers["Cache-Control"], "no-store")
                self.assertEqual(self.image_path.read_bytes(), uploaded.data)
                with Image.open(BytesIO(uploaded.data)) as image:
                    self.assertEqual(image.format, "WEBP")
                    self.assertEqual(image.size, (40, 24))
                read = self.client.get("/gui/log-background", headers=self.headers)
                self.assertEqual(read.data, uploaded.data)
                self.assertEqual(self.path.read_bytes(), before_gui)
        for _ in range(2):
            reset = self.client.delete("/gui/log-background", headers=self.headers)
            self.assertEqual(reset.status_code, 204)
            self.assertFalse(self.image_path.exists())
            self.assertEqual(log_background.load(), None)
        self.assertEqual(self.path.read_bytes(), before_gui)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_missing_and_invalid_tokens_precede_all_parsing_and_filesystem_work(self):
        for method, operation in (
            ("GET", "load"),
            ("HEAD", "load"),
            ("PUT", "save"),
            ("DELETE", "reset"),
        ):
            for headers in ({}, {"token": "other-instance"}):
                with (
                    self.subTest(method=method, headers=headers),
                    patch.object(log_background, operation) as action,
                    patch.object(log_background, "_encode") as parse,
                ):
                    response = self.client.open(
                        "/gui/log-background",
                        method=method,
                        headers=headers,
                        data=b"bad",
                    )
                    self.assertEqual(response.status_code, 403)
                    action.assert_not_called()
                    parse.assert_not_called()
        self.assertFalse(self.path.parent.exists())

    def test_authenticated_head_and_preflight_keep_the_existing_gui_boundary(self):
        self.upload()
        response = self.client.head("/gui/log-background", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/webp")
        self.assertEqual(response.data, b"")
        for method in ("GET", "HEAD", "PUT", "DELETE"):
            with (
                self.subTest(method=method),
                patch.object(log_background, "load") as read,
            ):
                allowed = self.client.options(
                    "/gui/log-background",
                    headers={
                        "Origin": "http://localhost",
                        "Access-Control-Request-Method": method,
                    },
                )
                self.assertEqual(allowed.status_code, 200)
                denied = self.client.options(
                    "/gui/log-background",
                    headers={
                        "Origin": "http://untrusted.invalid",
                        "Access-Control-Request-Method": method,
                    },
                )
                self.assertEqual(denied.status_code, 403)
                read.assert_not_called()

    def test_indexed_png_transparency_survives_reencoding(self):
        image = Image.new("P", (3, 2))
        image.putpalette([255, 0, 0, 0, 255, 0] + [0] * (768 - 6))
        image.putpixel((1, 0), 1)
        raw = BytesIO()
        image.save(raw, format="PNG", transparency=0)
        response = self.upload(raw.getvalue())
        self.assertEqual(response.status_code, 200)
        with Image.open(BytesIO(response.data)) as decoded:
            alpha = decoded.convert("RGBA").getchannel("A")
            self.assertEqual(alpha.getpixel((0, 0)), 0)
            self.assertEqual(alpha.getpixel((1, 0)), 255)

    def test_long_images_fit_the_webp_limit_without_enlarging_smaller_images(self):
        for original, expected in (
            ((40, 20), (40, 20)),
            ((20, 40), (20, 40)),
            ((39, 20), (39, 20)),
            ((20, 39), (20, 39)),
            ((41, 20), (40, 20)),
            ((20, 41), (20, 40)),
            ((80, 40), (40, 20)),
            ((40, 80), (20, 40)),
        ):
            with (
                self.subTest(original=original),
                patch.object(log_background, "MAX_WEBP_DIMENSION", 40),
            ):
                response = self.upload(image_bytes(size=original))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.image_path.read_bytes(), response.data)
                with Image.open(BytesIO(response.data)) as decoded:
                    self.assertEqual(decoded.size, expected)

    def test_resizing_keeps_exif_orientation_and_transparency(self):
        source = Image.new("RGBA", (80, 40), (255, 0, 0, 96))
        exif = source.getexif()
        exif[274] = 6
        raw = BytesIO()
        source.save(raw, format="PNG", exif=exif)
        with patch.object(log_background, "MAX_WEBP_DIMENSION", 40):
            response = self.upload(raw.getvalue())
        self.assertEqual(response.status_code, 200)
        with Image.open(BytesIO(response.data)) as decoded:
            self.assertEqual(decoded.size, (20, 40))
            self.assertEqual(
                decoded.convert("RGBA").getchannel("A").getextrema(), (96, 96)
            )

    def test_encoder_errors_keep_the_saved_image_and_return_a_readable_message(self):
        self.upload()
        before = self.image_path.read_bytes()
        raw = image_bytes(color="blue")
        with patch.object(
            Image.Image, "save", side_effect=ValueError("encoding error 5")
        ):
            response = self.upload(raw)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json["message"], "图片无法转换为背景图，请选择其他图片"
        )
        self.assertEqual(self.image_path.read_bytes(), before)
        self.assertEqual(self.upload(raw).status_code, 200)
        self.assertNotEqual(self.image_path.read_bytes(), before)

    def test_unknown_length_uploads_are_bounded_and_not_read_without_authentication(
        self,
    ):
        limit = log_background.MAX_IMAGE_BYTES
        for headers, status in (
            (self.headers, 413),
            ({}, 403),
            ({"token": "wrong"}, 403),
        ):
            stream = BytesIO(b"x" * (limit + 2))
            with (
                self.subTest(headers=headers),
                patch.object(log_background, "_encode") as decode,
            ):
                response = self.client.put(
                    "/gui/log-background",
                    headers=headers,
                    content_type="image/png",
                    environ_overrides={
                        "CONTENT_LENGTH": "",
                        "wsgi.input_terminated": True,
                        "wsgi.input": stream,
                    },
                )
                self.assertEqual(response.status_code, status)
                self.assertEqual(stream.tell(), limit + 1 if status == 413 else 0)
                decode.assert_not_called()

    def test_invalid_content_and_decoded_pixel_limits_keep_the_saved_image(self):
        self.upload()
        before = self.image_path.read_bytes()
        for content in (
            b"not an image",
            b"<svg></svg>",
            image_bytes("GIF"),
            image_bytes()[:30],
        ):
            with self.subTest(content=content[:20]):
                self.assertEqual(self.upload(content).status_code, 400)
                self.assertEqual(self.image_path.read_bytes(), before)
        with patch.object(log_background, "MAX_IMAGE_PIXELS", 100):
            self.assertEqual(self.upload().status_code, 400)
        with patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            self.assertEqual(self.upload().status_code, 400)
        animated = BytesIO()
        Image.new("RGB", (10, 10), "red").save(
            animated,
            format="WEBP",
            save_all=True,
            append_images=[Image.new("RGB", (10, 10), "blue")],
            duration=100,
        )
        self.assertEqual(self.upload(animated.getvalue()).status_code, 400)
        self.assertEqual(self.image_path.read_bytes(), before)

    def test_oversized_requests_never_decode_or_replace_the_image(self):
        self.upload()
        before = self.image_path.read_bytes()
        with patch.object(log_background, "_encode") as decode:
            response = self.upload(b"x" * (log_background.MAX_IMAGE_BYTES + 1))
        self.assertEqual(response.status_code, 413)
        decode.assert_not_called()
        self.assertEqual(self.image_path.read_bytes(), before)

    def test_storage_failures_preserve_image_and_allow_retry(self):
        self.upload()
        before = self.image_path.read_bytes()
        with patch.object(gui, "atomic_write", side_effect=OSError("disk full")):
            self.assertEqual(self.upload(image_bytes(color="blue")).status_code, 503)
        self.assertEqual(self.image_path.read_bytes(), before)
        with patch.object(gui, "_gui_file_lock", side_effect=TimeoutError("busy")):
            response = self.client.delete("/gui/log-background", headers=self.headers)
            self.assertEqual(response.status_code, 503)
        self.assertEqual(self.image_path.read_bytes(), before)
        self.assertEqual(self.upload(image_bytes(color="blue")).status_code, 200)
        self.assertNotEqual(self.image_path.read_bytes(), before)

    def test_real_server_does_not_apply_profile_generation_to_background(self):
        with patch("arknights_mower.utils.network_settings.start_proxy_sync"):
            import server

        with (
            patch.object(server.app, "token", self.app.token, create=True),
            patch(
                "arknights_mower.utils.config_profiles.check_generation",
                side_effect=AssertionError(
                    "GUI preferences are independent of profiles"
                ),
            ) as check,
        ):
            client = server.app.test_client()
            for method in ("PUT", "GET", "DELETE"):
                response = client.open(
                    "/gui/log-background",
                    method=method,
                    data=image_bytes() if method == "PUT" else None,
                    headers={**self.headers, "X-Mower-Config-Generation": "obsolete"},
                )
                self.assertIn(response.status_code, (200, 204))
            check.assert_not_called()
