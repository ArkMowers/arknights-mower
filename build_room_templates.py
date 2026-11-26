"""从 MowerFonts 原字体和进驻筛选实机截图生成随软件分发的房间识别模板。

MOWERFONTS_DIR 指向 MowerFonts/fonts。用 --check 校验内置 PNG 的像素，
用 --output-dir DIR 在指定目录生成六张 PNG。Windows 的 Pillow 10.3.0、
NumPy 1.26.4 和 OpenCV 4.9.0 可复现原 PNG 字节。
"""

import argparse
import hashlib
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from build_font_subsets import MASTERY_SOURCE_SHA256, ROOM_SOURCE_SHA256, source_font

PACKAGE = Path(__file__).resolve().parent / "arknights_mower"
ROOM = PACKAGE / "resources/room"
FILTER_CAPTURE = PACKAGE / "tests/fixtures/selection/station_filter_b102_20261125.png"


def _load_font(filename, digest, size):
    path = source_font(filename)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"原字体 SHA-256 不匹配：{path}")
    return ImageFont.truetype(BytesIO(data), size, layout_engine=ImageFont.Layout.BASIC)


def _product_templates(font):
    templates = {}
    for name, text, size in (
        ("product_gold", "赤金", (71, 34)),
        ("product_detail_gold", "赤金", (76, 37)),
        ("product_exp3", "中级作战记录", (216, 34)),
        ("product_detail_exp3", "中级作战记录", (228, 37)),
        ("strategy_locked", "贸易站3级后可切换", (237, 27)),
    ):
        canvas = Image.new("L", (len(text) * 200, 230))
        ImageDraw.Draw(canvas).text((0, 0), text, fill=255, font=font)
        ink = np.asarray(canvas.crop(canvas.getbbox()))
        pixels = cv2.resize(ink, size, interpolation=cv2.INTER_AREA)
        templates[name] = Image.fromarray(pixels)
    return templates


def _station_filter_atlas(font):
    bands = []
    for title in ("进驻状态", "宿舍锁定", "未进驻", "全部"):
        mask = font.getmask(title, mode="L")
        gray = Image.frombytes("L", mask.size, bytes(mask))
        bands.append(gray.point(lambda value: 255 if value >= 112 else 0))

    # B102 裁片每帧高 128 px。第一帧菜单收起，第四帧菜单展开。
    with Image.open(FILTER_CAPTURE) as capture:
        if capture.mode != "RGB" or capture.size != (145, 768):
            raise ValueError(f"进驻筛选截图应为 145×768 RGB：{FILTER_CAPTURE}")
        blue = capture.getchannel("B")
        for top in (0, 3 * 128):
            arrow = blue.crop((111, top, 145, top + 47))
            bands.append(arrow.point(lambda value: 255 if value > 145 else 0))

    atlas = Image.new("L", (104, 156))
    for row, band in enumerate(bands):
        box = band.getbbox()
        if box is None or box[2] - box[0] > 104 or box[3] - box[1] > 26:
            raise ValueError(f"进驻筛选图集第 {row + 1} 行为空或超出 104×26")
        atlas.paste(band.crop(box), (0, row * 26))
    return atlas


def build_room_templates(directory: Path, *, check: bool):
    product_font = _load_font("NotoSansHans-Medium.otf", ROOM_SOURCE_SHA256, 180)
    filter_font = _load_font("SourceHanSansCN-Medium.ttf", MASTERY_SOURCE_SHA256, 22)
    templates = _product_templates(product_font)
    templates["station_filter_glyphs"] = _station_filter_atlas(filter_font)

    if not check:
        directory.mkdir(parents=True, exist_ok=True)
    for name, image in templates.items():
        path = directory / f"{name}.png"
        if check:
            with Image.open(path) as stored:
                if (
                    stored.format != "PNG"
                    or stored.mode != image.mode
                    or stored.size != image.size
                    or stored.tobytes() != image.tobytes()
                ):
                    raise ValueError(f"模板与生成结果不符：{path}")
        else:
            image.save(path, optimize=name == "station_filter_glyphs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        nargs="?",
        const=ROOM,
        type=Path,
        metavar="DIR",
        help="校验指定目录的六张 PNG，默认为仓内的 resources/room",
    )
    mode.add_argument(
        "--output-dir",
        type=Path,
        metavar="DIR",
        help="在指定目录生成六张 PNG",
    )
    args = parser.parse_args()
    try:
        build_room_templates(
            args.check or args.output_dir, check=args.check is not None
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
