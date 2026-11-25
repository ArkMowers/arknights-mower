"""Build the glyph bank for the stage preview's AEwide text component."""

import argparse
from pathlib import Path
from string import ascii_uppercase, digits

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def build(font_path, output):
    alphabet = ascii_uppercase + digits + "-"
    glyphs, ratios = [], []
    for size in (26, 46, 64):
        font = ImageFont.truetype(str(font_path), size)
        masks, aspects = [], []
        for char in alphabet:
            image = Image.new("L", (120, 120))
            ImageDraw.Draw(image).text((4, 0), char, font=font, fill=255)
            bitmap = np.asarray(image)
            x, y, w, h = cv2.boundingRect((bitmap > 100).astype(np.uint8))
            mask = (bitmap[y : y + h, x : x + w] > 110).astype(np.uint8) * 255
            masks.append(cv2.resize(mask, (24, 32), interpolation=cv2.INTER_AREA))
            aspects.append(w / h)
        glyphs.append(masks)
        ratios.append(aspects)
    np.savez_compressed(output, alphabet=alphabet, glyphs=glyphs, ratios=ratios)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path, help="MowerFonts/fonts/AEwide.otf")
    parser.add_argument(
        "--output", type=Path, default="arknights_mower/models/stage_code.npz"
    )
    args = parser.parse_args()
    build(args.font, args.output)
