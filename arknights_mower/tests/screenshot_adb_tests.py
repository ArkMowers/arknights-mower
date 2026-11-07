"""Raw-frame acceptance and bounded capture at the screenshot adapter seam."""

import unittest
from unittest.mock import patch

import numpy as np

from arknights_mower.tests.screenshot_fixtures import (
    alternate_formats,
    gzip_frame,
    rgba_frame,
)
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.screenshot import (
    MAX_COMPRESSED_BYTES,
    MAX_RAW_BYTES,
    capture_adb_frame,
    decode_adb_frame,
)


class ADBFrameTests(unittest.TestCase):
    def test_decodes_legacy_and_color_space_headers_without_pixel_shift(self):
        for modern in (False, True):
            with self.subTest(modern=modern):
                frame = decode_adb_frame(
                    gzip_frame(rgba_frame(modern=modern)),
                    header_size=16 if modern else 12,
                )
                self.assertEqual(frame.shape, (1080, 1920, 3))
                self.assertEqual(frame.dtype, np.uint8)
                self.assertEqual(frame[0, 0].tolist(), [255, 128, 0])
                self.assertEqual(frame[-1, -1].tolist(), [0, 0, 0])

    def test_decodes_supported_pixel_layouts_to_rgb(self):
        for name, raw in alternate_formats().items():
            with self.subTest(pixel_format=name):
                frame = decode_adb_frame(gzip_frame(raw), header_size=12)
                expected = [255, 130, 0] if name == "rgb565" else [255, 128, 0]
                self.assertEqual(frame[0, 0].tolist(), expected)
                self.assertEqual(frame[-1, -1].tolist(), [0, 0, 0])

    def test_header_version_is_explicit_so_four_byte_truncation_is_rejected(self):
        for modern, size in ((False, 12), (True, 16)):
            raw = rgba_frame(modern=modern)
            for invalid in (raw[:-4], raw + b"\0" * 4):
                with self.subTest(modern=modern, length=len(invalid)):
                    with self.assertRaisesRegex(ValueError, "长度|字节上限"):
                        decode_adb_frame(gzip_frame(invalid), header_size=size)

    def test_rejects_malformed_gzip_headers_dimensions_formats_and_payload(self):
        raw = rgba_frame(modern=True)
        variants = {
            "short header": b"\0" * 11,
            "portrait": bytes.fromhex("38040000 80070000") + raw[8:],
            "wrong width": bytes.fromhex("00050000") + raw[4:],
            "unknown format": raw[:8] + bytes.fromhex("99000000") + raw[12:],
            "unknown color space": raw[:12] + bytes.fromhex("ff000000") + raw[16:],
            "short pixels": raw[:-1],
            "extra pixels": raw + b"\0",
        }
        for name, invalid in variants.items():
            with self.subTest(variant=name), self.assertRaises(ValueError):
                decode_adb_frame(gzip_frame(invalid), header_size=16)
        valid = gzip_frame(raw)
        for invalid in (b"not gzip", valid[:-1], valid + b"garbage", valid + valid):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                decode_adb_frame(invalid, header_size=16)

    def test_black_pixels_are_valid_when_protocol_and_dimensions_are_valid(self):
        for modern in (False, True):
            with self.subTest(modern=modern):
                result = decode_adb_frame(
                    gzip_frame(rgba_frame(modern=modern, black=True)),
                    header_size=16 if modern else 12,
                )
                self.assertFalse(np.any(result))

    def test_limits_both_compressed_and_expanded_bytes(self):
        for invalid in (
            b"\0" * (MAX_COMPRESSED_BYTES + 1),
            gzip_frame(b"\0" * (MAX_RAW_BYTES + 1)),
        ):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                decode_adb_frame(invalid, header_size=16)

    def test_corrupt_gzip_checksum_is_not_a_frame(self):
        data = bytearray(gzip_frame(rgba_frame(modern=True)))
        data[-8] ^= 1
        with self.assertRaisesRegex(ValueError, "解压"):
            decode_adb_frame(bytes(data), header_size=16)


class CaptureSocket:
    def __init__(self, output):
        self.output = bytearray(b"OKAYOKAY" + output)
        self.sent = []
        self.closed = False
        self.timeouts = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        result = bytes(self.output[:size])
        del self.output[:size]
        return result


class ADBCaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=None,
            )
        )

    def test_capture_uses_verified_sdk_layout_and_only_selected_serial(self):
        for sdk, modern in ((b"26\n", False), (b"27\n", True), (b"35\n", True)):
            connections = [
                CaptureSocket(sdk),
                CaptureSocket(gzip_frame(rgba_frame(modern=modern))),
            ]
            with (
                self.subTest(sdk=sdk),
                patch(
                    "arknights_mower.utils.device.screenshot.socket.create_connection",
                    side_effect=connections,
                ),
            ):
                frame = capture_adb_frame("chosen-adb", "chosen-serial")
                self.assertEqual(frame[0, 0].tolist(), [255, 128, 0])
            for connection in connections:
                self.assertTrue(connection.closed)
                self.assertIn(b"host:transport:chosen-serial", connection.sent[0])
                self.assertTrue(
                    all(0 < timeout <= 10 for timeout in connection.timeouts)
                )

    def test_sdk_failure_prevents_frame_capture_and_closes_owned_socket(self):
        for sdk in (b"", b"unknown", b"27\nerror", b"0", b"2" * 65):
            connection = CaptureSocket(sdk)
            with (
                self.subTest(sdk=sdk),
                patch(
                    "arknights_mower.utils.device.screenshot.socket.create_connection",
                    side_effect=[connection],
                ),
                self.assertRaises(ValueError),
            ):
                capture_adb_frame("chosen-adb", "chosen-serial")
            self.assertTrue(connection.closed)

    def test_capture_rejects_native_failure_and_truncated_handshake(self):
        for response in (b"FAIL0007offline", b"OK", b"FAILffff", b"WHAT"):
            connection = CaptureSocket(b"")
            connection.output = bytearray(response)
            with (
                self.subTest(response=response),
                patch(
                    "arknights_mower.utils.device.screenshot.socket.create_connection",
                    return_value=connection,
                ),
                self.assertRaises(ConnectionError),
            ):
                capture_adb_frame("chosen-adb", "chosen-serial")
            self.assertTrue(connection.closed)

    def test_verified_sdk_does_not_allow_four_byte_truncated_modern_frame(self):
        connections = [
            CaptureSocket(b"27"),
            CaptureSocket(gzip_frame(rgba_frame(modern=True)[:-4])),
        ]
        with (
            patch(
                "arknights_mower.utils.device.screenshot.socket.create_connection",
                side_effect=connections,
            ),
            self.assertRaisesRegex(ValueError, "长度"),
        ):
            capture_adb_frame("chosen-adb", "chosen-serial")
        self.assertTrue(all(connection.closed for connection in connections))

    def test_capture_stops_reading_at_byte_limit_and_closes_socket(self):
        connections = [
            CaptureSocket(b"27"),
            CaptureSocket(b"x" * (MAX_COMPRESSED_BYTES + 2)),
        ]
        with (
            patch(
                "arknights_mower.utils.device.screenshot.socket.create_connection",
                side_effect=connections,
            ),
            self.assertRaisesRegex(ValueError, "字节上限"),
        ):
            capture_adb_frame("chosen-adb", "chosen-serial")
        self.assertTrue(all(connection.closed for connection in connections))
        self.assertEqual(bytes(connections[1].output), b"x")

    def test_slow_trickle_cannot_reset_the_shared_execution_read_deadline(self):
        now = [0]

        class SlowSocket(CaptureSocket):
            def recv(self, size):
                now[0] += 2.5
                return super().recv(size)

        connection = SlowSocket(b"27")
        with (
            patch(
                "arknights_mower.utils.device.screenshot.time.monotonic",
                side_effect=lambda: now[0],
            ),
            patch(
                "arknights_mower.utils.device.screenshot.socket.create_connection",
                side_effect=[connection],
            ),
            self.assertRaisesRegex(TimeoutError, "超时"),
        ):
            capture_adb_frame("chosen-adb", "chosen-serial")
        self.assertTrue(connection.closed)
        self.assertEqual(now[0], 10)

    def test_context_deadline_is_used_for_every_socket_operation(self):
        connections = [
            CaptureSocket(b"27"),
            CaptureSocket(gzip_frame(rgba_frame(modern=True))),
        ]
        with (
            device_io_budget(lambda: 0.5),
            patch(
                "arknights_mower.utils.device.screenshot.socket.create_connection",
                side_effect=connections,
            ) as connect,
        ):
            capture_adb_frame("chosen-adb", "chosen-serial")
        self.assertTrue(
            all(call.kwargs["timeout"] <= 0.5 for call in connect.call_args_list)
        )
        self.assertTrue(
            all(timeout <= 0.5 for c in connections for timeout in c.timeouts)
        )

    def test_missing_serial_never_opens_a_transport(self):
        with patch(
            "arknights_mower.utils.device.screenshot.socket.create_connection"
        ) as connect:
            with self.assertRaisesRegex(ValueError, "serial"):
                capture_adb_frame("chosen-adb", "")
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
