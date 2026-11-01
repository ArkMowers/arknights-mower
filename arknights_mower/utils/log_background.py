"""当前实例的运行日志背景图。"""

import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from arknights_mower.utils.config import gui
from arknights_mower.utils.config_backup import backup_lock

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_WEBP_DIMENSION = 16_383
FILENAME = "log-background.webp"


def _path():
    return gui.gui_path.parent / FILENAME


def _encode(content):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("请选择 PNG、JPEG 或 WebP 图片")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError("图片像素不能超过 2400 万")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("请选择静态图片")
                source.load()
                image = ImageOps.exif_transpose(source).convert(
                    "RGBA"
                    if "A" in source.getbands() or "transparency" in source.info
                    else "RGB"
                )
                image.thumbnail(
                    (MAX_WEBP_DIMENSION, MAX_WEBP_DIMENSION), Image.Resampling.LANCZOS
                )
                output = BytesIO()
                try:
                    image.save(output, format="WEBP", quality=90)
                except ValueError as exc:
                    raise ValueError("图片无法转换为背景图，请选择其他图片") from exc
        encoded = output.getvalue()
        if len(encoded) > MAX_IMAGE_BYTES:
            raise ValueError("处理后的图片超过 8 MiB，请选择较小的图片")
        return encoded
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("图片无法读取或尺寸过大，请选择有效的静态图片") from exc


def load():
    with backup_lock, gui._gui_lock, gui._gui_file_lock():
        try:
            with _path().open("rb") as stream:
                content = stream.read(MAX_IMAGE_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError("已保存的背景图超过 8 MiB，请重新选择图片")
        return content


def save(content):
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("图片不能超过 8 MiB")
    encoded = _encode(content)
    with backup_lock, gui._gui_lock, gui._gui_file_lock():
        gui.atomic_write(_path(), lambda stream: stream.buffer.write(encoded))
    return encoded


def reset():
    with backup_lock, gui._gui_lock, gui._gui_file_lock():
        _path().unlink(missing_ok=True)
