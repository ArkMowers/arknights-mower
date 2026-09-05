import json
from typing import Dict, List, Optional
from zlib import compress, decompress

from base45 import b45decode, b45encode
from PIL import Image, ImageChops, ImageDraw
from pyzbar import pyzbar
from qrcode.constants import ERROR_CORRECT_L
from qrcode.main import QRCode

QRCODE_SIZE = 215
QRCODE_COUNT = 16
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
    qr = QRCode(error_correction=ERROR_CORRECT_L)
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


def _scan_and_cover(img: Image.Image) -> List:
    """扫出图中所有二维码，扫到的用白块盖住防止重复计数。

    原实现在「只剩 quality>1 的低置信二维码」时会无限循环（continue 跳过了盖白块，
    却不中断 while）——这里加 found 守卫：一轮扫不到任何可用二维码就结束。
    """
    result = []
    while True:
        data = pyzbar.decode(img)
        if not data:
            break
        draw = ImageDraw.Draw(img)
        found = False
        for d in data:
            if d.quality > 1:
                continue
            found = True
            left = d.rect.left - 2
            top = d.rect.top - 2
            right = left + d.rect.width + 5
            bottom = top + d.rect.height + 5
            draw.rectangle((left, top, right, bottom), fill=WHITE)
            result.append(d)
        if not found:
            break
    return result


def _center_x(decoded) -> float:
    return decoded.rect.left + decoded.rect.width / 2.0


def _center_y(decoded) -> float:
    return decoded.rect.top + decoded.rect.height / 2.0


def _order_qrcodes(result: List) -> List:
    """按几何位置排二维码顺序，不依赖图片总尺寸/偏移。

    原实现用 `i.rect.top * 2 > img.size[1]` 区分顶排/底排，图一旦被加高或整体平移，
    底排会被误判成顶排导致顺序错乱（`Error -3`）。这里改成：按中心 Y 聚成行（相邻
    中心 Y 差 < 中位块高的 0.5 视为同一行），行内再按中心 X 排序。对任意画布尺寸/偏移
    都稳定；右下角那排因与底排同 Y、X 更大，排序后自然落在底排之后。
    """
    if not result:
        return []
    heights = sorted(d.rect.height for d in result)
    median_height = heights[len(heights) // 2]
    gap = max(1.0, median_height * 0.5)
    items = sorted(result, key=_center_y)
    rows = []
    cur = [items[0]]
    for d in items[1:]:
        if _center_y(d) - _center_y(cur[-1]) > gap:
            rows.append(cur)
            cur = [d]
        else:
            cur.append(d)
    rows.append(cur)
    ordered = []
    for row in rows:
        row.sort(key=_center_x)
        ordered.extend(row)
    return ordered


def decode(img: Image.Image) -> Optional[Dict]:
    img = img.convert("RGB")
    if img.getpixel((0, 0)) == BLACK:
        img = ImageChops.invert(img)
    # 多档放大重扫：pyzbar 对太小的二维码扫不出（导出图被缩小/压缩到 ~90px 以下一张
    # 都扫不出），放大到可识别尺寸再扫。取「扫出最多」的那一档，避免某一档漏扫；
    # 放大后的最大边长限在 8000，防止大图被无谓放大导致内存膨胀。
    max_side = max(img.width, img.height)
    scales = [1]
    for s in (2, 3, 4, 6, 8):
        if max_side * s <= 8000:
            scales.append(s)
    best = []
    for s in scales:
        work = (
            img
            if s == 1
            else img.resize((img.width * s, img.height * s), Image.LANCZOS)
        )
        got = _scan_and_cover(work)
        if len(got) > len(best):
            best = got
        if len(best) >= QRCODE_COUNT:  # 已集齐全套 16 个，无需再放大
            break
    if not best:
        return None
    ordered = _order_qrcodes(best)
    result = b45decode(b"".join([d.data for d in ordered]))
    return json.loads(decompress(result).decode("utf-8"))
