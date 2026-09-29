"""Decode raw ADB frames and capture them within one bounded socket session."""

import re
import socket
import struct
import time
import zlib

import numpy as np

from arknights_mower.utils.device.adb_client.server import guard_adb
from arknights_mower.utils.device.io_budget import io_timeout

WIDTH, HEIGHT = 1920, 1080
MAX_RAW_BYTES = 16 + WIDTH * HEIGHT * 4
MAX_COMPRESSED_BYTES = MAX_RAW_BYTES + 64 * 1024
CAPTURE_TIMEOUT = 10


def decode_adb_frame(compressed: bytes, *, header_size: int) -> np.ndarray:
    """Return RGB from an Android raw screencap gzip member, never crop it.

    AOSP screencap writes three uint32 words before Android 8.1 and adds a
    color-space uint32 in Android 8.1+. Rows contain width * bytesPerPixel;
    the GraphicBuffer stride padding is not written into the stream.
    The caller must supply the verified layout: inferring it from length
    would confuse a truncated modern frame with a complete legacy frame.
    """
    if header_size not in (12, 16):
        raise ValueError("ADB 截图帧头版本未知")
    if not compressed or len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError("ADB gzip 压缩帧数据长度无效")
    try:
        decoder = zlib.decompressobj(wbits=31)
        raw = decoder.decompress(compressed, MAX_RAW_BYTES + 1)
    except zlib.error as exc:
        raise ValueError("ADB gzip 帧无法解压") from exc
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("ADB gzip 解压帧超过字节上限")
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("ADB gzip 帧被截断或包含多余数据")
    if len(raw) < 12:
        raise ValueError("ADB 截图帧头被截断")
    width, height, pixel_format = struct.unpack_from("<III", raw)
    if (width, height) != (WIDTH, HEIGHT):
        raise ValueError(f"ADB 实际帧尺寸错误：{width}×{height}，需要 1920×1080")
    channels = {1: 4, 2: 4, 3: 3, 4: 2, 5: 4}.get(pixel_format)
    if channels is None:
        raise ValueError(f"ADB 截图像素格式不支持：{pixel_format}")
    if len(raw) != header_size + width * height * channels:
        raise ValueError("ADB 截图像素长度与帧头不一致")
    if header_size == 16 and struct.unpack_from("<I", raw, 12)[0] not in (0, 1, 2):
        raise ValueError("ADB 截图颜色空间无效")
    if pixel_format == 4:
        words = np.frombuffer(raw, "<u2", offset=header_size).reshape(height, width)
        # Expand RGB565 with bit replication, including full white at 0xffff.
        red, green, blue = (words >> 11) & 31, (words >> 5) & 63, words & 31
        return np.stack(
            (
                (red << 3) | (red >> 2),
                (green << 2) | (green >> 4),
                (blue << 3) | (blue >> 2),
            ),
            axis=-1,
        ).astype(np.uint8)
    rgb = np.frombuffer(raw, np.uint8, offset=header_size).reshape(
        height, width, channels
    )[:, :, :3]
    return (rgb[:, :, ::-1] if pixel_format == 5 else rgb).copy()


def _adb_output(serial, command, limit, remaining):
    """One selected transport, one command, capped reads and no socket retries."""
    with socket.create_connection(
        ("127.0.0.1", 5037), timeout=remaining()
    ) as connection:

        def receive(length):
            output = bytearray()
            while len(output) < length:
                connection.settimeout(remaining())
                data = connection.recv(length - len(output))
                remaining()
                if not data:
                    raise ConnectionError("ADB 截图协议响应被截断")
                output.extend(data)
            return bytes(output)

        def request(service):
            payload = service.encode("utf-8")
            if len(payload) > 65535:
                raise ValueError("ADB 截图请求长度超过协议上限")
            connection.settimeout(remaining())
            connection.sendall(f"{len(payload):04x}".encode() + payload)
            status = receive(4)
            if status == b"FAIL":
                length = receive(4)
                if re.fullmatch(rb"[0-9a-fA-F]{4}", length) is None:
                    raise ConnectionError("ADB 截图错误响应长度无效")
                size = int(length, 16)
                if size > 4096:
                    raise ConnectionError("ADB 截图错误响应超过字节上限")
                message = receive(size).decode("utf-8", "replace")
                raise ConnectionError(f"ADB 截图请求失败：{message}")
            if status != b"OKAY":
                raise ConnectionError("ADB 截图协议响应状态无效")

        request(f"host:transport:{serial}")
        request(f"exec:{command}")
        output = bytearray()
        while True:
            connection.settimeout(remaining())
            data = connection.recv(min(65536, limit + 1 - len(output)))
            remaining()
            if not data:
                return bytes(output)
            output.extend(data)
            if len(output) > limit:
                raise ValueError("ADB 截图响应超过字节上限")


def capture_adb_frame(adb_path: str, serial: str) -> np.ndarray:
    """Capture the pinned target within one deadline and fixed memory bounds.

    The SDK selects the raw header layout, avoiding the ambiguous four-byte
    truncation of a modern header. AOSP first added the color-space word in
    Android 8.1 (SDK 27); Android 8.0 still writes the legacy three words.
    The existing shared server is only observed, never started or restarted.
    """
    if not serial.strip():
        raise ValueError("ADB 截图必须明确指定设备 serial")
    deadline = time.monotonic() + io_timeout(CAPTURE_TIMEOUT)

    def remaining():
        timeout = io_timeout(deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("ADB gzip 截图执行或读取超时")
        return timeout

    guard_adb(adb_path, timeout=remaining())
    sdk_output = _adb_output(serial, "getprop ro.build.version.sdk", 64, remaining)
    if re.fullmatch(rb"[1-9][0-9]{0,3}\s*", sdk_output) is None:
        raise ValueError("ADB 无法确认 Android SDK 版本，不能验证截图帧头")
    header_size = 16 if int(sdk_output) >= 27 else 12
    compressed = _adb_output(
        serial, "screencap 2>/dev/null | gzip -1", MAX_COMPRESSED_BYTES, remaining
    )
    remaining()
    frame = decode_adb_frame(compressed, header_size=header_size)
    remaining()
    return frame
