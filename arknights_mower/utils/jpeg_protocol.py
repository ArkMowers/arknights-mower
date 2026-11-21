"""Fixed-size screenshot input, output and control message limits."""

import struct

MAX_RAW_BYTES = 1920 * 1080 * 3
MAX_JPEG_BYTES = 1920 * 1080 * 4
MAPPING_BYTES = MAX_RAW_BYTES + MAX_JPEG_BYTES
TOKEN_BYTES = 64
MAX_ERROR_BYTES = 512
REQUEST = struct.Struct("!IIII")
RESPONSE = struct.Struct("!BI")
