import json
from typing import Dict, List
from zlib import compress, decompress

from base45 import b45decode, b45encode
from PIL import Image, ImageChops
from pyzbar import pyzbar
from qrcode.main import QRCode

QRCODE_SIZE = 680
GAP_SIZE = 44
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def encode(data: str, n: int = 4, theme: str = "light") -> List[Image.Image]:
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


def export(plan: Dict, upper: Image.Image) -> Image.Image:
    img = Image.new(
        upper.mode,
        (upper.width, upper.height + GAP_SIZE + QRCODE_SIZE),
        (255, 255, 255),
    )
    img.paste(upper)
    qrcode_list = encode(json.dumps(plan))
    for idx, i in enumerate(qrcode_list):
        img.paste(i, (GAP_SIZE + idx * (GAP_SIZE + QRCODE_SIZE), upper.height))
    return img


def decode(img: Image.Image) -> Dict:
    data = pyzbar.decode(img)
    data.sort(key=lambda i: i.rect.left)
    data = b45decode(b"".join([i.data for i in data]))
    return json.loads(decompress(data).decode("utf-8"))
