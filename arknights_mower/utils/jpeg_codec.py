"""RGB and grayscale PNG/JPEG encoding without OpenCV color conversion."""

from io import BytesIO
from struct import pack

from PIL import Image

from arknights_mower.utils.jpeg_protocol import MAX_JPEG_BYTES, MAX_RAW_BYTES

JPEG_QUALITY = 75


def frame_shape(rgb, *, bounded=True):
    import numpy as np

    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim not in (2, 3)
        or (rgb.ndim == 3 and rgb.shape[2] != 3)
        or rgb.nbytes <= 0
    ):
        raise ValueError("JPEG 输入必须是非空 uint8 RGB 或灰度数组")
    if bounded and rgb.nbytes > MAX_RAW_BYTES:
        raise ValueError("原始截图超过单帧容量")
    height, width = rgb.shape[:2]
    return width, height, 1 if rgb.ndim == 2 else 3


def _save(image, *, bounded=True, lossless=False):
    with BytesIO() as output:
        if lossless:
            image.save(output, format="PNG", compress_level=1)
        else:
            image.save(output, format="JPEG", quality=JPEG_QUALITY, subsampling=2)
        data = output.getvalue()
    if not data or (bounded and len(data) > MAX_JPEG_BYTES):
        raise ValueError("JPEG 编码结果为空或超过单帧上限")
    return data


def encode_jpeg(rgb):
    frame_shape(rgb, bounded=False)
    with Image.fromarray(rgb) as image:
        return _save(image, bounded=False)


def encode_packed(width, height, channels, data, *, lossless=False, with_preview=False):
    if (
        channels not in (1, 3)
        or width <= 0
        or height <= 0
        or not 0 < width * height * channels <= MAX_RAW_BYTES
        or len(data) != width * height * channels
    ):
        raise ValueError("截图共享输入尺寸无效")
    with Image.frombytes(
        "L" if channels == 1 else "RGB", (width, height), data
    ) as image:
        if with_preview:
            original = _save(image, lossless=True)
            preview = _save(image)
            return pack("!I", len(original)) + original + preview
        return _save(image, lossless=True) if lossless else _save(image)
