"""Offline AOSP raw screencap samples; no emulator or image encoder required.

The 12-byte Android 7/8.0 header is width, height, HAL pixel format. Android 8.1+
adds a color-space word (0 unknown, 1 sRGB, 2 Display P3). Each fixture has
the same first RGB pixel (255, 128, 0), followed by black pixels.

Protocol references, checked 2026-09-27:
https://github.com/aosp-mirror/platform_frameworks_base/blob/android-7.1.2_r1/cmds/screencap/screencap.cpp
https://github.com/aosp-mirror/platform_frameworks_base/blob/android-8.0.0_r1/cmds/screencap/screencap.cpp
https://github.com/aosp-mirror/platform_frameworks_base/blob/android-8.1.0_r1/cmds/screencap/screencap.cpp
https://github.com/aosp-mirror/platform_system_core/blob/android-7.1.2_r1/include/system/graphics.h
"""

import gzip

PIXELS = 1920 * 1080


def rgba_frame(*, modern=False, black=False):
    header = bytes.fromhex("80070000 38040000 01000000")
    if modern:
        header += bytes.fromhex("01000000")
    first = b"\0\0\0\xff" if black else b"\xff\x80\0\xff"
    return header + first + b"\0\0\0\xff" * (PIXELS - 1)


def gzip_frame(raw):
    return gzip.compress(raw, compresslevel=1, mtime=0)


def alternate_formats():
    dimensions = bytes.fromhex("80070000 38040000")
    return {
        "rgbx8888": dimensions
        + bytes.fromhex("02000000")
        + b"\xff\x80\0\xaa"
        + b"\0\0\0\xaa" * (PIXELS - 1),
        "rgb888": dimensions
        + bytes.fromhex("03000000")
        + b"\xff\x80\0"
        + b"\0\0\0" * (PIXELS - 1),
        "rgb565": dimensions
        + bytes.fromhex("04000000")
        + bytes.fromhex("00fc")
        + b"\0\0" * (PIXELS - 1),
        "bgra8888": dimensions
        + bytes.fromhex("05000000")
        + b"\0\x80\xff\xff"
        + b"\0\0\0\xff" * (PIXELS - 1),
    }
