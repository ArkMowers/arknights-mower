import json
from typing import Dict, List, Optional
from zlib import compress, decompress

from base45 import b45decode, b45encode
from PIL import Image, ImageChops, ImageDraw
from pyzbar import pyzbar
from qrcode.main import QRCode

QRCODE_SIZE = 215
GAP_SIZE = 16
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
TOP = 40
BOTTOM = 995
LEFT = 40


def encode(data: str, n: int = 16, theme: str = "light") -> List[Image.Image]:
    data = b45encode(compress(data.encode("utf-8"), level=9))
    length = len(data)
    split: List[bytes] = []
    for i in range(n):
        start = length // n * i
        end = length if i == n - 1 else length // n * (i + 1)
        split.append(data[start:end])
    result: List[Image.Image] = []
    qr = QRCode()
    fg, bg = (BLACK, WHITE) if theme == "light" else (WHITE, BLACK)
    for i in split:
        qr.add_data(i)
        img: Image.Image = qr.make_image(fill_color=fg, back_color=bg)
        result.append(trim(img.get_image()))
        qr.clear()
    return result


def trim(img: Image.Image) -> Image.Image:
    bg = Image.new(img.mode, img.size, img.getpixel((0, 0)))
    diff = ImageChops.difference(img, bg)
    img = img.crop(diff.getbbox())
    img = img.resize((QRCODE_SIZE, QRCODE_SIZE))
    return img


def export(plan: Dict, img: Image.Image, theme: str = "light") -> Image.Image:
    qrcode_list = encode(json.dumps(plan), theme=theme)
    for idx, i in enumerate(qrcode_list[:7]):
        img.paste(i, (LEFT + idx * (GAP_SIZE + QRCODE_SIZE), TOP))
    for idx, i in enumerate(qrcode_list[7:14]):
        img.paste(i, (LEFT + idx * (GAP_SIZE + QRCODE_SIZE), BOTTOM))
    for idx, i in enumerate(qrcode_list[14:]):
        img.paste(i, (2520 + idx * (GAP_SIZE + QRCODE_SIZE), BOTTOM))
    img = img.convert("RGB")
    return img


def decode(img: Image.Image) -> Optional[Dict]:
    img = img.convert("RGB")
    if img.getpixel((0, 0)) == BLACK:
        img = ImageChops.invert(img)
    result = []
    while len(data := pyzbar.decode(img)):
        img1 = ImageDraw.Draw(img)
        for d in data:
            left = d.rect.left - 2
            top = d.rect.top - 2
            right = left + d.rect.width + 5
            bottom = top + d.rect.height + 5
            scope = ((left, top), (right, bottom))
            img1.rectangle(scope, fill=WHITE)
        result += data
    try:
        result.sort(key=lambda i: (i.rect.top * 2 > img.size[1], i.rect.left))
        result = b45decode(b"".join([i.data for i in result]))
        return json.loads(decompress(result).decode("utf-8"))
    except Exception:
        return None
